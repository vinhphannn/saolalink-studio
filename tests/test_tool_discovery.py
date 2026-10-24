"""Installed tool discovery on different machine layouts; no downloads or USB access."""
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from core.tool_discovery import discover_tools, search_directories
from core.setup_guidance import next_steps
from core.diagnostics import Check


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Studio discovery có dấu ')
        self.root = Path(self.temp.name).resolve()
        self.config = AppConfig(self.root / 'source', self.root / 'builds', generator='Unix Makefiles')

    def tearDown(self):
        self.temp.cleanup()

    def executable(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(); path.chmod(0o755)
        return str(path)

    def test_find_missing_tool_without_overwriting_custom_paths_or_generator(self):
        suffix = '.exe' if sys.platform == 'win32' else ''
        custom = self.executable(self.root / ('custom/cmake' + suffix))
        standard = self.executable(self.root / ('vendor/git' + suffix))
        config = replace(self.config, cmake=custom, git='not-installed')
        with patch('core.tool_discovery.search_path', return_value=str(self.root / 'vendor')):
            result = discover_tools(config, only={'git'})
        self.assertEqual(Path(result.git), Path(standard))
        self.assertEqual(Path(result.cmake), Path(custom))
        self.assertEqual(result.generator, 'Unix Makefiles')
        self.assertEqual(result.source, self.config.source)

    def test_arm_discards_other_releases_and_finds_extracted_download(self):
        suffix = '.exe' if sys.platform == 'win32' else ''
        wrong = self.executable(self.root / ('wrong/arm-none-eabi-g++' + suffix))
        right = self.executable(self.root / ('arm-gnu-toolchain-14.2.rel1/bin/arm-none-eabi-g++' + suffix))
        config = replace(self.config, toolchain=Path(wrong).parent)
        with patch('core.tool_discovery.search_path', return_value=str(Path(right).parent)), \
                patch('core.tool_discovery.arm_version', side_effect=lambda path: Path(path) == Path(right)):
            result = discover_tools(config, only={'toolchain'})
        self.assertEqual(result.toolchain, Path(right).parent)

    def test_common_windows_locations_without_existing_process_path(self):
        programs, local = self.root / 'Program Files', self.root / 'Local'
        for folder in (programs / 'CMake/bin', programs / 'LLVM/bin', programs / 'Git/cmd',
                       local / 'Microsoft/WinGet/Links', local / 'Programs/CMake/bin'):
            folder.mkdir(parents=True)
        with patch.dict(os.environ, {'ProgramFiles': str(programs), 'ProgramFiles(x86)': str(programs), 'LOCALAPPDATA': str(local)}):
            directories = search_directories(self.root, platform='win32', home=self.root)
        self.assertIn(str(programs / 'CMake/bin'), directories)
        self.assertIn(str(programs / 'LLVM/bin'), directories)
        self.assertIn(str(local / 'Microsoft/WinGet/Links'), directories)

    def test_lookup_in_downloads_is_bounded_to_known_tools(self):
        arm = self.root / 'Downloads/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi/bin'
        unrelated = self.root / 'Downloads/private-project/deep/tool/bin'
        arm.mkdir(parents=True); unrelated.mkdir(parents=True)
        directories = search_directories(self.root, home=self.root, platform='linux')
        self.assertIn(str(arm), directories)
        self.assertNotIn(str(unrelated), directories)

    def test_llvm_path_is_library_folder_not_compiler_bin(self):
        folder = self.root / 'LLVM/bin'
        folder.mkdir(parents=True)
        library = 'libclang.dll' if sys.platform == 'win32' else 'libclang.so'
        (folder / library).touch()
        with patch('core.tool_discovery.search_path', return_value=str(folder)):
            result = discover_tools(self.config, only={'llvm'})
        self.assertEqual(result.llvm, str(folder))

    def test_readable_next_steps_cover_manual_tools_and_success(self):
        errors = [Check('build', name, 'error', 'missing') for name in ('Arm compiler', 'EdgeTX checkout', 'LLVM/libclang')]
        text = next_steps(errors)
        self.assertIn('14.2.rel1', text)
        self.assertIn('Git clone', text)
        self.assertIn('Install missing', text)
        self.assertIn('Save & apply', next_steps([]))


if __name__ == '__main__':
    unittest.main()
