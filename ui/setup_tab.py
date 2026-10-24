"""Editable per-machine setup; validation runs off the Tk thread."""
from pathlib import Path
from tkinter import filedialog, messagebox
import os
import webbrowser
import customtkinter as ctk

from core.config import settings_path
from core.diagnostics import diagnose
from core.setup_repair import make_plan, install
from core.tool_discovery import discover_tools
from core.setup_guidance import GETTING_STARTED, DOWNLOADS, next_steps

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
        self.advanced_widgets = []
        ctk.CTkLabel(self, text='Machine setup', font=ctk.CTkFont(size=24, weight='bold')).pack(anchor='w', pady=(8, 0))
        ctk.CTkLabel(self, text='1  Choose project folders    →    2  Find / install tools    →    3  Check & save', anchor='w').pack(fill='x')
        self.notice = ctk.CTkLabel(self, text='Select paths for this computer. Save & apply, then check setup.', anchor='w')
        self.notice.pack(fill='x')
        ctk.CTkLabel(self, text=f'User settings: {settings_path()}', anchor='w', text_color='gray65').pack(fill='x')
        overrides = [name for name in ('EDGETX_DIR', 'SAOLALINK_BUILD_DIR', 'ARM_TOOLCHAIN_DIR') if os.environ.get(name)]
        if overrides:
            ctk.CTkLabel(self, text='Environment overrides on next launch: ' + ', '.join(overrides), text_color='#efbd63').pack(anchor='w')
        self.advanced = ctk.CTkCheckBox(self, text='Show tool paths and advanced options', command=self.toggle_advanced)
        self.advanced.pack(anchor='w', pady=(8, 0))
        form = ctk.CTkScrollableFrame(self, height=230)
        form.pack(fill='both', expand=True, pady=6)
        form.grid_columnconfigure(1, weight=1)
        for row, (name, label, kind) in enumerate(FIELDS):
            caption = ctk.CTkLabel(form, text=label, anchor='w')
            caption.grid(row=row, column=0, padx=8, pady=4, sticky='w')
            entry = ctk.CTkEntry(form, height=34)
            entry.grid(row=row, column=1, padx=4, pady=4, sticky='ew')
            self.entries[name] = entry
            if kind:
                button = ctk.CTkButton(form, text='Browse…', width=95, height=34, command=lambda n=name, k=kind: self.browse(n, k))
                button.grid(row=row, column=2, padx=8)
                self.buttons.append(button)
            if name not in ('source', 'builds'):
                self.advanced_widgets += [caption, entry] + ([button] if kind else [])
        row = len(FIELDS)
        generator_caption = ctk.CTkLabel(form, text='CMake generator', anchor='w')
        generator_caption.grid(row=row, column=0, padx=8, pady=4, sticky='w')
        self.generator = ctk.CTkOptionMenu(form, values=['Ninja', 'Unix Makefiles', 'MinGW Makefiles', 'NMake Makefiles'])
        self.generator.grid(row=row, column=1, padx=4, pady=4, sticky='w')
        baud_caption = ctk.CTkLabel(form, text='Default serial baud rate', anchor='w')
        baud_caption.grid(row=row + 1, column=0, padx=8, pady=4, sticky='w')
        self.baud = ctk.CTkOptionMenu(form, values=['9600', '19200', '38400', '57600', '115200', '230400', '460800', '921600'])
        self.baud.grid(row=row + 1, column=1, padx=4, pady=4, sticky='w')
        self.advanced_widgets += [generator_caption, self.generator, baud_caption, self.baud]
        export_button = ctk.CTkButton(form, text='Export setup checks…', height=36, command=self.export)
        export_button.grid(row=row + 2, column=1, padx=4, pady=8, sticky='w')
        self.advanced_widgets.append(export_button); self.buttons.append(export_button)
        self.basic_help = ctk.CTkLabel(form, text=(
            'Start with Find tools. Installed tools are filled automatically.\n\n'
            'Then Install missing to review downloads and complete the OS installer dialogs.\n\n'
            'If something still needs a vendor download, Setup guide explains which package to choose '
            'and where to point Browse. Check setup shows your next steps.'), wraplength=800, justify='left', anchor='w')
        self.basic_help.grid(row=2, column=0, columnspan=3, padx=8, pady=18, sticky='w')
        self.toggle_advanced()
        ctk.CTkLabel(self, text='Tool paths are filled automatically when found. Setup guide includes download links and manual steps.',
                    anchor='w', text_color='gray65').pack(fill='x')
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.pack(fill='x', pady=4)
        for label, callback in [('Find tools', self.detect), ('Install missing…', self.repair),
                                ('Check setup', self.check), ('Save & apply', self.save),
                                ('Setup guide', self.guide)]:
            button = ctk.CTkButton(bar, text=label, width=125, height=38, command=callback)
            button.pack(side='left', padx=(0, 6))
            self.buttons.append(button)
        self.results = ctk.CTkTextbox(self, height=130, font=('Courier', 12))
        self.results.pack(fill='x', pady=(4, 0))
        self.fill(app.config_data)

    def toggle_advanced(self):
        for widget in self.advanced_widgets:
            widget.grid() if self.advanced.get() else widget.grid_remove()
        self.basic_help.grid_remove() if self.advanced.get() else self.basic_help.grid()

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
        try:
            config = self.candidate()
        except Exception as error:
            self.notice.configure(text=str(error)); return
        self.notice.configure(text='Finding installed tools and checking paths…')
        def work():
            found = discover_tools(config)
            self.app.events.put(('setup_detected', (found, diagnose(found, scan=True))))
        self.app.background(work)

    def show_detected(self, result):
        config, checks = result
        self.fill(config)
        self.show_checks(checks)

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
        text = 'NEXT STEPS\n' + next_steps(checks) + '\n\nCHECK DETAILS\n' + '\n\n'.join(map(str, checks))
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
            found = discover_tools(config)
            checks = diagnose(found)
            self.app.events.put(('setup_repair_plan', make_plan(found, checks)))
        self.app.background(prepare)

    def show_repair_plan(self, plan):
        self.fill(plan.config)
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
        self.install_log('\nNEXT STEPS\n' + next_steps(checks) + '\n')
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
        frame = ctk.CTkScrollableFrame(window); frame.pack(fill='both', expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text='Set up this computer', font=ctk.CTkFont(size=22, weight='bold')).pack(anchor='w', pady=8)
        for title, detail in GETTING_STARTED:
            ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(weight='bold')).pack(anchor='w', pady=(10, 2))
            ctk.CTkLabel(frame, text=detail, wraplength=750, justify='left', anchor='w').pack(fill='x')
        for title, url, detail in DOWNLOADS:
            ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(weight='bold')).pack(anchor='w', pady=(16, 2))
            ctk.CTkLabel(frame, text=detail, wraplength=750, justify='left', anchor='w').pack(fill='x')
            ctk.CTkButton(frame, text='Open official page', command=lambda link=url: self.open_link(link)).pack(anchor='w', pady=5)
        ctk.CTkButton(frame, text='Read full setup reference', command=self.reference).pack(anchor='w', pady=18)

    def open_link(self, url):
        try:
            if not webbrowser.open(url):
                raise OSError('No default browser found. Open this address manually:\n' + url)
        except OSError as error:
            messagebox.showerror('Open download page', str(error), parent=self)

    def reference(self):
        window = ctk.CTkToplevel(self)
        window.title('SaolaLink Studio — Full setup reference'); window.geometry('850x650')
        text = ctk.CTkTextbox(window, wrap='word'); text.pack(fill='both', expand=True, padx=12, pady=12)
        text.insert('end', (Path(__file__).resolve().parents[1] / 'docs/SETUP.md').read_text(encoding='utf-8'))
        text.configure(state='disabled')

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.txt', initialfile='saolalink-setup-checks.txt')
        if path:
            try:
                Path(path).write_text(self.results.get('1.0', 'end'), encoding='utf-8')
            except OSError as error:
                messagebox.showerror('Export failed', str(error), parent=self)
