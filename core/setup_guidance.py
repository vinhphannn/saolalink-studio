"""Plain setup instructions shared by check results and the in-app guide."""
GETTING_STARTED = (
    ('1. Choose your project', 'Browse to the EdgeTX Git checkout (the folder containing CMakeLists.txt and radio). '
     'Choose a writable build output folder. The two projects can be anywhere on this computer.'),
    ('2. Find and install tools', 'Click Find tools to fill installed tool paths. Click Install missing to review and '
     'install supported missing components. After installation, paths are filled automatically. '
     'Use Show tool paths only for a custom installation or a missing item.'),
    ('3. Check and save', 'Click Check setup and follow Next steps for any errors. When ready, click Save & apply. '
     'Settings are remembered on this computer. Choose your board in Build before building; Flash and COM scanning '
     'are separate operations.'),
)

DOWNLOADS = (
    ('EdgeTX source', 'https://github.com/vinhphannn/edgetx/tree/SAOLALINKV1',
     'Use the SaolaLink fork, branch SAOLALINKV1, as a Git clone with submodules. A source ZIP has no Git history '
     'and cannot pass all build checks. Browse to the clone root. See README for GitHub Desktop and Git instructions.'),
    ('Arm GNU 14.2.rel1', 'https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads',
     'Select the archived 14.2.rel1 release, target arm-none-eabi (not aarch64-none-elf or arm-none-linux-gnueabihf). '
     'Windows x64: mingw-w64-x86_64 package; Linux x64: x86_64 package. Run the vendor installer or extract the entire '
     'archive into your tools folder. Find tools searches common tools/Downloads locations. If needed, Browse to '
     'the extracted root or bin folder; the compiler must report 14.2.1.'),
    ('CMake', 'https://cmake.org/download/', 'Prefer Install missing. Manual install: choose a stable native installer '
     '(CMake >= 3.24). On Windows choose x64 and enable the installer PATH option. Then Find tools.'),
    ('Git for Windows', 'https://git-scm.com/downloads/win', 'Needed for the EdgeTX checkout and submodules. '
     'Install Git for command-line use, then Find tools. On Linux prefer Install missing.'),
    ('Ninja', 'https://github.com/ninja-build/ninja/releases', 'Prefer Install missing. For a portable package, extract '
     'the native binary and Browse to ninja/ninja.exe under Show tool paths. Keep the generator set to Ninja. '
     'Keep an existing Make generator unless you clean its old build cache.'),
    ('LLVM / libclang', 'https://github.com/llvm/llvm-project/releases', 'Prefer Install missing. On Windows use the '
     'native LLVM installer containing bin/libclang.dll; Find tools will look in LLVM/bin. On Linux install the '
     'distribution libclang development package with builtin headers. Python clang bindings alone are insufficient.'),
    ('dfu-util', 'https://dfu-util.sourceforge.net/releases/', 'Prefer Install missing on Linux. On Windows download '
     'a Windows binary package, extract the whole package including its DLLs, then Browse to dfu-util.exe. '
     'The USB driver is configured separately.'),
    ('Windows USB driver', 'https://zadig.akeo.ie/', 'Only if required for STM32 DFU: select the STM32 DFU interface '
     'and its WinUSB-compatible driver. Keep the CDC/COM interface on its serial driver. For Linux USB permissions '
     'and detailed driver instructions, see the full setup reference.'),
    ('WinGet / App Installer', 'https://learn.microsoft.com/en-us/windows/package-manager/winget/',
     'If Install missing cannot find WinGet, install/update Microsoft App Installer, restart Studio, and retry. '
     'Alternatively use the vendor links above and Find tools after installation.'),
)


def next_steps(checks):
    failed = {check.name for check in checks if check.status == 'error'}
    steps = []
    if 'EdgeTX checkout' in failed or 'Git checkout' in failed:
        steps.append('Select the SaolaLink EdgeTX Git clone root, not Studio or a source ZIP. Open Setup guide > EdgeTX source.')
    if failed & {'Arm compiler', 'Arm tools'}:
        steps.append('Open Setup guide > Arm GNU 14.2.rel1. Install/extract that release, then Find tools or Browse to its root/bin.')
    if failed & {'Submodules', 'Submodule revisions'}:
        steps.append('Initialize the recorded EdgeTX submodules. See README > Get the EdgeTX source; then Check setup again.')
    repairable = failed - {'EdgeTX checkout', 'Git checkout', 'Arm compiler', 'Arm tools', 'Submodules', 'Submodule revisions'}
    if repairable:
        steps.append('Click Install missing to review available repairs. If an item has no automatic installer, '
                     'open Setup guide for its download/selection instructions and use Show tool paths.')
    if failed:
        steps.append('After fixing the listed items: Find tools > Check setup > Save & apply.')
    else:
        steps.append('No setup errors found. Save & apply, then open Build. An empty device scan simply means no device was detected.')
    return '\n'.join(f'{number}. {text}' for number, text in enumerate(steps, 1))
