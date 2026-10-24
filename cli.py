"""Build/flash/compare and per-machine setup without a GUI dependency."""
import argparse
import json
from pathlib import Path
import queue
import sys
from core.builder import FirmwareBuilder
from core.config import AppConfig, PROFILES, settings_path
from core.comparison import report, compare_generated
from core.device_service import DeviceService
from core.diagnostics import diagnose


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='SaolaLink firmware tools')
    parser.add_argument('action', choices=['setup', 'configure', 'build', 'clean', 'devices', 'flash', 'compare', 'doctor'])
    parser.add_argument('--profile', choices=PROFILES, default='saolalink-v1')
    parser.add_argument('--mode', choices=['Debug', 'Release'], default='Debug')
    parser.add_argument('--kind', choices=['firmware', 'bootloader', 'application'], default='firmware')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--usb-path', help='Exact DFU USB path from the devices command')
    parser.add_argument('--config', type=Path, help='Use a different settings JSON file')
    parser.add_argument('--save', action='store_true', help='Save setup values to this user\'s settings file')
    parser.add_argument('--scope', choices=['all', 'build', 'flash', 'serial'], default='all', help='doctor capability to check')
    parser.add_argument('--scan', action='store_true', help='doctor: enumerate DFU and serial devices without opening serial ports')
    for flag, dest in [('source', 'source'), ('build-dir', 'builds'), ('toolchain', 'toolchain'),
                       ('cmake', 'cmake'), ('git', 'git'), ('dfu-util', 'dfu_util'),
                       ('build-tool', 'build_tool'), ('generator', 'generator'), ('python', 'build_python'),
                       ('native-cc', 'native_cc'), ('native-cxx', 'native_cxx'), ('llvm', 'llvm'),
                       ('library-prefix', 'library_prefix'), ('dependency-cache', 'dependency_cache'),
                       ('vsdevcmd', 'vsdevcmd'), ('serial-port', 'serial_port'), ('serial-baud', 'serial_baud')]:
        parser.add_argument('--' + flag, dest=dest, help='Override Setup: ' + dest)
    args = parser.parse_args()
    if args.save and args.action != 'setup':
        parser.error('--save is only available with setup')
    builder = None
    try:
        try:
            config = AppConfig.load(args.config)
        except ValueError as error:
            if args.action != 'setup':
                raise
            print(f'WARNING: {error}', file=sys.stderr)
            config = AppConfig.detected()
        values = {name: getattr(args, name) for name in config.to_dict() if getattr(args, name, None) is not None}
        config = config.updated(values)
        if args.action == 'setup':
            if args.save:
                config.save(args.config)
                print('Saved: ' + str(args.config or settings_path()))
            print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
            return 0
        builder = FirmwareBuilder(config)
        profile = PROFILES[args.profile]
        if args.action == 'compare':
            print(report(config.source, config.tool('git'), config.environment(build=False)) + compare_generated(config.builds, args.mode))
            return 0
        if args.action == 'doctor':
            checks = diagnose(config, groups=('build', 'flash', 'serial') if args.scope == 'all' else (args.scope,), scan=args.scan)
            print('\n\n'.join(map(str, checks)))
            return 1 if any(check.status == 'error' for check in checks) else 0
        if args.action == 'devices':
            devices = DeviceService(config).discover()
            print('\n'.join(d.label for d in devices) or 'No STM32 DFU device found')
            return 0
        if args.action == 'flash':
            if not args.usb_path:
                parser.error('flash requires --usb-path from the devices command')
            devices = [d for d in DeviceService(config).discover() if d.path == args.usb_path and d.vid_pid == profile.dfu_id]
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
        if builder:
            builder.runner.stop()
        return 130
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
