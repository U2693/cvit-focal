# Ideas

## cvit / emulator UI

- `.STA` should keep moving toward real device status.
  - **Started:** COMMAND now asks the emulator-assisted cvit status service, and shows mounted/empty plus CVIT/FOREIGN for `H0`/`H1`.
  - Next: show write protection state per device.
  - Eventually expose this through a kernel status call rather than emulator assistance.

- Add commands to enable/disable writes to individual disks.
  - Example monitor/TUI commands: `WRITE H0 ON`, `WRITE H0 OFF`, `WRITE H1 ON`, `WRITE F0 OFF`.
  - Default generated/system images could mount read-only unless explicitly enabled.
  - `.STA` should show write protection state per device.
  - Useful for protecting `out/os.img` while allowing a work image such as `disks/work.img`.

- Add a toggleable `MUX1` overlay in the TUI.
  - When hidden, the normal CONSOLE has focus.
  - When visible, `MUX1` appears over the console and receives keyboard focus.
  - Provide a function-key/button-row toggle.
  - Keep CONSOLE output visible underneath or restore it when the overlay closes.
  - Later generalize to `MUX2`/`MUX3`.

- Fantasy peripheral: add a TMS9928A-style video card to biscvit.
  - Use an unused MMIO range for VDP data/control/status ports.
  - Emulate 16 KiB VRAM, VDP registers, address latch, status flags, and optional vblank interrupt.
  - Start with text/tile rendering in a toggleable TUI video overlay; later add sprites and richer graphics modes.
  - Add cvit demos such as `VDPDEMO` or monitor poke examples that display text/tiles.
  - Use the frame interrupt as a practical playground for CPU6 interrupt and future MMU experiments.

## A modern take on nursery rhymes
