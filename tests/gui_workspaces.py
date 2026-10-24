"""Workflow UI checks with fake artifacts/devices. Never builds or writes USB hardware."""
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


with tempfile.TemporaryDirectory(prefix='Studio workflows ') as temporary:
    os.environ['SAOLALINK_CONFIG'] = str(Path(temporary) / 'settings.json')
    from core.device_service import DfuDevice
    from ui.main_window import AppWindow, PROFILE_LABELS
    import customtkinter as ctk
    ctk.set_appearance_mode('Dark')
    app = AppWindow()

    def settle():
        for _ in range(12):
            app.update(); time.sleep(0.02)

    def page(name):
        app.tabs.set(name); app.tab_changed(); settle()

    def capture(name):
        folder = os.environ.get('GUI_WORKSPACE_SCREENSHOTS')
        if folder:
            from PIL import ImageGrab
            destination = Path(folder); destination.mkdir(parents=True, exist_ok=True)
            settle()
            ImageGrab.grab().save(destination / (name + '.png'))

    def visible_in_tab(widget, name):
        assert widget.winfo_ismapped(), widget.cget('text') + ' is hidden'
        bottom = widget.winfo_rooty() + widget.winfo_height()
        tab = app.tabs.tab(name)
        assert bottom <= tab.winfo_rooty() + tab.winfo_height(), widget.cget('text') + ' requires scrolling'

    try:
        settle()
        for name in ('Build', 'Flash USB', 'Serial monitor', 'Setup'):
            assert app.tabs.tab(name)
        try:
            app.tabs.tab('Compare Pocket')
            raise AssertionError('Developer comparison should not be a primary tab')
        except ValueError:
            pass
        assert not any(isinstance(widget, ctk.CTkButton) and widget.cget('text') == 'Setup'
                       for widget in app.header.winfo_children()), 'Setup is duplicated in the header'
        assert not app.stop_button.winfo_manager(), 'Stop should be hidden while idle'
        page('Build')
        assert app.hardware_bar.winfo_manager()
        assert not app.build_tab.advanced.expanded and not app.build_tab.details.expanded
        assert not app.log_section.expanded
        with patch.object(app, 'operation') as action:
            app.build_tab.firmware.button.invoke(); app.build_tab.bootloader.button.invoke(); app.build_tab.clean_button.invoke()
            assert [call.args for call in action.call_args_list] == [('build', 'firmware'), ('build', 'bootloader'), ('clean',)]
        capture('build')
        app.geometry('1020x700'); settle()
        for button in (app.build_tab.firmware.button, app.build_tab.bootloader.button, app.build_tab.clean_button):
            assert button.cget('height') >= 40
            visible_in_tab(button, 'Build')
        capture('build-small')
        page('Flash USB')
        visible_in_tab(app.flash_tab.firmware.button, 'Flash USB')
        visible_in_tab(app.flash_tab.bootloader.button, 'Flash USB')
        capture('flash-small')
        app.geometry('1180x820'); settle()

        rom = DfuDevice('0483:df11', 'test-rom', 'TEST-ONLY', '@Internal Flash /0x08000000/')
        usb = DfuDevice('0483:df11', 'test-app', 'TEST-ONLY', '@SaolaLink App /0x08008000/')

        def artifact(profile, mode, kind):
            return Path(temporary) / (kind + '.bin'), {
                'size': 2048, 'built_at': 'test build', 'sha256': 'test-only',
                'address': '0x08008000' if kind == 'application' else '0x08000000'}

        with patch.object(app.builder, 'artifact', side_effect=artifact):
            app.update_artifact()
            app.dfu_devices = [rom, usb]
            app.flash_tab.devices.configure(values=[rom.label, usb.label])
            app.flash_tab.devices.set(rom.label); app.flash_tab.refresh_state()
            assert app.flash_tab.firmware.button.cget('state') == 'disabled'
            assert app.flash_tab.bootloader.button.cget('state') == 'normal'
            with patch.object(app, 'flash') as upload:
                app.flash_tab.firmware.button.invoke(); upload.assert_not_called()
                app.flash_tab.bootloader.button.invoke(); upload.assert_called_once_with('bootloader')
            app.flash_tab.devices.set(usb.label); app.flash_tab.refresh_state()
            assert app.flash_tab.firmware.button.cget('state') == 'normal'
            assert app.flash_tab.bootloader.button.cget('state') == 'disabled'
            assert app.flash_tab.full_image.cget('state') == 'disabled'
            with patch.object(app, 'flash') as upload:
                app.flash_tab.firmware.button.invoke(); upload.assert_called_once_with('application')
            capture('flash-usb-ready-test-data')
            with patch('ui.main_window.messagebox.askyesno', return_value=False), patch.object(app, 'background') as background:
                app.flash('application'); background.assert_not_called()
            with patch('ui.main_window.messagebox.askyesno', return_value=True), \
                    patch.object(app, 'background') as background, patch.object(app.builder, 'flash') as write:
                app.flash('application')
                background.call_args.args[0]()
                write.assert_called_once_with(app.profile, 'Debug', 'application', usb)
            app._checking = True; app.sync_controls()
            assert app.build_tab.clean_button.cget('state') == 'disabled'
            assert app.flash_tab.firmware.button.cget('state') == 'disabled'
            assert app.flash_tab.scan_button.cget('state') == 'disabled'
            app._checking = False; app.sync_controls()
            app.profile_picker.set(PROFILE_LABELS['saolalink-v1']); app.context_changed()
            assert app.selected_device() is None, 'Changing hardware must clear the previous USB selection'
            assert app.flash_tab.firmware.button.cget('state') == 'disabled', 'Application upload is DevEBox-only'
            app.profile_picker.set(PROFILE_LABELS['saolalink-devebox']); app.context_changed()
            app.mode_picker.set('Release'); app.context_changed()
            assert 'Release' in app.context_label.cget('text')
        app.mode_picker.set('Debug'); app.context_changed()
        app.open_comparison(); settle()
        assert app.comparison_window.winfo_exists()
        app.comparison_window.destroy()
        app.open_workflow_guide(); settle()
        for child in app.winfo_children():
            if isinstance(child, ctk.CTkToplevel) and child.winfo_exists():
                child.destroy()
        page('Serial monitor')
        assert not app.hardware_bar.winfo_manager() and not app.log_section.winfo_manager()
        assert app.serial_tab.terminal.winfo_height() > 200
        capture('serial')
        page('Setup')
        assert not app.hardware_bar.winfo_manager() and not app.log_section.winfo_manager()
        capture('setup')
        page('Build'); app.show_error('Test failure: details should be visible')
        assert app.log_section.expanded
        assert 'Test failure' in app.log.get('1.0', 'end')
        print('Workspace navigation, large actions, USB route gating, confirmation, busy state, profiles and logs: OK')
    finally:
        app._checking = False
        app.close()
