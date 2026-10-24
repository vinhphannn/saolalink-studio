"""Compare board data and shared integration against a fixed Pocket commit."""
import difflib
import json
import re
import subprocess
from pathlib import Path
from core.config import BASELINE_COMMIT

HW_PATH = 'radio/src/boards/hw_defs/'
TARGET_PATH = 'radio/src/targets/taranis/'
INTEGRATION_FILES = ['cmake/Macros.cmake', TARGET_PATH + 'CMakeLists.txt', TARGET_PATH + 'hal.h',
    TARGET_PATH + 'board.h', TARGET_PATH + 'board.cpp', TARGET_PATH + 'lcd_driver_spi.cpp',
    'radio/src/gui/navigation/navigation.h', 'radio/src/edgetx.cpp',
    'radio/util/hw_defs/legacy_names.py', 'radio/util/build-firmware.py']

def git(source, *args, executable='git', env=None):
    result = subprocess.run([executable, *args], cwd=source, env=env, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', check=True)
    return result.stdout

def diff(a, b, old, new):
    return ''.join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), fromfile=old, tofile=new)) or '(no differences)\n'

def canonical(data):
    return json.dumps(data, sort_keys=True, indent=2) + '\n'

def report(source: Path, executable='git', env=None):
    def source_git(*args):
        return git(source, *args, executable=executable, env=env)
    baseline = json.loads(source_git('show', BASELINE_COMMIT + ':' + HW_PATH + 'pocket.json'))
    pocket = json.loads((source / HW_PATH / 'pocket.json').read_text())
    custom = json.loads((source / HW_PATH / 'saolalinkv1.json').read_text())
    hardware = dict(custom); hardware['identity'] = baseline['identity']
    text = f'SaolaLink V1 vs Pocket\nPinned baseline: {BASELINE_COMMIT}\n\n'
    text += '=== Hardware changes (identity excluded) ===\n' + diff(canonical(baseline), canonical(hardware), 'Pocket baseline', 'SaolaLink V1 hardware')
    text += '\n=== Full board definition (including identity) ===\n' + diff(canonical(baseline), canonical(custom), 'Pocket baseline', 'SaolaLink V1')
    text += '\n=== Upstream Pocket drift in this checkout ===\n' + diff(canonical(baseline), canonical(pocket), 'Pocket baseline', 'Pocket current')
    original = source_git('show', BASELINE_COMMIT + ':' + TARGET_PATH + 'CMakeLists.txt')
    block = re.search(r'  elseif\(PCBREV STREQUAL POCKET\)\n(.*?)(?=  elseif\()', original, re.S).group(1)
    current = (source / TARGET_PATH / 'saolalink_v1/target.cmake').read_text()
    current = ''.join(line for line in current.splitlines(True) if not line.startswith('#'))
    # Separate the intentional flavour rename from build option differences.
    text += '\n=== Build settings (flavour rename normalized) ===\n' + diff(block, current.replace('set(FLAVOUR saolalinkv1)', 'set(FLAVOUR pocket)'), 'Pocket target', 'SaolaLink V1 target')
    text += '\n=== SaolaLink HAL overrides ===\n' + (source / TARGET_PATH / 'saolalink_v1/hal_overrides.h').read_text()
    text += '\n=== Integration changes since pinned baseline ===\n'
    text += source_git('diff', BASELINE_COMMIT, '--', *INTEGRATION_FILES) or '(no differences)\n'
    return text

def compare_generated(builds: Path, mode='Debug'):
    """Compare the effective HAL after code generation, not only input JSON."""
    files = [builds / key / mode.lower() / 'arm-none-eabi/radio/src' / f'{flavour}.json.h'
             for key, flavour in [('pocket', 'pocket'), ('saolalink-v1', 'saolalinkv1')]]
    if not all(path.is_file() for path in files):
        return '\n=== Effective HAL ===\nBuild both Pocket and SaolaLink V1 in the same mode to compare the preprocessed HAL macros.\n'
    def macros(path):
        return '\n'.join(sorted(line for line in path.read_text().splitlines() if line.startswith('#define '))) + '\n'
    return '\n=== Effective HAL macros ===\n' + diff(macros(files[0]), macros(files[1]), str(files[0]), str(files[1]))
