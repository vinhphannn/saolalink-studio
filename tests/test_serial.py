"""Exercise actual pyserial IO with a POSIX pseudo-terminal, no hardware needed."""
import os
from pathlib import Path
import pty
import queue
import select
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.serial_service import SerialMonitor, discover_ports


def eventually(predicate, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Timed out waiting for serial worker')


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.path = os.ttyname(self.slave)
        self.monitor = SerialMonitor()

    def tearDown(self):
        self.monitor.close()
        if self.master is not None:
            os.close(self.master)
        os.close(self.slave)

    def received(self, wanted):
        parts = []
        def check():
            while True:
                try:
                    parts.append(self.monitor.received.get_nowait())
                except queue.Empty:
                    break
            return wanted in ''.join(parts)
        eventually(check)
        return ''.join(parts)

    def test_real_receive_send_and_split_utf8(self):
        self.monitor.connect(self.path)
        eventually(lambda: self.monitor.state == 'connected')
        os.write(self.master, b'ALIVE 1s\r\n')
        self.assertIn('ALIVE 1s', self.received('ALIVE 1s'))
        text = 'Kết nối'.encode()
        os.write(self.master, text[:2]); time.sleep(0.08)
        os.write(self.master, text[2:])
        self.assertIn('Kết nối', self.received('Kết nối'))
        self.monitor.send('i')
        self.assertTrue(select.select([self.master], [], [], 2)[0])
        self.assertEqual(os.read(self.master, 20), b'i')
        eventually(lambda: self.monitor.tx_bytes == 1)
        self.monitor.disconnect()
        eventually(lambda: self.monitor.state == 'disconnected')
        self.assertFalse(self.monitor._thread.is_alive())

    def test_unplug_reports_error_and_allows_reconnect(self):
        self.monitor.connect(self.path)
        eventually(lambda: self.monitor.state == 'connected')
        os.close(self.master); self.master = None
        eventually(lambda: self.monitor.state == 'disconnected')
        events = []
        while not self.monitor.events.empty():
            events.append(self.monitor.events.get_nowait())
        self.assertTrue(any(kind == 'error' for kind, _ in events))
        self.monitor._thread.join(1)
        # A second open attempt must run, then report a missing device cleanly.
        self.monitor.connect('/dev/saolalink-does-not-exist')
        eventually(lambda: self.monitor.state == 'disconnected')

    def test_invalid_send_and_receive_backpressure(self):
        with self.assertRaises(RuntimeError):
            self.monitor.send('i')
        for _ in range(300):
            self.monitor._receive('data')
        self.assertEqual(self.monitor.received.qsize(), 256)
        self.assertEqual(self.monitor.dropped_chunks, 44)
        with self.assertRaises(ValueError):
            self.monitor.connect('', 115200)

    def test_discovery_includes_usb_bridges_and_native_cdc(self):
        ports = [SimpleNamespace(device='/dev/ttyUSB0', description='CP2102 USB-UART',
                                 hwid='USB VID:PID=10C4:EA60', serial_number='ABC'),
                 SimpleNamespace(device='/dev/ttyACM0', description='STM32 VCP',
                                 hwid='USB VID:PID=0483:5740', serial_number='DEF')]
        with patch('core.serial_service.list_ports.comports', return_value=ports):
            found = discover_ports()
        self.assertEqual(len(found), 2)
        self.assertIn('CP2102', found[1].label)
        self.assertIn('10C4:EA60', found[1].details)


if __name__ == '__main__':
    unittest.main()
