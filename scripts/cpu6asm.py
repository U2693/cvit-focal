"""Tiny CPU6 assembler with label support, automatic branch relaxation and symbols.

Encodings come from the HDIPL 6.2 listing (wipl.asm), the Centurion wiki
(https://github.com/Nakazoto/CenturionComputer/wiki/Instructions) and the biscvit
emulator.  Register pairs are A,B,X,Y,Z,S,C,P (biscvit calls X/Y/Z/S/C/P
RT/DX/EX/SP/GX/HX); byte registers are AH,AL,BH,BL,... .

Features
  * Labels (``NAME+4`` / ``NAME-7`` also accepted as operands), ``equ`` constants and ``var`` scratch-memory allocation.  Any 16-bit
    operand may be an int or a symbol name (label / equ / var).
  * Relative branches and ``jmp``/``jsr`` (rel8) relax automatically: a branch
    out of range becomes an inverted short branch over a ``jmp``/absolute jump.
  * Data directives: db, dw, ascii, asciz, ds, align.
  * page_safe=True: NOP-pad instructions so none straddles a 256-byte page.
  * listing() / symbols() for debugging.

Relative branches are relative to the next instruction.
"""

import re

PAIRS = {"A": 0, "B": 1, "X": 2, "Y": 3, "Z": 4, "S": 5, "C": 6, "P": 7}
BREGS = {n + h: i * 2 + j for i, n in enumerate("ABXYZSCP") for j, h in enumerate("HL")}
BRANCH_INVERSE = {0x10: 0x11, 0x11: 0x10, 0x12: 0x13, 0x13: 0x12, 0x14: 0x15, 0x15: 0x14,
                  0x16: 0x17, 0x17: 0x16, 0x18: 0x19, 0x19: 0x18}
JMP_REL, JSR_REL, JMP_ABS, JSR_ABS = 0x73, 0x7B, 0x71, 0x79


def pair(r):
    return r if isinstance(r, int) else PAIRS[r.upper()]


def breg(r):
    return r if isinstance(r, int) else BREGS[r.upper()]


class AsmError(Exception):
    pass


class Asm:
    def __init__(self, org, page_safe=False):
        self.org = org
        self.items = []          # ('b', bytes) ('lbl', name) ('ref', prefix, sym) ('rel', op, sym) ('align', n, fill)
        self._labels = set()
        self.syms = {}           # equ / var symbols
        self.var_ptr = None
        # page_safe (ME-5): the microcode CPU in the Meisaka emulator
        # mis-executes instructions that straddle a 256-byte page
        # boundary (proven on w_write stores; see docs/bare-metal-plan.md).
        # When enabled, _layout NOP-pads so no instruction item crosses.
        self.page_safe = page_safe
        self._instr = set()
        self._pads = {}

    # -- low level -----------------------------------------------------
    def raw(self, *b, data=False):
        self.items.append(("b", bytes(b)))
        if not data:
            self._instr.add(len(self.items) - 1)
        return self

    def u16(self, v):
        if isinstance(v, str):
            self.items.append(("ref", b"", v))
        else:
            self.items.append(("b", bytes([(v >> 8) & 255, v & 255])))
        return self

    def label(self, name):
        if name in self._labels or name in self.syms:
            raise AsmError(f"duplicate symbol {name!r}")
        self._labels.add(name)
        self.items.append(("lbl", name))
        return self

    def _op16(self, op, v):
        """Opcode followed by a 16-bit big-endian operand (int or symbol)."""
        if isinstance(v, str):
            self.items.append(("ref", bytes([op]), v))
        else:
            self.items.append(("b", bytes([op, (v >> 8) & 255, v & 255])))
        self._instr.add(len(self.items) - 1)
        return self

    def _rel(self, op, label):
        self.items.append(("rel", op, label))
        self._instr.add(len(self.items) - 1)
        return self

    def _abs16(self, op, label):
        return self._op16(op, label)

    # -- symbols -------------------------------------------------------
    def equ(self, name, value):
        if name in self._labels or name in self.syms:
            raise AsmError(f"duplicate symbol {name!r}")
        self.syms[name] = value
        return value

    def vars_at(self, addr):
        self.var_ptr = addr
        return self

    def var(self, name, size=2):
        if self.var_ptr is None:
            raise AsmError("call vars_at(addr) before var()")
        addr = self.var_ptr
        self.equ(name, addr)
        self.var_ptr += size
        return addr

    # -- data directives ------------------------------------------------
    def db(self, *vals):
        for v in vals:
            if isinstance(v, (bytes, bytearray)):
                self.raw(*v, data=True)
            elif isinstance(v, str):
                self.raw(*v.encode(), data=True)
            else:
                self.raw(v & 255, data=True)
        return self

    def dw(self, *vals):
        for v in vals:
            self.u16(v)
        return self

    def ascii(self, text):
        return self.raw(*(text.encode() if isinstance(text, str) else text), data=True)

    def asciz(self, text):
        return self.ascii(text).raw(0)

    def ds(self, n, fill=0):
        return self.raw(*([fill] * n), data=True)

    def align(self, n, fill=0):
        self.items.append(("align", n, fill))
        return self

    # -- layout / output ------------------------------------------------
    @staticmethod
    def _rel_sizes(op):
        """(short, long) byte sizes of a relaxable item."""
        if op in (JMP_REL, JSR_REL):
            return 2, 3
        return 2, 5

    def _layout(self):
        long = set()
        pads = {}
        for _pass in range(500):
            addrs, labels, pc = [], {}, self.org
            pending = []
            for i, it in enumerate(self.items):
                k = it[0]
                if k == "lbl":
                    pending.append(i)
                    addrs.append(pc)
                    continue
                pc += pads.get(i, 0)
                for j in pending:
                    labels[self.items[j][1]] = pc
                    addrs[j] = pc
                pending = []
                addrs.append(pc)
                if k == "b":
                    pc += len(it[1])
                elif k == "ref":
                    pc += len(it[1]) + 2
                elif k == "rel":
                    pc += self._rel_sizes(it[1])[i in long]
                elif k == "align":
                    pc += -pc % it[1]
            for j in pending:
                labels[self.items[j][1]] = pc
                addrs[j] = pc
            table = dict(self.syms)
            table.update(labels)
            changed = False
            for i, it in enumerate(self.items):
                if it[0] == "rel" and i not in long:
                    tgt = self._resolve(table, it[2])
                    disp = tgt - (addrs[i] + 2)
                    if not -128 <= disp <= 127:
                        long.add(i)
                        changed = True
            if self.page_safe:
                for i in self._instr:
                    it = self.items[i]
                    k = it[0]
                    if k == "b":
                        size = len(it[1])
                    elif k == "ref":
                        size = len(it[1]) + 2
                    elif k == "rel":
                        size = self._rel_sizes(it[1])[i in long]
                    else:
                        continue
                    if size < 2:
                        continue
                    base = addrs[i] - pads.get(i, 0)
                    need = -base % 256 if (base % 256) + size > 256 else 0
                    if pads.get(i, 0) != need:
                        pads[i] = need
                        changed = True
            if not changed:
                self._pads = pads
                return addrs, table, long
        raise AsmError("layout did not converge")

    @staticmethod
    def _resolve(table, sym):
        """Resolve NAME, NAME+N or NAME-N (N decimal or 0x..)."""
        if sym in table:
            return table[sym]
        m = re.fullmatch(r"([A-Za-z_]\w*)\s*([+-])\s*(0x[0-9A-Fa-f]+|\d+)", sym)
        if m and m.group(1) in table:
            n = int(m.group(3), 0)
            return (table[m.group(1)] + (n if m.group(2) == "+" else -n)) & 0xFFFF
        raise AsmError(f"undefined symbol {sym!r}")

    @property
    def labels(self):
        return self._layout()[1]

    def bytes(self):
        addrs, table, long = self._layout()
        out = bytearray()
        for i, it in enumerate(self.items):
            k = it[0]
            if k != "lbl":
                out += bytes([1]) * self._pads.get(i, 0)
            if k == "b":
                out += it[1]
            elif k == "ref":
                v = self._resolve(table, it[2])
                out += it[1] + bytes([(v >> 8) & 255, v & 255])
            elif k == "rel":
                op, tgt = it[1], self._resolve(table, it[2])
                if i in long:
                    if op in (JMP_REL, JSR_REL):
                        out += bytes([JMP_ABS if op == JMP_REL else JSR_ABS, (tgt >> 8) & 255, tgt & 255])
                    elif op in BRANCH_INVERSE:
                        out += bytes([BRANCH_INVERSE[op], 3, JMP_ABS, (tgt >> 8) & 255, tgt & 255])
                    else:
                        raise AsmError(f"cannot relax opcode {op:02X}")
                else:
                    out += bytes([op, (tgt - (addrs[i] + 2)) & 255])
            elif k == "align":
                out += bytes([it[2]]) * (-(self.org + len(out)) % it[1])
        return bytes(out)

    def symbols(self):
        """Sorted (address, name) pairs for labels and symbols."""
        return sorted((v, k) for k, v in self._layout()[1].items())

    def listing(self):
        """Human-readable listing: address, bytes, label markers."""
        addrs, table, long = self._layout()
        data = self.bytes()
        lines, pos = [], 0
        for i, it in enumerate(self.items):
            k = it[0]
            if k == "lbl":
                lines.append(f"{addrs[i]:04X}            {it[1]}:")
                continue
            end = (addrs[i + 1] if i + 1 < len(self.items) else self.org + len(data)) - self.org
            chunk = data[pos:end]
            pos = end
            for j in range(0, max(len(chunk), 1), 6):
                part = chunk[j:j + 6]
                note = ""
                if j == 0:
                    if k == "rel":
                        note = f"-> {it[2]}" + (" (long)" if i in long else "")
                    elif k == "ref":
                        note = f"-> {it[2]}"
                lines.append(f"{addrs[i] + j:04X}  {part.hex(' ').upper():<18}{note}")
        return "\n".join(lines)

    # -- text asm export --------------------------------------------------
    # Native-style text for reading and sharing (a little literate: labels,
    # symbols and the few things the binary cannot say for itself are kept).
    # This is an export only -- cpu6asm does not assemble text input (yet).
    _PAIR_NAMES = "ABXYZSCP"
    _SINGLE_OPS = {0x00: "HLT", 0x01: "NOP", 0x09: "RSR", 0x38: "INA",
                   0x58: "AAB", 0x59: "SAB", 0x5A: "NAB", 0x5E: "XAZ",
                   0x5C: "XAY", 0x49: "SABB", 0x2C: "SRAB"}
    _OP16_TEXT = {0x90: "LDA=", 0xD0: "LDB=", 0x91: "LDA/", 0x81: "LDAB/",
                  0xD1: "LDB/", 0xC1: "LDBB/", 0xB1: "STA/", 0xA1: "STAB/",
                  0xF1: "STB/", 0xE1: "STBB/", 0x71: "JMP/", 0x79: "JSR/"}
    _IX_TEXT = {0x85: "LDAB", 0x95: "LDA", 0xA5: "STAB", 0xB5: "STA",
                0xC5: "LDBB", 0xD5: "LDB", 0xE5: "STBB", 0xF5: "STB",
                0x75: "JMP", 0x7D: "JSR"}
    _REL_TEXT = {0x10: "BL", 0x11: "BNC", 0x16: "BM", 0x17: "BP",
                 0x14: "BZ", 0x15: "BNZ", 0x18: "BGZ", 0x19: "BLE",
                 JMP_REL: "JMP", JSR_REL: "JSR"}

    @classmethod
    def _breg_name(cls, i):
        return cls._PAIR_NAMES[i >> 1] + ("H" if i % 2 == 0 else "L")

    def _decode_ix(self, op, chunk):
        b = chunk[1]
        reg = self._PAIR_NAMES[b >> 5]
        mode = {0: "", 1: "+", 2: "-"}[b & 3]
        operand = ("*" if b & 4 else "") + reg + mode
        if b & 8:
            operand += f"+{chunk[2]}"
        return f"{self._IX_TEXT[op]} {operand}"

    def _decode_md(self, op, e, word):
        name = "MUL" if op == 0x77 else "DIV"
        hi, lo = e >> 4, e & 15
        src = self._PAIR_NAMES[hi >> 1]
        dst = self._PAIR_NAMES[lo >> 1]
        tail = f",{dst}" if dst != src else ""
        if hi % 2 == 1 and lo % 2 == 0:
            return f"{name}= {word},{src}{tail}"     # immediate word
        if hi % 2 == 0 and lo % 2 == 1:
            return f"{name}/ {word},{src}{tail}"     # word at address
        return f"{name}- {src},{word},{dst}"         # word at idx+disp

    def _decode_instr(self, chunk):
        op = chunk[0]
        if len(chunk) == 1 and op in self._SINGLE_OPS:
            return self._SINGLE_OPS[op]
        if op in self._IX_TEXT and len(chunk) in (2, 3):
            return self._decode_ix(op, chunk)
        if op in (0x77, 0x78) and len(chunk) == 2:
            b = chunk[1]
            name = "MUL" if op == 0x77 else "DIV"
            return f"{name} {self._PAIR_NAMES[b >> 5]},{self._PAIR_NAMES[(b >> 1) & 7]}"
        if op in (0x77, 0x78) and len(chunk) == 4:
            return self._decode_md(op, chunk[1], (chunk[2] << 8) | chunk[3])
        if op in self._OP16_TEXT and len(chunk) == 3:
            return f"{self._OP16_TEXT[op]} X'{(chunk[1] << 8) | chunk[2]:04X}'"
        if len(chunk) == 2:
            b = chunk[1]
            if op == 0x45:
                return f"XFRB {self._breg_name(b >> 4)},{self._breg_name(b & 15)}"
            if op == 0x42:
                return f"ANDB {self._breg_name(b >> 4)},{self._breg_name(b & 15)}"
            if op == 0x43:
                return f"ORB {self._breg_name(b >> 4)},{self._breg_name(b & 15)}"
            if op == 0x55:
                return f"XFR {self._PAIR_NAMES[b >> 5]},{self._PAIR_NAMES[(b >> 1) & 7]}"
            if op == 0x30:
                return f"INR {self._PAIR_NAMES[b >> 5]},{(b & 31) + 1}"
            if op == 0x31:
                return f"DCR {self._PAIR_NAMES[b >> 5]},{(b & 31) + 1}"
            if op == 0x20:
                return f"INRB {self._breg_name(b >> 4)},{(b & 15) + 1}"
            if op == 0x21:
                return f"DCRB {self._breg_name(b >> 4)},{(b & 15) + 1}"
            if op == 0x7E:
                return f"PUSH {self._breg_name(b >> 4)},{(b & 15) + 1}"
            if op == 0x7F:
                return f"POP {self._breg_name(b >> 4)},{(b & 15) + 1}"
            if op == 0x66:
                return f"SVC X'{b:02X}'"
            if op == 0x35:
                return f"SLL A,{b + 1}"
            if op == 0x80:
                return f"LDAB= {b}"
            if op == 0xC0:
                return f"LDBB= {b}"
            if op == 0x2F:
                return f"DMA X'{b:02X}'"
        return "DB " + ",".join(f"X'{b:02X}'" for b in chunk) + "  ; undecoded"

    @staticmethod
    def _decode_data(chunk):
        if len(chunk) >= 8 and len(set(chunk)) == 1:
            fill = f"  ; fill X'{chunk[0]:02X}'" if chunk[0] else ""
            return f"DS {len(chunk)}{fill}" 
        if len(chunk) == 2 and not all(32 <= b < 127 for b in chunk):
            return f"DW X'{(chunk[0] << 8) | chunk[1]:04X}'"
        parts, run = [], bytearray()
        for b in chunk:
            if 32 <= b < 127 and b != 0x27:
                run.append(b)
            else:
                if run:
                    parts.append(f"'{run.decode()}'")
                    run = bytearray()
                parts.append(f"X'{b:02X}'")
        if run:
            parts.append(f"'{run.decode()}'")
        return "DB " + ",".join(parts)

    def asm(self, title=None):
        """Native-style text assembly of this program (export, not input)."""
        addrs, table, long = self._layout()
        data = self.bytes()
        lines = [f"* {title or 'cpu6asm export'}",
                 "* Text export from cpu6asm.py -- for reading and sharing;",
                 "* cpu6asm does not (yet) assemble text input.",
                 f"* Origin X'{self.org:04X}'"]
        for name, val in sorted(self.syms.items(), key=lambda kv: kv[1]):
            lines.append(f"{name:<10}EQU       X'{val:04X}'")
        if self.syms:
            lines.append("*")
        pos, label, prev_data = 0, None, False
        for i, it in enumerate(self.items):
            k = it[0]
            if k == "lbl":
                if label is not None:
                    lines.append(f"{label}:")
                label = it[1]
                continue
            end = (addrs[i + 1] if i + 1 < len(self.items)
                   else self.org + len(data)) - self.org
            chunk = data[pos:end]
            pos = end
            if k == "b" and chunk == b"\x00" and prev_data and label is None:
                lines[-1] += ",0"     # asciz terminator rides its string
                continue
            texts = []
            npad = self._pads.get(i, 0)
            if npad:
                chunk = chunk[npad:]
                texts += ["NOP  ; page-boundary pad"] * npad
            if k == "align":
                texts.append(f"DS {len(chunk)}  ; align {it[1]}")
                prev_data = False
            elif k == "rel":
                text = f"{self._REL_TEXT[it[1]]} {it[2]}"
                if i in long:
                    text += "  ; long form: inverted branch over JMP/"
                texts.append(text)
                prev_data = False
            elif k == "ref":
                prefix, sym = it[1], it[2]
                if len(prefix) == 0:
                    texts.append(f"DW {sym}")
                elif len(prefix) == 1:
                    texts.append(f"{self._OP16_TEXT[prefix[0]]} {sym}")
                else:
                    texts.append(self._decode_md(prefix[0], prefix[1], sym))
                prev_data = False
            elif i in self._instr and not (chunk == b"\x00" and prev_data):
                texts.append(self._decode_instr(chunk))
                prev_data = False
            else:
                text = self._decode_data(chunk)
                texts.append(text)
                prev_data = chr(39) in text
            for text in texts:
                lines.append(f"{label:<10}{text}" if label else f"          {text}")
                label = None
        if label is not None:
            lines.append(f"{label}:")
        return "\n".join(lines)


    # -- simple ops ------------------------------------------------------
    def nop(self): return self.raw(0x01)
    def hlt(self): return self.raw(0x00)
    def rsr(self): return self.raw(0x09)
    def ina(self): return self.raw(0x38)
    def aab(self): return self.raw(0x58)       # A + B -> B
    def sab(self): return self.raw(0x59)       # A - B -> B (carry = no borrow)
    def nab(self): return self.raw(0x5A)       # A & B -> B
    def xaz(self): return self.raw(0x5E)
    def xay(self): return self.raw(0x5C)
    def sabb(self): return self.raw(0x49)      # AL - BL -> BL
    def srab(self): return self.raw(0x2C)
    def xfrb_au_al(self): return self.raw(0x45, 0x01)
    def xfrb_al_bl(self): return self.raw(0x45, 0x13)
    def andb_bl_al(self): return self.raw(0x42, 0x31)
    def orb_bl_al(self): return self.raw(0x43, 0x31)   # AL | BL -> AL
    def xfrb_bl_al(self): return self.raw(0x45, 0x31)
    def xfrb_dl_al(self): return self.raw(0x45, 0x71)
    def jmp_y(self): return self.raw(0x75, 0x60)
    def jsr_y(self): return self.raw(0x7D, 0x60)   # JSR via Y (0x78 is DIVU on real hardware)
    def svc(self, v): return self.raw(0x66, v & 255)
    def sll_ax(self, n): return self.raw(0x35, n - 1)
    def ldab_zinc(self): return self.raw(0x85, 0x81)  # AL = (Z)+
    def stab_yinc(self): return self.raw(0xA5, 0x61)  # (Y)+ = AL

    # -- register-generic ops --------------------------------------------
    def xfr(self, src, dst): return self.raw(0x55, (pair(src) << 5) | (pair(dst) << 1))
    def xfrb(self, src, dst): return self.raw(0x45, (breg(src) << 4) | breg(dst))
    def inr(self, r, n=1): return self.raw(0x30, (pair(r) << 5) | (n - 1))
    def dcr(self, r, n=1): return self.raw(0x31, (pair(r) << 5) | (n - 1))
    def inrb(self, r, n=1): return self.raw(0x20, (breg(r) << 4) | (n - 1))
    def dcrb(self, r, n=1): return self.raw(0x21, (breg(r) << 4) | (n - 1))
    def inr_z(self, n=1): return self.inr("Z", n)
    # MUL/DIV (semantics from optest07.asm).  Result goes to dst: MUL = high word in dst and low word in the
    # next pair when dst is A/X/Z/C (pair index even), low word only in dst otherwise.  DIV = remainder in dst
    # and quotient in the next pair when dst is even, quotient only in dst otherwise.
    def mulu(self, src, dst):
        """MUL src,dst: src * dst -> dst (:next)."""
        return self.raw(0x77, (pair(src) << 5) | (pair(dst) << 1))
    def divu(self, src, dst):
        """DIV src,dst: dst / src -> remainder in dst, quotient in next pair (dst even) or in dst (dst odd)."""
        return self.raw(0x78, (pair(src) << 5) | (pair(dst) << 1))
    def _md(self, op, e, word):
        if isinstance(word, str):
            self.items.append(("ref", bytes([op, e]), word))
        else:
            self.items.append(("b", bytes([op, e, (word >> 8) & 255, word & 255])))
        self._instr.add(len(self.items) - 1)
        return self
    def mul_imm(self, imm, src, dst=None):
        """MUL= imm,src[,dst]: imm * src."""
        return self._md(0x77, ((pair(src) << 1 | 1) << 4) | (pair(dst if dst is not None else src) << 1), imm)
    def div_imm(self, imm, src, dst=None):
        """DIV= imm,src[,dst]: src / imm."""
        return self._md(0x78, ((pair(src) << 1 | 1) << 4) | (pair(dst if dst is not None else src) << 1), imm)
    def mul_mem(self, addr, src, dst=None):
        """MUL/ addr,src[,dst]: [addr] * src."""
        return self._md(0x77, ((pair(src) << 1) << 4) | (pair(dst if dst is not None else src) << 1 | 1), addr)
    def div_mem(self, addr, src, dst=None):
        """DIV/ addr,src[,dst]: src / [addr]."""
        return self._md(0x78, ((pair(src) << 1) << 4) | (pair(dst if dst is not None else src) << 1 | 1), addr)
    def mul_idx(self, idx, disp, dst):
        """MUL- idx,disp,dst: [idx+disp] * dst (disp is a 16-bit word)."""
        return self._md(0x77, ((pair(idx) << 1 | 1) << 4) | (pair(dst) << 1 | 1), disp)
    def div_idx(self, idx, disp, dst):
        """DIV- idx,disp,dst: dst / [idx+disp]."""
        return self._md(0x78, ((pair(idx) << 1 | 1) << 4) | (pair(dst) << 1 | 1), disp)
    def push(self, first, count=1): return self.raw(0x7E, (breg(first) << 4) | (count - 1))
    def pop(self, first, count=1): return self.raw(0x7F, (breg(first) << 4) | (count - 1))

    # -- indexed addressing (register, ''/'+'/'-' , optional disp8, optional indirect) --
    @staticmethod
    def idx(reg, mode="", disp=None, indirect=False):
        b = pair(reg) << 5
        b |= {"": 0, "+": 1, "-": 2}[mode]
        if disp is not None:
            b |= 8
        if indirect:
            b |= 4
        return bytes([b] + ([disp & 255] if disp is not None else []))

    def _ix(self, op, reg, mode, disp, indirect):
        return self.raw(op, *self.idx(reg, mode, disp, indirect))
    def ldab_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0x85, reg, mode, disp, indirect)
    def lda_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0x95, reg, mode, disp, indirect)
    def stab_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0xA5, reg, mode, disp, indirect)
    def sta_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0xB5, reg, mode, disp, indirect)
    def ldbb_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0xC5, reg, mode, disp, indirect)
    def ldb_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0xD5, reg, mode, disp, indirect)
    def stbb_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0xE5, reg, mode, disp, indirect)
    def stb_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0xF5, reg, mode, disp, indirect)
    def jmp_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0x75, reg, mode, disp, indirect)
    def jsr_x(self, reg, mode="", disp=None, indirect=False): return self._ix(0x7D, reg, mode, disp, indirect)

    # DMA
    def dma_sad_a(self): return self.raw(0x2F, 0x00)
    def dma_sct_a(self): return self.raw(0x2F, 0x02)
    def dma_sdv_0(self): return self.raw(0x2F, 0x04)
    def dma_eab(self): return self.raw(0x2F, 0x06)

    # -- loads / stores (16-bit operands may be symbols) ---------------------
    def lda_i(self, v): return self._op16(0x90, v)
    def ldb_i(self, v): return self._op16(0xD0, v)
    def ldab_i(self, v): return self.raw(0x80, v & 255)
    def ldbb_i(self, v): return self.raw(0xC0, v & 255)
    def lda_d(self, a): return self._op16(0x91, a)
    def ldab_d(self, a): return self._op16(0x81, a)
    def ldb_d(self, a): return self._op16(0xD1, a)
    def ldbb_d(self, a): return self._op16(0xC1, a)
    def sta_d(self, a): return self._op16(0xB1, a)
    def stab_d(self, a): return self._op16(0xA1, a)
    def stb_d(self, a): return self._op16(0xF1, a)
    def stbb_d(self, a): return self._op16(0xE1, a)
    def lda_label(self, l): return self._op16(0x90, l)   # A = address of label
    def ldb_label(self, l): return self._op16(0xD0, l)
    def lda_z(self, d): return self.raw(0x95, 0x88, d)
    def ldab_z(self, d): return self.raw(0x85, 0x88, d)
    def lda_bx(self, d): return self.raw(0x95, 0x28, d)
    def ldab_bx(self, d): return self.raw(0x85, 0x28, d)
    def stab_z(self, d): return self.raw(0xA5, 0x88, d)
    def stb_z(self, d): return self.raw(0xF5, 0x88, d)

    # -- jumps and branches (all relax automatically) -------------------------
    def jmp(self, l): return self._rel(JMP_REL, l)
    def jsr(self, l): return self._rel(JSR_REL, l)
    def jmp_abs(self, l): return self._op16(JMP_ABS, l)
    def jsr_abs(self, l): return self._op16(JSR_ABS, l)
    def bl(self, l): return self._rel(0x10, l)   # carry set (AL >= BL after sabb)
    def bnc(self, l): return self._rel(0x11, l)  # carry clear
    def bm(self, l): return self._rel(0x16, l)
    def bp(self, l): return self._rel(0x17, l)
    def bz(self, l): return self._rel(0x14, l)
    def bnz(self, l): return self._rel(0x15, l)
    def bgz(self, l): return self._rel(0x18, l)  # > 0
    def ble(self, l): return self._rel(0x19, l)  # <= 0
    # readable aliases for compare results (unsigned, after cmp_*)
    beq, bne, bhs, blo, bgt = bz, bnz, bl, bnc, bgz

    # compare helpers: set flags for AL/AX versus an immediate (clobber BL/BX)
    def cmp_al(self, imm): return self.ldbb_i(imm).sabb()
    def cmp_ax(self, imm): return self.ldb_i(imm).sab()

    def print(self, text, mux=0xF201):
        for ch in text.encode():
            self.ldbb_i(ch).stbb_d(mux)
        return self
