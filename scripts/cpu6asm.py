"""Tiny CPU6 assembler: only the instruction forms we need, with label support.

Encodings were taken from the HDIPL 6.2 listing (wipl.asm) matched against the
bytes of a real image.  Relative branches are relative to the next instruction.
"""


class Asm:
    def __init__(self, org):
        self.org = org
        self.buf = bytearray()
        self.labels = {}
        self.fix = []  # (kind, offset, label)

    @property
    def pc(self):
        return self.org + len(self.buf)

    def raw(self, *b):
        self.buf += bytes(b)
        return self

    def label(self, name):
        assert name not in self.labels, name
        self.labels[name] = self.pc
        return self

    def _rel(self, op, label):
        self.buf += bytes([op, 0])
        self.fix.append(("rel8", len(self.buf) - 1, label))
        return self

    def _abs16(self, op, label):
        self.buf += bytes([op, 0, 0])
        self.fix.append(("abs16", len(self.buf) - 2, label))
        return self

    def u16(self, v):
        self.buf += bytes([(v >> 8) & 255, v & 255])
        return self

    # simple ops ------------------------------------------------------
    def nop(self): return self.raw(0x01)
    def hlt(self): return self.raw(0x00)
    def rsr(self): return self.raw(0x09)
    def ina(self): return self.raw(0x38)
    def aab(self): return self.raw(0x58)       # A + B -> B
    def nab(self): return self.raw(0x5A)       # A & B -> B
    def xaz(self): return self.raw(0x5E)
    def xay(self): return self.raw(0x5C)
    def sabb(self): return self.raw(0x49)      # AL - BL -> BL
    def srab(self): return self.raw(0x2C)
    def xfrb_au_al(self): return self.raw(0x45, 0x01)
    def xfrb_al_bl(self): return self.raw(0x45, 0x13)
    def andb_bl_al(self): return self.raw(0x42, 0x31)
    def jmp_y(self): return self.raw(0x75, 0x60)
    def svc(self, v): return self.raw(0x66, v & 255)
    # DMA
    def dma_sad_a(self): return self.raw(0x2F, 0x00)
    def dma_sct_a(self): return self.raw(0x2F, 0x02)
    def dma_sdv_0(self): return self.raw(0x2F, 0x04)
    def dma_eab(self): return self.raw(0x2F, 0x06)
    # loads / stores
    def lda_i(self, v): return self.raw(0x90).u16(v)
    def ldb_i(self, v): return self.raw(0xD0).u16(v)
    def ldab_i(self, v): return self.raw(0x80, v & 255)
    def ldbb_i(self, v): return self.raw(0xC0, v & 255)
    def lda_d(self, a): return self.raw(0x91).u16(a)
    def ldab_d(self, a): return self.raw(0x81).u16(a)
    def ldb_d(self, a): return self.raw(0xD1).u16(a)
    def ldbb_d(self, a): return self.raw(0xC1).u16(a)
    def sta_d(self, a): return self.raw(0xB1).u16(a)
    def stab_d(self, a): return self.raw(0xA1).u16(a)
    def stb_d(self, a): return self.raw(0xF1).u16(a)
    def stbb_d(self, a): return self.raw(0xE1).u16(a)
    def lda_z(self, d): return self.raw(0x95, 0x88, d)
    def ldab_z(self, d): return self.raw(0x85, 0x88, d)
    def lda_bx(self, d): return self.raw(0x95, 0x28, d)
    def ldab_bx(self, d): return self.raw(0x85, 0x28, d)
    def stab_z(self, d): return self.raw(0xA5, 0x88, d)
    def stb_z(self, d): return self.raw(0xF5, 0x88, d)
    # branches
    def jmp(self, l): return self._rel(0x73, l)
    def jsr(self, l): return self._rel(0x7B, l)
    def jmp_abs(self, l): return self._abs16(0x71, l)
    def jsr_abs(self, l): return self._abs16(0x79, l)
    def bz(self, l): return self._rel(0x14, l)
    def bnz(self, l): return self._rel(0x15, l)
    def bl(self, l): return self._rel(0x10, l)

    def print(self, text, mux=0xF201):
        for ch in text.encode():
            self.ldbb_i(ch).stbb_d(mux)
        return self

    def bytes(self):
        out = bytearray(self.buf)
        for kind, off, label in self.fix:
            if kind == "rel8":
                rel = self.labels[label] - (self.org + off + 1)
                assert -128 <= rel <= 127, (label, rel)
                out[off] = rel & 255
            elif kind == "abs16":
                v = self.labels[label]
                out[off] = (v >> 8) & 255
                out[off + 1] = v & 255
            else:
                raise AssertionError(kind)
        return bytes(out)
