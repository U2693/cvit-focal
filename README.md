# biscvit

A small C# terminal UI emulator/monitor for the Centurion CPU6, based on the public experimental CPU6 monitor in `../CenturionComputer/boots/cpu6.cs` and related references.

## Run

```sh
dotnet run --project biscvit -- --load program.bin 0100 --pc 0100
```

Options: `--load file addr`, `--pc addr`, `--sp addr`, `--floppy image`, `--floppy-sector-size n`, `--floppy-sectors-per-track n`, `--floppy-heads n`, `--floppy-tracks n`, `--boot-floppy`, `--run`, `--max n`.

TUI keys: `s` step, `r` run/pause, `n` step 100, `+`/`-` adjust run speed, arrows/page scroll memory, `home` follow PC, `g` goto, `m` edit memory bytes, `p` set PC, `b` breakpoint, `l` load binary, `q`/F10 quit. Writes to MMIO `F201` appear in the terminal pane; typed printable keys feed reads from `F201`.
