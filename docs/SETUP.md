# Machine setup — Linux and Windows

Each member can keep Studio, EdgeTX, build output and tools in separate folders.
Machine settings are stored per user, outside both Git repositories:

- Linux: `$XDG_CONFIG_HOME/SaolaLinkStudio/settings.json`, or `~/.config/SaolaLinkStudio/settings.json`.
- Windows: `%APPDATA%\SaolaLinkStudio\settings.json`.
- Optional override: `SAOLALINK_CONFIG` points to a different settings JSON file.

The app opens Setup on first run, an unreadable settings file, or a missing EdgeTX checkout.
You can always open Setup from the header or its tab. A broken build setup does not prevent
using the serial monitor. Settings are not shared through Git; install the tools for each OS.

## Install and start Studio

Use Python 3.10 or newer. Installing Studio's GUI dependencies is necessary before launching Setup.
After Studio starts, **Setup → Install missing…** can install supported missing build tools and
Python packages with a review step. Checking setup or pressing Build never installs anything.

Linux, from your Studio checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Fedora needs `python3-tkinter`; Ubuntu/Debian need `python3-tk` for Tk.
If already using a workspace-level virtual environment, you can keep using it.

Windows PowerShell, from your Studio checkout:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

No PowerShell activation or execution-policy change is needed. Use Python with Tcl/Tk installed.
A separate Python environment may be selected for firmware builds.

## Choose paths, then Save & apply

1. EdgeTX checkout: select the repository root containing CMakeLists.txt and radio/.
   Use the company's SaolaLink fork and branch, not an unrelated upstream target:
   https://github.com/vinhphannn/edgetx/tree/SAOLALINKV1
   Initialize submodules with `git submodule update --init --recursive`.
2. Build output folder: choose a writable folder OUTSIDE the EdgeTX and Studio source trees.
   Prefer a short Windows path, such as `C:\sl-build`. Clean removes only the selected board/mode output.
3. Arm GNU: select the installation root or bin directory for **14.2.rel1**;
   the compiler must report **14.2.1**. Windows tools must be native Windows .exe files.
4. CMake: select cmake/cmake.exe, version >= 3.24.
5. Git: select git/git.exe.
6. Generator and build tool: Ninja with ninja/ninja.exe is recommended on both systems.
   Unix Makefiles, MinGW Makefiles and NMake Makefiles are also supported when their matching
   build tool and host environment are installed. Do not use a multi-configuration Visual Studio generator.
7. Build Python: select the Python executable whose environment contains EdgeTX's Python packages.
   For a virtual environment select bin/python (Linux) or Scripts/python.exe (Windows), not just its directory.
8. dfu-util: select dfu-util/dfu-util.exe. Keep companion libusb DLLs from the Windows distribution with it.
9. LLVM: on Windows, select the folder containing libclang.dll (normally LLVM/bin).
   On Linux, use your distribution's libclang installation; a custom library folder is added to
   LD_LIBRARY_PATH. Check setup runs the selected EdgeTX checkout's libclang loader, so a successful
   load confirms the actual loader behavior. The checkout's own search order still applies.
10. Optional native C and C++ compilers: select host compilers, not the Arm cross-compiler.
    Linux can normally use cc/c++. Windows can use Visual Studio's clang/clang++ or MSVC.
    For a Visual Studio toolchain, select its Common7/Tools/VsDevCmd.bat to import the x64 SDK/toolchain
    environment inside Studio. Alternatively start Studio from a prepared x64 Developer terminal.
    Selecting cl.exe alone does not supply the Windows SDK or linker environment.
11. Library prefixes: optional CMake installation prefixes separated by semicolons. For example Qt/SDL
    prefixes matter for native EdgeTX targets; they are not replacements for Python packages or libclang.
12. Dependency cache: optional shared folder for CMake FetchContent downloads.
    The first build may need network access to fetch dependencies.
13. Preferred serial port and baud: optional defaults, never an automatic connection.
    Select the actual COM/tty device after scanning; port numbers can change between machines.

Use Detect tools to populate tools found on PATH, then review the form. It does not download anything.
Check setup checks the form values. Save & apply activates and persists them. Changing configuration
is blocked during an operation or an active serial connection. Disconnect and wait for tasks first.

## Install missing components from the GUI

1. Choose your EdgeTX checkout and paths in Setup.
2. Click **Install missing…**. Studio checks the form and opens a list of proposed installations
   and remaining issues. You can close the list without changing anything.
3. Click **Install & recheck** to run the listed installers. Complete the operating system's
   administrator authentication or publisher installer dialog if one opens. Progress and errors
   appear in Setup. Studio never asks for or stores administrator passwords.
4. Review the recheck and updated paths, then **Save & apply**. If a newly discovered dependency
   is still missing, use Install missing again to review the next repair.

Supported system repairs:

- Fedora: CMake, Git, Ninja/Make, host GCC/G++, dfu-util and `clang-devel` (native libclang and headers).
  Uses only the official `fedora` and `updates` repositories for this transaction, with signature
  checking enabled; it does not change saved repository configuration.
- Ubuntu/Debian: the equivalent packages through the configured APT repositories. Package indexes
  must already be usable. Linux installation requires `pkexec` and a working desktop Polkit agent.
  If authentication is cancelled or unavailable, Setup reports that and stops.
- Windows: CMake, Git, Ninja and LLVM through installed WinGet, with exact package IDs and the
  publisher's interactive installers. The review states that Install accepts the WinGet source
  and package agreements. Restart Studio if Windows has not exposed new tools on PATH yet.
- Missing EdgeTX Python modules: install the selected checkout into the chosen build virtual
  environment. If Build Python is a system Python, Studio creates a private virtual environment
  under its per-user cache folder instead of modifying system Python. On Debian/Ubuntu this may
  require the distribution's matching Python venv package first.

An install can fail due to network, repository or version issues. The actual recheck determines
readiness; an installer exiting successfully does not guarantee the whole build environment works.
Keep Studio open during installation. Stop task applies to builds, not package transactions.

Some setup still needs a selection or a vendor installer: the Arm compiler must be **14.2.rel1**,
the EdgeTX checkout/submodules must exist, and USB drivers/permissions need the correct interface.
These appear as remaining issues in the review; Studio does not replace USB drivers or install a
different Arm release. Download Arm GNU from
https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads and Browse to its root/bin.
Other Linux distributions, Windows without WinGet, and custom toolchains retain manual path setup.

## Install EdgeTX Python build packages

Prefer **Install missing…** to avoid terminal commands. For manual installation, run pip using the
SAME Python selected as Build Python. Substitute your actual paths:

Linux example:

```sh
/path/to/build-venv/bin/python -m pip install -e /path/to/edgetx
```

PowerShell example (quotes allow spaces):

```powershell
& 'D:\Build Tools\venv\Scripts\python.exe' -m pip install -e 'D:\Firmware\edgetx'
```

Check setup checks both the modules and whether EdgeTX can initialize libclang. Installing the
Python clang bindings alone does not install the native LLVM/libclang library and builtin headers.

## USB DFU and serial access

Check setup enumerates devices but does not open a serial connection or program flash.
An empty scan means no matching device was found at that moment, not that all USB drivers are verified.
Actual serial permission/busy errors are reported when you explicitly connect.

Linux: arrange udev access for STM32 USB DFU (0483:df11). Serial access commonly uses dialout
or uucp depending on the distribution. Check the device permissions and group membership;
log out/in after group changes. Avoid running the whole Studio application as root.

Windows: STM32 ROM/EdgeTX DFU needs a libusb-compatible driver (commonly WinUSB).
If using Zadig, select only the intended STM32 DFU interface. USB CDC/COM and USB-UART bridges
use their serial driver: do not replace the COM interface's driver with WinUSB.
Install your CH340/CP210x/other bridge driver if the manufacturer requires it.

Close other applications holding the serial port. DFU mode is not a COM port. Native USB CDC may
appear/disappear when switching between firmware and bootloader modes; rescan and select again.

## Repair setup and command-line use

Open Setup after moving a checkout, changing tools, or seeing a missing-tool error. Use Check setup
and Export checks to collect readable diagnostics for another team member. No build is started by
checking setup. Save & apply switches the displayed artifact and clears the old DFU selection.

The GUI and CLI share settings. Explicit CLI flags take precedence over the saved settings.
Legacy EDGETX_DIR, SAOLALINK_BUILD_DIR and ARM_TOOLCHAIN_DIR environment variables override
saved settings when loading them. Remove stale environment overrides if saved paths seem to revert.
The Setup tab displays a notice when these overrides are active.

```sh
python cli.py setup
python cli.py setup --source /path/to/edgetx --build-dir /path/to/output --toolchain /path/to/arm/bin --save
python cli.py doctor --scope build
python cli.py doctor --scope flash --scan
python cli.py doctor --scope serial --scan
python cli.py setup --config /path/to/settings.json --save
```

Use quoted native paths on Windows. Tools are launched as argument lists, without a shell;
spaces in checkout/tool paths do not require embedding quote characters into Setup fields.
An invalid JSON settings file can be repaired through Setup or `cli.py setup ... --save`.
Review a failed check before building; drivers and all real-device behavior still require hardware testing.

When upgrading an existing workspace, auto-detection preserves its previous CMake generator.
If you change generators or move EdgeTX while reusing output, Studio reports incompatible caches
before configuring. Choose the affected board/mode and use Build → Clean, or select a new output
folder in Setup. Checking setup never deletes previous firmware artifacts.
