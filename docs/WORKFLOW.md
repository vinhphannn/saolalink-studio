# Build and USB workflow

The four main tabs are Build, Flash USB, Serial monitor, and Setup.
Setup appears once in the navigation. Serial and Setup have their own output areas;
they do not show the build log or hardware selector.

## Hardware profiles are not Git branches

The hardware selector applies to Build and Flash USB together:

- DevEBox • 8 MHz: the current STM32F407 development board, with the adapted
  EdgeTX USB bootloader and application-only updates.
- SaolaLink V1 • 12 MHz: the standard SaolaLink target / crystal configuration.
- Pocket • reference hardware: the reference target for development comparisons.

Choose the profile matching the physical board before building or uploading.
Changing hardware clears the old USB selection; scan again for that board.
Debug is the initial build mode. The active mode is displayed beside the profile.
Change it under Build > Build options & developer tools. Different hardware/mode
combinations have separate build outputs; switching modes can require a new build.

Studio's main Git branch contains the current application. feat/portable-setup is
the older setup-development branch; new users should use main. Firmware work belongs
in the EdgeTX repository on branch SAOLALINKV1. Studio uses the checkout selected in
Setup and does not switch its Git branch for you.

## First machine setup

1. Run the Studio launcher. On first launch, Setup opens automatically.
2. Choose the EdgeTX Git checkout and a separate writable build output folder.
3. Find tools, then Install missing to review supported installers.
4. Follow NEXT STEPS and Setup guide for any remaining paths/vendor tools.
5. Check setup, then Save & apply. Select the actual board in Build.

See SETUP.md for tool downloads, per-machine paths, Python, USB drivers and permissions.

## Everyday firmware changes (DevEBox)

1. Make your changes in the EdgeTX checkout selected in Setup.
2. Open Build and verify DevEBox • 8 MHz and the displayed build mode.
3. Click Build firmware. Configuration and environment checks run automatically.
   The status/progress indicator shows the current task. Stop current task appears
   only while a cancellable build/configure/clean/upload is running.
4. Wait for Completed and the Firmware card's Ready status. Build files & verification
   details contains the binary path, timestamp, size and SHA256 if needed.
5. On the board set BOOT0=0. Hold RTN (PC5) while powering on or pressing RESET;
   then release RTN. This enters the installed EdgeTX USB loader.
6. Open Flash USB, click Scan USB devices and select the intended EdgeTX application
   loader. Multiple radios can share the same USB VID/PID; check the path/serial.
7. Click Flash firmware via USB. Review the hardware, build mode, selected USB
   device and file in the confirmation dialog, then confirm that upload.
8. Wait for completion and reset the DevEBox normally, without holding RTN.

This action uploads the application-only file and preserves the bootloader.
Build firmware prepares the full firmware, bootloader and application-only artifacts
for DevEBox, so it is not necessary to click Build bootloader after every firmware edit.
Older USB loaders may enter through PA0; install the updated loader through ROM DFU
once to use RTN. Uploading only a new application does not update the loader.

## Install or update the DevEBox bootloader

1. Choose DevEBox • 8 MHz and the required mode in Build.
2. Click Build bootloader and wait for its Ready status. A successful full DevEBox
   firmware build can also have prepared a verified bootloader.
3. On the board set BOOT0=1 and reset to enter STM32 ROM DFU.
4. In Flash USB, Scan USB devices and select the correct ROM DFU device.
5. Click Flash bootloader via DFU. Review the selected hardware/device and confirm.
6. Wait for completion, return BOOT0 to 0, and reset. The board can now use its
   EdgeTX USB loader for the everyday firmware flow above.

A standalone bootloader build must not be treated as a new application build.
After changing the bootloader, rebuild firmware if the previous linked application
artifact was invalidated. The UI reports when a new firmware build is required.

## Clean, recovery and advanced actions

- Clean build files is always visible in Build. It removes only the selected
  hardware/mode output, including its binaries/manifests. The EdgeTX and Studio
  sources remain available. Build again before uploading.
- Build > Build options & developer tools contains Debug/Release, Configure only,
  Compare with Pocket, the source path and this guide. Configure only does not
  produce a verified flashable binary. Compare opens a separate report window.
- Flash USB > Recovery & USB details contains Flash full image via ROM DFU.
  This replaces both application and bootloader; use a successful matching full
  firmware build. V1/Pocket currently use this path for firmware uploads; their
  application-only EdgeTX USB upload is not configured in Studio.
- ROM DFU writes bootloader/full image at 0x08000000. The DevEBox EdgeTX loader
  uploads application-only at 0x08008000. Studio validates these routes and artifact
  hashes again when uploading; an enabled button is not a replacement for validation.
- Operation log is collapsed by default on Build and Flash USB. Open it for full
  command output. It opens automatically on task failure. Each runner operation
  also writes a log file under the configured build output's logs directory.

## Serial monitor

1. Boot the application normally and connect its USB CDC / USB-UART interface.
2. Open Serial monitor > Scan ports. Choose the actual COM/tty device and baud.
3. Click Connect. For EdgeTX CLI use LF and send help or devboard.
4. Receive/send logs normally; Clear, Save log and Auto-scroll stay in the terminal.
5. Disconnect before changing machine setup. Switching between DFU and application
   modes can change the port number; scan again after the board reconnects.

An empty USB DFU scan is different from an empty serial scan. For driver/udev/group
access or a busy port, follow SETUP.md. Scanning never flashes or opens a serial port.
