"""Editable per-machine setup; validation runs off the Tk thread."""
from pathlib import Path
from tkinter import filedialog, messagebox
import os
import customtkinter as ctk

from core.config import AppConfig, settings_path
from core.diagnostics import diagnose
from core.setup_repair import make_plan, install

FIELDS = (
    ('source', 'EdgeTX checkout', 'directory'),
    ('builds', 'Build output folder', 'directory'),
    ('toolchain', 'Arm GNU 14.2.rel1 (root or bin)', 'directory'),
    ('cmake', 'CMake executable', 'file'),
    ('git', 'Git executable', 'file'),
    ('build_tool', 'Ninja / Make executable', 'file'),
    ('build_python', 'Build Python executable', 'file'),
    ('dfu_util', 'dfu-util executable', 'file'),
    ('llvm', 'LLVM bin / libclang folder (optional)', 'directory'),
    ('native_cc', 'Host C compiler (optional)', 'file'),
    ('native_cxx', 'Host C++ compiler (optional)', 'file'),
    ('library_prefix', 'CMake library prefixes (optional; separated by ;)', 'prefix'),
    ('dependency_cache', 'Dependency download cache (optional)', 'directory'),
    ('vsdevcmd', 'Windows VsDevCmd.bat (optional)', 'file'),
    ('serial_port', 'Preferred COM / tty port (optional)', None),
)


class SetupTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.entries = {}
        self.buttons = []
        self._busy = None
        self.repair_window = None
        ctk.CTkLabel(self, text='Machine setup', font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', pady=(8, 0))
        self.notice = ctk.CTkLabel(self, text='Select paths for this computer. Save & apply, then check setup.', anchor='w')
        self.notice.pack(fill='x')
        ctk.CTkLabel(self, text=f'User settings: {settings_path()}', anchor='w', text_color='gray65').pack(fill='x')
        overrides = [name for name in ('EDGETX_DIR', 'SAOLALINK_BUILD_DIR', 'ARM_TOOLCHAIN_DIR') if os.environ.get(name)]
        if overrides:
            ctk.CTkLabel(self, text='Environment overrides on next launch: ' + ', '.join(overrides), text_color='#efbd63').pack(anchor='w')
        form = ctk.CTkScrollableFrame(self, height=230)
        form.pack(fill='both', expand=True, pady=6)
        form.grid_columnconfigure(1, weight=1)
        for row, (name, label, kind) in enumerate(FIELDS):
            ctk.CTkLabel(form, text=label, anchor='w').grid(row=row, column=0, padx=8, pady=4, sticky='w')
            entry = ctk.CTkEntry(form)
            entry.grid(row=row, column=1, padx=4, pady=4, sticky='ew')
            self.entries[name] = entry
            if kind:
                button = ctk.CTkButton(form, text='Browse…', width=85, command=lambda n=name, k=kind: self.browse(n, k))
                button.grid(row=row, column=2, padx=8)
                self.buttons.append(button)
        row = len(FIELDS)
        ctk.CTkLabel(form, text='CMake generator', anchor='w').grid(row=row, column=0, padx=8, pady=4, sticky='w')
        self.generator = ctk.CTkOptionMenu(form, values=['Ninja', 'Unix Makefiles', 'MinGW Makefiles', 'NMake Makefiles'])
        self.generator.grid(row=row, column=1, padx=4, pady=4, sticky='w')
        ctk.CTkLabel(form, text='Default serial baud rate', anchor='w').grid(row=row + 1, column=0, padx=8, pady=4, sticky='w')
        self.baud = ctk.CTkOptionMenu(form, values=['9600', '19200', '38400', '57600', '115200', '230400', '460800', '921600'])
        self.baud.grid(row=row + 1, column=1, padx=4, pady=4, sticky='w')
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.pack(fill='x', pady=4)
        for label, callback in [('Detect tools', self.detect), ('Save & apply', self.save),
                                ('Check setup', self.check), ('Install missing…', self.repair),
                                ('Setup guide', self.guide), ('Export checks', self.export)]:
            button = ctk.CTkButton(bar, text=label, width=125, command=callback)
            button.pack(side='left', padx=(0, 6))
            self.buttons.append(button)
        self.results = ctk.CTkTextbox(self, height=130, font=('Courier', 12))
        self.results.pack(fill='x', pady=(4, 0))
        self.fill(app.config_data)

    def fill(self, config):
        for name, entry in self.entries.items():
            entry.delete(0, 'end')
            entry.insert(0, str(getattr(config, name) or ''))
        self.generator.set(config.generator)
        self.baud.set(str(config.serial_baud))

    def browse(self, name, kind):
        selected = (filedialog.askdirectory(parent=self, title='Select ' + name) if kind in ('directory', 'prefix') else
                    filedialog.askopenfilename(parent=self, title='Select ' + name))
        if selected:
            entry = self.entries[name]
            value = entry.get().strip()
            entry.delete(0, 'end')
            entry.insert(0, value + ';' + selected if kind == 'prefix' and value else selected)

    def candidate(self):
        values = {name: entry.get() for name, entry in self.entries.items()}
        values.update(generator=self.generator.get(), serial_baud=self.baud.get())
        return self.app.config_data.updated(values)

    def detect(self):
        detected = AppConfig.detected()
        # Preserve user-chosen source/output and optional settings while refreshing tools.
        for name in ('toolchain', 'cmake', 'git', 'build_tool', 'build_python', 'dfu_util', 'llvm'):
            value = getattr(detected, name)
            if value:
                entry = self.entries[name]
                entry.delete(0, 'end'); entry.insert(0, str(value))
        self.generator.set(detected.generator)
        self.notice.configure(text='Detected tools placed in the form. Review, then Save & apply.')

    def save(self):
        try:
            self.app.apply_setup(self.candidate())
            self.notice.configure(text='Saved and applied. Check setup before your next build or flash.')
        except Exception as error:
            messagebox.showerror('Setup', str(error), parent=self)

    def check(self):
        try:
            config = self.candidate()
        except Exception as error:
            self.notice.configure(text=str(error)); return
        self.notice.configure(text='Checking the form values; no serial port will be opened and no device will be flashed…')
        self.app.background(lambda: self.app.events.put(('setup_checks', diagnose(config, scan=True))))

    def show_checks(self, checks):
        text = '\n\n'.join(map(str, checks))
        self.results.delete('1.0', 'end'); self.results.insert('end', text)
        errors = sum(check.status == 'error' for check in checks)
        self.notice.configure(text=f'Check complete: {errors} error(s). Checks use the form values; Save & apply activates changes.')

    def repair(self):
        try:
            config = self.candidate()
        except Exception as error:
            self.notice.configure(text=str(error)); return
        self.notice.configure(text='Checking what can be installed. You can review the list before installing…')
        def prepare():
            checks = diagnose(config)
            self.app.events.put(('setup_repair_plan', make_plan(config, checks)))
        self.app.background(prepare)

    def show_repair_plan(self, plan):
        self.show_checks(plan.checks)
        if self.repair_window and self.repair_window.winfo_exists():
            self.repair_window.destroy()
        window = self.repair_window = ctk.CTkToplevel(self)
        window.title('Install missing components'); window.geometry('780x560')
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(window, text='Review installation', font=ctk.CTkFont(size=20, weight='bold')).pack(anchor='w', padx=18, pady=12)
        text = ctk.CTkTextbox(window, wrap='word')
        text.pack(fill='both', expand=True, padx=18, pady=6)
        text.insert('end', plan.summary()); text.configure(state='disabled')
        bar = ctk.CTkFrame(window, fg_color='transparent'); bar.pack(fill='x', padx=18, pady=14)
        ctk.CTkButton(bar, text='Close', command=window.destroy).pack(side='right', padx=6)
        if plan.steps:
            ctk.CTkButton(bar, text='Install & recheck', command=lambda: self.start_repair(plan, window)).pack(side='right', padx=6)
        ctk.CTkButton(bar, text='Setup guide', command=lambda: self.guide(window)).pack(side='left')
        # Delay the grab until mapping; works on Windows and X11.
        window.after(100, lambda: window.grab_set() if window.winfo_exists() else None)

    def start_repair(self, plan, window):
        if self.app._checking or self.app.builder.runner.running:
            return
        window.destroy()
        self.results.delete('1.0', 'end')
        self.notice.configure(text='Installing… Complete any operating-system authentication/installer dialog. Keep Studio open.')
        def work():
            log = lambda line: self.app.events.put(('setup_install_log', line))
            config, failures = install(plan, log)
            log('\nRechecking setup…\n')
            checks = diagnose(config, scan=True)
            self.app.events.put(('setup_repair_result', (config, checks, failures)))
        self.app.background(work)

    def install_log(self, line):
        self.results.insert('end', line); self.results.see('end')

    def show_repair_result(self, result):
        config, checks, failures = result
        self.fill(config)
        self.install_log('\n' + '\n\n'.join(map(str, checks)) + '\n')
        errors = sum(check.status == 'error' for check in checks)
        self.notice.configure(text=(f'Installation stopped: {failures[0]}' if failures else
            f'Installation finished; recheck: {errors} error(s).') + ' Review the form, then Save & apply.')

    def set_busy(self, busy):
        if busy == self._busy:
            return
        self._busy = busy
        state = 'disabled' if busy else 'normal'
        for button in self.buttons:
            button.configure(state=state)

    def guide(self, review=None):
        if review is not None:
            review.destroy()
        window = ctk.CTkToplevel(self)
        window.title('SaolaLink Studio — Setup guide'); window.geometry('850x650')
        text = ctk.CTkTextbox(window, wrap='word')
        text.pack(fill='both', expand=True, padx=12, pady=12)
        text.insert('end', (Path(__file__).resolve().parents[1] / 'docs/SETUP.md').read_text(encoding='utf-8'))
        text.configure(state='disabled')

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.txt', initialfile='saolalink-setup-checks.txt')
        if path:
            try:
                Path(path).write_text(self.results.get('1.0', 'end'), encoding='utf-8')
            except OSError as error:
                messagebox.showerror('Export failed', str(error), parent=self)
