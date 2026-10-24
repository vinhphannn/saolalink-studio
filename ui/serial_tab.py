"""Serial terminal widgets. All widget updates run on the Tk thread."""
import queue
import threading
from tkinter import filedialog
import customtkinter as ctk

from core.serial_service import SerialMonitor, discover_ports


class SerialTab(ctk.CTkFrame):
    def __init__(self, master, config=None):
        super().__init__(master, fg_color='transparent')
        self.preferred_port = config.serial_port if config else ''
        self.monitor = SerialMonitor()
        self.scan_events = queue.Queue()
        self.ports = []
        self.scanning = False
        self._last_state = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        ctk.CTkLabel(self, text='Serial monitor', font=ctk.CTkFont(size=26, weight='bold')).grid(row=0, column=0, sticky='w', pady=(8, 4))
        ctk.CTkLabel(self, text='Scan ports → select COM / tty and baud → Connect. For EdgeTX CLI, send help or devboard with LF.\nUSB firmware uploads use Flash USB, separately from this terminal.',
                    justify='left', text_color='gray65').grid(row=1, column=0, sticky='w')
        controls = ctk.CTkFrame(self)
        controls.grid(row=2, column=0, sticky='ew', pady=8)
        controls.grid_columnconfigure(0, weight=1)
        self.port_picker = ctk.CTkComboBox(controls, values=['Scan for serial ports'], height=38, state='readonly', command=self.show_port)
        self.port_picker.grid(row=0, column=0, sticky='ew', padx=8, pady=8)
        self.baud = ctk.CTkComboBox(controls, width=110, height=38, state='readonly', values=['9600', '19200', '38400', '57600', '115200', '230400', '460800', '921600'])
        self.baud.set(str(config.serial_baud if config else 115200)); self.baud.grid(row=0, column=1, padx=4)
        self.scan_button = ctk.CTkButton(controls, text='Scan ports', width=115, height=40, command=self.scan)
        self.scan_button.grid(row=0, column=2, padx=4)
        self.connect_button = ctk.CTkButton(controls, text='Connect', width=125, height=40, command=self.toggle)
        self.connect_button.grid(row=0, column=3, padx=8)
        self.port_info = ctk.CTkLabel(controls, text='No port selected', anchor='w', text_color='gray65', wraplength=900)
        self.port_info.grid(row=1, column=0, columnspan=4, sticky='ew', padx=8)
        self.connection = ctk.CTkLabel(self, text='Disconnected', anchor='w')
        self.connection.grid(row=3, column=0, sticky='ew')
        self.terminal = ctk.CTkTextbox(self, font=('monospace', 12), state='disabled')
        self.terminal.grid(row=4, column=0, sticky='nsew', pady=4)
        send = ctk.CTkFrame(self, fg_color='transparent')
        send.grid(row=5, column=0, sticky='ew', pady=4)
        send.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(send, height=38, placeholder_text='EdgeTX CLI command: help, devboard')
        self.entry.grid(row=0, column=0, sticky='ew', padx=(0, 6))
        self.entry.bind('<Return>', lambda _: self.send())
        self.ending = ctk.CTkOptionMenu(send, values=['None', 'LF', 'CRLF'], width=85)
        self.ending.set('LF'); self.ending.grid(row=0, column=1, padx=4)
        self.send_button = ctk.CTkButton(send, text='Send', width=85, height=38, command=self.send)
        self.send_button.grid(row=0, column=2, padx=4)
        ctk.CTkButton(send, text='Clear', width=75, height=38, command=self.clear).grid(row=0, column=3, padx=4)
        ctk.CTkButton(send, text='Save log', width=85, height=38, command=self.save).grid(row=0, column=4)
        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.grid(row=6, column=0, sticky='ew')
        self.autoscroll = ctk.CTkCheckBox(footer, text='Auto-scroll', width=115)
        self.autoscroll.select(); self.autoscroll.pack(side='left')
        self.stats = ctk.CTkLabel(footer, text='RX 0 B | TX 0 B', text_color='gray65')
        self.stats.pack(side='right')
        self.write('[INFO] EdgeTX DevEBox USB CDC: select its COM/ttyACM port, connect, send help or devboard with LF ending.\n'
                   '[INFO] Updated bootloader: hold RTN (PC5) at power-on/RESET for USB DFU; BOOT0 remains LOW.\n')
        self.poll()
        self.scan()

    def apply_config(self, config):
        self.preferred_port = config.serial_port
        self.baud.set(str(config.serial_baud))
        self.scan()

    def write(self, text):
        self.terminal.configure(state='normal')
        self.terminal.insert('end', text)
        # Bound both long lines and ordinary logs to keep a long session responsive.
        if len(self.terminal.get('1.0', 'end-1c')) > 200000:
            self.terminal.delete('1.0', 'end-150000c')
        if self.autoscroll.get():
            self.terminal.see('end')
        self.terminal.configure(state='disabled')

    def clear(self):
        self.terminal.configure(state='normal'); self.terminal.delete('1.0', 'end'); self.terminal.configure(state='disabled')

    def save(self):
        path = filedialog.asksaveasfilename(defaultextension='.log', initialfile='saolalink-serial.log')
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as out:
                    out.write(self.terminal.get('1.0', 'end-1c'))
            except OSError as error:
                self.write(f'\n[ERROR] {error}\n')

    def show_port(self, _=None):
        port = next((p for p in self.ports if p.label == self.port_picker.get()), None)
        self.port_info.configure(text=port.details if port else 'No port selected')

    def scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_button.configure(state='disabled')
        def work():
            try:
                self.scan_events.put(('ports', discover_ports()))
            except Exception as error:
                self.scan_events.put(('error', str(error)))
        threading.Thread(target=work, daemon=True).start()

    def toggle(self):
        if self.monitor.state != 'disconnected':
            self.monitor.disconnect()
            return
        port = next((p for p in self.ports if p.label == self.port_picker.get()), None)
        try:
            if port is None:
                raise ValueError('Scan and select a serial port first')
            self.monitor.connect(port.device, int(self.baud.get()))
        except (ValueError, RuntimeError) as error:
            self.write(f'\n[ERROR] {error}\n')

    def send(self):
        text = self.entry.get()
        if not text:
            return
        try:
            self.monitor.send(text + {'None': '', 'LF': '\n', 'CRLF': '\r\n'}[self.ending.get()])
            self.entry.delete(0, 'end')
        except (ValueError, RuntimeError) as error:
            self.write(f'\n[ERROR] {error}\n')

    def poll(self):
        for _ in range(30):
            try:
                kind, value = self.monitor.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'state':
                self.connection.configure(text=value)
                self.write(f'\n[{value}]\n')
            elif kind == 'error':
                self.write(f'\n[ERROR] {value}\n')
            elif kind == 'sent':
                self.write(f'\n[TX] {value!r}\n')
        chunks = []
        for _ in range(64):
            try:
                chunks.append(self.monitor.received.get_nowait())
            except queue.Empty:
                break
        if chunks:
            self.write(''.join(chunks))
        try:
            kind, value = self.scan_events.get_nowait()
            self.scanning = False
            self.scan_button.configure(state='normal')
            if kind == 'ports':
                old_device = self.preferred_port or next((p.device for p in self.ports if p.label == self.port_picker.get()), None)
                self.ports = value
                labels = [p.label for p in value] or ['No serial ports found']
                self.port_picker.configure(values=labels)
                selected = next((p.label for p in value if p.device == old_device), labels[0])
                self.port_picker.set(selected)
                self.show_port()
            else:
                self.write(f'\n[SCAN ERROR] {value}\n')
        except queue.Empty:
            pass
        state = self.monitor.state
        if state != self._last_state:
            self._last_state = state
            busy = state != 'disconnected'
            self.port_picker.configure(state='disabled' if busy else 'readonly')
            self.baud.configure(state='disabled' if busy else 'readonly')
            self.connect_button.configure(text='Disconnect' if busy else 'Connect')
            self.send_button.configure(state='normal' if state == 'connected' else 'disabled')
        self.stats.configure(text=f'RX {self.monitor.rx_bytes} B | TX {self.monitor.tx_bytes} B | Dropped {self.monitor.dropped_chunks} chunks')

    def close(self):
        self.monitor.close()
