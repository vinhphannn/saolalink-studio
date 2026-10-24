"""Serial discovery and one worker per connection; no Tk calls or auto-connect."""
import codecs
from dataclasses import dataclass
import queue
import threading
import os

import serial
from serial.tools import list_ports


@dataclass(frozen=True)
class SerialPort:
    device: str
    description: str
    hwid: str
    serial_number: str | None

    @property
    def label(self):
        return f'{self.device} | {self.description}'

    @property
    def details(self):
        return f'{self.hwid} | Serial: {self.serial_number or "not reported"}'


def discover_ports():
    # Do not filter to STM32: USB-TTL bridges and native USB CDC are both useful.
    return [SerialPort(p.device, p.description or 'Serial port', p.hwid or '', p.serial_number)
            for p in sorted(list_ports.comports(), key=lambda p: p.device)]


class SerialMonitor:
    def __init__(self):
        self.events = queue.Queue()  # lifecycle events, never mixed with bulk data
        self.received = queue.Queue(maxsize=256)
        self._outgoing = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.state = 'disconnected'
        self.port = ''
        self.baud = 115200
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.dropped_chunks = 0

    def connect(self, port, baud=115200):
        if not port:
            raise ValueError('Select a serial port first')
        if baud not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
            raise ValueError('Unsupported baud rate')
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError('Disconnect the current serial session first')
            self._stop = threading.Event()
            self._outgoing = queue.Queue(maxsize=64)
            self.rx_bytes = self.tx_bytes = self.dropped_chunks = 0
            self.port, self.baud = port, baud
            self.state = 'connecting'
            self.events.put(('state', f'Connecting to {port} at {baud}...'))
            self._thread = threading.Thread(target=self._run, daemon=True, name='saolalink-serial')
            self._thread.start()

    def disconnect(self):
        self._stop.set()

    def close(self):
        self.disconnect()
        if self._thread:
            self._thread.join(timeout=0.5)

    def send(self, text):
        if self.state != 'connected':
            raise RuntimeError('Serial port is not connected')
        payload = text.encode('utf-8')
        if len(payload) > 4096:
            raise ValueError('Send at most 4096 bytes at a time')
        try:
            self._outgoing.put_nowait(payload)
        except queue.Full:
            raise RuntimeError('Serial transmit queue is full; wait and try again') from None

    def _receive(self, text):
        if not text:
            return
        try:
            self.received.put_nowait(text)
        except queue.Full:
            self.dropped_chunks += 1

    def _run(self):
        conn = None
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            # Configure before opening. Do not intentionally pulse modem lines.
            conn = serial.Serial(port=None, baudrate=self.baud, timeout=0.05,
                                 write_timeout=0.25, xonxoff=False, rtscts=False,
                                 dsrdtr=False)
            conn.dtr = False
            conn.rts = False
            conn.port = self.port
            # Prevent a second instance from opening the same port on POSIX.
            if os.name == 'posix' and hasattr(conn, 'exclusive'):
                conn.exclusive = True
            conn.open()
            if self._stop.is_set():
                return
            self.state = 'connected'
            self.events.put(('state', f'Connected: {self.port} | {self.baud} baud | 8N1'))
            while not self._stop.is_set():
                try:
                    payload = self._outgoing.get_nowait()
                except queue.Empty:
                    payload = None
                if payload is not None:
                    written = conn.write(payload)
                    if written != len(payload):
                        raise serial.SerialTimeoutException('Incomplete serial write')
                    self.tx_bytes += written
                    self.events.put(('sent', payload.decode('utf-8', errors='replace')))
                chunk = conn.read(min(max(conn.in_waiting, 1), 2048))
                if chunk:
                    self.rx_bytes += len(chunk)
                    self._receive(decoder.decode(chunk))
        except (serial.SerialException, OSError) as error:
            if not self._stop.is_set():
                self.events.put(('error', f'{self.port}: {error}. Check cable, permissions and other serial applications.'))
        finally:
            self._receive(decoder.decode(b'', final=True))
            if conn is not None:
                try:
                    conn.close()
                except (serial.SerialException, OSError):
                    pass
            self.state = 'disconnected'
            self.events.put(('state', f'Disconnected: {self.port}'))
