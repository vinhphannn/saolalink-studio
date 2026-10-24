"""EdgeTX commands and artifact provenance, independent of the desktop UI."""
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from core.runner import OperationRunner
from core.diagnostics import require_build
from core.config import executable_in

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class FirmwareBuilder:
    def __init__(self, config):
        self.config = config
        self.runner = OperationRunner(config.builds / 'logs')

    def preflight(self):
        self.runner.env = self.config.environment()
        require_build(self.config, self.runner.env)

    def configure_commands(self, profile, mode):
        issue = self.config.cache_issue(profile, mode)
        if issue:
            raise ValueError(issue)
        directory = self.config.build_dir(profile, mode)
        path = lambda value: str(value).replace('\\', '/')
        command = [self.config.tool('cmake'), '--fresh', '-G', self.config.generator,
                   '-S', path(self.config.source), '-B', path(directory),
                   f'-DPCB={profile.pcb}', f'-DPCBREV={profile.pcbrev}',
                   f'-DCMAKE_BUILD_TYPE={mode}', '-DDEFAULT_MODE=2', '-DTRANSLATIONS=EN',
                   '-DUSE_FW_LTO=ON', '-DBOOTLOADER=ON', '-DFIRMWARE_STRIP_BOOTLOADER=OFF', '-DFIRMWARE_FORMAT_UF2=OFF',
                   f'-DPython3_EXECUTABLE={path(self.config.tool("python"))}']
        env = self.runner.env or self.config.environment()
        for variable, name in [('CMAKE_MAKE_PROGRAM', 'build-tool'), ('GIT_EXECUTABLE', 'git')]:
            tool = self.config.tool(name)
            resolved = shutil.which(tool, path=env['PATH']) or tool
            command.append(f'-D{variable}={path(resolved)}')
        if self.config.toolchain:
            command.append(f'-DARM_TOOLCHAIN_DIR={path(executable_in(self.config.toolchain, "arm-none-eabi-g++").parent)}')
        for variable, value in [('FETCHCONTENT_BASE_DIR', self.config.dependency_cache),
                                ('CMAKE_PREFIX_PATH', self.config.library_prefix)]:
            if value:
                command.append(f'-D{variable}={path(value)}')
        if profile.hse_hz is not None:
            command.append(f'-DSAOLALINK_HSE_HZ={profile.hse_hz}')
            command.append(f'-DSAOLALINK_DEVEBOX={"ON" if profile.key == "saolalink-devebox" else "OFF"}')
        return [command, [self.config.tool('cmake'), '--build', str(directory), '--target', 'arm-none-eabi-configure']]

    def build(self, profile, mode='Debug', kind='firmware', jobs=4):
        if kind not in ('firmware', 'bootloader'):
            raise ValueError('Unknown artifact kind')
        self.preflight()
        if not (self.config.source / 'radio/src/boards/hw_defs' / f'{profile.flavour}.json').is_file():
            raise ValueError(f'Target {profile.name} is missing from this EdgeTX checkout')
        directory = self.config.build_dir(profile, mode)
        manifest = directory / 'arm-none-eabi' / f'{kind}.manifest.json'
        if self.runner.running:
            return False
        # A failed or cancelled build must never leave a flashable old manifest.
        manifest.unlink(missing_ok=True)
        if profile.key == 'saolalink-devebox':
            for related in ('firmware', 'application', 'bootloader'):
                (directory / 'arm-none-eabi' / f'{related}.manifest.json').unlink(missing_ok=True)
        (directory / 'arm-none-eabi/radio/src' / f'{profile.flavour}.json.h').unlink(missing_ok=True)
        commands = self.configure_commands(profile, mode)
        commands.append([self.config.tool('cmake'), '--build', str(directory / 'arm-none-eabi'), '--target', 'hardware_defs', '--parallel', str(max(1, int(jobs)))])
        commands.append([self.config.tool('cmake'), '--build', str(directory), '--target', kind, '--parallel', str(max(1, int(jobs)))])
        return self.runner.start('build-' + kind, commands, self.config.source,
                                 lambda: self.record_artifact(profile, mode, kind))

    def configure(self, profile, mode='Debug'):
        self.preflight()
        return self.runner.start('configure', self.configure_commands(profile, mode), self.config.source)

    def record_artifact(self, profile, mode, kind):
        directory = self.config.build_dir(profile, mode) / 'arm-none-eabi'
        cache = (directory / 'CMakeCache.txt').read_text(encoding='utf-8')
        for key, value in {'PCB': profile.pcb, 'PCBREV': profile.pcbrev, 'CMAKE_BUILD_TYPE': mode,
                           'BOOTLOADER': 'ON', 'FIRMWARE_STRIP_BOOTLOADER': 'OFF'}.items():
            if not re.search(rf'^{key}:[^=]+={re.escape(value)}$', cache, re.M):
                raise ValueError(f'Actual CMake config does not match {key}={value}')
        definitions = (directory / 'radio/src' / f'{profile.flavour}.json.h').read_text(encoding='utf-8')
        if profile.key == 'saolalink-devebox' and not re.search(r'^SAOLALINK_DEVEBOX:[^=]+=ON$', cache, re.M):
            raise ValueError('DevEBox USB adaptation is not enabled in this build')
        if not re.search(rf'^#define RADIO_{profile.flavour.upper()} 1$', definitions, re.M):
            raise ValueError('The generated HAL does not match the selected board')
        if profile.hse_hz is not None:
            if not re.search(rf'^SAOLALINK_HSE_HZ:[^=]+={profile.hse_hz}$', cache, re.M):
                raise ValueError('The actual crystal setting does not match the selected board')
        binary = directory / f'{kind}.bin'
        if not binary.is_file():
            raise ValueError(f'Build did not produce {binary}')
        limit = profile.flash_size if kind == 'firmware' else profile.bootloader_size
        if not 8 <= binary.stat().st_size <= limit:
            raise ValueError(f'{kind} binary exceeds flash region or is empty')
        env = self.runner.env or self.config.environment()
        git = subprocess.run([self.config.tool('git'), 'rev-parse', 'HEAD'], cwd=self.config.source, env=env, capture_output=True, text=True, encoding='utf-8', check=True)
        changes = subprocess.run([self.config.tool('git'), 'diff', '--binary', 'HEAD'], cwd=self.config.source, env=env, capture_output=True, check=True)
        # Includes untracked target files too, so the manifest identifies their exact content.
        untracked = subprocess.run([self.config.tool('git'), 'ls-files', '-z', '--others', '--exclude-standard'], cwd=self.config.source, env=env, capture_output=True, text=True, encoding='utf-8', check=True)
        state = hashlib.sha256(changes.stdout)
        for name in sorted(filter(None, untracked.stdout.split('\0'))):
            path = self.config.source / name
            if path.is_file():
                state.update(name.encode()); state.update(path.read_bytes())
        manifest = {'profile': profile.key, 'pcbrev': profile.pcbrev, 'mode': mode, 'kind': kind,
                    'sha256': digest(binary), 'size': binary.stat().st_size,
                    'address': profile.flash_address, 'lto': True, 'bootloader_included': kind == 'firmware',
                    'commit': git.stdout.strip(), 'working_changes_sha256': state.hexdigest(),
                    'built_at': datetime.now(timezone.utc).isoformat()}
        manifest['hse_hz'] = profile.hse_hz
        manifest['devebox_usb'] = profile.key == 'saolalink-devebox'
        binary.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        if kind == 'firmware' and profile.key == 'saolalink-devebox':
            self.record_artifact(profile, mode, 'bootloader')
            app = directory / 'application.bin'
            app.write_bytes(binary.read_bytes()[profile.bootloader_size:])
            app_info = dict(manifest, kind='application', address='0x08008000',
                            bootloader_included=False, size=app.stat().st_size, sha256=digest(app))
            app.with_suffix('.manifest.json').write_text(json.dumps(app_info, indent=2) + '\n', encoding='utf-8')
        return f'Artifact: {binary}\nSize: {manifest["size"]} bytes | SHA256: {manifest["sha256"]}'

    def artifact(self, profile, mode, kind):
        if kind not in ('firmware', 'bootloader', 'application'):
            raise ValueError('Unknown artifact kind')
        binary = self.config.build_dir(profile, mode) / 'arm-none-eabi' / f'{kind}.bin'
        manifest = binary.with_suffix('.manifest.json')
        if not binary.is_file() or not manifest.is_file():
            raise ValueError('Build this target successfully in Studio before flashing')
        info = json.loads(manifest.read_text(encoding='utf-8'))
        expected = {'profile': profile.key, 'pcbrev': profile.pcbrev, 'mode': mode, 'kind': kind, 'address': profile.flash_address}
        if profile.key == 'saolalink-devebox':
            expected['devebox_usb'] = True
        if kind == 'application':
            if profile.key != 'saolalink-devebox':
                raise ValueError('USB bootloader application upload is configured for DevEBox only')
            expected['address'] = '0x08008000'
        if profile.hse_hz is not None:
            expected['hse_hz'] = profile.hse_hz
            if info.get('hse_hz') != profile.hse_hz:
                raise ValueError(f'Old or wrong crystal manifest: select the correct profile and rebuild. Expected HSE {profile.hse_hz // 1000000} MHz. DevEBox requires the EdgeTX USB build.')
        if any(info.get(key) != value for key, value in expected.items()) or info.get('sha256') != digest(binary):
            raise ValueError('Artifact does not match the selected target or has changed; rebuild first')
        if kind == 'firmware' and info.get('bootloader_included') is not True:
            raise ValueError('DFU at flash base requires the complete bootloader-inclusive firmware')
        limit = (profile.flash_size - profile.bootloader_size if kind == 'application' else
                 profile.flash_size if kind == 'firmware' else profile.bootloader_size)
        if not 8 <= binary.stat().st_size <= limit:
            raise ValueError('Artifact size does not fit the target flash region')
        return binary, info

    def flash(self, profile, mode, kind, device):
        if device.vid_pid != profile.dfu_id or not device.path:
            raise ValueError('Select an STM32 ROM DFU device with a unique USB path')
        binary, _ = self.artifact(profile, mode, kind)
        if kind == 'application':
            if not device.edgetx_bootloader:
                raise ValueError('Hold RTN (PC5) at power-on or RESET with BOOT0=0; select the EdgeTX @SaolaLink App DFU device (requires updated bootloader)')
            address = '0x08008000'
        else:
            if device.edgetx_bootloader:
                raise ValueError('EdgeTX DFU protects the bootloader. Use Flash application, or ROM DFU for bootloader install.')
            address = profile.flash_address if profile.key == 'saolalink-devebox' else profile.flash_address + ':leave'
        self.runner.env = self.config.environment(build=False)
        command = [self.config.tool('dfu-util'), *device.selector_args(), '-a', '0', '-s', address, '-D', str(binary)]
        return self.runner.start('flash-' + kind, [command], binary.parent)

    def clean(self, profile, mode):
        self.config.updated({})
        directory = self.config.build_dir(profile, mode)
        self.runner.env = self.config.environment(build=False)
        return self.runner.start('clean', [[sys.executable, '-c',
            'import pathlib,shutil,sys; p=pathlib.Path(sys.argv[1]); shutil.rmtree(p) if p.exists() else None', str(directory)]], Path.home())
