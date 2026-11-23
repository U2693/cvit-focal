import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "scripts"))
from cpu6asm import Asm

a = Asm(0x5000)
a.lda_i(0x6000).xfr("A", "Y")
a.lda_i(0).ldab_x("Y", disp=0).stab_d(0x6100)
a.xfr("Y", "A").ldb_i(1).aab().xfr("B", "Y")
a.lda_i(0).ldab_x("Y", disp=0).stab_d(0x6101)
a.xfr("Y", "A").sta_d(0x6102)
a.hlt()
code = a.bytes()
blob = code + bytes(0x1000 - len(code)) + b"PROG1XYZ"
(root / "out" / "test-y.bin").write_bytes(blob)
print("wrote", len(blob))
