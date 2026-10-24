"""Desktop entry point; CLI is available separately as cli.py."""
import customtkinter as ctk
from contextlib import suppress
import tkinter
from ui.main_window import AppWindow

def main():
    ctk.set_appearance_mode('Dark')
    ctk.set_default_color_theme('dark-blue')
    app = AppWindow()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.builder.runner.stop()
        app.serial_tab.close()
        with suppress(tkinter.TclError):
            app.destroy()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
