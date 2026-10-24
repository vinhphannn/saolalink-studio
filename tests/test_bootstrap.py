"""Bootstrap reuse/failure behavior. Network installation is exercised by the launchers in CI."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bootstrap import prepare


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Studio launcher có dấu ')
        self.root = Path(self.temp.name).resolve()
        self.requirements = self.root / 'requirements.txt'
        self.requirements.write_text('customtkinter>=5.2,<7\npyserial>=3.5,<4\n', encoding='utf-8')
        self.folder = self.root / '.venv'
        self.python = self.folder / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        (self.folder / 'pyvenv.cfg').touch()
        self.marker = self.folder / '.studio-requirements.sha256'
        self.prefix = SimpleNamespace(returncode=0, stdout=str(self.folder), stderr='')

    def tearDown(self):
        self.temp.cleanup()

    def test_unchanged_environment_does_not_run_pip(self):
        self.marker.write_text(hashlib.sha256(self.requirements.read_bytes()).hexdigest(), encoding='utf-8')
        with patch('bootstrap.subprocess.run', side_effect=[self.prefix, SimpleNamespace(returncode=0)]) as run:
            self.assertEqual(prepare(self.root), self.python)
        self.assertEqual(run.call_count, 2)
        self.assertFalse(any('pip' in call.args[0] for call in run.call_args_list))

    def test_first_install_uses_private_python_and_handles_paths_with_spaces(self):
        with patch('bootstrap.subprocess.run', side_effect=[self.prefix, SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)]) as run:
            prepare(self.root)
        command = run.call_args_list[1].args[0]
        self.assertEqual(command[:4], [str(self.python), '-m', 'pip', 'install'])
        self.assertEqual(command[-1], str(self.requirements))
        self.assertTrue(self.marker.exists())

    def test_failed_install_is_not_marked_ready(self):
        with patch('bootstrap.subprocess.run', side_effect=[self.prefix, subprocess.CalledProcessError(1, 'pip')]):
            with self.assertRaises(subprocess.CalledProcessError):
                prepare(self.root)
        self.assertFalse(self.marker.exists())

    def test_moved_environment_reports_fix_instead_of_launching_wrong_python(self):
        wrong = SimpleNamespace(returncode=0, stdout=str(self.root / 'old-location'), stderr='')
        with patch('bootstrap.subprocess.run', return_value=wrong) as run:
            with self.assertRaisesRegex(RuntimeError, 'remove only its .venv'):
                prepare(self.root)
        self.assertEqual(run.call_count, 1)

    def test_existing_non_venv_directory_is_never_erased(self):
        (self.folder / 'pyvenv.cfg').unlink()
        important = self.folder / 'keep.txt'
        important.write_text('keep', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'will not erase'):
            prepare(self.root)
        self.assertEqual(important.read_text(encoding='utf-8'), 'keep')


if __name__ == '__main__':
    unittest.main()
