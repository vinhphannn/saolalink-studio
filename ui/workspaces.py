"""Independent workspaces, using only callbacks into the core services."""
import customtkinter as ctk
from tkinter import filedialog, messagebox

class BuildTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        ctk.CTkLabel(self, text='Build firmware', font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w', pady=12)
        ctk.CTkLabel(self, text='Separate board / Debug / Release outputs. LTO enabled; Debug retains symbols.', text_color='gray65').pack(anchor='w')
        bar = ctk.CTkFrame(self)
        bar.pack(fill='x', pady=16)
        for label, callback in [('Check tools', app.doctor), ('Configure', lambda: app.operation('configure')),
            ('Build firmware', lambda: app.operation('build', 'firmware')), ('Build bootloader', lambda: app.operation('build', 'bootloader')),
            ('Clean', lambda: app.operation('clean'))]:
            ctk.CTkButton(bar, text=label, width=110, command=callback).pack(side='left', padx=5, pady=12)
        self.artifact = ctk.CTkLabel(self, text='No verified artifact selected.', justify='left', anchor='w', wraplength=820)
        self.artifact.pack(fill='x', pady=8)

class FlashTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        ctk.CTkLabel(self, text='Flash over USB DFU', font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w', pady=12)
        ctk.CTkLabel(self, text='Install/update bootloader once with BOOT0=1 (ROM DFU) to enable RTN entry.\nThen BOOT0=0, hold RTN (PC5) at power-on or RESET; upload application only. Older loaders use PA0.', justify='left', text_color='gray65').pack(anchor='w')
        bar = ctk.CTkFrame(self)
        bar.pack(fill='x', pady=16)
        self.devices = ctk.CTkOptionMenu(bar, values=['Refresh to discover devices'], width=660)
        self.devices.pack(side='left', padx=10, pady=12)
        ctk.CTkButton(bar, text='Refresh', width=100, command=app.refresh_devices).pack(side='right', padx=10)
        self.status = ctk.CTkLabel(self, text='ROM install: 0x08000000 • EdgeTX application: 0x08008000 • Alt 0', text_color='gray65')
        self.status.pack(anchor='w')
        actions = ctk.CTkFrame(self, fg_color='transparent')
        actions.pack(fill='x', pady=16)
        ctk.CTkButton(actions, text='Flash full image (ROM)', command=lambda: app.flash('firmware')).pack(side='left', padx=(0, 8))
        ctk.CTkButton(actions, text='Flash bootloader', command=lambda: app.flash('bootloader')).pack(side='left')
        ctk.CTkButton(actions, text='Flash application (EdgeTX USB)', width=240, command=lambda: app.flash('application')).pack(side='left', padx=8)
        ctk.CTkLabel(self, text='Only artifacts with a matching target manifest and SHA256 can be flashed.', text_color='gray65').pack(anchor='w')

class CompareTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        ctk.CTkLabel(self, text='Compare with Pocket', font=ctk.CTkFont(size=26, weight='bold')).pack(anchor='w', pady=12)
        ctk.CTkLabel(self, text='Pinned baseline • Hardware changes • Build settings • HAL overrides • Integration diff', text_color='gray65').pack(anchor='w')
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.pack(fill='x', pady=12)
        ctk.CTkButton(bar, text='Refresh comparison', command=app.compare).pack(side='left')
        ctk.CTkButton(bar, text='Export report', command=self.export).pack(side='left', padx=8)
        self.text = ctk.CTkTextbox(self, font=('monospace', 12))
        self.text.pack(fill='both', expand=True)

    def set_report(self, text):
        self.text.delete('1.0', 'end'); self.text.insert('end', text)

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.diff', initialfile='saolalink-v1-vs-pocket.diff')
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as output:
                    output.write(self.text.get('1.0', 'end'))
            except OSError as error:
                messagebox.showerror('Export failed', str(error))
