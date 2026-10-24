"""GUI integration check. Run with a real display or xvfb-run; no USB writes."""
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix='Studio GUI ') as temporary:
    os.environ['SAOLALINK_CONFIG'] = str(Path(temporary) / 'settings.json')
    for name in ('EDGETX_DIR', 'SAOLALINK_BUILD_DIR', 'ARM_TOOLCHAIN_DIR'):
        os.environ.pop(name, None)
    from core.config import AppConfig
    from ui.main_window import AppWindow
    import customtkinter as ctk
    ctk.set_appearance_mode('Dark')
    app = AppWindow()
    try:
        app.update()
        assert app.tabs.get() == 'Setup', 'First run must open Setup'
        assert not app.log.winfo_manager(), 'Setup should have room for its form'
        config = app.config_data.updated({'builds': str(Path(temporary) / 'Output with spaces'), 'serial_port': 'COM12'})
        app.apply_setup(config)
        assert AppConfig.load().builds == config.builds
        assert app.builder.config == config
        assert app.serial_tab.preferred_port == 'COM12'
        assert 'Refresh' in app.flash_tab.devices.get()
        if os.environ.get('GUI_SMOKE_SCREENSHOT'):
            from PIL import ImageGrab
            # CustomTkinter schedules sizing/drawing callbacks after mapping.
            for _ in range(20):
                app.update()
                time.sleep(0.025)
            ImageGrab.grab().save(os.environ['GUI_SMOKE_SCREENSHOT'])
        app.setup_tab.guide()
        app.update()
        for child in app.winfo_children():
            if isinstance(child, ctk.CTkToplevel):
                child.destroy()
        # Applying configuration is forbidden while an operation is in progress.
        app._checking = True
        try:
            app.apply_setup(config)
            raise AssertionError('Setup was applied during an active task')
        except ValueError:
            pass
        app._checking = False
        app.setup_tab.check()
        deadline = time.monotonic() + 90
        while app._checking and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert not app._checking, 'Setup diagnostics did not finish'
        assert '[OK]' in app.setup_tab.results.get('1.0', 'end') or '[ERROR]' in app.setup_tab.results.get('1.0', 'end')
        print('GUI first-run, apply, guide, busy guard and diagnostics: OK')
    finally:
        app._checking = False
        app.close()
