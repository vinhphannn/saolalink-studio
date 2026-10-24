"""Read-only capability checks; never flash hardware or open a serial port."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from core.config import WINDOWS, PROFILES


@dataclass(frozen=True)
class Check:
    group: str
    name: str
    status: str
    message: str

    def __str__(self):
        return f'[{self.status.upper()}] {self.group} / {self.name}: {self.message}'


def run(command, env, cwd=None, timeout=15):
    return subprocess.run(command, env=env, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


def diagnose(config, groups=('build', 'flash', 'serial'), scan=False, env=None):
    checks = []
    def add(group, name, status, message):
        checks.append(Check(group, name, status, str(message)))
    try:
        config.updated({})
        env = config.environment(build='build' in groups) if env is None else env
    except Exception as error:
        return [Check('setup', 'Configuration', 'error', str(error))]

    def probe(group, name, command, validate=None):
        try:
            result = run(command, env)
            output = (result.stdout + '\n' + result.stderr).strip()
            if result.returncode:
                raise ValueError(output[-1200:] or f'exit status {result.returncode}')
            message = validate(output) if validate else (output.splitlines()[0] if output else 'Available')
            add(group, name, 'ok', message)
            return output
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            add(group, name, 'error', f'{error}. Review this tool in Setup.')
            return None

    def tool(name):
        try:
            return config.tool(name)
        except ValueError:
            return ''  # Let probe report each missing tool without aborting other checks.

    if 'build' in groups:
        required = ('CMakeLists.txt', 'cmake/toolchain/arm-none-eabi.cmake', 'radio/src/boards/hw_defs/saolalinkv1.json')
        missing = [name for name in required if not (config.source / name).is_file()]
        add('build', 'EdgeTX checkout', 'error' if missing else 'ok',
            f'Missing {", ".join(missing)} in {config.source}' if missing else config.source)
        def cmake_version(output):
            match = re.search(r'cmake version (\d+)\.(\d+)', output)
            if not match or tuple(map(int, match.groups())) < (3, 24):
                raise ValueError('CMake >= 3.24 is required')
            return output.splitlines()[0]
        probe('build', 'CMake', [tool('cmake'), '--version'], cmake_version)
        def arm_version(output):
            if output.strip() != '14.2.1':
                raise ValueError(f'Arm GNU 14.2.rel1 (14.2.1) is required; found {output.strip()}')
            return 'Arm GNU 14.2.rel1 (14.2.1)'
        probe('build', 'Arm compiler', [config.compiler(), '-dumpfullversion'], arm_version)
        arm_bin = Path(config.compiler()).parent if config.toolchain else None
        missing_arm = []
        for name in ('gcc', 'g++', 'ar', 'ld', 'objcopy', 'ranlib', 'size', 'strip'):
            executable = f'arm-none-eabi-{name}' + ('.exe' if WINDOWS else '')
            if not ((arm_bin / executable).is_file() if arm_bin else shutil.which(executable, path=env['PATH'])):
                missing_arm.append(executable)
        add('build', 'Arm tools', 'error' if missing_arm else 'ok',
            'Missing: ' + ', '.join(missing_arm) if missing_arm else 'Compiler and binary utilities found')
        args = ['/?'] if config.generator == 'NMake Makefiles' else ['--version']
        probe('build', f'Build tool ({config.generator})', [tool('build-tool'), *args])
        git_output = probe('build', 'Git', [tool('git'), '--version'])
        if git_output and not missing:
            probe('build', 'Git checkout', [config.tool('git'), '-C', str(config.source), 'rev-parse', '--show-toplevel'])
            status = probe('build', 'Submodules', [config.tool('git'), '-C', str(config.source), 'submodule', 'status', '--recursive'])
            if status and any(line.startswith(('-', '+', 'U')) for line in status.splitlines()):
                add('build', 'Submodule revisions', 'error', 'Initialize/restore the recorded submodules with git submodule update --init --recursive')
        python_probe = (
            'import importlib.util,json,sys; '
            'mods=["asciitree","clang","jinja2","lz4","PIL","pydantic","elftools","typing_extensions"]; '
            'missing=[m for m in mods if importlib.util.find_spec(m) is None]; '
            'print(json.dumps({"version":list(sys.version_info[:3]),"missing":missing})); '
            'sys.exit(0)'
        )
        def python_version(output):
            data = json.loads(output)
            if data['version'][:2] < [3, 10]:
                raise ValueError('Build Python must be >= 3.10')
            if data['missing']:
                raise ValueError('Build Python is missing: ' + ', '.join(data['missing']) +
                                 '. Install the selected EdgeTX checkout into this Python environment (see Setup guide).')
            return 'Python ' + '.'.join(map(str, data['version'])) + '; EdgeTX Python packages found'
        python_ok = probe('build', 'Build Python', [tool('python'), '-c', python_probe], python_version)
        clang_script = config.source / 'radio/util/find_clang.py'
        if python_ok and clang_script.is_file():
            probe('build', 'LLVM/libclang', [config.tool('python'), '-c',
                'import sys; sys.path.insert(0, sys.argv[1]); import find_clang; '
                'ok = find_clang.initLibClang(); '
                'headers = ["-I" + find_clang.builtin_hdr_path] if ok and find_clang.builtin_hdr_path else []; '
                'raise SystemExit(0 if ok and find_clang.canFindBuiltinHeaders(find_clang.index, headers) else 1)', str(clang_script.parent)])
        for label, selected, candidates in (
            ('Host C compiler', config.native_cc, ('cc', 'gcc', 'clang', 'cl')),
            ('Host C++ compiler', config.native_cxx, ('c++', 'g++', 'clang++', 'cl')),
        ):
            found = (shutil.which(selected, path=env['PATH']) if selected else
                     next((path for name in candidates if (path := shutil.which(name, path=env['PATH']))), None))
            add('build', label, 'ok' if found else 'error', found or 'Choose host compiler paths; Windows MSVC also needs VsDevCmd.bat in Setup')
        directory = config.builds
        while not directory.exists() and directory.parent != directory:
            directory = directory.parent
        add('build', 'Build output', 'ok' if directory.is_dir() and os.access(directory, os.W_OK) else 'error', config.builds)
        if config.dependency_cache:
            directory = Path(config.dependency_cache).expanduser()
            while not directory.exists() and directory.parent != directory:
                directory = directory.parent
            add('build', 'Dependency cache', 'ok' if directory.is_dir() and os.access(directory, os.W_OK) else 'error', config.dependency_cache)
        for prefix in filter(None, (item.strip() for item in config.library_prefix.split(';'))):
            add('build', 'Library prefix', 'ok' if Path(prefix).expanduser().is_dir() else 'error', prefix)
        if config.llvm:
            add('build', 'LLVM folder', 'ok' if Path(config.llvm).expanduser().is_dir() else 'error', config.llvm)
        cache_issues = [issue for profile in PROFILES.values() for mode in ('Debug', 'Release')
                        if (issue := config.cache_issue(profile, mode))]
        if cache_issues:
            add('build', 'Existing build caches', 'warn', '\n'.join(cache_issues))
        if WINDOWS and len(str(config.builds)) > 90:
            add('build', 'Windows paths', 'warn', 'A short build path such as C:/sl-build reduces Windows path-length issues')

    if 'flash' in groups:
        available = probe('flash', 'dfu-util', [tool('dfu-util'), '--version'])
        hint = ('Install a compatible WinUSB driver for the STM32 DFU interface; CDC/COM uses its serial driver.' if WINDOWS else
                'USB DFU requires udev access. Serial devices may require dialout/uucp group access; reconnect after changing permissions.')
        add('flash', 'USB access', 'info', hint)
        if scan and available:
            try:
                from core.device_service import DeviceService
                devices = DeviceService(config).discover()
                add('flash', 'DFU scan', 'ok' if devices else 'warn',
                    '\n'.join(device.label for device in devices) or 'No STM32 DFU device connected; enter ROM/EdgeTX DFU before flashing')
            except Exception as error:
                add('flash', 'DFU scan', 'error', str(error))

    if 'serial' in groups:
        try:
            import serial
            from core.serial_service import discover_ports
            add('serial', 'pySerial', 'ok', f'{serial.__version__} (Studio Python: {sys.executable})')
            if scan:
                ports = discover_ports()
                add('serial', 'Port scan', 'ok' if ports else 'warn',
                    '\n'.join(port.label for port in ports) or 'No serial ports found. Check USB cable and CDC/USB-UART driver; scanning does not open a port.')
        except Exception as error:
            add('serial', 'Serial discovery', 'error', str(error))
    return checks


def require_build(config, env=None):
    errors = [str(check) for check in diagnose(config, groups=('build',), env=env) if check.status == 'error']
    if errors:
        raise ValueError('Build setup needs attention:\n' + '\n'.join(errors) + '\nOpen Setup to select or repair the paths.')
