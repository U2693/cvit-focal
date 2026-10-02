# biscvit

A small C# terminal UI emulator/monitor for the Centurion CPU6, based on the public experimental CPU6 monitor in `../CenturionComputer/boots/cpu6.cs` and related references.

## Run

```sh
dotnet run -- --load program.bin 0100 --pc 0100
```

Common boot scripts:

```sh
./scripts/boot.sh       # bundled bootstrap + floppy image; sends F0\r
./scripts/boot_hawk.sh  # bundled bootstrap + Hawk image; sends H0\r
```

Options: `--load file addr`, `--pc addr`, `--sp addr`, `--boot-rom file`, `--type text`, `--trace`, `--floppy-trace`, `--floppy image`, `--hawk image`, `--floppy-sector-size n`, `--floppy-sectors-per-track n`, `--floppy-heads n`, `--floppy-tracks n`, `--hawk-sector-size n`, `--hawk-sector-stride n`, `--hawk-sectors-per-track n`, `--hawk-heads n`, `--hawk-image-offset n`, `--boot-floppy`, `--run`, `--max n`.

Experimental: `--ffc-linear-experimental` makes the FFC shim treat track/sector command bytes as one 16-bit linear block address. Do not use it for normal floppy booting; FDIPL uses floppy CHS addressing.

Devices: MUX terminal status/data at `F200/F201`, simple floppy registers at `F140-F145`, Hawk drive registers at `F140-F148` when `--hawk` is mounted, and a bootstrap-compatible FFC shim at `F800/F801` supporting command DMA (`43`) and execute (`45`).

TUI keys: `Ctrl-Tab`, `Alt-=` or `Esc =` toggle terminal focus, `s` step, `r` run/pause, `n` step 100, `c` clear HALT, `Ctrl-R` reset CPU, `+`/`-` adjust run speed, `[`/`]` adjust refresh rate, arrows/page scroll memory, `home` follow PC, `g` goto, `m` edit memory bytes, `p` set PC, `b` breakpoint, `l` load binary, `q`/F10 quit. Writes to MMIO `F201` appear in the terminal pane; typed printable keys feed reads from `F201`.
