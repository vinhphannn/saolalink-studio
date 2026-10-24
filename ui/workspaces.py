"""Build and USB flashing stay separate; advanced tools are disclosed on demand."""
import customtkinter as ctk
from tkinter import filedialog, messagebox

from ui.components import ActionCard, BUTTON_HEIGHT, Disclosure


class BuildTab(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.buttons = []
        self._busy = None
        ctk.CTkLabel(self, text='Build firmware', font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w', pady=(8, 4))
        ctk.CTkLabel(self, text='Choose the hardware above, then build. Configuration runs automatically before each build.',
                    anchor='w', justify='left', wraplength=880, text_color='gray65').pack(fill='x', pady=(0, 14))
        cards = ctk.CTkFrame(self, fg_color='transparent'); cards.pack(fill='x')
        cards.grid_columnconfigure((0, 1), weight=1, uniform='build')
        self.firmware = ActionCard(cards, 'Firmware',
            'Build the radio application. For DevEBox, this also prepares the application-only file for everyday USB updates.',
            'Build firmware', lambda: app.operation('build', 'firmware'))
        self.firmware.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        self.bootloader = ActionCard(cards, 'Bootloader',
            'Build the bootloader separately when installing a new board or updating the loader. Everyday firmware edits do not need this step.',
            'Build bootloader', lambda: app.operation('build', 'bootloader'))
        self.bootloader.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        clean = ctk.CTkFrame(self, fg_color='transparent'); clean.pack(fill='x', pady=14)
        self.clean_button = ctk.CTkButton(clean, text='Clean build files', width=180, height=BUTTON_HEIGHT,
            fg_color=('gray75', 'gray28'), hover_color=('gray65', 'gray35'), text_color=('gray10', 'gray95'), command=lambda: app.operation('clean'))
        self.clean_button.pack(side='left', padx=(0, 12))
        ctk.CTkLabel(clean, text='Clear this hardware / mode output when you need a fresh build.\nClean removes its previous binaries; build again before flashing.',
                    justify='left', anchor='w', wraplength=620, text_color='gray65').pack(side='left', fill='x', expand=True)
        self.buttons += [self.firmware.button, self.bootloader.button, self.clean_button]
        self.details = Disclosure(self, 'Build files & verification details'); self.details.pack(fill='x', pady=(0, 8))
        self.artifact = ctk.CTkLabel(self.details.content, text='No build selected.', justify='left', anchor='w', wraplength=880)
        self.artifact.pack(fill='x', padx=8)
        self.advanced = Disclosure(self, 'Build options & developer tools'); self.advanced.pack(fill='x', pady=(0, 8))
        options = ctk.CTkFrame(self.advanced.content, fg_color='transparent'); options.pack(fill='x', padx=8, pady=4)
        ctk.CTkLabel(options, text='Build mode').pack(side='left', padx=(0, 12))
        app.mode_picker = ctk.CTkOptionMenu(options, values=['Debug', 'Release'], height=36, command=lambda _: app.context_changed())
        app.mode_picker.set('Debug'); app.mode_picker.pack(side='left')
        ctk.CTkLabel(self.advanced.content, text='Debug keeps debug symbols; both modes use LTO. Each hardware / mode has its own output folder.',
                    wraplength=850, anchor='w', justify='left', text_color='gray65').pack(fill='x', padx=8, pady=6)
        tools = ctk.CTkFrame(self.advanced.content, fg_color='transparent'); tools.pack(fill='x', padx=8, pady=8)
        for text, callback in [('Configure only', lambda: app.operation('configure')),
                               ('Compare with Pocket…', app.open_comparison), ('Workflow guide…', app.open_workflow_guide)]:
            button = ctk.CTkButton(tools, text=text, height=36, command=callback)
            button.pack(side='left', padx=(0, 8))
            if text == 'Configure only':
                self.buttons.append(button)
        app.source_label = ctk.CTkLabel(self.advanced.content, text=f'EdgeTX source: {app.config_data.source}', anchor='w', justify='left', wraplength=850)
        app.source_label.pack(fill='x', padx=8, pady=6)

    def set_artifacts(self, artifacts):
        lines = []
        for kind, card in (('firmware', self.firmware), ('bootloader', self.bootloader)):
            path, info, error = artifacts[kind]
            card.note.configure(text=f'Ready • {info["size"]:,} bytes' if info else 'Build required • ' + error)
            if info:
                lines.append(f'{kind.title()}: {path}\n{info["size"]:,} bytes • built {info["built_at"]}\nSHA256 {info["sha256"]}')
            else:
                lines.append(f'{kind.title()}: {error}')
        self.artifact.configure(text='\n\n'.join(lines))

    def set_busy(self, busy):
        if self._busy != busy:
            self._busy = busy
            for button in self.buttons:
                button.configure(state='disabled' if busy else 'normal')


class FlashTab(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self._state = None
        ctk.CTkLabel(self, text='Flash over USB', font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w', pady=(8, 4))
        ctk.CTkLabel(self, text='Build first. Put the radio in the required USB mode, scan, then select the exact device.',
                    anchor='w', justify='left', wraplength=880, text_color='gray65').pack(fill='x', pady=(0, 12))
        selector = ctk.CTkFrame(self); selector.pack(fill='x', pady=(0, 12)); selector.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(selector, text='USB DFU device', anchor='w').grid(row=0, column=0, padx=12, pady=(8, 0), sticky='ew')
        self.devices = ctk.CTkOptionMenu(selector, values=['Scan to discover USB devices'], width=380, height=38, command=lambda _: self.refresh_state())
        self.devices.grid(row=1, column=0, padx=12, pady=(4, 8), sticky='ew')
        self.scan_button = ctk.CTkButton(selector, text='Scan USB devices', width=160, height=BUTTON_HEIGHT, command=app.refresh_devices)
        self.scan_button.grid(row=1, column=1, padx=(0, 12), pady=(4, 8))
        self.status = ctk.CTkLabel(selector, text='No device selected. Scan after entering USB DFU mode.', anchor='w', justify='left', wraplength=850, text_color='gray65')
        self.status.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 8), sticky='ew')
        cards = ctk.CTkFrame(self, fg_color='transparent'); cards.pack(fill='x')
        cards.grid_columnconfigure((0, 1), weight=1, uniform='flash')
        self.firmware = ActionCard(cards, 'Everyday firmware update',
            'DevEBox: BOOT0=0. Hold RTN (PC5) while powering on or resetting, then release. Scan and select the EdgeTX USB loader. This preserves the bootloader.',
            'Flash firmware via USB', lambda: app.flash('application'))
        self.firmware.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        self.bootloader = ActionCard(cards, 'Bootloader install / update',
            'Enter STM32 ROM DFU with BOOT0=1 and reset. Scan and select the ROM DFU device. After uploading, set BOOT0=0 and reset to leave ROM DFU.',
            'Flash bootloader via DFU', lambda: app.flash('bootloader'))
        self.bootloader.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        self.recovery = Disclosure(self, 'Recovery & USB details'); self.recovery.pack(fill='x', pady=12)
        ctk.CTkLabel(self.recovery.content, text='Full-image recovery replaces both bootloader and application through ROM DFU. '
            'Use the matching full firmware build. For V1 / Pocket profiles, this is the available firmware flashing path.\n'
            'DevEBox addresses: bootloader / full image 0x08000000; application-only 0x08008000. '
            'Older USB loaders may use PA0 instead of RTN; update the bootloader through ROM DFU to use RTN.',
            justify='left', anchor='w', wraplength=850, text_color='gray65').pack(fill='x', padx=8, pady=6)
        self.full_image = ctk.CTkButton(self.recovery.content, text='Flash full image via ROM DFU', height=40,
            fg_color='#875332', hover_color='#a56a40', command=lambda: app.flash('firmware'))
        self.full_image.pack(anchor='w', padx=8, pady=6)
        ctk.CTkButton(self.recovery.content, text='Detailed USB workflow…', height=36, command=app.open_workflow_guide).pack(anchor='w', padx=8, pady=6)

    def refresh_state(self, busy=None):
        if busy is None:
            busy = self.app.busy
        device = self.app.selected_device()
        supported = self.app.profile.key == 'saolalink-devebox'
        ready = {kind: bool(value[1]) for kind, value in self.app.artifacts.items()}
        state = (busy, device, supported, tuple(ready.items()))
        if state == self._state:
            return
        self._state = state
        self.scan_button.configure(state='disabled' if busy else 'normal')
        self.devices.configure(state='disabled' if busy else 'normal')
        self.status.configure(text=('EdgeTX application loader selected • use Firmware update.' if device and device.edgetx_bootloader else
            'STM32 ROM DFU selected • use Bootloader or full-image recovery.' if device else
            'No device selected. Enter the required USB mode, then Scan USB devices.'))
        for kind, button, note in (('application', self.firmware.button, self.firmware.note),
                                   ('bootloader', self.bootloader.button, self.bootloader.note),
                                   ('firmware', self.full_image, None)):
            reason = ''
            if kind == 'application' and not supported:
                reason = 'USB application updates are configured for DevEBox. Other profiles use full-image recovery below.'
            elif not ready.get(kind):
                reason = 'Build firmware first.' if kind in ('application', 'firmware') else 'Build bootloader first.'
            elif not device:
                reason = 'Scan and select a USB device.'
            elif (kind == 'application') != device.edgetx_bootloader:
                reason = 'Select the EdgeTX USB loader.' if kind == 'application' else 'Select STM32 ROM DFU (BOOT0=1 + reset).'
            button.configure(state='disabled' if busy or reason else 'normal')
            if note:
                note.configure(text=reason or 'Ready • verify device and confirm upload.')


class CompareTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        ctk.CTkLabel(self, text='Compare with Pocket', font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', pady=8)
        ctk.CTkLabel(self, text='Developer report: hardware, build settings and source differences.', text_color='gray65').pack(anchor='w')
        bar = ctk.CTkFrame(self, fg_color='transparent'); bar.pack(fill='x', pady=12)
        ctk.CTkButton(bar, text='Refresh comparison', height=40, command=app.compare).pack(side='left')
        ctk.CTkButton(bar, text='Export report', height=40, command=self.export).pack(side='left', padx=8)
        self.text = ctk.CTkTextbox(self, font=('monospace', 12)); self.text.pack(fill='both', expand=True)

    def set_report(self, text):
        self.text.delete('1.0', 'end'); self.text.insert('end', text)

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.diff', initialfile='saolalink-v1-vs-pocket.diff')
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as output:
                    output.write(self.text.get('1.0', 'end'))
            except OSError as error:
                messagebox.showerror('Export failed', str(error), parent=self)
