# Bootable Hawk drive candidates

Likely bootable Hawk/platter images live under `../CenturionComputer/Software/Data Packs/`.

Strong candidates:

- `../CenturionComputer/Software/Data Packs/CENTOS_11.IMG`
- `../CenturionComputer/Software/Data Packs/CENTOS_12.IMG`
- `../CenturionComputer/Software/Data Packs/CENTOS_13.IMG`
- `../CenturionComputer/Software/Data Packs/HWKRPL2.IMG`
- `../CenturionComputer/Software/Data Packs/HWKRPL3.IMG`
- `../CenturionComputer/Software/Data Packs/MINOS.IMG`
- `../CenturionComputer/Software/Data Packs/HWKFIX.IMG`
- `../CenturionComputer/Software/Data Packs/HAWK_DAVE.IMG`

Related duplicates/variants:

- `../CenturionComputer/Software/Disassembler/CENTOS_12_HWKRCV.IMG`
- `../CenturionComputer/Software/Disassembler/Platters/HWKRPL2.IMG`

## Why these look bootable

Most are about `6.65 MB`, likely Hawk platter images.  String scans show `HDIPL` near the beginning and, for several images, operating-system strings such as `@LOAD`, `READY`, and `MONITOR`.

`../CenturionComputer/docs/wipl.md` identifies the CPU6 WIPL/HDIPL image as the Hawk Disk IPL.  These images contain `HDIPL` rather than only `FDIPL`, so they are better Hawk boot candidates than the floppy images.

Quick scan results from the first 200 KB, high bit masked:

```text
CENTOS_11.IMG                 HDIPL @LOAD READY MONITOR
CENTOS_12.IMG                 HDIPL @LOAD READY MONITOR
CENTOS_13.IMG                 HDIPL @LOAD READY MONITOR
CPU5FIX.IMG                   HDIPL READY CEN
CPU5PLT.IMG                   HDIPL READY CEN
HAWK_DAVE.IMG                 HDIPL FDIPL @LOAD READY MONITOR
HWKFIX.IMG                    HDIPL @LOAD READY CEN
HWKRPL2.IMG                   HDIPL @LOAD READY MONITOR
HWKRPL3.IMG                   HDIPL @LOAD
MINOS.IMG                     HDIPL @LOAD READY MONITOR CEN
CENTOS_12_HWKRCV.IMG          HDIPL @LOAD READY MONITOR
Disassembler/Platters/HWKRPL2 HDIPL @LOAD READY MONITOR
```

Suggested starting order:

1. `CENTOS_12.IMG`
2. `HWKRPL2.IMG`
3. `MINOS.IMG`
4. `HAWK_DAVE.IMG`
