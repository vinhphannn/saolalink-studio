# SaolaLink Studio

Desktop build/flash tool for Saolatek RC transmitters, using a small
`core/` + `ui/` architecture.
Python + CustomTkinter; core services also work through a CLI without Tk.

## Run

Clone Studio and the SaolaLink EdgeTX fork as sibling directories. From a
workspace directory (for example `saolatek`):

```bash
git clone https://github.com/vinhphannn/saolalink-studio.git
git clone --branch SAOLALINKV1 https://github.com/vinhphannn/edgetx.git
git -C edgetx submodule update --init --recursive
```

Then, from that same workspace directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r saolalink-studio/requirements.txt -e ./edgetx
.venv/bin/python saolalink-studio/main.py
```

To install an application-menu entry and Desktop shortcut, and pin it to GNOME dash:

```bash
.venv/bin/python saolalink-studio/install_desktop.py --pin
```

The Linux launcher uses the Python environment running the installer and includes a custom RC radio
icon. Omit `--pin` to install shortcuts without changing GNOME favorites. Re-run
the installer after moving the project. `Ctrl+C` in a terminal stops the active
operation and exits the GUI without a traceback.

The GUI needs a working display and Tk (`python3-tk` on Ubuntu, `python3-tkinter` on Fedora).
For native Windows setup, see [docs/SETUP.md](docs/SETUP.md).
Build needs CMake >= 3.24, a native C/C++ compiler, Make (or the CMake default
generator), and **Arm GNU Toolchain 14.2.rel1**. EdgeTX rejects other ARM GCC
versions. The project-local toolchain is detected automatically at
`.tools/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi/bin`.
DFU needs `dfu-util` and USB access for STM32 `0483:df11`.

Environment overrides:

- `EDGETX_DIR`: EdgeTX source directory; defaults to `../edgetx` relative to Studio.
- `SAOLALINK_BUILD_DIR`: output directory; defaults to the project's `build/`.
- `ARM_TOOLCHAIN_DIR`: the **bin directory** containing `arm-none-eabi-g++`.

The GUI defaults to **SaolaLink DevEBox 8MHz (EdgeTX USB)** for the current bare
development board. CLI defaults to **SaolaLink V1** (12 MHz).
Both use `PCB=X7`, `PCBREV=SAOLALINK_V1` with separate build directories.
Pocket remains selectable as a reference. Debug and Release outputs are isolated:
`build/<profile>/<debug|release>/arm-none-eabi/`.
Build defaults: stick mode 2, English, LTO enabled (matching upstream Pocket builds),
complete bootloader-inclusive `.bin`. Debug keeps symbols but optimization/LTO can
inline functions and affect single-stepping.

## Workspaces

- **Build**: check tools, configure, build firmware/bootloader, clean, stop; shows the verified firmware artifact.
- **Flash**: discover STM32 ROM DFU devices, select exact USB path, flash the selected profile's firmware or bootloader.
  DevEBox uses **Flash bootloader** once in ROM DFU, then **Flash application
  (EdgeTX USB)** at 0x08008000. Install the updated bootloader once via ROM
  DFU to enable RTN entry (updating the application alone cannot change it).
  BOOT0 stays LOW for application updates; hold **RTN (PC5)** at power-on or
  RESET to enter the EdgeTX loader, then release RTN. The loader waits until
  reset; press RESET without RTN after uploading. Older loaders use PA0.
- **Serial monitor**: scan COM/tty ports with device description and USB identity,
  select baud (115200 by default), connect/disconnect, receive logs and send UTF-8
  commands with None/LF/CRLF ending. Clear, save the visible log and toggle
  auto-scroll. RX/TX byte counts and dropped-chunk counts are shown. The display
  retains at most about 200,000 characters; export before old text is trimmed.
  Scanning never opens a device. DTR/RTS are requested low without an intentional
  reset pulse; driver/hardware behaviour during open can still vary.
- **Compare Pocket**: hardware diff with identity separated, target build settings,
  Pocket drift, local HAL overrides, integration diff against a fixed upstream
  commit; export a report. Building both profiles also exposes effective HAL macro differences.

The operation log remains visible across tabs, with one file per operation in
`build/logs/`. The runner serializes operations and stops child process groups.

Serial discovery is intentionally separate from DFU discovery. USB-TTL bridges
(CH340, CP210x, FTDI, etc.) and native USB CDC ports are listed without filtering
to a particular VID/PID. Select the actual adapter; a ROM DFU device is not a COM
port. The DevEBox EdgeTX profile enables native USB CDC CLI: select its ttyACM/COM
port and send `help` or `devboard` with LF ending. No USB-TTL adapter is required.
The EdgeTX fork contains the board-specific firmware and bootloader sources.

The serial feature separates core/device discovery from the UI/job queue,
using a plain UART worker. Worker threads never
update Tk widgets. Unplug/read/write errors disconnect the session and are shown
in the terminal. A new connection always requires an explicit Connect action.

Restart Studio after updating code. `pyserial>=3.5,<4` is included in requirements.

## CLI

```bash
.venv/bin/python saolalink-studio/cli.py doctor
.venv/bin/python saolalink-studio/cli.py build --profile saolalink-v1 --mode Debug
.venv/bin/python saolalink-studio/cli.py build --profile pocket --mode Debug
.venv/bin/python saolalink-studio/cli.py build --kind bootloader
.venv/bin/python saolalink-studio/cli.py compare > build/pocket-comparison.diff
.venv/bin/python saolalink-studio/cli.py devices
# Replace 1-2 with the exact path reported by devices:
.venv/bin/python saolalink-studio/cli.py flash --usb-path 1-2 --kind firmware
```

Flash does not build automatically. It requires a successful Studio build and a
matching `.manifest.json`. The manifest is created only after checking actual CMake
settings and the generated radio macro, and records profile, kind, mode, commit, working-source
fingerprint, size and SHA256. Failed/cancelled builds invalidate the corresponding
manifest. A changed or cross-target artifact is rejected.

Firmware DFU writes the **whole image, including EdgeTX bootloader**, at
`0x08000000`, alt 0, then exits DFU. Bootloader-only writes use the same base,
with a 32 KiB size limit. ROM DFU VID/PID does not identify which physical board
is connected; select the matching board profile. Enter ROM DFU through the board's
BOOT0/reset sequence; this is distinct from the EdgeTX SD-card bootloader.
The tool does not modify model files or build/flash the ELRS RF module firmware.

## Extend

- `core/config.py`: add a `BoardProfile` to `PROFILES`; the GUI and CLI pick it up.
- `core/builder.py`: CMake command planning, artifact validation and DFU flashing.
- `core/runner.py`: process execution, cancellation, queue events and log files.
- `core/device_service.py`: DFU discovery and unique device selection.
- `core/comparison.py`: fixed Pocket baseline and source/generated HAL comparison.
- `ui/workspaces.py`: separate Build, Flash and Compare widgets.
- `ui/main_window.py`: orchestration; workers never call Tk APIs directly.

Core does not import CustomTkinter. Add another transport by implementing its
command planning in a core service and wiring one workspace callback.
DFU commands use the executable selected in Setup on Linux and Windows;
USB drivers and device permissions must be configured on each machine.

## Verify

```bash
.venv/bin/python -m unittest discover -s saolalink-studio/tests -v
```

Tests cover operation failure/cancellation, isolation, full-image flags, artifact
integrity and target mismatch, and multiple devices sharing one DFU VID/PID.

## Linux / Windows machine setup

Open **Setup** on first launch or from the header at any time. Browse to your
EdgeTX checkout, output folder, Arm GNU toolchain, CMake, Ninja/Make, Git,
build Python and dfu-util. Studio and EdgeTX do not need to be siblings.
Optional LLVM, library prefixes, dependency cache and Visual Studio environment
paths are also available. Use **Save & apply**, then **Check setup**.

Use **Install missing… → Install & recheck** to review and install supported missing
tools and EdgeTX Python packages from the GUI. Linux uses the desktop authentication
dialog; Windows uses WinGet and publisher installers. Progress appears in Setup.
Review the resulting paths and **Save & apply**. Arm GNU 14.2.rel1 and USB driver
selection still require the correct vendor installation/interface; remaining issues
are listed explicitly. Checks and builds never start installers automatically.

Settings live in your user profile, outside Git; each team member configures
their own machine. Build, flash and serial diagnostics are separate. Serial
scanning never opens a port or automatically connects. Failed setup checks
include the tool and a repair hint; **Export checks** saves a shareable report.

See [the setup guide](docs/SETUP.md) for supported automatic repairs, manual installation,
USB/COM drivers, Python dependencies, path overrides and CLI setup.

```sh
python cli.py setup
python cli.py doctor --scope build
python cli.py doctor --scope flash --scan
python cli.py doctor --scope serial --scan
```

The process runner uses POSIX process groups on Linux and process-tree
termination on Windows. Automated tests run on both platforms through GitHub
Actions; real USB flashing/serial access and firmware builds still need testing
on the intended machine, tool versions and hardware.
