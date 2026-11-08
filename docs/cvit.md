# cvit personality

cvit is the planned Apple ProDOS-inspired personality for the custom Hawk
boot path.  It is not a disk-format clone; it borrows ProDOS' user model and MLI
shape while using the native 400-byte Disk6/Hawk layout in `docs/hawk-layout.md`.

## Kernel/member split

- `SYSTEM/KERNEL`: resident kernel loaded by sector 0 at `0x0800`.
- `SYSTEM/COMMAND`: command interpreter, analogous to `BASIC.SYSTEM`/shell.
- `SYSTEM/BASIC`: later BASIC personality/runtime.
- `SYSTEM/CED`: resident CED-style line editor, entered as `.CED` during bring-up.
- `HELP/*`: staged source-tree location for a future second library (`H0:HELP`).

## Kernel jump table

The kernel image starts with absolute jump vectors so loaded programs can call a
stable API without knowing internal addresses:

| Offset | Vector |
| --- | --- |
| `0800` | `cold_start` |
| `0803` | `warm_start` |
| `0806` | `syscall` |
| `0809` | `quit` |
| `080C` | `read_block` |
| `080F` | `write_block` |
| `0812` | `open` |
| `0815` | `close` |
| `0818` | `read` |
| `081B` | `write` |
| `081E` | `get_file_info` |
| `0821` | `set_file_info` |
| `0824` | `create` |
| `0827` | `destroy` |
| `082A` | `rename` |
| `082D` | `set_prefix` |
| `0830` | `get_prefix` |

For now, KERNEL provides the boot/banner, COMMAND loader path, and a first
`read_block` implementation for 400-byte Disk6 floppy sectors via the FFC. The
`syscall` vector is entered by `SVC $40`; `AX` is the function selector and `BX`
points to a function-specific control block. Other unimplemented vectors print
`?UNIMPL` and return during bring-up.

### `read_block` Disk6 control block

Jump/call vector `080C` with `BX` pointing at:

| Offset | Meaning |
| --- | --- |
| `+0` | FFC unit (`0` for `F0:`) |
| `+1` | track |
| `+2` | sector within track |
| `+3` | head |
| `+4` | destination address, big-endian u16 |

The vector reads one 400-byte sector into the destination and returns the FFC
result in `AL` (`0` on success). For the default 20-sector Disk6 geometry,
logical sector `N` maps to `track=N/20`, `sector=N%20`, `head=0`.

## System call ABI

Programs call cvit services with:

```text
AX      function selector
BX      control block pointer
SVC $40
```

Initial selectors:

| AX | Function | Control block |
| --- | --- | --- |
| `0001` | console putc | `CB+0`: byte character, displayed on the current terminal |
| `0002` | Disk6 read block | same control block as `read_block` vector |

Unknown selectors currently print `?SVC` and return.

## User model

Prompt and paths should feel Apple-ish:

```text
cvit V0.1
]PREFIX /SYSTEM
]CAT
]RUN COMMAND
```

Preferred path syntax:

```text
/SYSTEM/KERNEL
/SYSTEM/COMMAND
/SYSTEM/BASIC
/BIN/HELLO
```

## Fully-qualified file names

A cvit FQFN is:

```text
[device:][path/]name
```

Device names are case-insensitive:

| Device | Meaning |
| --- | --- |
| `H0:` | Hawk platter 0 |
| `H1:` | Hawk platter 1 |

Rules during bring-up:

- Missing device means the current/default device, initially `H0:`.
- `H0:ZEP` or `H1:ZEP` means member `ZEP` in the current prefix, initially `/SYSTEM`.
- `/SYSTEM/ZEP` is an absolute cvit path on the current device.
- `H1:/SYSTEM/ZEP` is fully qualified: device plus absolute path.
- Names are stored uppercase in the current SYSTEM library; member names remain limited to 10 characters by the current Hawk directory row format.
- Whitespace around CED commands is ignored, but whitespace inside file names is not part of the planned syntax.

Examples:

```text
.CED H1:ZEP
CED:W
Wrote H1:ZEP

.CED H0:/SYSTEM/TEST
CED:P5,9
```

## Executable convention

Flat binaries can remain during early bring-up, but cvit executables should
move toward a small header:

```text
magic      "CV"
load_addr  u16
entry_addr u16
size       u16/u24
type       byte    ; SYS/BIN/TXT/BAS/DIR equivalent
```

## Milestones

1. Boot banner, stable jump table, ProDOS-style prompt. **Done.**
2. Console `putc`/`puts`/`getc` routines.
3. Hawk `read_block`/`write_block` wrappers over native 400-byte sectors. **Started:** `CAT` reads sector `0x20` directly.
4. Read `SYSTEM` library and list members with `CAT`. **Started:** host-assisted catalog reads rows until the `84 8D` terminator, including extended directories on newly built images (see `hawk-layout.md`).
5. `TYPE name` demo: a text member is read from Hawk and displayed on the console. **Done for existing SYSTEM members such as `WELCOME`, `TEST`, and `ZEP`.**
6. Load and run `SYSTEM/COMMAND`. **Done:** KERNEL loads COMMAND at `0x3000` and jumps to it.
7. Interactive COMMAND loop. **Started:** supports `PREFIX [device:/path]`, `CAT`/`CATALOG [prefix]` (including `H0:`/`H1:`), `TYPE WELCOME`, `RUN NAME` for flat `$0100` SYS members, `HELP`, `PANEL` for a CPU6 front-panel view of run state, PC, flags, IPL, and registers, native `.STA`, `.DEBUG`, `.CED`, `.KEYS`, and `QUIT`.
8. Resident debugger. **Started:** `.DEBUG` enters a monitor shell. `R` displays registers, `X $NNNN` examines/dumps memory, `DNNNN` deposits bytes until `.`, `U $NNNN` disassembles memory, and placeholders remain for breakpoints, single-step, mini-assembler, and quit.
9. CED editor. **Started:** `.CED [file]` enters a CED-style line editor with `CED:` prompt, loads existing text from the active file, and defaults to `/SYSTEM/TEST`. Whitespace in commands is ignored; `A` appends auto-numbered text lines until a blank line or `.`; `P5,9` or `5,9P` prints lines 5-9, `DISPLAY` defaults to the current terminal, numeric input sets/deletes lines, `W` writes the active member, creating a one-sector TXT preallocation if needed, `W file` switches/writes a member (for example `H1:ZEP`), and `Q` exits.
