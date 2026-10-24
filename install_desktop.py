"""Install this checkout as a user application and optional GNOME favorite."""
import argparse
import ast
from pathlib import Path
import shutil
import subprocess

APP_ID = 'saolalink-studio.desktop'
STUDIO = Path(__file__).resolve().parent
PROJECT = STUDIO.parent

def desktop_entry():
    python = PROJECT / '.venv/bin/python'
    if not python.is_file():
        raise RuntimeError(f'Python environment not found: {python}')
    return f'''[Desktop Entry]
Version=1.0
Type=Application
Name=SaolaLink Studio
Comment=Build, flash and compare firmware for SaolaLink RC transmitters
Comment[vi]=Build, nạp và so sánh firmware tay cầm RC SaolaLink
Exec="{python}" "{STUDIO / 'main.py'}"
TryExec={python}
Path={PROJECT}
Icon={STUDIO / 'assets/saolalink-studio.svg'}
Terminal=false
Categories=Development;Electronics;
Keywords=SaolaLink;Saolatek;RC;EdgeTX;DFU;Firmware;
StartupNotify=true
StartupWMClass=Saolalinkstudio
'''

def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin', action='store_true', help='Also add to GNOME favorites, keeping existing favorites')
    parser.add_argument('--prepare', action='store_true', help='Only write the reviewable desktop file inside the project')
    args = parser.parse_args()
    local = STUDIO / APP_ID
    local.write_text(desktop_entry())
    local.chmod(0o755)
    if shutil.which('desktop-file-validate'):
        subprocess.run(['desktop-file-validate', str(local)], check=True)
    if args.prepare:
        print(local); return
    applications = Path.home() / '.local/share/applications'
    applications.mkdir(parents=True, exist_ok=True)
    installed = applications / APP_ID
    shutil.copy2(local, installed)
    print(f'Application: {installed}')
    directory = subprocess.run(['xdg-user-dir', 'DESKTOP'], text=True, capture_output=True, check=True).stdout.strip()
    # Do not place a shortcut in the home folder if desktop icons are disabled.
    if directory and Path(directory) != Path.home():
        desktop = Path(directory)
        desktop.mkdir(parents=True, exist_ok=True)
        shortcut = desktop / APP_ID
        shutil.copy2(local, shortcut)
        result = subprocess.run(['gio', 'set', str(shortcut), 'metadata::trusted', 'true'], capture_output=True, text=True)
        print(f'Desktop: {shortcut}')
        if result.returncode:
            print('If the desktop asks, right-click the shortcut and choose Allow Launching.')
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(applications)], check=True)
    if args.pin:
        result = subprocess.run(['gsettings', 'get', 'org.gnome.shell', 'favorite-apps'], capture_output=True, text=True, check=True)
        value = result.stdout.strip()
        favorites = [] if value == '@as []' else ast.literal_eval(value)
        if APP_ID not in favorites:
            favorites.append(APP_ID)
            subprocess.run(['gsettings', 'set', 'org.gnome.shell', 'favorite-apps', repr(favorites)], check=True)
        print('Pinned to GNOME favorites.')

if __name__ == '__main__':
    run()
