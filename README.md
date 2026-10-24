# SaolaLink Studio

Desktop build/flash tool for Saolatek RC transmitters, using a small
`core/` + `ui/` architecture.
Python + CustomTkinter; core services also work through a CLI without Tk.

## Download and start

Studio is currently distributed as source, with launch scripts; this repository does not yet
provide a standalone `.exe` or AppImage. Python is needed once on each machine. The launchers
create a private `.venv`, install Studio's GUI packages on first launch, and open the app.
You do not need to activate a virtual environment or type pip commands. Internet is needed for
the initial dependency download; an unchanged, prepared launcher does not reinstall packages.

Download [Studio ZIP](https://github.com/vinhphannn/saolalink-studio/archive/refs/heads/main.zip)
and **extract the whole ZIP** into a writable folder, or clone
[the Studio repository](https://github.com/vinhphannn/saolalink-studio).
Run from the extracted folder, not inside the ZIP. Studio and EdgeTX may be in different locations.

| Computer | Prerequisites | Start Studio |
| --- | --- | --- |
| Windows 10/11, x64 | Desktop Python 3.10+ with Tcl/Tk and pip; Python 3.12 is used in CI. Install [Python for Windows](https://www.python.org/downloads/windows/), including the launcher / PATH option when offered. | Double-click **start-studio.cmd**. A console shows first-launch installation progress and errors. Keep it open while Studio is running. No PowerShell activation is needed. |
| Fedora Workstation, x86_64 | Python 3, pip and Tk; see the one-time package command below. Desktop Polkit authentication is needed for Install missing. | Open **start-studio.sh** with Run as Program / Run in Terminal if your file manager supports it. If required, allow executing the script in Properties → Permissions. Terminal fallback: `bash start-studio.sh`. |
| Ubuntu / Debian desktop, x86_64 | Python 3 with venv, pip and Tk; see below. Desktop Polkit authentication is needed for Install missing. | Run **start-studio.sh**, with the same file-manager or terminal steps as Fedora. |
| Linux ARM64, Windows ARM64, macOS | Not validated by this project's build/USB test matrix. | Do not assume an x64 toolchain works natively. Linux ARM64 needs an appropriate host Arm GNU package; manual setup and hardware validation are required. macOS has no automatic installer flow here. |

### Linux prerequisites (once per machine)

These OS packages must exist before a Python GUI can start. The launcher reports a missing
Python/Tk/venv component; it does not run Studio as root.

Fedora:

```sh
sudo dnf install python3 python3-pip python3-tkinter
```

Ubuntu / Debian:

```sh
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-tk
```

Then open `start-studio.sh` from the extracted Studio folder. If a Linux file manager opens the
script in an editor, choose Run as Program / Run in Terminal, or open a terminal in that folder
and run `bash start-studio.sh`. Do not copy another member's `.venv` to your computer.

For an optional Linux application-menu/Desktop shortcut after first launch, from the Studio folder:

```sh
.venv/bin/python install_desktop.py
```

Add `--pin` for a GNOME favorite. Re-run the shortcut installer after moving Studio. Existing
users may keep their current Python environment and shortcut; close/reopen Studio after updates.
If you move a launcher installation, remove only its disposable `.venv` and run the launcher again.
Saved machine settings are separate; see [the full setup reference](docs/SETUP.md).

## First-time setup in the app

1. **Choose project folders.** In Setup, Browse to your EdgeTX Git clone (the folder containing
   `CMakeLists.txt` and `radio/`). Choose a writable build output folder outside both source trees.
   See **Get the EdgeTX source** below if this is a new computer.
2. **Find tools.** Studio searches PATH, current Windows registry PATH, common vendor install
   locations, workspace `.tools`, and known tool folders under Downloads/tools. Found paths are
   filled in automatically. Valid custom selections and the existing generator are preserved.
3. **Install missing… → Install & recheck.** Review the proposed packages first. Complete any OS
   authentication / vendor installer dialog. Progress appears in Setup. Successfully installed
   tools are searched again and their paths are filled automatically. Python build dependencies
   go into the selected virtual environment, or a private build environment if a system Python
   was selected. No root pip installation is used.
4. **Follow NEXT STEPS.** Check results say what remains to do. **Setup guide** has clickable
   official download pages and instructions. **Show tool paths and advanced options** reveals
   individual paths only when you need them. Files installed outside the searched locations
   may still need Browse; Studio does not scan your whole disk.
5. **Check setup → Save & apply.** Filled paths are not activated until saved. Settings are per
   user and reused on later launches. If only USB/COM is needed, a broken firmware toolchain
   does not block the serial monitor.

| Component | Automatic installation | Manual choice if still missing |
| --- | --- | --- |
| CMake ≥ 3.24, Git, Ninja/Make | Fedora/Ubuntu/Debian; CMake/Git/Ninja through WinGet on Windows | Use the vendor link in Setup guide, install the native version, then Find tools. For a portable copy, Browse to its executable. Keep the build generator matched to Ninja/Make. |
| Arm GNU **14.2.rel1** (compiler **14.2.1**) | Vendor download/selection required | Open Setup guide → Arm GNU. Choose target **arm-none-eabi**. Windows x64: `mingw-w64-x86_64` host package; Linux x64: `x86_64` host package. Install/extract the full archive, then Find tools or Browse to its root/bin folder. Do not choose an arbitrary newer release. |
| Native LLVM / libclang and headers | Fedora/Ubuntu/Debian; WinGet LLVM on Windows | Setup guide explains the native installation. Windows folder must contain `libclang.dll`; Python clang bindings alone are not enough. |
| EdgeTX Python packages | Install missing, after selecting a valid EdgeTX checkout | Usually no paths to type. The selected/new build Python is filled after a successful install; Save & apply. |
| Host C/C++ compiler | Fedora/Ubuntu/Debian packages | Windows needs a native compiler/SDK: use LLVM with a suitable Windows SDK or Visual Studio C++ tools. For MSVC select `VsDevCmd.bat` in advanced options. Arm GCC is not the host compiler. |
| dfu-util | Fedora/Ubuntu/Debian packages | Windows: Setup guide → dfu-util, extract the Windows binaries including companion DLLs, then Browse to `dfu-util.exe`. |
| USB DFU driver / serial permissions | Requires selecting the correct device/interface | Follow [USB and COM instructions](docs/SETUP.md#usb-dfu-and-serial-access). Windows DFU uses a compatible WinUSB driver; CDC/COM keeps its serial driver. Linux needs udev/group access. A successful tool check does not verify real USB access. |

Check setup and Build never start installers automatically. A missing item outside the supported
repair list stays visible with instructions. If a new Windows installation is not found, restart
Studio to refresh the process environment and use Find tools again.

## Get the EdgeTX source

Use [the SaolaLink EdgeTX fork, branch SAOLALINKV1](https://github.com/vinhphannn/edgetx/tree/SAOLALINKV1).
For a graphical clone, use GitHub Desktop on Windows or your Git client: clone the fork, switch to
**SAOLALINKV1**, and initialize the recorded submodules. Git command-line tools are still needed
by builds. A firmware source ZIP has no Git checkout/history and will fail those checks.

If your Git client does not offer submodule initialization, use its terminal once. These commands
work in a Git-equipped terminal on both systems; substitute your clone location:

```sh
git clone --branch SAOLALINKV1 --recurse-submodules https://github.com/vinhphannn/edgetx.git
# For an existing clone:
git -C /path/to/edgetx submodule update --init --recursive
```

In Setup, Browse to that clone; it does not have to sit beside Studio. A new checkout may need
network access again during the first CMake build. Updates to the two repositories are separate.

## Update or repair a Studio installation

Close Studio before updating. Git users can pull the Studio repository; ZIP users can extract a
fresh download into a new folder and run its launcher. Launch scripts refresh GUI requirements
when `requirements.txt` changes. If startup fails, its console shows the reason; see
[troubleshooting](docs/SETUP.md#launcher-troubleshooting). After moving EdgeTX/tools, use Setup
again. Machine-specific paths are never copied through Git.

Existing environment overrides remain supported: `EDGETX_DIR`, `SAOLALINK_BUILD_DIR` and
`ARM_TOOLCHAIN_DIR` (Arm root or bin). Remove a stale override if a saved path seems to revert.

## Firmware defaults

The GUI defaults to **DevEBox • 8 MHz** for the current bare
development board. CLI defaults to **SaolaLink V1** (12 MHz).
Both use `PCB=X7`, `PCBREV=SAOLALINK_V1` with separate build directories.
Pocket remains selectable as a reference. Debug and Release outputs are isolated:
`build/<profile>/<debug|release>/arm-none-eabi/`.
Build defaults: stick mode 2, English, LTO enabled (matching upstream Pocket builds),
complete bootloader-inclusive `.bin`. Debug keeps symbols but optimization/LTO can
inline functions and affect single-stepping.

## Workspaces

Four tabs separate the daily tasks. Large primary buttons stay visible; occasional
actions are one level under a named details/options section. The shared **Hardware
profile** selector applies to Build and Flash USB. It selects the physical board /
crystal, not a Git branch. It is hidden in Serial monitor and Setup.

- **Build**: **Build firmware**, **Build bootloader**, and **Clean build files**.
  Configuration/environment checks run automatically when building. The two build
  cards show whether their artifacts are ready. Paths, timestamps and hashes are
  under **Build files & verification details**. **Build options & developer tools**
  contains Debug/Release, Configure only, Compare with Pocket, the source path and
  a detailed workflow guide. The active mode is still visible beside the hardware.
- **Flash USB**: **Scan USB devices**, an explicit device selector, and two primary
  actions: **Flash firmware via USB** for everyday DevEBox application updates,
  and **Flash bootloader via DFU** for a first install/loader update through ROM DFU.
  Each card explains the board's entry sequence and why its button is unavailable
  when a build/device/mode is missing. Every real upload still requires confirmation
  and core artifact/device validation. Full-image ROM recovery is under
  **Recovery & USB details**. V1/Pocket firmware uploads currently use that ROM path.
- **Serial monitor**: scan COM/tty ports with device description and USB identity,
  select baud (115200 by default), connect/disconnect, receive logs and send UTF-8
  commands with None/LF/CRLF ending. Clear, save the visible log and toggle
  auto-scroll. RX/TX byte counts and dropped-chunk counts are shown. The display
  retains at most about 200,000 characters; export before old text is trimmed.
  Scanning never opens a device. DTR/RTS are requested low without an intentional
  reset pulse; driver/hardware behaviour during open can still vary.
- **Setup**: the single place for project folders, installed tools and machine
  diagnostics. Basic setup stays short; individual tool paths and exporting checks
  are under **Show tool paths and advanced options**. No duplicate Setup header button.

**Operation log** is collapsed by default on Build/Flash USB and expands on errors.
The status/progress indicator shows active work. **Stop current task** appears only
while a cancellable runner operation is active. Actions and hardware/mode selection
are disabled while a task is in progress. Serial monitor and Setup have their own
output areas. Runner logs are also saved in the configured build folder's `logs/`.

See [the step-by-step Build / USB / Serial workflow](docs/WORKFLOW.md) for the first
bootloader install, daily firmware edits, BOOT0/RTN sequences, Clean and recovery.
Compare with Pocket opens a secondary developer-report window; it is no longer a
main navigation tab. Its hardware/source/HAL comparisons and exports remain available.

Use Studio's **main** Git branch for the current app. **feat/portable-setup** is the
older setup-development branch. The firmware repository uses **SAOLALINKV1**;
changing the hardware dropdown does not switch that checkout's Git branch.

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

From the Studio folder after running its launcher (Windows uses `.venv\Scripts\python.exe`):

```bash
.venv/bin/python cli.py doctor
.venv/bin/python cli.py build --profile saolalink-v1 --mode Debug
.venv/bin/python cli.py build --profile pocket --mode Debug
.venv/bin/python cli.py build --kind bootloader
.venv/bin/python cli.py compare
.venv/bin/python cli.py devices
# Replace 1-2 with the exact path reported by devices:
.venv/bin/python cli.py flash --usb-path 1-2 --kind firmware
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
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover operation failure/cancellation, isolation, full-image flags, artifact
integrity and target mismatch, and multiple devices sharing one DFU VID/PID.

## Linux / Windows machine setup

Open the **Setup** tab on first launch or at any time. Browse to your
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
include the tool and a repair hint; **Export setup checks…** under advanced options saves a shareable report.

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
