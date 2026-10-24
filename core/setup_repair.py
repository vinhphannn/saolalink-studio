"""Explicit, reviewable dependency installation, separate from read-only checks."""
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys

from core.config import data_dir
from core.tool_discovery import discover_tools


@dataclass(frozen=True)
class InstallStep:
    title: str
    command: tuple[str, ...]
    elevated: bool = False
    updates: tuple[tuple[str, str], ...] = ()
    repairs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepairPlan:
    config: object
    checks: tuple
    steps: tuple[InstallStep, ...]
    notes: tuple[str, ...]

    def summary(self):
        parts = [step.title for step in self.steps]
        if self.steps:
            parts.append('Downloads require internet. System packages may include dependencies. '
                         'Administrator authentication is handled by the operating system. '
                         'Keep Studio open until installation finishes.')
        if self.notes:
            parts.append('Also needs attention:\n' + '\n'.join(self.notes))
        return '\n\n'.join(parts) or 'No missing components found.'


def python_environment(config):
    """Probe the selected Python before choosing an isolated install destination."""
    result = subprocess.run([config.tool('python'), '-c',
        'import json,sys; print(json.dumps({"venv":sys.prefix != sys.base_prefix,'
        '"version":list(sys.version_info[:2])}))'], capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=15, check=True,
        env=config.environment(build=False))
    return json.loads(result.stdout)


def make_plan(config, checks, *, platform=None, distro=None):
    """Only plan repairs for failed checks; this function never installs anything."""
    platform = platform or sys.platform
    if distro is None:
        try:
            distro = __import__('platform').freedesktop_os_release().get('ID', '') if platform == 'linux' else ''
        except OSError:
            distro = ''
    failed = {check.name: check for check in checks if check.status == 'error'}
    covered, steps, notes = set(), [], []
    packages = []
    mappings = {
        'CMake': ('cmake', 'cmake', 'Kitware.CMake'),
        'Git': ('git', 'git', 'Git.Git'),
        'LLVM/libclang': ('clang-devel', 'libclang-dev', 'LLVM.LLVM'),
        'Host C compiler': ('gcc', 'gcc', None),
        'Host C++ compiler': ('gcc-c++', 'g++', None),
        'dfu-util': ('dfu-util', 'dfu-util', None),
    }
    if config.generator in ('Ninja', 'Unix Makefiles'):
        mappings[f'Build tool ({config.generator})'] = (
            ('ninja-build', 'ninja-build', 'Ninja-build.Ninja') if config.generator == 'Ninja' else ('make', 'make', None))
    supported_linux = platform == 'linux' and distro in ('fedora', 'ubuntu', 'debian')
    for name, choices in mappings.items():
        if name not in failed:
            continue
        if supported_linux:
            packages.append(choices[0 if distro == 'fedora' else 1])
            covered.add(name)
        elif platform == 'win32' and choices[2] and (winget := shutil.which('winget')):
            package = choices[2]
            steps.append(InstallStep(f'Install/repair {name} using Windows Package Manager ({package}). '
                'The publisher installer will open. Clicking Install also accepts the WinGet source and package agreements.',
                (winget, 'install', '--id', package, '--exact', '--source', 'winget', '--interactive',
                 '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity'), repairs=(name,)))
            covered.add(name)
    if packages:
        pkexec = shutil.which('pkexec')
        manager = '/usr/bin/dnf' if distro == 'fedora' else '/usr/bin/apt-get'
        if pkexec and Path(manager).is_file():
            # Fedora's official repos avoid unrelated third-party key prompts. Signature checks stay on.
            args = ('--repo=fedora', '--repo=updates', '-y', 'install') if distro == 'fedora' else ('install', '-y')
            steps.insert(0, InstallStep('Install/repair system packages: ' + ', '.join(dict.fromkeys(packages)) +
                (' (official Fedora repositories).' if distro == 'fedora' else ' (configured APT repositories).'),
                (pkexec, '--disable-internal-agent', manager, *args, *dict.fromkeys(packages)),
                elevated=True, repairs=tuple(sorted(covered))))
        else:
            covered.difference_update(mappings)
            notes.append('A desktop Polkit authentication agent and the system package manager are required for automatic Linux installation.')

    python_error = failed.get('Build Python')
    if python_error and 'Build Python is missing:' in python_error.message and (config.source / 'pyproject.toml').is_file():
        try:
            info = python_environment(config)
            if info['version'] < [3, 10]:
                raise ValueError('Choose Python 3.10 or newer first.')
            python = config.tool('python')
            updates = ()
            if not info['venv']:
                folder = data_dir() / 'build-python'
                python = str(folder / ('Scripts/python.exe' if platform == 'win32' else 'bin/python'))
                steps.append(InstallStep(f'Create a private build Python environment in {folder}.',
                    (config.tool('python'), '-m', 'venv', str(folder))))
                updates = (('build_python', python),)
            steps.append(InstallStep(f'Install EdgeTX Python build packages into {python} from {config.source}.',
                (python, '-m', 'pip', 'install', '--disable-pip-version-check', '-e', str(config.source)), updates=updates))
            covered.add('Build Python')
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            notes.append(f'Could not prepare Python packages: {error}')
    if any(name in failed for name in ('Arm compiler', 'Arm tools')):
        notes.append('Arm GNU must be exactly 14.2.rel1 (14.2.1). Install that release from Arm, then Browse to its root/bin folder. Studio will not substitute a different compiler release.')
        covered.update(('Arm compiler', 'Arm tools'))
    for name in sorted(failed.keys() - covered):
        notes.append(f'{name}: review its path/details in Check setup. No automatic repair is available for this check.')
    if platform == 'win32' and steps:
        notes.append('If newly installed tools are not detected, restart Studio to refresh Windows PATH, then Check setup.')
    return RepairPlan(config, tuple(checks), tuple(steps), tuple(notes))


def refreshed_config(config, checks):
    """Replace only failed selections when a repaired tool is actually discoverable."""
    failed = {check.name for check in checks if check.status == 'error'}
    fields = set()
    for name, field in (
        ('CMake', 'cmake'), ('Git', 'git'), ('dfu-util', 'dfu_util'),
        ('Host C compiler', 'native_cc'), ('Host C++ compiler', 'native_cxx'),
        (f'Build tool ({config.generator})', 'build_tool'),
    ):
        if name in failed:
            fields.add(field)
    if 'LLVM/libclang' in failed:
        fields.add('llvm')
        config = config.updated({'llvm': ''})
    return discover_tools(config, only=fields)


def install(plan, log):
    """Execute a user-approved plan, streaming output. Never elevate Studio/Python."""
    config, failures, repaired = plan.config, [], set()
    for step in plan.steps:
        log('\n' + step.title + '\n')
        try:
            # Do not attach a terminal or collect administrator passwords. pkexec uses the desktop agent.
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
            with subprocess.Popen(list(step.command), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                    env=config.environment(build=False), **options) as process:
                for line in process.stdout:
                    log(line)
                status = process.wait()
            if status:
                if step.elevated and status in (126, 127):
                    raise ValueError('Administrator authentication was cancelled or unavailable. Use a desktop session with a Polkit authentication agent and try again.')
                raise ValueError(f'Installer returned {status}. Review the output above; check your internet connection and package-manager messages.')
            config = config.updated(dict(step.updates))
            repaired.update(step.repairs)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            failures.append(str(error))
            log('[ERROR] ' + str(error) + '\n')
            break  # Do not cascade into dependent steps after a failed installation.
    return refreshed_config(config, [check for check in plan.checks if check.name in repaired]), tuple(failures)
