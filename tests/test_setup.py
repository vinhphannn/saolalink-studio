"""Portable setup, configured tools and process cancellation without USB hardware."""
from dataclasses import replace
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig, executable_in, settings_path
from core.builder import FirmwareBuilder
from core.device_service import DeviceService
from core.diagnostics import diagnose
from core.runner import OperationRunner
from core.serial_service import SerialMonitor, discover_ports


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Studio setup ')
        self.root = Path(self.temp.name).resolve()
        self.config = AppConfig(self.root / 'Firmware riêng', self.root / 'Build output')
        self.env = {key: value for key, value in os.environ.items() if key not in
                    ('EDGETX_DIR', 'SAOLALINK_BUILD_DIR', 'ARM_TOOLCHAIN_DIR', 'SAOLALINK_CONFIG')}

    def tearDown(self):
        self.temp.cleanup()

    def test_save_reload_and_cli_environment_precedence(self):
        path = self.root / 'user settings/settings.json'
        saved = self.config.updated({'toolchain': self.root / 'Arm tools', 'serial_baud': '230400',
                                     'serial_port': 'COM12', 'dfu_util': 'C:/USB Tools/dfu-util.exe'})
        saved.save(path)
        with patch.dict(os.environ, self.env, clear=True):
            loaded = AppConfig.load(path)
            self.assertEqual(loaded, saved)
            with patch.dict(os.environ, {'EDGETX_DIR': str(self.root / 'Other source')}):
                overridden = AppConfig.load(path)
                self.assertEqual(overridden.source, self.root / 'Other source')
                self.assertEqual(overridden.serial_port, 'COM12')
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['version'], 1)
        self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_corrupt_or_wrong_settings_report_recovery(self):
        path = self.root / 'settings.json'
        for data in ('{bad', '[]', '{"version":2,"settings":{}}', '{"version":1,"settings":{"serial_baud":1}}'):
            path.write_text(data, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Open Setup'):
                AppConfig.load(path)

    def test_reject_output_overlapping_sources_and_invalid_values(self):
        for value in (self.config.source, Path(__file__).resolve().parents[1]):
            with self.assertRaisesRegex(ValueError, 'outside'):
                self.config.updated({'builds': value})
        with self.assertRaises(ValueError):
            self.config.updated({'serial_baud': 123})
        with self.assertRaises(ValueError):
            self.config.updated({'generator': 'Visual Studio 17 2022'})
        with self.assertRaises(ValueError):
            self.config.updated({'cmake': 'cmake\nother-command'})

    def test_per_user_settings_path_on_each_platform(self):
        with patch.dict(os.environ, {'APPDATA': str(self.root / 'Roaming')}, clear=True), patch('core.config.WINDOWS', True):
            self.assertEqual(settings_path(), self.root / 'Roaming/SaolaLinkStudio/settings.json')
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root / 'xdg')}, clear=True), patch('core.config.WINDOWS', False):
            self.assertEqual(settings_path(), self.root / 'xdg/SaolaLinkStudio/settings.json')

    def test_windows_arm_executable_suffix_and_install_root(self):
        arm = self.root / 'Arm install/bin'
        arm.mkdir(parents=True)
        (arm / 'arm-none-eabi-g++.exe').touch()
        with patch('core.config.WINDOWS', True):
            self.assertEqual(executable_in(arm.parent, 'arm-none-eabi-g++'), arm / 'arm-none-eabi-g++.exe')

    def test_visual_studio_environment_preserves_unicode_and_path(self):
        script = self.root / 'Visual Studio tools/VsDevCmd.bat'
        script.parent.mkdir()
        script.touch()
        config = replace(self.config, vsdevcmd=str(script))
        result = SimpleNamespace(stdout='Path=C:/Native tools\nINCLUDE=C:/Thư viện/include\n')
        with patch('core.config.WINDOWS', True), patch('core.config.subprocess.run', return_value=result) as run:
            env = config.environment()
        self.assertEqual(env['INCLUDE'], 'C:/Thư viện/include')
        self.assertIn('C:/Native tools', env['PATH'])
        self.assertEqual(run.call_args.kwargs['encoding'], 'utf-16-le')
        self.assertIn('/u', run.call_args.args[0])

    def test_commands_use_configured_tools_and_paths_as_single_arguments(self):
        selected = replace(self.config, cmake=str(self.root / 'CMake tools/cmake'),
                           build_python=str(self.root / 'Build Python/python'),
                           build_tool=str(self.root / 'Ninja tools/ninja'), git=str(self.root / 'Git tools/git'),
                           dependency_cache=str(self.root / 'shared cache'), library_prefix='C:/Lib One;D:/Lib Two')
        commands = FirmwareBuilder(selected).configure_commands(__import__('core.config', fromlist=['PROFILES']).PROFILES['saolalink-v1'], 'Debug')
        self.assertEqual(commands[0][0], selected.cmake)
        self.assertEqual(commands[1][0], selected.cmake)
        self.assertIn(str(selected.source).replace('\\', '/'), commands[0])
        self.assertIn('-DPython3_EXECUTABLE=' + selected.build_python.replace('\\', '/'), commands[0])
        self.assertIn('-DFETCHCONTENT_BASE_DIR=' + selected.dependency_cache.replace('\\', '/'), commands[0])
        self.assertIn('-DCMAKE_PREFIX_PATH=C:/Lib One;D:/Lib Two', commands[0])

    def test_dfu_uses_configured_executable_without_build_tools(self):
        config = replace(self.config, cmake='', build_tool='', dfu_util=str(self.root / 'USB tools/dfu-util.exe'), vsdevcmd='not-installed.bat')
        output = 'Found DFU: [0483:df11] path="1-2", alt=0, name="@Internal Flash", serial="ABC"'
        with patch('core.device_service.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=output, stderr='')) as run:
            devices = DeviceService(config).discover()
        self.assertEqual(run.call_args.args[0], [config.dfu_util, '-l'])
        self.assertEqual(devices[0].serial, 'ABC')

    def test_serial_checks_do_not_require_edgetx_or_build_tools(self):
        config = replace(self.config, cmake='', build_tool='', build_python='', dfu_util='', git='')
        checks = diagnose(config, groups=('serial',), scan=True)
        self.assertFalse(any(check.status == 'error' for check in checks), checks)
        self.assertTrue(any(check.name == 'Port scan' for check in checks))

    def test_diagnostics_collect_missing_tools_instead_of_aborting(self):
        config = replace(self.config, cmake='', build_tool='', build_python='', dfu_util='', git='')
        checks = diagnose(config, groups=('build', 'flash'))
        failed = {check.name for check in checks if check.status == 'error'}
        self.assertTrue({'CMake', 'Git', 'Build Python', 'dfu-util'}.issubset(failed), failed)

    def test_cli_setup_persists_independent_paths_and_repairs_json(self):
        path = self.root / 'cli/settings.json'
        path.parent.mkdir()
        path.write_text('{broken', encoding='utf-8')
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'cli.py'), 'setup',
                   '--config', str(path), '--source', str(self.config.source), '--build-dir', str(self.config.builds),
                   '--serial-port', 'COM12', '--save']
        result = subprocess.run(command, env=self.env, text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Firmware riêng', result.stdout)
        with patch.dict(os.environ, self.env, clear=True):
            saved = AppConfig.load(path)
        self.assertEqual(saved.source, self.config.source)
        self.assertEqual(saved.serial_port, 'COM12')

    def test_windows_com_discovery_and_no_posix_exclusive_request(self):
        ports = [SimpleNamespace(device='COM12', description='STM32 USB CDC', hwid='USB VID:PID=0483:5740', serial_number='A')]
        with patch('core.serial_service.list_ports.comports', return_value=ports):
            self.assertEqual(discover_ports()[0].device, 'COM12')
        monitor = SerialMonitor()
        class Connection:
            in_waiting = 0
            def open(self):
                pass
            def read(self, size):
                monitor._stop.set()
                return b''
            def close(self):
                pass
            @property
            def exclusive(self):
                raise AssertionError('POSIX exclusive option accessed on Windows')
        with patch('core.serial_service.os.name', 'nt'), patch('core.serial_service.serial.Serial', return_value=Connection()):
            monitor._run()
        self.assertEqual(monitor.state, 'disconnected')


class ProcessTreeTests(unittest.TestCase):
    def test_cancel_stops_descendants_and_preserves_environment_paths(self):
        with tempfile.TemporaryDirectory(prefix='Studio runner ') as temporary:
            root = Path(temporary)
            ready, child_marker, inherited = [root / name for name in ('ready', 'child marker', 'env marker')]
            child = 'import pathlib,sys,time; time.sleep(1.5); pathlib.Path(sys.argv[1]).touch()'
            parent = ('import os,pathlib,subprocess,sys,time; '
                      'pathlib.Path(sys.argv[3]).write_text(os.environ["STUDIO_TEST_VALUE"], encoding="utf-8"); '
                      'subprocess.Popen([sys.executable,"-c",sys.argv[4],sys.argv[2]]); '
                      'pathlib.Path(sys.argv[1]).touch(); time.sleep(30)')
            env = dict(os.environ, STUDIO_TEST_VALUE='đường dẫn with spaces', PYTHONUTF8='1')
            runner = OperationRunner(root / 'logs', env=env)
            runner.start('tree', [[sys.executable, '-c', parent, str(ready), str(child_marker), str(inherited), child]], root)
            try:
                deadline = time.monotonic() + 8
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists())
                runner.stop()
                while True:
                    event, success = runner.events.get(timeout=10)
                    if event == 'finished':
                        self.assertFalse(success)
                        break
                self.assertEqual(inherited.read_text(encoding='utf-8'), 'đường dẫn with spaces')
                time.sleep(1.7)
                self.assertFalse(child_marker.exists(), 'Compiler descendant survived cancellation')
            finally:
                runner.stop()
