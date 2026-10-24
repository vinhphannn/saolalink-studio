"""The same build/flash/compare services without a GUI dependency."""
import argparse
import queue
import sys
from core.builder import FirmwareBuilder
from core.config import AppConfig, PROFILES
from core.comparison import report, compare_generated
from core.device_service import DeviceService

def main():
    parser = argparse.ArgumentParser(description='SaolaLink firmware tools')
    parser.add_argument('action', choices=['configure', 'build', 'clean', 'devices', 'flash', 'compare', 'doctor'])
    parser.add_argument('--profile', choices=PROFILES, default='saolalink-v1')
    parser.add_argument('--mode', choices=['Debug', 'Release'], default='Debug')
    parser.add_argument('--kind', choices=['firmware', 'bootloader', 'application'], default='firmware')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--usb-path', help='Exact DFU USB path from the devices command')
    args = parser.parse_args()
    config = AppConfig.default()
    builder = FirmwareBuilder(config)
    profile = PROFILES[args.profile]
    try:
        if args.action == 'compare':
            print(report(config.source) + compare_generated(config.builds, args.mode)); return 0
        if args.action == 'doctor':
            builder.preflight(); print(f'OK | {config.source} | ARM GNU 14.2.1'); return 0
        if args.action == 'devices':
            devices = DeviceService().discover()
            print('\n'.join(d.label for d in devices) or 'No STM32 DFU device found'); return 0
        if args.action == 'flash':
            if not args.usb_path:
                parser.error('flash requires --usb-path from the devices command')
            devices = [d for d in DeviceService().discover() if d.path == args.usb_path and d.vid_pid == profile.dfu_id]
            if len(devices) != 1:
                raise ValueError('The selected DFU device is missing or ambiguous')
            builder.flash(profile, args.mode, args.kind, devices[0])
        elif args.action == 'build':
            builder.build(profile, args.mode, 'firmware' if args.kind == 'application' else args.kind, args.jobs)
        else:
            getattr(builder, args.action)(profile, args.mode)
        while True:
            try:
                event, value = builder.runner.events.get(timeout=1)
            except queue.Empty:
                continue
            if event == 'log':
                print(value, end='', flush=True)
            elif event == 'started':
                print('Log: ' + value)
            elif event == 'finished':
                return 0 if value else 1
    except KeyboardInterrupt:
        builder.runner.stop()
        return 130
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
