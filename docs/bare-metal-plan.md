# Bare-Metal FOCAL: Implementation Plan

Status: plan only, nothing built yet. Written 2026-11-23 at Randall direction.
Scope: the stage-2 system (Hawk IPL, kernel, FOCAL) with no emulator host
services. Companion docs: focal.md, bootable-hawk.md, hawk-layout.md,
cvit-filesystem.html, interrupt-guide.html.

## 0. What bare-metal means here

Today biscvit intercepts four SVCs in the emulator host: 0x40 (console),
0x56 (RUN a binary member), 0x57 (LOAD), 0x58 (SAVE). FOCAL and its dot
commands depend on all four. Bare-metal means the kernel serves every one
of them with CPU6 code, on the metal and, as the proving step, inside
biscvit with host interception switched off. The on-disk format does not
change: an image written by the bare-metal kernel must read in biscvit
and the other way round.

## 1. Where we stand

- Console putc: host serves 0x40 fn 1. A kernel version already exists in
  the kernel syscall (jump table at 0x0806), but with a control-block ABI
  (function in AX, block pointer in BX, block saved at 0x2EFE). FOCAL uses
  the host register ABI instead: BL = function, AL = char, EX = string
  pointer for fn 2, char returned in AL for fn 3.
- Console fn 2 (print NUL-terminated string) and fn 3 (getc): host only.
  The hardware model is MUX0 at 0xF200 (status: bit 0 RX ready, bit 1 TX
  ready) and 0xF201 (data). The addresses come from WIPL reverse
  engineering, not from a board manual.
- LOAD and SAVE: host only. FocalLoad and FocalSave in Program.cs walk
  the FOCAL slots at 0x8000 and convert to and from numbered text lines;
  CvitFileSystem does directory scan, member lookup, and writes.
- RUN (0x56, the FOCAL bang command): host only (RunSystemMember).
- Hawk read: the kernel already drives the controller at 0xF140..0xF148
  directly (emit_hawk_read in cvit/src/hawk.py); cold start loads FOCAL
  with it. Hawk write: modelled in the emulator (DMA, ExecuteHawkCommand)
  but the kernel write_block vector is an ?UNIMPL stub, as are all the
  file-level vectors (open, close, read, write, create, destroy, rename,
  set_prefix, get_prefix).
- SVC on the metal is JSYS: the CPU pushes map, IPL, X, and the argument,
  switches to map 0, and enters at 0x0100; RSV returns. The emulator
  fallthrough already models this for SVCs it does not intercept. No
  kernel-owned handler sits at 0x0100 yet.
- The kernel read_block in the jump table is the Disk6 variant. The
  stage-2 boot path is Hawk. Which device the filesystem sits on has to
  be one answer, and for stage 2 it is Hawk.

## 2. Decisions to rule before building

- D1, one console ABI. RULED 2026-11-23 (Randall): the register shape.
  The kernel 0x40 ABI is BL = function, AL = char, EX = string pointer,
  char back in AL for getc. The control-block dispatcher stays at the
  0x0806 jump-table slot for direct callers from the COMMAND world;
  the ruling covers who answers the SVC instruction.
- D2, where LOAD and SAVE live. RULED 2026-11-23 (Randall): option A.
  The kernel owns 0x57 and 0x58 exactly as the host does today,
  slots-to-text conversion included. FOCAL needs zero changes; the
  proven host semantics move as-is. RUN (0x56) is kernel work as well.
- D3, memory and MMU. RULED 2026-11-23 (Randall): option 1, single map.
  Everything lives in map 0: JSYS door at 0x0100, kernel at 0x0800,
  FOCAL at 0x5000, slots at 0x8000; the JSYS map switch is ceremonial.
  The handler switches to a private kernel stack on entry and leaves
  the caller stack balanced for RSV. JSYS and RSV behaviour on silicon
  stays on the verify list.
- D4, console input. RULED 2026-11-23 (Randall): option 1, polled getc
  (spin on 0xF200 bit 0, read 0xF201). No type-ahead beyond the UART
  holding register for v1. The choice is invisible across the ABI:
  MUX interrupts with a per-port ring buffer (enables at 0xF20A and
  0xF20E) can slot in behind getc later without FOCAL knowing.

## 3. Stages

- ME-0, host-off switch. Add a biscvit flag (name it --bare-metal) that
  stops host interception of 0x40, 0x56, 0x57, 0x58 so those SVCs take
  the real JSYS path. Exit: a stage-2 boot in bare-metal mode reaches the
  kernel door and prints ?SVC, and the test harness can run both modes.
- ME-1, JSYS door and console. Kernel handler at 0x0100 dispatching 0x40
  fn 1, 2, 3 in the register ABI, with a correct RSV return. Exit: in
  bare-metal mode stage 2 boots to the star prompt, typed lines echo,
  TYPE and FOR probes run, QUIT prints BYE.
  DONE 2026-11-23. The door is a jmp_abs at 0x0100 that cold start
  installs over the first bytes of the bootstrap ROM (512 bytes,
  resident at 0x0100; IPL has already run by then). The dispatcher
  saves A/B/EX, reads the svc byte from the caller stack, switches
  to a kernel stack at 0x2000, serves fn 1/2/3 polled on
  0xF200/0xF201, answers anything else ?SVC, restores A last (after
  ferrying SP home) and returns via RSV. Found on the way: the ROM
  leaves SP at 0x1000, and the kernel grown by this stage reaches
  0x0FFD, so cold start now moves SP to 0x2000 before anything
  pushes. Verified bare-metal: banner, prompt, echo, TYPE/FOR
  probes, program run, .save/.load give ?SVC with the session
  alive, QUIT gives BYE. Normal mode unchanged; test_focal 15/15.
- ME-2, Hawk write_block. Port the write command sequence from the
  emulator Hawk model into cvit/src/hawk.py beside emit_hawk_read and
  wire the kernel write_block vector. Exit: a kernel probe writes a
  sector and reads it back byte-identical in bare-metal mode.
  DONE 2026-11-23. hawk.py gained emit_hawk_write (immediate form,
  command 1) and the control-block pair emit_hawk_read_block /
  emit_hawk_write_block: BX points at +0 u16 sector, +2 u16 buffer;
  AL returns the F144 status byte and the routine never halts. The
  stage-2 kernel now uses the Hawk pair for both block vectors (the
  Disk6 FFC read_block stays in the stock kernel for the COMMAND
  world; the stage-2 syscall fn2 convention changes with it). Probe
  scripts/test_me2.py: word i = i pattern written to sector 6000,
  buffer zeroed, read back, all 200 words compared: WRITE READBACK
  OK in bare-metal and normal modes. test_focal still 15/15.
- ME-3, filesystem read path. Port directory scan, DX header handling,
  member lookup, and gap-derived capacity from CvitFileSystem to kernel
  code on read_block. Exit: dot-load of MANDEL works in bare-metal mode
  and WRITE lists it back unchanged.
  DONE 2026-11-23. cvit/src/fsload.py ports the host FocalLoad
  contract to kernel code: path parse (LOAD/OAD prefix, H0:/H1:,
  prefix/member split), /SYSTEM and /HELP libraries, DX directory
  scan in two passes (member page, then gap-derived capacity),
  member staging at 0x3000, CV-header length rule, slot conversion
  identical to the host (key rule, 61-char bodies, 128 slots). The
  dispatcher routes SVC 0x57 to it and now saves/restores DX as
  well. Two findings along the way: (1) the boot ROM does its HDIPL
  work with SP = 0x1000 and pushes through 0x0FE0-0x0FFF before
  cold start runs, so build_kernel2 aligns past 0x1000 and asserts
  that window stays padding; (2) the JSYS handler originally
  switched to SP = 0x2E00, the same top FOCAL inherits, so a deep
  handler call chain (fs_scan to hawk_busy) overwrote the JSYS
  frame on the caller stack and RSV popped a corrupted IPL byte;
  the CPU6 register file is IPL-banked, so FOCAL resumed with all
  registers reading zero. The handler stack is now private at
  0x2C00 (D3 made literal). Verified bare-metal: dot-load and
  statement LOAD of PROG1 and BIG1 (WRITE byte-identical to the
  host load, runs match), repeated statement LOAD, ?NO FILE with
  the program preserved, bare LOAD gives ?LOAD WHAT, /HELP and
  unknown prefixes give ?NO FILE. ME-2 probe and test_focal
  15/15 still green.
- ME-4, filesystem write path and RUN. Port WriteTextMember semantics,
  including the 2026-11-22 allocator (size at creation, relocate on
  regrow, append-only UAL), plus the 0x56 RUN loader. Exit: the full
  scripted stage-2 session (help, save, load, run, bang-egg, QUIT) is
  green with host services off, and test_focal stays green in normal
  mode.
  DONE 2026-11-23. cvit/src/fssave.py serves 0x58 (full
  WriteTextMember semantics: create at ceil(len/400) sectors,
  relocate on regrow, append-only UAL, 0x20 fill, host error
  strings) and 0x56 (CV-header and raw members, JSR-style frame
  planted above the JSYS frame so the member RSR returns into
  FOCAL). SAVE, LOAD, and RUN share one parser (fssave
  emit_fs_parse) and fsload fs_scan/fs_stage/fs_libset; the scan
  also records row positions for the write path. Room came from
  a loop-based load_focal in build_stage2; the kernel ends at
  0x2EFF with a build assert below 0x2F20, and a traced SAVE
  session shows the private stack (top 0x2F40) bottoming at
  0x2F36. Strongest check: the same scripted session (create
  BIG1, create PROG1, grow PROG1 past capacity) run in normal
  mode and in bare-metal mode produces byte-identical disk
  images. That test caught one bug: the serializer held its
  body pointer in Z across putc, and the Hawk block routines
  clobber Z on a sector flush; the pointer now lives in a cell
  (w_bptr). Also verified bare-metal: bang-egg prints HELLO
  FROM EGG and returns to the prompt, ?SAVE WHAT, ?NO LIBRARY
  on SAVE, create and load in /HELP, the 2.05 line-key
  round-trip under the shared parser, repeated statement LOAD.
  ME-2 probe and test_focal 15/15 still green. The raw-member
  RUN path is implemented to host semantics but untested (no
  raw test member exists yet).
- ME-5, hardware bring-up. Console first light (banner on the real
  terminal), then the prompt, then save and load on the real Hawk.
  Exit: the Sierpinski carpet runs from a dot-load on hardware.
  STATUS 2026-11-23: redirected to the Meisaka web emulator (no
  hardware access). First light achieved: the unmodified image boots,
  the console door serves the prompt, LOAD and RUN verify against the
  microcode core. SAVE found two faults. (1) The DSK2 write-protect
  mask (register +3) was never set, so protocol writes were silently
  discarded; fixed in hawk.py (wpmask 0xFF before write commands) and
  proven by the ME-2 probe. (2) OPEN: inside w_write a single value
  corrupts in a layout-dependent way on the microcode core: most
  builds halt at PC 0 after allocation and the directory row land but
  before the data flush; some builds complete but flush to a wrong
  sector. Dead never-executed bytes flip the outcome, and the same
  kernel is byte-parity correct on biscvit, so this is treated as an
  emulator fidelity fault, not a kernel bug. Exit test (carpet from a
  dot-load) still ahead; LOAD works there, so a biscvit-baked image
  can carry it.

## 4. Open hardware questions (verify, never assume)

- MUX addresses, status bits, and baud configuration on the real board.
- Hawk register, command, and status semantics on the controller, and
  real sector geometry versus the 400-byte payload convention the image
  files use.
- The HDIPL load address and entry contract versus the stage-2 image
  layout (KERNEL sits at sector 0x24 in the built image).
- JSYS and RSV stack and map behaviour on silicon.
- Whether the Disk6 read_block stays for the COMMAND world or the file
  vectors converge on Hawk everywhere.

## 5. Non-goals

- COMMAND and CED stay host-served; this plan covers the FOCAL system.
- No FOCAL language changes. TYPE percent formats, TYPE dollar, and
  bracket synonyms stay parked.
- No on-disk format changes.
- Multiple sessions. Randall, 2026-11-23: a future thing, not this
  plan. Expect it to press on D3 (per-session slot areas in one map)
  and D4 (per-port buffering) when it comes.

## 6. Risks

- Kernel size. The filesystem port is the big code mass, and the kernel
  shares low memory with a hard boundary at FOCAL (0x5000). Measure at
  ME-3; if the port outgrows the space, the load layout gets revisited
  before the semantics do.
- State placement. Filesystem state goes in a fixed kernel workspace.
  The Nova page-zero squeeze is the standing warning against letting it
  sprawl.
- ABI drift. Two console ABIs already exist. ME-1 must land exactly one
  for the FOCAL world, or every later stage inherits the confusion.
