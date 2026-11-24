# CVIT FOCAL

A stand-alone FOCAL interpreter for the Centurion CPU6, distributed as a bootable Hawk disk image: `cvit-focal.img`.

Boot chain: Hawk IPL, then a small bare-metal kernel, then FOCAL. No Centurion OS is required. The kernel serves the console and the CVIT filesystem directly (catalog, load, save, run), so a FOCAL program can be saved to the disk image and loaded back in a later session.

## Try it in a browser (no install)

1. Download `cvit-focal.img` from the releases page.
2. Open the Meisaka Centurion emulator: https://eciv.net/meisaka/cen/cen.html
3. Attach the image to the Fixed drive. Leave the Diag Select switches at zero and the Diag ROMs option unchecked.
4. Run, click CRT0, and at the `D=` prompt type `H1` and press Enter.

The kernel banner appears, then the FOCAL banner and the `*` prompt. Ask for the catalog of saved files:

```
*.cat

NAME TYPE
KERNEL SYS
CATALOG SYS
EGG SYS
FOCAL SYS
```

## Run it locally with biscvit

This repo also contains biscvit, the CPU6 emulator that CVIT FOCAL was developed on. With nix, `nix develop` provides the dotnet SDK.

Build the disk image:

```sh
python3 scripts/build_stage2.py        # writes out/stage2.img
```

Boot it. Bare-metal mode lets the kernel serve everything itself:

```sh
dotnet run -- --bare-metal --boot-rom roms/bootstrap_unscrambled.bin --hawk out/stage2.img --run
```

At the `D=` prompt type `H0` and press Enter.

The bootstrap ROM is Centurion firmware and is not included in this repo; place the unscrambled bootstrap at `roms/bootstrap_unscrambled.bin`. The browser route above needs no ROM file.

## FOCAL on the CPU6

- Decimal floating point (7-digit mantissa), plus FABS, FSGN, FITR, FSQT
- Subscripted variables; X and X(0) are the same variable
- Dot commands at the `*` prompt:

| command | effect |
| --- | --- |
| `.cat [library]` | list saved files (default library /SYSTEM) |
| `.save NAME` | save the current program |
| `.load NAME` | load a saved program |
| `.run NAME` | load a program and start it |
| `.help` | the built-in command summary |

Binary members run with `!NAME`. Try `!EGG`, or `!CATALOG`, a small client of the kernel catalog service.

## For user programs: the kernel API

The kernel exposes a jump table at 0x0800 and a set of supervisor calls, so machine-language programs can use kernel services instead of driving the hardware directly:

- SVC 0x40: console character I/O (BL = function, AL = character)
- SVC 0x52: catalog (command string at 0x2F00)
- SVC 0x56: run a member
- SVC 0x57: load a member
- SVC 0x58: save a member

The CATALOG member in the image is the worked example: a user program whose only job is to call SVC 0x52. See docs/bare-metal-plan.md section 7 for the design notes.

## Also in this repo

- **biscvit**, the emulator: a C# terminal UI emulator and monitor for the CPU6. Options include --load, --pc, --sp, --boot-rom, --type, --trace, --hawk / --hawk0 / --hawk1, --floppy, --bare-metal, --run, --max. Devices: MUX console at F200/F201, MUX1 at F208/F209, Hawk registers at F140-F148.
- **cvit OS**, the earlier COMMAND-style system for the Hawk disk (the `]` prompt). See docs/cvit.md.

## Docs

- docs/focal.md: the FOCAL dialect and the dot commands
- docs/bare-metal-plan.md: kernel design, the bare-metal stages, and the API direction
- docs/assembler.md: the CPU6 assembler used by the build scripts
- docs/bignum-notes.md and docs/centos-notes.md: hardware and OS research notes

## Known issue

Saving from FOCAL works in biscvit in both hosted and bare-metal modes, verified byte-identical disk images. On the Meisaka microcode core, kernel SAVE currently shows a layout-dependent fault that is under investigation; loading and running work there. biscvit is the reference platform.

## License

MIT. See LICENSE.
