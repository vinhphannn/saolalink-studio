"""UI owns widgets; worker threads communicate through queues only."""
import queue
import threading
from pathlib import Path
from tkinter import PhotoImage
import customtkinter as ctk
from tkinter import messagebox

from core.config import AppConfig, PROFILES
from core.builder import FirmwareBuilder
from core.device_service import DeviceService
from core.comparison import report, compare_generated
from ui.workspaces import BuildTab, FlashTab, CompareTab
from ui.serial_tab import SerialTab

class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__(className='SaolaLinkStudio')
        self.app_icon = PhotoImage(file=str(Path(__file__).resolve().parents[1] / 'assets/saolalink-studio.png'))
        self.iconphoto(True, self.app_icon)
        self.config_data = AppConfig.default()
        self.builder = FirmwareBuilder(self.config_data)
        self.events = queue.Queue()
        self.dfu_devices = []
        self._checking = False
        self.title('SaolaLink Studio — RC Firmware Tools')
        self.geometry('1180x800'); self.minsize(1020, 700)
        self.protocol('WM_DELETE_WINDOW', self.close)
        header = ctk.CTkFrame(self)
        header.pack(fill='x', padx=18, pady=(18, 8))
        ctk.CTkLabel(header, text='SAOLALINK STUDIO', font=ctk.CTkFont(size=20, weight='bold')).pack(side='left', padx=14, pady=14)
        self.profile_picker = ctk.CTkOptionMenu(header, values=[p.name for p in PROFILES.values()], command=lambda _: self.update_artifact())
        self.profile_picker.pack(side='left', padx=10)
        self.profile_picker.set(PROFILES['saolalink-devebox'].name)
        self.mode_picker = ctk.CTkOptionMenu(header, values=['Debug', 'Release'], width=100, command=lambda _: self.update_artifact())
        self.mode_picker.pack(side='left')
        ctk.CTkButton(header, text='Stop task', width=100, fg_color='#943c3c', command=self.builder.runner.stop).pack(side='right', padx=12)
        ctk.CTkLabel(self, text=f'Source: {self.config_data.source}', anchor='w').pack(fill='x', padx=24)
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill='both', expand=True, padx=18, pady=8)
        for name in ['Build', 'Flash', 'Serial monitor', 'Compare Pocket']:
            self.tabs.add(name)
        self.build_tab = BuildTab(self.tabs.tab('Build'), self); self.build_tab.pack(fill='both', expand=True)
        self.flash_tab = FlashTab(self.tabs.tab('Flash'), self); self.flash_tab.pack(fill='both', expand=True)
        self.serial_tab = SerialTab(self.tabs.tab('Serial monitor')); self.serial_tab.pack(fill='both', expand=True)
        self.compare_tab = CompareTab(self.tabs.tab('Compare Pocket'), self); self.compare_tab.pack(fill='both', expand=True)
        self.status = ctk.CTkLabel(self, text='Ready', anchor='w'); self.status.pack(fill='x', padx=24)
        self.log = ctk.CTkTextbox(self, height=200, font=('monospace', 12)); self.log.pack(fill='x', padx=18, pady=(0, 18))
        self.log.insert('end', 'EdgeTX DevEBox: Build firmware first. Install bootloader once via ROM DFU; then upload application via EdgeTX USB DFU.\n')
        self.update_artifact()
        self.after(50, self.poll)

    @property
    def profile(self):
        return next(p for p in PROFILES.values() if p.name == self.profile_picker.get())

    def append(self, text):
        self.log.insert('end', text); self.log.see('end')

    def background(self, callback):
        if self.builder.runner.running or self._checking:
            self.append('[BUSY] Wait for the current operation.\n'); return
        self._checking = True
        self.status.configure(text='Working…')
        def run():
            try:
                callback()
            except Exception as error:
                self.events.put(('error', str(error)))
            finally:
                self.events.put(('checked', None))
        threading.Thread(target=run, daemon=True).start()

    def doctor(self):
        def check():
            self.builder.preflight()
            self.events.put(('log', '[OK] EdgeTX checkout, CMake and Arm GNU 14.2.1 are available.\n'))
        self.background(check)

    def operation(self, name, kind='firmware'):
        profile, mode = self.profile, self.mode_picker.get()
        self.background(lambda: self.builder.build(profile, mode, kind) if name == 'build' else getattr(self.builder, name)(profile, mode))

    def refresh_devices(self):
        self.background(lambda: self.events.put(('devices', DeviceService().discover())))

    def compare(self):
        mode = self.mode_picker.get()
        self.background(lambda: self.events.put(('comparison', report(self.config_data.source) + compare_generated(self.config_data.builds, mode))))

    def flash(self, kind):
        if self.builder.runner.running or self._checking:
            self.append('[BUSY] Wait for the current operation.\n'); return
        try:
            device = next((d for d in self.dfu_devices if d.label == self.flash_tab.devices.get()), None)
            if device is None:
                raise ValueError('Refresh and select the USB DFU device first')
            profile, mode = self.profile, self.mode_picker.get()
            binary, info = self.builder.artifact(profile, mode, kind)
            if kind == 'application' and not device.edgetx_bootloader:
                raise ValueError('Select EdgeTX @SaolaLink App DFU: BOOT0=0, hold RTN (PC5) at power-on or RESET (requires updated bootloader)')
            if kind != 'application' and device.edgetx_bootloader:
                raise ValueError('This is EdgeTX USB DFU. Use Flash application to preserve the bootloader.')
            if messagebox.askyesno('Flash selected device', f'{profile.name} • {mode} • {kind}\n{info["size"]} bytes at {info["address"]}\nUSB {device.path} / {device.serial}\n\n{binary}\n\nProgram this device?'):
                self.background(lambda: self.builder.flash(profile, mode, kind, device))
        except Exception as error:
            self.append(f'[ERROR] {error}\n')

    def update_artifact(self):
        try:
            path, info = self.builder.artifact(self.profile, self.mode_picker.get(), 'firmware')
            text = f'{path}\n{info["size"]} bytes • built {info["built_at"]}\nSHA256 {info["sha256"]}'
        except (ValueError, OSError) as error:
            text = str(error)
        self.build_tab.artifact.configure(text=text)

    def poll(self):
        self.serial_tab.poll()
        for events in [self.events, self.builder.runner.events]:
            try:
                while True:
                    kind, value = events.get_nowait()
                    if kind in ('log', 'error'):
                        self.append(('[ERROR] ' if kind == 'error' else '') + value + ('\n' if kind == 'error' else ''))
                    elif kind == 'started':
                        self.status.configure(text='Running • Log: ' + value)
                    elif kind == 'finished':
                        self.status.configure(text='Completed' if value else 'Failed / cancelled'); self.update_artifact()
                    elif kind == 'checked':
                        self._checking = False
                        if not self.builder.runner.running:
                            self.status.configure(text='Ready')
                    elif kind == 'devices':
                        self.dfu_devices = [d for d in value if d.vid_pid == self.profile.dfu_id]
                        labels = [d.label for d in self.dfu_devices] or ['No USB DFU device found']
                        self.flash_tab.devices.configure(values=labels); self.flash_tab.devices.set(labels[0])
                    elif kind == 'comparison':
                        self.compare_tab.set_report(value)
            except queue.Empty:
                pass
        self.profile_picker.configure(state='disabled' if self.builder.runner.running or self._checking else 'normal')
        self.mode_picker.configure(state='disabled' if self.builder.runner.running or self._checking else 'normal')
        self.after(50, self.poll)

    def close(self):
        if self.builder.runner.running:
            if not messagebox.askyesno('Stop operation', 'Stop the current operation and close Studio?'):
                return
            self.builder.runner.stop()
        self.serial_tab.close()
        self.destroy()
