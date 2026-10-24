"""Find installed tools without changing PATH, downloading, or replacing working selections."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def search_directories(workspace, *, platform=None, home=None):
    platform = platform or sys.platform
    home = Path(home or Path.home())
    roots = [Path(workspace) / '.tools', Path(workspace) / 'tools', Path(__file__).resolve().parents[1] / '.tools',
             home / '.local', home / 'Downloads', home / 'tools']
    directories = []
    if platform == 'win32':
        programs = [Path(os.environ.get(name, default)) for name, default in
                    (('ProgramFiles', 'C:/Program Files'), ('ProgramFiles(x86)', 'C:/Program Files (x86)'))]
        local = Path(os.environ.get('LOCALAPPDATA', str(home / 'AppData/Local')))
        roots += programs + [local / 'Programs', local / 'Microsoft/WinGet/Packages']
        directories += [local / 'Microsoft/WinGet/Links']
        for root in programs + [local / 'Programs']:
            directories += [root / 'CMake/bin', root / 'Git/cmd', root / 'LLVM/bin']
    else:
        roots += [Path('/opt'), Path('/usr/local')]
        directories += [Path('/usr/local/bin'), Path('/usr/bin'), home / '.local/bin']
    # Only inspect known names and a bounded depth; never crawl entire disks/home folders.
    for root in roots:
        for pattern in ('arm-gnu-toolchain-14.2.rel1*', 'Arm GNU Toolchain*/*14.2*',
                        '*CMake*', '*Ninja*', '*LLVM*', '*dfu-util*'):
            for folder in sorted(root.glob(pattern)):
                if folder.is_dir():
                    directories += [folder, folder / 'bin', folder / 'win64']
    return list(dict.fromkeys(str(folder) for folder in directories if folder.is_dir()))


def search_path(workspace, *, platform=None, home=None):
    platform = platform or sys.platform
    paths = [os.environ.get('PATH', '')]
    if platform == 'win32':
        try:
            import winreg
            for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
                              (winreg.HKEY_CURRENT_USER, 'Environment')):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        paths.append(os.path.expandvars(winreg.QueryValueEx(handle, 'Path')[0]))
                except OSError:
                    pass
        except ImportError:
            pass
    paths += search_directories(workspace, platform=platform, home=home)
    return os.pathsep.join(paths)


def find_executable(value, path):
    value = str(Path(value).expanduser()) if value else ''
    if not value:
        return None
    return shutil.which(value, path=path)


def arm_version(executable):
    try:
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
        result = subprocess.run([str(executable), '-dumpfullversion'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=5, **flags)
        return result.returncode == 0 and result.stdout.strip() == '14.2.1'
    except (OSError, subprocess.SubprocessError):
        return False


def discover_tools(config, only=None, *, platform=None, workspace=None):
    """Return config with missing paths filled. `only` can refresh specific failed checks."""
    platform = platform or sys.platform
    workspace = Path(workspace or Path(__file__).resolve().parents[2])
    path = search_path(workspace, platform=platform)
    updates = {}
    names = {'cmake': 'cmake', 'git': 'git', 'dfu_util': 'dfu-util', 'build_python': sys.executable,
             'build_tool': {'Ninja': 'ninja', 'Unix Makefiles': 'make', 'MinGW Makefiles': 'mingw32-make',
                            'NMake Makefiles': 'nmake'}[config.generator],
             'native_cc': 'clang' if platform == 'win32' else 'cc',
             'native_cxx': 'clang++' if platform == 'win32' else 'c++'}
    for field, name in names.items():
        if only is not None and field not in only:
            continue
        selected = find_executable(getattr(config, field), path)
        # Resolve a bare command to its executable so users can see where it was found.
        if only is not None and (found := find_executable(name, path)):
            updates[field] = found
        elif selected:
            updates[field] = selected
        elif found := find_executable(name, path):
            updates[field] = found
    if only is None or 'toolchain' in only:
        suffix = '.exe' if platform == 'win32' else ''
        candidates = [config.compiler()]
        for directory in path.split(os.pathsep):
            if directory:
                candidates.append(str(Path(directory) / ('arm-none-eabi-g++' + suffix)))
        for candidate in dict.fromkeys(candidates):
            resolved = find_executable(candidate, path)
            if resolved and arm_version(resolved):
                updates['toolchain'] = str(Path(resolved).parent)
                break
    if only is None or 'llvm' in only:
        selected = Path(config.llvm).expanduser() if config.llvm else None
        filenames = ('libclang.dll',) if platform == 'win32' else ('libclang.so',)
        folders = ([selected] if selected else []) + [Path(folder) for folder in path.split(os.pathsep) if folder]
        if platform != 'win32':
            folders += [Path('/usr/lib64'), Path('/usr/lib'), Path('/usr/local/lib')]
            folders += sorted(Path('/usr/lib').glob('llvm-*/lib'), reverse=True)
        for folder in folders:
            if any((folder / name).is_file() for name in filenames):
                updates['llvm'] = str(folder)
                break
    return config.updated(updates)
