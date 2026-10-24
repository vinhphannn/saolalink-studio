"""UI orchestration; workers communicate through queues and never touch Tk widgets."""
import queue
import threading
from pathlib import Path
from tkinter import PhotoImage, messagebox
import customtkinter as ctk

from core.config import AppConfig, PROFILES, settings_path
from core.builder import FirmwareBuilder
from core.device_service import DeviceService
from core.comparison import report, compare_generated
from ui.components import Disclosure
from ui.workspaces import BuildTab, FlashTab, CompareTab
from ui.serial_tab import SerialTab
from ui.setup_tab import SetupTab

PROFILE_LABELS = {
    'saolalink-devebox': 'DevEBox • 8 MHz',
    'saolalink-v1': 'SaolaLink V1 • 12 MHz',
    'pocket': 'Pocket • reference hardware',
}


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__(className='SaolaLinkStudio')
        self.app_icon = PhotoImage(file=str(Path(__file__).resolve().parents[1] / 'assets/saolalink-studio.png'))
        self.iconphoto(True, self.app_icon)
        setup_error = ''
        try:
            self.config_data = AppConfig.default()
        except ValueError as error:
            setup_error = str(error)
            self.config_data = AppConfig.detected()
        self.builder = FirmwareBuilder(self.config_data)
        self.events = queue.Queue()
        self.dfu_devices = []
        self.artifacts = {}
        self._checking = False
        self._task_failed = False
        self._controls_busy = None
        self._task_label = 'Ready'
        self._profile_key = 'saolalink-devebox'
        self.comparison_window = None
        self.compare_tab = None
        self.comparison_report = ''
        self.title('SaolaLink Studio — RC Firmware Tools')
        self.geometry('1180x820'); self.minsize(1020, 700)
        self.protocol('WM_DELETE_WINDOW', self.close)

        self.header = ctk.CTkFrame(self)
        self.header.pack(fill='x', padx=18, pady=(16, 8))
        ctk.CTkLabel(self.header, text='SAOLALINK STUDIO', font=ctk.CTkFont(size=21, weight='bold')).pack(side='left', padx=16, pady=14)
        ctk.CTkLabel(self.header, text='Build  /  USB flash  /  Serial', text_color='gray65').pack(side='left', padx=8)
        self.stop_button = ctk.CTkButton(self.header, text='Stop current task', width=160, height=40,
            fg_color='#943c3c', hover_color='#ad4848', command=lambda: self.builder.runner.stop())

        self.hardware_bar = ctk.CTkFrame(self, fg_color='transparent')
        self.hardware_bar.pack(fill='x', padx=24, pady=(0, 4))
        ctk.CTkLabel(self.hardware_bar, text='Hardware profile', font=ctk.CTkFont(weight='bold')).pack(side='left', padx=(0, 12))
        self.profile_picker = ctk.CTkOptionMenu(self.hardware_bar, values=list(PROFILE_LABELS.values()), width=265,
            height=38, command=lambda _: self.context_changed())
        self.profile_picker.set(PROFILE_LABELS[self._profile_key]); self.profile_picker.pack(side='left')
        self.context_label = ctk.CTkLabel(self.hardware_bar, text='', anchor='w', text_color='gray65')
        self.context_label.pack(side='left', padx=16)

        self.tabs = ctk.CTkTabview(self, anchor='w', segmented_button_font=ctk.CTkFont(size=15, weight='bold'), command=self.tab_changed)
        self.tabs.pack(fill='both', expand=True, padx=18, pady=6)
        for name in ('Build', 'Flash USB', 'Serial monitor', 'Setup'):
            self.tabs.add(name)
        self.build_tab = BuildTab(self.tabs.tab('Build'), self); self.build_tab.pack(fill='both', expand=True)
        self.flash_tab = FlashTab(self.tabs.tab('Flash USB'), self); self.flash_tab.pack(fill='both', expand=True)
        self.serial_tab = SerialTab(self.tabs.tab('Serial monitor'), self.config_data); self.serial_tab.pack(fill='both', expand=True)
        self.setup_tab = SetupTab(self.tabs.tab('Setup'), self); self.setup_tab.pack(fill='both', expand=True)

        footer = ctk.CTkFrame(self, fg_color='transparent'); footer.pack(fill='x', padx=24, pady=4)
        self.status = ctk.CTkLabel(footer, text='Ready', anchor='w'); self.status.pack(side='left', fill='x', expand=True)
        self.progress = ctk.CTkProgressBar(footer, mode='indeterminate', width=160)
        self.log_section = Disclosure(self, 'Operation log')
        self.log_section.pack(fill='x', padx=18, pady=(0, 14))
        self.log = ctk.CTkTextbox(self.log_section.content, height=150, font=('monospace', 12), state='disabled')
        self.log.pack(fill='x')
        self.context_changed()
        if setup_error or not settings_path().is_file() or not (self.config_data.source / 'CMakeLists.txt').is_file():
            self.open_setup()
            self.setup_tab.notice.configure(text=setup_error or 'First run or moved checkout: choose project folders, find / install tools, then Check setup and Save & apply.')
            if setup_error:
                self.append('[SETUP] ' + setup_error + '\n')
        self.sync_controls()
        self.after(50, self.poll)

    @property
    def profile(self):
        return PROFILES[next(key for key, label in PROFILE_LABELS.items() if label == self.profile_picker.get())]

    @property
    def busy(self):
        return self.builder.runner.running or self._checking

    def selected_device(self):
        return next((device for device in self.dfu_devices if device.label == self.flash_tab.devices.get()), None)

    def reset_devices(self):
        self.dfu_devices = []
        self.flash_tab.devices.configure(values=['Scan to discover USB devices'])
        self.flash_tab.devices.set('Scan to discover USB devices')

    def context_changed(self):
        if self.profile.key != self._profile_key:
            self._profile_key = self.profile.key
            self.reset_devices()
        self.context_label.configure(text=f'{self.mode_picker.get()} • separate output for each hardware / mode')
        self.update_artifact()

    def append(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text); self.log.see('end')
        self.log.configure(state='disabled')

    def show_error(self, text):
        self._task_failed = True
        self.append('[ERROR] ' + text + '\n')
        self.status.configure(text='Needs attention • review the message in Setup or the operation log.')
        if text.startswith('Build setup needs attention:'):
            self.open_setup()
            self.setup_tab.notice.configure(text='Build setup needs attention. Click Install missing… to review available repairs.')
        if self.tabs.get() == 'Setup':
            self.setup_tab.install_log('[ERROR] ' + text + '\n')
        else:
            self.log_section.set_expanded(True)

    def background(self, callback, label='Working…'):
        if self.busy:
            self.status.configure(text='Wait for the current task to finish.'); return False
        self._checking = True
        self._task_failed = False
        self._task_label = label
        self.status.configure(text=label)
        self.sync_controls()
        def run():
            try:
                callback()
            except Exception as error:
                self.events.put(('error', str(error)))
            finally:
                self.events.put(('checked', None))
        threading.Thread(target=run, daemon=True).start()
        return True

    def open_setup(self):
        self.tabs.set('Setup'); self.tab_changed()

    def tab_changed(self):
        if not hasattr(self, 'log_section'):
            return
        work_tab = self.tabs.get() in ('Build', 'Flash USB')
        if work_tab:
            if not self.hardware_bar.winfo_manager():
                self.hardware_bar.pack(fill='x', padx=24, pady=(0, 4), before=self.tabs)
            if not self.log_section.winfo_manager():
                self.log_section.pack(fill='x', padx=18, pady=(0, 14))
            self.update_artifact()
        else:
            self.hardware_bar.pack_forget()
            self.log_section.pack_forget()

    def open_comparison(self):
        if self.comparison_window and self.comparison_window.winfo_exists():
            self.comparison_window.lift(); return
        self.comparison_window = ctk.CTkToplevel(self)
        self.comparison_window.title('Developer tools — Compare with Pocket'); self.comparison_window.geometry('960x650')
        self.compare_tab = CompareTab(self.comparison_window, self); self.compare_tab.pack(fill='both', expand=True, padx=16, pady=12)
        self.compare_tab.set_report(self.comparison_report or 'Click Refresh comparison to generate a report from the configured EdgeTX checkout.')

    def open_workflow_guide(self):
        window = ctk.CTkToplevel(self)
        window.title('Build and USB workflow'); window.geometry('820x650')
        text = ctk.CTkTextbox(window, wrap='word', font=ctk.CTkFont(size=14)); text.pack(fill='both', expand=True, padx=16, pady=16)
        text.insert('end', (Path(__file__).resolve().parents[1] / 'docs/WORKFLOW.md').read_text(encoding='utf-8'))
        text.configure(state='disabled')

    def apply_setup(self, config):
        if self.busy:
            raise ValueError('Wait for the current task before applying Setup changes.')
        if self.serial_tab.monitor.state != 'disconnected':
            raise ValueError('Disconnect the serial monitor before applying Setup changes.')
        config.save()
        self.config_data = config
        self.builder = FirmwareBuilder(config)
        self.serial_tab.apply_config(config)
        self.reset_devices()
        self.source_label.configure(text=f'EdgeTX source: {config.source}')
        self.update_artifact()
        self.append('[SETUP] Saved machine settings to ' + str(settings_path()) + '\n')

    def operation(self, name, kind='firmware'):
        profile, mode = self.profile, self.mode_picker.get()
        label = {'build': 'Building ' + kind, 'configure': 'Configuring build', 'clean': 'Cleaning build files'}[name]
        self.background(lambda: self.builder.build(profile, mode, kind) if name == 'build' else getattr(self.builder, name)(profile, mode),
                        f'{label} • {PROFILE_LABELS[profile.key]} • {mode}')

    def refresh_devices(self):
        self.background(lambda: self.events.put(('devices', DeviceService(self.config_data).discover())), 'Scanning USB DFU devices…')

    def compare(self):
        mode = self.mode_picker.get()
        self.background(lambda: self.events.put(('comparison', report(self.config_data.source,
            self.config_data.tool('git'), self.config_data.environment(build=False)) + compare_generated(self.config_data.builds, mode))), 'Comparing with Pocket…')

    def flash(self, kind):
        if self.busy:
            self.status.configure(text='Wait for the current task to finish.'); return
        try:
            device = self.selected_device()
            if device is None:
                raise ValueError('Scan and select the exact USB DFU device first.')
            profile, mode = self.profile, self.mode_picker.get()
            binary, info = self.builder.artifact(profile, mode, kind)
            if kind == 'application' and not device.edgetx_bootloader:
                raise ValueError('Select the EdgeTX USB loader: BOOT0=0, hold RTN (PC5) at power-on or RESET, then release.')
            if kind != 'application' and device.edgetx_bootloader:
                raise ValueError('Select STM32 ROM DFU for bootloader / full-image uploads. The EdgeTX USB loader accepts application updates only.')
            labels = {'application': 'Firmware update (preserves bootloader)', 'bootloader': 'Bootloader install / update',
                      'firmware': 'Full-image recovery (replaces bootloader and application)'}
            if messagebox.askyesno('Confirm USB upload', f'{labels[kind]}\n{profile.name} • {mode}\n'
                f'USB {device.path} / {device.serial}\n{info["size"]:,} bytes at {info["address"]}\n\n{binary}\n\nProgram this device?', parent=self):
                self.background(lambda: self.builder.flash(profile, mode, kind, device), 'Uploading ' + labels[kind].lower() + '…')
        except Exception as error:
            self.show_error(str(error))

    def update_artifact(self):
        artifacts = {}
        for kind in ('firmware', 'bootloader', 'application'):
            try:
                path, info = self.builder.artifact(self.profile, self.mode_picker.get(), kind)
                artifacts[kind] = (path, info, '')
            except (ValueError, OSError) as error:
                artifacts[kind] = (None, None, str(error))
        self.artifacts = artifacts
        self.build_tab.set_artifacts(artifacts)
        self.flash_tab.refresh_state()

    def sync_controls(self):
        busy = self.busy
        if busy != self._controls_busy:
            self._controls_busy = busy
            state = 'disabled' if busy else 'normal'
            self.profile_picker.configure(state=state); self.mode_picker.configure(state=state)
            self.build_tab.set_busy(busy); self.setup_tab.set_busy(busy)
            if busy:
                self.progress.pack(side='right', padx=8); self.progress.start()
            else:
                self.progress.stop(); self.progress.pack_forget()
        if self.builder.runner.running and not self.stop_button.winfo_manager():
            self.stop_button.pack(side='right', padx=16, pady=10)
        elif not self.builder.runner.running and self.stop_button.winfo_manager():
            self.stop_button.pack_forget()
        self.flash_tab.refresh_state(busy)

    def poll(self):
        self.serial_tab.poll()
        for events in (self.events, self.builder.runner.events):
            try:
                while True:
                    kind, value = events.get_nowait()
                    if kind == 'log':
                        self.append(value)
                        if '[ERROR]' in value:
                            self._task_failed = True
                            self.log_section.set_expanded(True)
                    elif kind == 'error':
                        self.show_error(value)
                    elif kind == 'started':
                        self.status.configure(text=self._task_label)
                        self.append('Log file: ' + value + '\n')
                    elif kind == 'finished':
                        self.status.configure(text='Completed' if value else 'Failed / cancelled • open Operation log')
                        if not value:
                            self.log_section.set_expanded(True)
                        self.update_artifact()
                    elif kind == 'checked':
                        self._checking = False
                        if not self.builder.runner.running and not self._task_failed:
                            self.status.configure(text='Ready')
                    elif kind == 'devices':
                        old = self.selected_device()
                        self.dfu_devices = [device for device in value if device.vid_pid == self.profile.dfu_id]
                        labels = [device.label for device in self.dfu_devices] or ['No USB DFU device found']
                        self.flash_tab.devices.configure(values=labels)
                        selected = next((device.label for device in self.dfu_devices if old and device.path == old.path), labels[0])
                        self.flash_tab.devices.set(selected)
                    elif kind == 'comparison':
                        self.comparison_report = value
                        if self.comparison_window and self.comparison_window.winfo_exists():
                            self.compare_tab.set_report(value)
                    elif kind == 'setup_checks':
                        self.setup_tab.show_checks(value); self.append('\n'.join(map(str, value)) + '\n')
                    elif kind == 'setup_detected':
                        self.setup_tab.show_detected(value)
                    elif kind == 'setup_repair_plan':
                        self.setup_tab.show_repair_plan(value)
                    elif kind == 'setup_install_log':
                        self.setup_tab.install_log(value); self.append(value)
                    elif kind == 'setup_repair_result':
                        self.setup_tab.show_repair_result(value)
            except queue.Empty:
                pass
        self.sync_controls()
        self.after(50, self.poll)

    def close(self):
        if self._checking:
            self.status.configure(text='Wait for checks / installation to finish before closing.'); return
        if self.builder.runner.running:
            if not messagebox.askyesno('Stop operation', 'Stop the current operation and close Studio?', parent=self):
                return
            self.builder.runner.stop()
        self.serial_tab.close()
        self.destroy()
