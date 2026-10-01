# ProDOS-6 personality

ProDOS-6 is the planned Apple ProDOS-inspired personality for the custom Hawk
boot path.  It is not a disk-format clone; it borrows ProDOS' user model and MLI
shape while using the native 400-byte Disk6/Hawk layout in `docs/hawk-layout.md`.

## Kernel/member split

- `SYSTEM/KERNEL`: resident kernel loaded by sector 0 at `0x0800`.
- `SYSTEM/COMMAND`: command interpreter, analogous to `BASIC.SYSTEM`/shell.
- `SYSTEM/BASIC`: later BASIC personality/runtime.

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

For now, only the console/banner path is implemented; unimplemented vectors print
`?UNIMPL` and halt/return during bring-up.

## User model

Prompt and paths should feel Apple-ish:

```text
PRODOS-6 V0.1
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

## Executable convention

Flat binaries can remain during early bring-up, but ProDOS-6 executables should
move toward a small header:

```text
magic      "P6"
load_addr  u16
entry_addr u16
size       u16/u24
type       byte    ; SYS/BIN/TXT/BAS/DIR equivalent
```

## Milestones

1. Boot banner, stable jump table, ProDOS-style prompt.
2. Console `putc`/`puts`/`getc` routines.
3. Hawk `read_block`/`write_block` wrappers over native 400-byte sectors.
4. Read `SYSTEM` library and list `KERNEL`, `COMMAND`, `BASIC` with `CAT`.
5. Load and run `SYSTEM/COMMAND`.
