"""Installer planning and error handling; tests never install system packages."""
from dataclasses import replace
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from core.diagnostics import Check
from core.setup_repair import InstallStep, RepairPlan, install, make_plan, refreshed_config


def failed(*names):
    return [Check('build', name, 'error', 'missing') for name in names]


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Studio repair có dấu ')
        self.root = Path(self.temp.name)
        self.config = AppConfig(self.root / 'Edge TX', self.root / 'Output', llvm='old-llvm')

    def tearDown(self):
        self.temp.cleanup()

    def test_fedora_plan_is_read_only_official_repos_no_gpg_bypass(self):
        with patch('core.setup_repair.shutil.which', return_value='/usr/bin/pkexec'), \
                patch('core.setup_repair.Path.is_file', return_value=True), \
                patch('core.setup_repair.subprocess.Popen') as run:
            plan = make_plan(self.config, failed('LLVM/libclang', 'Host C++ compiler'), platform='linux', distro='fedora')
        run.assert_not_called()
        command = plan.steps[0].command
        self.assertEqual(command[:3], ('/usr/bin/pkexec', '--disable-internal-agent', '/usr/bin/dnf'))
        self.assertIn('--repo=fedora', command)
        self.assertIn('--repo=updates', command)
        self.assertIn('clang-devel', command)
        self.assertIn('gcc-c++', command)
        self.assertFalse(any('gpg' in part for part in command))

    def test_debian_packages_and_no_unsupported_automatic_installer(self):
        with patch('core.setup_repair.shutil.which', return_value='/usr/bin/pkexec'), \
                patch('core.setup_repair.Path.is_file', return_value=True):
            plan = make_plan(self.config, failed('LLVM/libclang', 'dfu-util'), platform='linux', distro='debian')
        self.assertIn('/usr/bin/apt-get', plan.steps[0].command)
        self.assertEqual(plan.steps[0].command[-2:], ('libclang-dev', 'dfu-util'))
        other = make_plan(self.config, failed('LLVM/libclang'), platform='linux', distro='arch')
        self.assertFalse(other.steps)
        self.assertIn('No automatic repair', other.summary())

    def test_windows_winget_exact_id_and_compiler_pin(self):
        with patch('core.setup_repair.shutil.which', return_value='C:/Windows/winget.exe'):
            plan = make_plan(self.config, failed('LLVM/libclang', 'Arm compiler'), platform='win32')
        self.assertEqual(len(plan.steps), 1)
        self.assertIn('LLVM.LLVM', plan.steps[0].command)
        self.assertIn('--exact', plan.steps[0].command)
        self.assertIn('--interactive', plan.steps[0].command)
        self.assertIn('14.2.rel1', plan.summary())
        self.assertIn('accepts', plan.summary())

    def test_no_errors_no_install_and_no_pkexec_reports_remedy(self):
        plan = make_plan(self.config, [Check('build', 'LLVM/libclang', 'ok', 'found')], platform='linux', distro='fedora')
        self.assertFalse(plan.steps)
        with patch('core.setup_repair.shutil.which', return_value=None):
            plan = make_plan(self.config, failed('LLVM/libclang'), platform='linux', distro='fedora')
        self.assertFalse(plan.steps)
        self.assertIn('Polkit', plan.summary())

    def python_plan(self, is_venv):
        self.config.source.mkdir(exist_ok=True)
        (self.config.source / 'pyproject.toml').touch()
        check = Check('build', 'Build Python', 'error', 'Build Python is missing: clang')
        with patch('core.setup_repair.python_environment', return_value={'venv': is_venv, 'version': [3, 12]}), \
                patch('core.setup_repair.data_dir', return_value=self.root / 'User data'):
            return make_plan(self.config, [check], platform=sys.platform, distro='')

    def test_python_install_uses_selected_venv_and_keeps_path_one_argument(self):
        plan = self.python_plan(True)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].command[0], self.config.build_python)
        self.assertEqual(plan.steps[0].command[-1], str(self.config.source))
        self.assertFalse(plan.steps[0].elevated)

    def test_system_python_creates_managed_venv_never_root_pip(self):
        plan = self.python_plan(False)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].command[1:4], ('-m', 'venv', str(self.root / 'User data/build-python')))
        self.assertNotEqual(plan.steps[1].command[0], self.config.build_python)
        self.assertEqual(dict(plan.steps[1].updates)['build_python'], plan.steps[1].command[0])
        self.assertTrue(all(not step.elevated for step in plan.steps))

    def test_auth_cancel_preserves_paths_and_stops_dependent_steps(self):
        steps = (InstallStep('LLVM', ('pkexec', '/usr/bin/dnf'), elevated=True, repairs=('LLVM/libclang',)),
                 InstallStep('next', ('must-not-run',)))
        plan = RepairPlan(self.config, tuple(failed('LLVM/libclang')), steps, ())
        process = Mock()
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        process.stdout = io.StringIO('Cancelled\n')
        process.wait.return_value = 126
        logs = []
        with patch('core.setup_repair.subprocess.Popen', return_value=process) as run:
            config, errors = install(plan, logs.append)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(config.llvm, 'old-llvm')
        self.assertIn('cancelled', errors[0])
        self.assertIn('Cancelled\n', logs)
        self.assertEqual(run.call_args.kwargs['stdin'], __import__('subprocess').DEVNULL)
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_real_worker_streams_and_applies_updates_only_on_success(self):
        target = str(self.root / 'managed-python')
        good = InstallStep('safe probe', (sys.executable, '-c', 'print("ready")'), updates=(('build_python', target),))
        bad = InstallStep('failure', (sys.executable, '-c', 'raise SystemExit(2)'), updates=(('build_python', 'wrong'),))
        logs = []
        result, errors = install(RepairPlan(self.config, (), (good, bad), ()), logs.append)
        self.assertEqual(result.build_python, target)
        self.assertEqual(len(errors), 1)
        self.assertTrue(any('ready' in line for line in logs))

    def test_refresh_preserves_working_custom_tools(self):
        config = replace(self.config, cmake='/custom/cmake', build_tool='/custom/ninja')
        with patch('core.setup_repair.shutil.which', return_value='/new/git'):
            updated = refreshed_config(config, failed('Git'))
        self.assertEqual(updated.git, '/new/git')
        self.assertEqual(updated.cmake, '/custom/cmake')
        self.assertEqual(updated.build_tool, '/custom/ninja')
        self.assertEqual(updated.llvm, 'old-llvm')


if __name__ == '__main__':
    unittest.main()
