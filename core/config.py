"""Per-user setup and board registry shared by the GUI and CLI."""
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

PROJECT_DIR = Path(__file__).resolve().parents[2]
BASELINE_COMMIT = '65db64b4890c399b8fcc9cc6a3d002c2b86e4706'
WINDOWS = sys.platform == 'win32'


def settings_path():
    override = os.environ.get('SAOLALINK_CONFIG')
    if override:
        return Path(override).expanduser().resolve()
    if WINDOWS:
        base = Path(os.environ['APPDATA']) if os.environ.get('APPDATA') else Path.home() / 'AppData/Roaming'
    else:
        base = Path(os.environ['XDG_CONFIG_HOME']) if os.environ.get('XDG_CONFIG_HOME') else Path.home() / '.config'
    return base / 'SaolaLinkStudio' / 'settings.json'


def data_dir():
    if WINDOWS:
        base = Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home() / 'AppData/Local'
    else:
        base = Path(os.environ['XDG_CACHE_HOME']) if os.environ.get('XDG_CACHE_HOME') else Path.home() / '.cache'
    return base / 'SaolaLinkStudio'


def executable_in(directory, name):
    """Accept a toolchain installation root or its bin folder."""
    suffix = '.exe' if WINDOWS else ''
    for parent in (Path(directory), Path(directory) / 'bin'):
        candidate = parent / (name + suffix)
        if candidate.is_file():
            return candidate
    return Path(directory) / (name + suffix)


@dataclass(frozen=True)
class BoardProfile:
    key: str
    name: str
    pcb: str
    pcbrev: str
    flavour: str
    flash_size: int = 512 * 1024
    bootloader_size: int = 32 * 1024
    flash_address: str = '0x08000000'
    dfu_id: str = '0483:df11'
    hse_hz: int | None = None


PROFILES = {
    'saolalink-v1': BoardProfile('saolalink-v1', 'SaolaLink V1', 'X7', 'SAOLALINK_V1', 'saolalinkv1', hse_hz=12000000),
    'saolalink-devebox': BoardProfile('saolalink-devebox', 'SaolaLink DevEBox 8MHz (EdgeTX USB)', 'X7', 'SAOLALINK_V1', 'saolalinkv1', hse_hz=8000000),
    'pocket': BoardProfile('pocket', 'RadioMaster Pocket (reference)', 'X7', 'POCKET', 'pocket'),
}


@dataclass(frozen=True)
class AppConfig:
    source: Path
    builds: Path
    toolchain: Path | None = None
    cmake: str = 'cmake'
    git: str = 'git'
    dfu_util: str = 'dfu-util'
    build_tool: str = 'ninja'
    generator: str = 'Ninja'
    build_python: str = sys.executable
    native_cc: str = ''
    native_cxx: str = ''
    llvm: str = ''
    library_prefix: str = ''
    dependency_cache: str = ''
    vsdevcmd: str = ''
    serial_port: str = ''
    serial_baud: int = 115200

    @classmethod
    def detected(cls):
        bundled = PROJECT_DIR / '.tools/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi/bin'
        arm = shutil.which('arm-none-eabi-g++')
        toolchain = bundled if bundled.is_dir() else (Path(arm).parent if arm else None)
        generator = 'Ninja' if WINDOWS or shutil.which('ninja') else 'Unix Makefiles'
        def tool(name):
            return shutil.which(name) or name
        llvm = shutil.which('clang')
        return cls(
            PROJECT_DIR / 'edgetx',
            PROJECT_DIR / 'build' if (PROJECT_DIR / 'build').is_dir() else data_dir() / 'builds',
            toolchain,
            cmake=tool('cmake'), git=tool('git'), dfu_util=tool('dfu-util'),
            build_tool=tool('ninja' if generator == 'Ninja' else 'make'), generator=generator,
            native_cc=os.environ.get('CC', ''), native_cxx=os.environ.get('CXX', ''),
            llvm=str(Path(llvm).parent) if llvm else '',
        )

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else settings_path()
        config = cls.detected()
        if path.is_file():
            try:
                document = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(document, dict) or document.get('version') != 1:
                    raise ValueError('Unsupported settings format (expected version 1)')
                values = document.get('settings')
                if not isinstance(values, dict):
                    raise ValueError('Settings must be a JSON object')
                config = config.updated(values)
            except (OSError, ValueError, TypeError) as error:
                raise ValueError(f'Cannot load Setup from {path}: {error}. Open Setup to repair it.') from error
        overrides = {field: os.environ[var] for field, var in (
            ('source', 'EDGETX_DIR'), ('builds', 'SAOLALINK_BUILD_DIR'), ('toolchain', 'ARM_TOOLCHAIN_DIR'))
            if os.environ.get(var)}
        return config.updated(overrides)

    @classmethod
    def default(cls):
        return cls.load()

    def updated(self, values):
        allowed = {field.name for field in fields(self)}
        changes = {}
        for name, value in values.items():
            if name not in allowed:
                continue
            if name == 'serial_baud':
                value = int(value)
                if value not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
                    raise ValueError('Unsupported default serial baud rate')
            elif name in ('source', 'builds', 'toolchain'):
                if value is not None and not isinstance(value, (str, Path)):
                    raise ValueError(f'{name} must be a path')
                text = str(value or '').strip()
                if not text and name != 'toolchain':
                    raise ValueError(f'{name} cannot be empty')
                value = Path(text).expanduser().resolve() if text else None
            else:
                if not isinstance(value, str):
                    raise ValueError(f'{name} must be text')
                value = value.strip()
                if '\n' in value or '\r' in value or '\x00' in value:
                    raise ValueError(f'{name} must be a single path or value')
                if value and name in ('llvm', 'dependency_cache', 'vsdevcmd'):
                    value = str(Path(value).expanduser().resolve())
                if value and name == 'library_prefix':
                    value = ';'.join(str(Path(part.strip()).expanduser().resolve())
                                     for part in value.split(';') if part.strip())
            changes[name] = value
        result = replace(self, **changes)
        result = replace(result, source=result.source.resolve(), builds=result.builds.resolve())
        if result.generator not in ('Ninja', 'Unix Makefiles', 'MinGW Makefiles', 'NMake Makefiles'):
            raise ValueError('Choose a supported single-configuration CMake generator')
        # Clean removes builds/<profile>/<mode>. Never let it overlap source or app files.
        protected = (result.source, Path(__file__).resolve().parents[1])
        for profile in PROFILES.values():
            for mode in ('Debug', 'Release'):
                output = result.build_dir(profile, mode).resolve()
                if any(root == output or root.is_relative_to(output) or output.is_relative_to(root)
                       for root in protected):
                    raise ValueError('Build output must be outside the EdgeTX and Studio source folders')
        return result

    def to_dict(self):
        return {name: str(value) if isinstance(value, Path) else value for name, value in asdict(self).items()}

    def save(self, path=None):
        path = Path(path) if path else settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({'version': 1, 'settings': self.to_dict()}, ensure_ascii=False, indent=2) + '\n'
        fd, temp = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, path)
        finally:
            Path(temp).unlink(missing_ok=True)

    def tool(self, name):
        value = {'cmake': self.cmake, 'git': self.git, 'dfu-util': self.dfu_util,
                 'build-tool': self.build_tool, 'python': self.build_python}[name]
        if not value:
            raise ValueError(f'Choose {name} in Setup')
        return str(Path(value).expanduser())

    def compiler(self):
        return str(executable_in(self.toolchain, 'arm-none-eabi-g++')) if self.toolchain else 'arm-none-eabi-g++'

    def environment(self, build=True):
        env = os.environ.copy()
        if build and WINDOWS and self.vsdevcmd:
            path = Path(self.vsdevcmd)
            # This is a user-selected Visual Studio script; prohibit cmd metacharacters.
            if not path.is_file() or path.suffix.lower() != '.bat' or any(c in str(path) for c in '%&^|<>"!\r\n'):
                raise ValueError('Select a valid VsDevCmd.bat path without shell metacharacters in Setup')
            result = subprocess.run(['cmd.exe', '/d', '/u', '/c', f'call "{path}" -arch=x64 -host_arch=x64 >nul && set'],
                                    capture_output=True, text=True, encoding='utf-16-le', errors='replace', timeout=30, check=True)
            for line in result.stdout.splitlines():
                key, sep, value = line.partition('=')
                if sep and key:
                    # Windows environment names are case-insensitive, Python dicts are not.
                    for old in list(env):
                        if old.upper() == key.upper():
                            del env[old]
                    env[key.upper()] = value
        directories = []
        for value in (self.cmake, self.git, self.dfu_util, self.build_tool, self.build_python):
            if not value:
                continue
            value = str(Path(value).expanduser())
            if Path(value).is_file():
                directories.append(str(Path(value).resolve().parent))
        if self.toolchain:
            directories.append(str(executable_in(self.toolchain, 'arm-none-eabi-g++').parent))
        if self.llvm:
            directories.append(str(Path(self.llvm).expanduser().resolve()))
        path_key = next((key for key in env if key.upper() == 'PATH'), 'PATH')
        env['PATH'] = os.pathsep.join(dict.fromkeys(directories + [env.pop(path_key, '')]))
        if self.llvm and not WINDOWS:
            env['LD_LIBRARY_PATH'] = str(Path(self.llvm).expanduser().resolve()) + os.pathsep + env.get('LD_LIBRARY_PATH', '')
        if build and self.native_cc:
            env['CC'] = self.native_cc
        if build and self.native_cxx:
            env['CXX'] = self.native_cxx
        env['PYTHONUTF8'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        return env

    def build_dir(self, profile, mode):
        if mode not in ('Debug', 'Release'):
            raise ValueError('Build type must be Debug or Release')
        return self.builds / profile.key / mode.lower()
