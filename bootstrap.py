"""Prepare a private Studio environment and launch it. Uses only Python's standard library."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


def prepare(studio, log=print):
    if sys.version_info < (3, 10):
        raise RuntimeError('Studio needs Python 3.10 or newer. Install desktop Python with Tcl/Tk; see README.md.')
    try:
        import tkinter  # noqa: F401; verify the system Python includes Tk before downloading packages.
    except ImportError as error:
        raise RuntimeError('Python is missing Tk. Fedora: install python3-tkinter; Ubuntu/Debian: python3-tk. '
                           'Windows: install desktop Python with Tcl/Tk. See README.md, then run this launcher again.') from error
    studio = Path(studio).resolve()
    folder = studio / '.venv'
    python = folder / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if folder.exists() and not (folder / 'pyvenv.cfg').is_file():
        raise RuntimeError(f'{folder} already exists but is not a Python virtual environment. '
                           'Choose another Studio folder or move that folder aside; the launcher will not erase it.')
    if not python.is_file():
        log(f'Creating private Studio environment: {folder}', flush=True)
        try:
            venv.EnvBuilder(with_pip=True).create(folder)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError('Could not create the Studio environment. On Ubuntu/Debian install python3-venv '
                               f'for this Python version. Use a writable extracted folder. Details: {error}') from error
    environment = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    probe = [str(python), '-c', 'import sys; print(sys.prefix)']
    result = subprocess.run(probe, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            env=environment, timeout=15, **flags)
    if result.returncode or Path(result.stdout.strip()).resolve() != folder:
        raise RuntimeError('The Studio .venv is no longer usable (for example after moving folders or upgrading Python). '
                           'Close Studio, remove only its .venv folder, and run the launcher again. Your machine settings '
                           'are stored separately.\n' + result.stderr[-1000:])
    requirements = studio / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = folder / '.studio-requirements.sha256'
    modules = [str(python), '-c', 'import customtkinter, serial, tkinter']
    ready = (marker.is_file() and marker.read_text(encoding='utf-8').strip() == fingerprint and
             subprocess.run(modules, capture_output=True, env=environment, **flags).returncode == 0)
    if not ready:
        log('Installing Studio GUI dependencies. Internet is needed for the first launch / changed requirements.', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)],
                       env=environment, check=True)
        subprocess.run(modules, env=environment, check=True, **flags)
        marker.write_text(fingerprint + '\n', encoding='utf-8')
    return python


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='Prepare the private environment without opening the GUI')
    args = parser.parse_args()
    studio = Path(__file__).resolve().parent
    try:
        python = prepare(studio)
        if args.prepare_only:
            print('Studio environment is ready.'); return 0
        return subprocess.run([str(python), str(studio / 'main.py')], cwd=studio).returncode
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'\nStudio could not start: {error}\nSee README.md > Download and start; fix the reported item and run this launcher again.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
