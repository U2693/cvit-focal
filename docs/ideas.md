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

## A modern take on nursery rhymes
