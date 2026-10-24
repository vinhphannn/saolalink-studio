import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.builder import FirmwareBuilder, digest
from core.config import AppConfig, PROFILES, PROJECT_DIR
from core.device_service import parse_devices, DfuDevice
from core.runner import OperationRunner
from core.comparison import report, git

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = AppConfig(PROJECT_DIR / 'edgetx', self.root)
        self.builder = FirmwareBuilder(self.config)
        self.profile = PROFILES['saolalink-v1']

    def tearDown(self):
        self.temp.cleanup()

    def make_artifact(self):
        binary = self.config.build_dir(self.profile, 'Debug') / 'arm-none-eabi/firmware.bin'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'firmware-data')
        info = dict(profile=self.profile.key, pcbrev=self.profile.pcbrev, mode='Debug', kind='firmware',
                    address=self.profile.flash_address, sha256=digest(binary), bootloader_included=True, hse_hz=self.profile.hse_hz)
        binary.with_suffix('.manifest.json').write_text(json.dumps(info))
        return binary

    def test_profile_and_full_image_configuration(self):
        command = self.builder.configure_commands(self.profile, 'Debug')[0]
        self.assertIn('-DPCBREV=SAOLALINK_V1', command)
        self.assertIn('-DBOOTLOADER=ON', command)
        self.assertIn('-DUSE_FW_LTO=ON', command)
        self.assertIn('-DFIRMWARE_STRIP_BOOTLOADER=OFF', command)
        self.assertNotEqual(self.config.build_dir(self.profile, 'Debug'), self.config.build_dir(PROFILES['pocket'], 'Debug'))
        self.assertNotEqual(self.config.build_dir(self.profile, 'Debug'), self.config.build_dir(self.profile, 'Release'))

    def test_artifact_tamper_and_cross_target_rejected(self):
        binary = self.make_artifact()
        self.assertEqual(self.builder.artifact(self.profile, 'Debug', 'firmware')[0], binary)
        with self.assertRaises(ValueError):
            self.builder.artifact(PROFILES['pocket'], 'Debug', 'firmware')
        binary.write_bytes(b'changed-content')
        with self.assertRaises(ValueError):
            self.builder.artifact(self.profile, 'Debug', 'firmware')

    def test_devebox_clock_is_isolated_and_wrong_clock_manifest_rejected(self):
        dev = PROFILES['saolalink-devebox']
        self.assertIn('-DSAOLALINK_HSE_HZ=8000000', self.builder.configure_commands(dev, 'Debug')[0])
        self.assertIn('-DSAOLALINK_HSE_HZ=12000000', self.builder.configure_commands(self.profile, 'Debug')[0])
        self.assertNotEqual(self.config.build_dir(dev, 'Debug'), self.config.build_dir(self.profile, 'Debug'))
        binary = self.make_artifact()
        manifest = binary.with_suffix('.manifest.json')
        info = json.loads(manifest.read_text()); info['hse_hz'] = 8000000
        manifest.write_text(json.dumps(info))
        with self.assertRaises(ValueError):
            self.builder.artifact(self.profile, 'Debug', 'firmware')


    def test_stripped_image_rejected(self):
        binary = self.make_artifact()
        path = binary.with_suffix('.manifest.json')
        info = json.loads(path.read_text()); info['bootloader_included'] = False
        path.write_text(json.dumps(info))
        with self.assertRaises(ValueError):
            self.builder.artifact(self.profile, 'Debug', 'firmware')

    def test_wrong_effective_radio_cannot_get_a_manifest(self):
        directory = self.config.build_dir(self.profile, 'Debug') / 'arm-none-eabi'
        (directory / 'radio/src').mkdir(parents=True)
        (directory / 'CMakeCache.txt').write_text('PCB:STRING=X7\nPCBREV:STRING=SAOLALINK_V1\nCMAKE_BUILD_TYPE:STRING=Debug\nBOOTLOADER:BOOL=ON\nFIRMWARE_STRIP_BOOTLOADER:BOOL=OFF\n')
        (directory / 'radio/src/saolalinkv1.json.h').write_text('#define RADIO_X7 1\n')
        with self.assertRaisesRegex(ValueError, 'generated HAL'):
            self.builder.record_artifact(self.profile, 'Debug', 'firmware')

    def test_new_build_invalidates_previous_flash_manifest(self):
        binary = self.make_artifact()
        with patch.object(self.builder, 'preflight'), patch.object(self.builder.runner, 'start', return_value=True):
            self.builder.build(self.profile, 'Debug')
        self.assertFalse(binary.with_suffix('.manifest.json').exists())
        with self.assertRaises(ValueError):
            self.builder.artifact(self.profile, 'Debug', 'firmware')

    def test_flash_exact_device_address_and_no_automatic_build(self):
        self.make_artifact()
        device = DfuDevice('0483:df11', '1-2', 'ABC', '@Internal Flash')
        with patch.object(self.builder.runner, 'start', return_value=True) as start:
            self.builder.flash(self.profile, 'Debug', 'firmware', device)
            command = start.call_args.args[1][0]
            self.assertEqual(command[command.index('-p') + 1], '1-2')
            self.assertEqual(command[command.index('-s') + 1], '0x08000000:leave')
        with self.assertRaises(ValueError):
            self.builder.flash(self.profile, 'Debug', 'firmware', DfuDevice('0483:df11', '', '', ''))

    def test_dfu_same_vid_pid_distinct_paths_and_alt_filter(self):
        lines = '\n'.join(f'Found DFU: [0483:df11] path="{path}", alt={alt}, name="{name}", serial="{serial}"'
                         for path, alt, name, serial in [('1-2', 0, '@Internal Flash', 'A'), ('1-3', 0, '@Internal Flash', 'B'),
                         ('1-2', 1, '@Option Bytes', 'A')])
        self.assertEqual([d.path for d in parse_devices(lines)], ['1-2', '1-3'])
        self.assertEqual(parse_devices('Found Runtime: [0483:df11] path="1-2", alt=0, name="@Internal Flash"'), [])

    def test_edgetx_application_dfu_keeps_bootloader_out_of_upload(self):
        self.profile = PROFILES['saolalink-devebox']
        directory = self.config.build_dir(self.profile, 'Debug') / 'arm-none-eabi'
        directory.mkdir(parents=True)
        app = directory / 'application.bin'
        app.write_bytes(b'application-vector-data')
        info = dict(profile=self.profile.key, pcbrev=self.profile.pcbrev, mode='Debug',
                    kind='application', address='0x08008000', sha256=digest(app),
                    hse_hz=8000000, devebox_usb=True, bootloader_included=False)
        manifest = app.with_suffix('.manifest.json')
        manifest.write_text(json.dumps(info))
        line = 'Found DFU: [0483:df11] path="1-2", alt=0, name="@SaolaLink App /0x08008000/02*016Kg,01*064Kg,03*128Kg", serial="ABC"'
        device, = parse_devices(line)
        self.assertTrue(device.edgetx_bootloader)
        with patch.object(self.builder.runner, 'start', return_value=True) as start:
            self.builder.flash(self.profile, 'Debug', 'application', device)
            command = start.call_args.args[1][0]
            self.assertEqual(command[command.index('-s') + 1], '0x08008000')
            self.assertEqual(command[-1], str(app))
        with self.assertRaisesRegex(ValueError, 'Hold RTN'):
            self.builder.flash(self.profile, 'Debug', 'application',
                               DfuDevice('0483:df11', '1-2', 'ABC', '@Internal Flash'))
        info['address'] = '0x08000000'
        manifest.write_text(json.dumps(info))
        with self.assertRaises(ValueError):
            self.builder.artifact(self.profile, 'Debug', 'application')

    def test_software_dfu_rejects_full_image(self):
        self.make_artifact()
        with self.assertRaisesRegex(ValueError, 'protects the bootloader'):
            self.builder.flash(self.profile, 'Debug', 'firmware',
                DfuDevice('0483:df11', '1-2', 'ABC', '@SaolaLink App /0x08008000/'))

    def test_devebox_rebuild_invalidates_all_linked_artifacts(self):
        self.profile = PROFILES['saolalink-devebox']
        self.make_artifact()
        directory = self.config.build_dir(self.profile, 'Debug') / 'arm-none-eabi'
        for kind in ('application', 'bootloader'):
            (directory / f'{kind}.manifest.json').write_text('{}')
        with patch.object(self.builder, 'preflight'), patch.object(self.builder.runner, 'start', return_value=True):
            self.builder.build(self.profile, 'Debug')
        self.assertEqual(list(directory.glob('*.manifest.json')), [])

    def test_comparison_exposes_hardware_changes_separately_from_identity(self):
        baseline = json.loads((self.config.source / 'radio/src/boards/hw_defs/pocket.json').read_text())
        original_target = git(self.config.source, 'show', 'HEAD:radio/src/targets/taranis/CMakeLists.txt')
        hw = self.root / 'radio/src/boards/hw_defs'; hw.mkdir(parents=True)
        target = self.root / 'radio/src/targets/taranis/saolalink_v1'; target.mkdir(parents=True)
        custom = json.loads(json.dumps(baseline))
        custom['identity']['model'] = 'SaolaLink V1'
        custom['adc_inputs']['inputs'][0]['pin'] = 'LL_GPIO_PIN_9'
        (hw / 'pocket.json').write_text(json.dumps(baseline))
        (hw / 'saolalinkv1.json').write_text(json.dumps(custom))
        for name in ['target.cmake', 'hal_overrides.h']:
            (target / name).write_text((self.config.source / 'radio/src/targets/taranis/saolalink_v1' / name).read_text())
        with patch('core.comparison.git', side_effect=[json.dumps(baseline), original_target, '']):
            text = report(self.root)
        hardware = text.split('=== Hardware changes (identity excluded) ===')[1].split('=== Full board definition')[0]
        self.assertIn('LL_GPIO_PIN_9', hardware)
        self.assertNotIn('\"model\":', hardware)
        self.assertIn('=== Build settings (flavour rename normalized) ===', text)
        self.assertIn('+    set(HSE_VALUE ${SAOLALINK_HSE_HZ})', text)

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runner = OperationRunner(self.root / 'logs')

    def tearDown(self):
        self.runner.stop()
        self.temp.cleanup()

    def finish(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            event, value = self.runner.events.get(timeout=10)
            if event == 'finished':
                return value
        self.fail('Worker did not finish')

    def test_failure_prevents_next_command(self):
        marker = self.root / 'unexpected'
        self.runner.start('failure', [[sys.executable, '-c', 'raise SystemExit(7)'],
            [sys.executable, '-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).touch()', str(marker)]], self.root)
        self.assertFalse(self.finish())
        self.assertFalse(marker.exists())
        self.assertFalse(self.runner.running)

    def test_serialization_cancel_prevents_success_callback(self):
        callbacks = []
        self.runner.start('cancel', [[sys.executable, '-c', 'import time; time.sleep(30)']], self.root, lambda: callbacks.append(True))
        self.assertFalse(self.runner.start('second', [], self.root))
        self.runner.stop()
        self.assertFalse(self.finish())
        self.assertEqual(callbacks, [])
        self.assertFalse(self.runner.running)

if __name__ == '__main__':
    unittest.main()
