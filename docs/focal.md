# FOCAL on cvit

`RUN FOCAL` starts a small FOCAL-69-flavoured interpreter (`SYSTEM/FOCAL`, about 2.5 KB,
source in `scripts/focal.py`).  Numbers are **16-bit signed integers**.  `QUIT` returns to
the cvit `]` prompt.

```text
]RUN FOCAL

CVIT FOCAL V0.1
*1.1 ASK "N? ",N
*1.2 FOR I=1,N; TYPE I*I,!
*1.3 TYPE "DONE",!
*GO
N? 5
1
4
...
```

## Lines and modes
- A line starting with a number `G.SS` is stored (`1.1` means `1.10`; keys 0.01-99.99, 128 lines of up to 60
  characters); a number alone deletes the line.  Anything else runs immediately.
- Several commands per line are separated by `;`.  Commands are matched by their first letter,
  and the rest of the word is ignored (`T`, `TYPE`, `TYPEOUT`).

## Commands
| Command | Meaning |
| --- | --- |
| `TYPE items` | Items separated by `,`: `"text"`, `!` (CR LF), `#` (CR), or an expression (printed in decimal). `%` format specs are skipped. |
| `SET v=expr` | Assign a variable (`A`-`Z`, single letters, initially 0) |
| `ASK ["prompt",] v` | Read an expression from the terminal (prompt `:` if no string) |
| `IF (expr) a,b,c` | Go to line `a`, `b` or `c` for negative, zero, positive; a missing/blank target continues |
| `GO [n]` | Jump to line `n` (next existing line at or after it); `GO` alone runs from the first line |
| `DO n` | Call line `n.SS`, or every line of group `n` (`DO 2`); `RETURN` ends the call |
| `FOR v=a[,step],end; commands` | Loop; the commands are the rest of the line.  Negative steps count down |
| `RETURN` | End a `DO` (or the program) |
| `WRITE` | List the program in line order |
| `ERASE` | Delete all lines |
| `COMMENT text` | Ignore the rest of the line |
| `QUIT` | Leave FOCAL |

## Expressions
`+ - * /` with the usual precedence, unary `-`, parentheses, numbers and variables.  `/` truncates
toward zero.  Arithmetic wraps at 16 bits.  Errors: `?SYNTAX`, `?DIV0`, `?FULL` (all 128 line slots
used).  An error aborts the current run and returns to the `*` prompt.

## Not (yet) in this FOCAL
Floating point, named/array variables (`X(1)`), `FSIN`/`FSQT` and other functions, `^`, `MODIFY`,
`LIBRARY`, `TYPE $`, `%` output formatting, line-number-less `IF` forms, and saving programs.

## Implementation notes
- Register use: `Z` = text pointer, `A`/`B` = scratch and expression results, `Y` = scratch/`MULU` operand.
  The link register `X`/RT is never used for data because `MULU`/`DIVU` are done on `A:B`.
- Values and `FOR`/`DO` frames are on the hardware stack; the program is stored as 64-byte slots at
  `0x8000-0x9FFF`, so there is no memory shifting; "next line" is a scan for the smallest greater key.
- Memory: code at `0x5000`; line buffers at `0x7000`/`0x7060`; variables `0x70C0`; interpreter state `0x7100`.
- Tests: `python3 scripts/mk_test_os.py && python3 scripts/test_focal.py`.
