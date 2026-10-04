# Task: add the CPU6 MMU to biscvit

## Goal

biscvit (`Program.cs`, class `Cpu6`) currently emulates a flat 64 KiB machine: `mem` is a 65,536-byte array indexed directly by the 16-bit address. Give it the paged MMU that the Centurion CPU6 has, so CVIT can use 256 KiB of RAM.

The reference for behaviour is the CenturionJS emulator (https://github.com/DracoDrake/CenturionJS), files `src/cards/CPU6Card.ts` and `src/cards/CPU6/CPU6.ts`. Where this brief and that source disagree, follow the source and say so in your report.

The hard constraint: **everything that boots and runs today must still boot and run unchanged.** With the reset mapping, logical addresses `0x0000-0xEFFF` are identity-mapped, so existing CVIT code must see no difference until it executes an MMU instruction.

## The model to implement

- **Physical memory** is 256 KiB (`0x00000-0x3FFFF`), which is 128 pages of 2 KiB.
- **Page table**: 8 banks x 32 entries, one byte per entry, 256 bytes total. An entry is a physical page number.
- **Translation**: `physical = (table[bank * 32 + (addr >> 11)] << 11) | (addr & 0x07FF)`.
- **Low-memory bypass**: logical addresses below `0x0100` never go through the MMU. They are the CPU card's 256-byte register file (the per-interrupt-level registers), the same in every bank.
- **Unmapped physical addresses** (an entry of `0x80` or above yields an address past `0x3FFFF`): reads return `0xFF`, writes are ignored.
- **Reset**: every bank maps pages 0-29 to physical pages 0-29, page 30 to `0x7E`, page 31 to `0x7F`. Bank 0 is selected.

## Steps

### 1. Split storage

- Replace `mem` with a 256 KiB physical array and a separate 256-byte register-file array.
- Add the 256-byte page table and a current-bank field (0-7).
- In `Reset(ushort pc)`: clear the register file (as the current `Array.Clear(mem, 0, 0x100)` does), load the reset mapping into all eight banks, and select bank 0.

### 2. Route every memory access through translation

`Read8` and `Write8` are the choke points for CPU access. Restructure them as:

1. If `a < 0x0100`, use the register file and return.
2. Translate `a` to a physical address through the current bank.
3. Decode devices on the **physical** address, then fall through to physical RAM.

Device addresses move to physical page `0x7E`/`0x7F`, i.e. add `0x30000` to each existing constant: MUX `0xF200/0xF201/0xF208/0xF209/0xF20A/0xF20E` become `0x3F200...`, Hawk/floppy `0xF140-0xF148` become `0x3F140...`, FFC `0xF800/0xF801` become `0x3F800/0x3F801`. Under the reset mapping the logical addresses are unchanged, so existing code keeps working, and software that remaps pages 30-31 correctly loses access to I/O.

`Reg()`, `InterLevelAddr` and friends address `(ipl << 4) | reg`, which is below `0x0100`, so they need no change once step 1 of `Read8`/`Write8` is in place. Verify this rather than assume it.

There are about a dozen direct `mem[...]` uses and several `Buffer.BlockCopy` calls that bypass `Read8`/`Write8`. Find all of them (`grep -n "mem\b"`) and convert each one. None may index the physical array with a logical address. Specifically:

- **`Load(bytes, address)`**, the floppy boot copy to `0x0100`, and the `RunSystemMember`/`TypeSystemMember` copy to `0x0100`: write through the current bank, byte by byte or page by page.
- **SVC handlers and debugger code** that read command lines or dump memory (`mem[(ushort)(line + i)]`, `DebugDump`, the disassembler, deposit): read through the current bank, without device side effects. Add a side-effect-free `PeekLogical(ushort)` for this; reading `0xF201` through a debug dump must not dequeue a terminal character.
- **`Peek`/`Poke`** (used by the TUI): keep them logical through the current bank. Add `PeekPhysical(int)` for a future physical-memory view.

### 3. DMA transfers

`dmaAddr` is 16 bits and the Hawk, floppy and FFC transfers currently `BlockCopy` straight into `mem`. Change them to treat `dmaAddr` as a logical address translated through the **current bank at the time of the transfer**, copying in chunks that do not cross a 2 KiB page boundary. Keep the existing "crosses memory end" checks on the logical address. This preserves today's behaviour exactly under the identity map.

### 4. MMU instructions

Opcode `0x2E` is followed by a sub-opcode byte:

| Bytes | Name | Effect |
|---|---|---|
| `2E 0C bb hh ll` | LDMMU | Copy 32 bytes from logical address `hhll` into bank `bb & 7` |
| `2E 1C bb hh ll` | STMMU | Copy the 32 entries of bank `bb & 7` to logical address `hhll` |

- The 32 source/destination bytes are accessed through the bank that is current when the instruction executes.
- For LDMMU, read all 32 bytes into a temporary buffer first and then commit them, so loading the active bank cannot change the mapping halfway through the copy.
- The new mapping takes effect on the next fetch.
- No flags change.

**Existing behaviour to preserve.** `Misc8` currently handles `0x2E` as a two-byte instruction that loads a small constant into a register pair (`SetRegPair((e & 15) >> 1, e >> 5)`). Before changing it, search the CVIT sources and the `cpu6asm` assembler for anything that emits `0x2E`. If existing code relies on that form with a second byte other than `0x0C` or `0x1C`, keep the old behaviour for those values and add the two MMU forms alongside it. If nothing uses it, follow CenturionJS: any other sub-opcode consumes just that one byte and does nothing. Report which case you found.

### 5. Bank selection: do not wire up opcodes yet

On CenturionJS the active bank changes only through `JSYS` (`66 nn`) and `RSYS` (`0F`). In biscvit both opcodes already mean something else: `0x66` is the host-trapped `SVC` that CVIT's shell depends on, and `0x0F` is an interrupt-return variant. Do **not** change either opcode in this task.

Instead:

- Add an internal `SetMmuBank(int)` / `MmuBank` on `Cpu6`.
- Leave interrupt entry and return alone; they do not change the bank.
- List in your report every place in the CVIT sources that emits `0x66` or `0x0F`, so the owner can decide how bank switching should be exposed.

### 6. Debugger and disassembler

- Update both disassemblers (the `inst = "LDM"` case in the TUI and the one that prints `66 nn SVC`) to show `LDMMU b,(addr)` and `STMMU b,(addr)` as five-byte instructions.
- Add the current bank to the register displays (`PrintRegs`, `DebugRegs`).
- Add a way to dump the page table for one bank or all eight from the debugger/TUI.

## Verification

Add these as automated tests if the project has a test harness; otherwise add a `--selftest` path that runs them and exits non-zero on failure. Run them, and include the output in your report.

1. **Reset map.** After reset, STMMU of each bank yields `00 01 ... 1D 7E 7F`.
2. **Identity.** A byte written to logical `0x4000` is at physical `0x04000`.
3. **High pages.** A byte written to logical `0xFE00` is at physical `0x3FE00`.
4. **Remap.** Load a table into bank 0 with entry 8 set to `0x40`; a write to logical `0x4000` now lands at physical `0x20000`, and physical `0x04000` is unchanged.
5. **Round trip.** STMMU after LDMMU returns the same 32 bytes.
6. **Bypass.** With entry 0 remapped, addresses `0x0000-0x00FF` still read and write the register file, and `0x0100-0x07FF` follow the new mapping.
7. **I/O follows the page.** With entry 30 remapped to a RAM page, a write to logical `0xF201` produces no terminal output.
8. **Unmapped.** With an entry of `0x80`, reads return `0xFF` and writes change nothing.
9. **DMA.** A Hawk sector read into a remapped page lands at the remapped physical address, including a transfer that crosses a page boundary into a differently mapped page.
10. **Regression.** CVIT boots from the Hawk image to the `]` prompt, and `CAT`, `TYPE WELCOME`, `HELP` and `.DEBUG` behave as before. The floppy boot path still works.

## Out of scope

- Bootstrap and diagnostic ROMs.
- Changing the meaning of `0x66` or `0x0F`.
- Changes to the CVIT kernel or shell sources, beyond reading them to answer the questions above.

## Report back

- What changed, by area.
- Test results for all ten checks.
- Which `0x2E` case you found (legacy form in use or not).
- Every emitter of `0x66` and `0x0F` in the CVIT sources.
- Anything in CenturionJS that contradicted this brief.
