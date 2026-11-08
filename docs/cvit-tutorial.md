# Learning cvit

cvit is a small ProDOS-flavoured OS for the emulated Centurion CPU6, booted
from a Hawk disk image.  This page gets you from nothing to a running prompt,
then shows how programs talk to the kernel.  The design spec is `cvit.md`.

## 1. Build and boot

```sh
python3 scripts/mk_test_os.py          # writes out/os.img (and os/*.bin)
scripts/bis --hawk out/os.img          # boots it in the TUI
```

You need the .NET SDK and `roms/bootstrap_unscrambled.bin`.  `scripts/bis`
types `H0\r` at the bootstrap prompt for you (override with `BOOT_KEYS`).
The project targets .NET 9; use `nix develop` for the .NET SDK.

In the TUI, switch to terminal focus (`Ctrl-Tab`, `Alt-=` or `Esc =`) to type
at cvit; `q`/F10 quits the emulator when not in terminal focus.

Headless (no TUI interaction), useful for scripting:

```sh
scripts/bis --hawk out/os.img --run --max 3000000 --type 'H0\rCAT\rQ\r'
```

## 2. A first session

```text
cvit V0.1
COPYRIGHT (C) 2026 BISCVIT

cvit COMMAND V0.1
TYPE HELP FOR COMMANDS

]CAT

NAME       TYPE
KERNEL     SYS
WELCOME    TXT
FOCAL      BIN
COMMAND    SYS

]TYPE WELCOME
WELCOME TO cvit
THIS TEXT WAS LOADED FROM /SYSTEM/WELCOME.
]QUIT
BYE
```

| Command | What it does |
| --- | --- |
| `CAT` | List members of the `SYSTEM` library |
| `TYPE WELCOME` | Display the `WELCOME` text member |
| `RUN name` | Load and run an executable member, e.g. `RUN FOCAL` |
| `.STA` | Show system status |
| `HELP` | List commands |
| `QUIT` | Jump to the kernel `quit` vector, print `BYE`, halt |

See `cvit.md` for the current command and filesystem capabilities.

## 3. What is real and what is stubbed

| Area | State |
| --- | --- |
| Boot: ROM -> Hawk sector 0 -> `KERNEL` at `0800` -> `COMMAND` at `3000` | works |
| Console `putc`/`puts`/`getc` via `SVC $40` | works |
| `CAT`, `TYPE WELCOME` (read straight from Hawk sectors) | works |
| `read_block`, `write_block`, `open`, `close`, `read`, `write`, file info, `create`, `destroy`, `rename`, prefix calls | stubs: print `?UNIMPL` and return |
| `RUN` of `CV` executables (such as `FOCAL`) | works |
| FOCAL interpreter (integers; see `focal.md`) | works |

## 4. Calling the kernel

Programs use `SVC $40` with a function number in `BL` (it is clobbered):

| BL | Function | In | Out |
| --- | --- | --- | --- |
| 1 | `putc` | `AL` = char | |
| 2 | `puts` | `Z` (EX) = NUL-terminated string | unchanged |
| 3 | `getc` | | `AL` = char, or zero if none is available |

The same routines are in the jump table at `0833`/`0836`/`0839`; the full
table is in `cvit.md`.

With the assembler in `scripts/cpu6asm.py`, "hello" looks like this (this is
how `COMMAND` prints its banner):

```python
a.lda_label("msg").xaz()   # Z = &msg
a.ldbb_i(2).svc(0x40)                        # puts
a.rsr()
a.label("msg")
a.raw(*b"HELLO\r\n\x00")
```

and echoing a key:

```python
a.ldbb_i(3).svc(0x40)    # getc -> AL
a.ldbb_i(1).svc(0x40)    # putc AL
```

To make a program `RUN`-able, give it the 9-byte `CV` header described in
`cvit.md`, end it with `RSR`, and add it as a member.  `scripts/build_hello.py` generates an example at `out/hello.bin`. Add it to a
SYSTEM library with room for another member, then run `RUN HELLO`. The default image already includes HELLO; newly built images reserve room
for additional members.

For a bigger example, `RUN FOCAL` and read `focal.md`.
