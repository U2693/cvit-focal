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

## cvit OS

biscvit ships with **cvit**, a small ProDOS-inspired OS for the Hawk disk:

```sh
python3 scripts/mk_test_os.py       # builds out/os.img
python3 scripts/mk_data_img.py      # builds formatted scratch/work platter out/data.img
scripts/bis --hawk out/os.img       # boots to the ] prompt; try CAT, TYPE WELCOME, HELP
scripts/bis --hawk out/os.img --hawk1 out/data.img  # H1: scratch/self-hosting platter
scripts/hawk_export_tmp.py out/data.img              # export to a Windows-friendly temp dir
scripts/hawk_to_iso.sh out/data.img out/data.iso      # build a Windows-mountable ISO using nix/xorriso
```

See `docs/cvit.md` for the cvit spec. Other notes: `docs/assembler.md`, `docs/focal.md`,
`docs/centos-notes.md` (booting the real OS image, opcode findings) and `docs/bignum-notes.md` (the `0x46` bignum instructions).

Options: `--load file addr`, `--pc addr`, `--sp addr`, `--boot-rom file`, `--type text`, `--trace`, `--floppy-trace`, `--floppy image`, `--hawk image`/`--hawk0 image`, `--hawk1 image`, `--floppy-sector-size n`, `--floppy-sectors-per-track n`, `--floppy-heads n`, `--floppy-tracks n`, `--hawk-sector-size n`, `--hawk-sector-stride n`, `--hawk-sectors-per-track n`, `--hawk-heads n`, `--hawk-image-offset n`, `--boot-floppy`, `--halt`, `--run`, `--max n`. The TUI starts running by default; use `--halt` to start paused.

Experimental: `--ffc-linear-experimental` makes the FFC shim treat track/sector command bytes as one 16-bit linear block address. Do not use it for normal floppy booting; FDIPL uses floppy CHS addressing.

Devices: console MUX status/data at `F200/F201`, MUX1 status/data at `F208/F209`, simple floppy registers at `F140-F145`, Hawk drive registers at `F140-F148` when `--hawk` is mounted, and a bootstrap-compatible FFC shim at `F800/F801` supporting command DMA (`43`) and execute (`45`).

TUI: the view is a console screen with a function-key button row. Console focus is active by default; typed printable keys feed reads from `F201`. `F12` toggles a MUX1 overlay/focus using `F208/F209`. Buttons: `F1` run/pause, `F2` step, `F3` step 100, `F4` clear HALT, `F5` reset CPU, `F6` breakpoint, `F10` quit. Writes to MMIO `F201` appear in the console; writes to `F209` appear in MUX1.
