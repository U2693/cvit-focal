# biscvit

A small C# terminal UI emulator/monitor for the Centurion CPU6, based on the public experimental CPU6 monitor in `../CenturionComputer/boots/cpu6.cs` and related references.

## Run

```sh
dotnet run --project biscvit -- --load program.bin 0100 --pc 0100
```

Options: `--load file addr`, `--pc addr`, `--sp addr`, `--boot-rom file`, `--type text`, `--trace`, `--floppy image`, `--floppy-sector-size n`, `--floppy-sectors-per-track n`, `--floppy-heads n`, `--floppy-tracks n`, `--boot-floppy`, `--run`, `--max n`.

Devices: MUX terminal status/data at `F200/F201`, simple floppy registers at `F140-F145`, and a bootstrap-compatible FFC shim at `F800/F801` supporting command DMA (`43`) and execute (`45`).

TUI keys: `Alt-=` or `Esc =` toggle terminal focus, `s` step, `r` run/pause, `n` step 100, `+`/`-` adjust run speed, `[`/`]` adjust refresh rate, arrows/page scroll memory, `home` follow PC, `g` goto, `m` edit memory bytes, `p` set PC, `b` breakpoint, `l` load binary, `q`/F10 quit. Writes to MMIO `F201` appear in the terminal pane; typed printable keys feed reads from `F201`.
