"""DFU discovery distinguishes devices by USB path, not only VID:PID."""
from dataclasses import dataclass
import re
import subprocess

@dataclass(frozen=True)
class DfuDevice:
    vid_pid: str
    path: str
    serial: str
    name: str

    @property
    def label(self):
        return f'{self.vid_pid} | {self.serial or "no serial"} | USB {self.path} | {self.name}'

    def selector_args(self):
        args = ['-d', self.vid_pid, '-p', self.path]
        if self.serial:
            args.extend(['-S', self.serial])
        return args

    @property
    def edgetx_bootloader(self):
        return self.name.startswith('@SaolaLink App /0x08008000/')

def parse_devices(output):
    devices = {}
    for line in output.splitlines():
        match = re.search(r'Found DFU:\s*\[([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\]', line)
        path = re.search(r'path="([^"]+)"', line)
        alt = re.search(r'alt=(\d+)', line)
        name = re.search(r'name="([^"]+)"', line)
        if not (match and path and alt and alt.group(1) == '0' and name and
                ('Internal Flash' in name.group(1) or name.group(1).startswith('@SaolaLink App /0x08008000/'))):
            continue
        serial = re.search(r'serial="([^"]*)"', line)
        key = (match.group(1).lower(), path.group(1))
        devices[key] = DfuDevice(*key, serial.group(1) if serial else '', name.group(1))
    return list(devices.values())

class DeviceService:
    def __init__(self, config=None):
        self.config = config

    def discover(self):
        tool = self.config.tool('dfu-util') if self.config else 'dfu-util'
        env = self.config.environment(build=False) if self.config else None
        try:
            result = subprocess.run([tool, '-l'], env=env, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=10)
        except FileNotFoundError:
            raise RuntimeError('dfu-util was not found. Select dfu-util/dfu-util.exe in Setup.') from None
        if result.returncode:
            raise RuntimeError((result.stderr.strip() or result.stdout.strip() or 'DFU discovery failed') +
                               '\nCheck Setup, USB driver/access and whether another application owns the device.')
        return parse_devices(result.stdout)
