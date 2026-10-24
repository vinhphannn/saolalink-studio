"""GUI integration check. Run with a real display or xvfb-run; no USB writes."""
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

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
        assert not app.log_section.winfo_manager(), 'Setup should have room for its form'
        assert not app.hardware_bar.winfo_manager(), 'Hardware belongs to Build / Flash only'
        assert not app.setup_tab.entries['cmake'].winfo_manager(), 'Tool paths should be hidden in basic setup'
        app.setup_tab.advanced.select(); app.setup_tab.toggle_advanced()
        app.update()
        assert app.setup_tab.entries['cmake'].winfo_manager() == 'grid'
        app.setup_tab.advanced.deselect(); app.setup_tab.toggle_advanced()
        config = app.config_data.updated({'builds': str(Path(temporary) / 'Output with spaces'), 'serial_port': 'COM12'})
        app.apply_setup(config)
        assert AppConfig.load().builds == config.builds
        assert app.builder.config == config
        assert app.serial_tab.preferred_port == 'COM12'
        assert 'Scan' in app.flash_tab.devices.get()
        app.setup_tab.fill(config)
        with patch('ui.setup_tab.discover_tools', return_value=config), \
                patch('ui.setup_tab.diagnose', return_value=[]):
            app.setup_tab.detect()
            deadline = time.monotonic() + 10
            while app._checking and time.monotonic() < deadline:
                app.update(); time.sleep(0.01)
        assert 'NEXT STEPS' in app.setup_tab.results.get('1.0', 'end')
        assert app.setup_tab.candidate().source == config.source
        if os.environ.get('GUI_SMOKE_SCREENSHOT'):
            from PIL import ImageGrab
            # CustomTkinter schedules sizing/drawing callbacks after mapping.
            for _ in range(20):
                app.update()
                time.sleep(0.025)
            assert app.winfo_width() >= 1020 and app.winfo_height() >= 700
            assert app.setup_tab.entries['source'].winfo_width() > 200
            ImageGrab.grab().save(os.environ['GUI_SMOKE_SCREENSHOT'])
        app.setup_tab.guide()
        app.update()
        with patch('ui.setup_tab.webbrowser.open', return_value=True) as browser:
            app.setup_tab.open_link('https://www.python.org/downloads/windows/')
            browser.assert_called_once()
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
        # Exercise review -> explicit install -> recheck without installing any packages.
        from core.diagnostics import Check
        from core.setup_repair import InstallStep, RepairPlan
        checks = [Check('build', 'Demo dependency', 'error', 'Smoke test only')]
        plan = RepairPlan(config, tuple(checks), (InstallStep('Safe installer probe',
            (sys.executable, '-c', 'print("installer output reached Setup")')),), ())
        with patch('ui.setup_tab.diagnose', return_value=checks), patch('ui.setup_tab.make_plan', return_value=plan):
            app.setup_tab.repair()
            deadline = time.monotonic() + 10
            while app._checking and time.monotonic() < deadline:
                app.update(); time.sleep(0.01)
        assert app.setup_tab.repair_window.winfo_exists(), 'Installation must require a review'
        assert 'installer output reached Setup' not in app.setup_tab.results.get('1.0', 'end')
        review = app.setup_tab.repair_window
        app.setup_tab.guide(review)
        app.update()
        assert not review.winfo_exists(), 'Guide must release the review dialog grab'
        for child in app.winfo_children():
            if isinstance(child, ctk.CTkToplevel):
                child.destroy()
        app.setup_tab.show_repair_plan(plan)
        with patch('ui.setup_tab.diagnose', return_value=[Check('build', 'Demo dependency', 'ok', 'ready')]):
            app.setup_tab.start_repair(plan, app.setup_tab.repair_window)
            deadline = time.monotonic() + 10
            while app._checking and time.monotonic() < deadline:
                app.update(); time.sleep(0.01)
        assert not app._checking
        assert 'installer output reached Setup' in app.setup_tab.results.get('1.0', 'end')
        assert '[OK] build / Demo dependency' in app.setup_tab.results.get('1.0', 'end')
        app.setup_tab.check()
        deadline = time.monotonic() + 90
        while app._checking and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert not app._checking, 'Setup diagnostics did not finish'
        assert '[OK]' in app.setup_tab.results.get('1.0', 'end') or '[ERROR]' in app.setup_tab.results.get('1.0', 'end')
        print('GUI first-run, apply, guide, busy guard, install review, output and recheck: OK')
    finally:
        app._checking = False
        app.close()
