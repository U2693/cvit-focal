"""Kernel CVIT filesystem read path and SVC 0x57 (LOAD) handler (ME-3).

Emitted into the stage-2 kernel by build_stage2.py. Entry contract:
fs_load is reached from the JSYS dispatcher with BX = path string
pointer, running on the kernel stack with the caller registers saved
by the dispatcher. It mirrors the host FocalLoad semantics: parse the
path, find the member in the library directory, stage its text, clear
the FOCAL slots, convert lines to slots, and print the Loaded line.
Errors are printed here, exactly as the host prints them, and every
exit goes through jd_return.

Scope: read-only (SAVE is ME-4). Libraries: /SYSTEM (data sector
0x20, UAL 0x12) and /HELP (0x100, 0x18). Member text is staged at
0x3000; members needing more than 8192 staged bytes report ?TOO BIG.
Block transfers go through the kernel read_block vector (0x080C) with
the control block at CB below.
"""

STAGE = 0x3000
STAGE_MAX = 0x2000

NAME = 0x2F40    # member name bytes (10) 
NLEN = 0x2F4C
PATH = 0x2F80    # collected path spec (28 bytes)
PLEN = 0x2F9C
PSTART = 0x2F9E
SLASH = 0x2FA0
PFX = 0x2FA2     # 0 = SYSTEM, 1 = HELP
DSEC = 0x2FA4
USEC = 0x2FA6
LIBP = 0x2FA8
DBYTES = 0x2FAA
ROW = 0x2FAC
RPTR = 0x2FAE
DIDX = 0x2FB0
RCNT = 0x2FB2
FOUND = 0x2FB4
PAGE = 0x2FB6
NEXTP = 0x2FB8
CAP = 0x2FBA
TPTR = 0x2FBC
TEND = 0x2FBE
SPTR = 0x2FC0
CNT = 0x2FC2
NUM = 0x2FC4
NDIG = 0x2FC6
GRP = 0x2FC8
SUB = 0x2FCA
KEY = 0x2FCC
BLEN = 0x2FCE
MCNT = 0x2FD0
MADD = 0x2FD2
MRES = 0x2FD4
TMP = 0x2FD6
TMP2 = 0x2FD8
CH = 0x2FDA
CB = 0x2FE0      # read_block CB: +0 sector, +2 buffer
PASS = 0x2FE4
RPAGE = 0x2FE6
SOFF = 0x2FE8
SSEC = 0x2FEA
NSEC = 0x2FEC
J = 0x2FEE
BPTR = 0x2FF0
MATCH = 0x2FF2
CA = 0x2FF4
CL = 0x2FF6
LA = 0x2FF8
LL = 0x2FFA
MS = 0x2FFC      # member start index in PATH
FSERR = 0x2FFE     # fs_stage oversize flag (1 = member exceeds staging)


def _inc(a, cell):
    a.lda_d(cell).ldb_i(1).aab().stb_d(cell)


def _add(a, cell, n):
    a.lda_d(cell).ldb_i(n).aab().stb_d(cell)


def _zinc(a):
    a.xfr("Z", "A").ldb_i(1).aab().xfr("B", "Z")


def _yinc(a):
    a.xfr("Y", "A").ldb_i(1).aab().xfr("B", "Y")


def _cmp_char(a, z, disp, ch, no_label):
    # branch to no_label if byte at [Z+disp] != ch (ch is an int)
    a.lda_i(0).ldab_z(disp).ldbb_i(ch).sabb().bnz(no_label)


def emit_fs_load(a):
    # ---------------- path collection ----------------
    a.label("fs_load")
    a.jsr_abs("p_parse_load")
    a.lda_d("p_err").ldb_i(0).sab().bnz("fs_loadwhat")
    a.lda_d(PFX).ldb_i(2).sab().bz("fs_nofile")
    a.jmp_abs("fs_load2")
    a.label("fs_load2")
    a.jsr_abs("fs_libset")
    # ---------------- directory scan ----------------
    a.label("fs_scan1")
    a.lda_i(0).sta_d(FOUND)
    a.lda_i(1).sta_d(PASS)
    a.jsr_abs("fs_scan")
    a.lda_d(FOUND).ldb_i(0).sab().bz("fs_nofile")
    a.lda_d(LIBP).sta_d(NEXTP)
    a.lda_i(2).sta_d(PASS)
    a.jsr_abs("fs_scan")
    a.lda_d(NEXTP).ldb_d(PAGE).sab().stb_d(MCNT)                # MCNT = next - page
    a.lda_i(200).sta_d(MADD)
    a.jsr_abs("fs_mul")
    a.lda_d(MRES).sta_d(CAP)
    a.lda_d(CAP).ldb_i(0).sab().bz("fs_nofile")
    a.jsr_abs("fs_stage")
    a.lda_d(FSERR).ldb_i(0).sab().bnz("fs_toobig")
    a.lda_d(TPTR).ldb_d(CAP).aab().stb_d(TEND)
    # CV header rule, else trim trailing NUL/space
    a.lda_d(TPTR).xaz()
    _cmp_char(a, "Z", 0, 0x43, "fs_trim")                       # C
    _cmp_char(a, "Z", 1, 0x56, "fs_trim")                       # V
    a.lda_d(TPTR).xaz().lda_z(6).ldb_i(9).aab().stb_d(TMP)      # TMP = declared length
    a.lda_d(TMP).ldb_d(CAP).sab().bz("fs_cv_set")
    a.lda_d(TMP).ldb_d(CAP).sab().bl("fs_trim")                 # declared > cap: trim instead
    a.label("fs_cv_set")
    a.lda_d(TMP).ldb_d(TPTR).aab().stb_d(TEND)
    a.jmp_abs("fs_clear")
    a.label("fs_trim")
    a.lda_d(TEND).ldb_d(TPTR).sab().bz("fs_clear")
    a.lda_d(TEND).ldb_i(1).sab().stb_d(TMP)
    a.lda_d(TMP).xaz()
    a.lda_i(0).ldab_z(0).ldbb_i(0).sabb().bz("fs_trim_cut")
    a.lda_i(0).ldab_z(0).ldbb_i(0x20).sabb().bnz("fs_clear")
    a.label("fs_trim_cut")
    a.lda_d(TMP).sta_d(TEND)
    a.jmp_abs("fs_trim")
    # ---------------- clear slots ----------------
    a.label("fs_clear")
    a.lda_i(0x8000).xaz()
    a.lda_i(0).sta_d(J)
    a.label("fs_clear_l")
    a.lda_i(0).stab_z(0)
    a.xfr("Z", "A").ldb_i(64).aab().xfr("B", "Z")
    _inc(a, J)
    a.lda_d(J).ldb_i(128).sab().bnz("fs_clear_l")
    # ---------------- convert lines to slots ----------------
    a.lda_i(0).sta_d(CNT)
    a.lda_i(0x8000).sta_d(SPTR)
    a.label("fs_conv")
    a.lda_d(CNT).ldb_i(128).sab().bl("fs_loaded")
    a.lda_d(TPTR).ldb_d(TEND).sab().bl("fs_loaded")
    a.label("fs_sep")
    a.lda_d(TPTR).ldb_d(TEND).sab().bl("fs_loaded")
    a.jsr_abs("fs_peek")
    a.ldbb_i(0x0D).sabb().bz("fs_sep_eat")
    a.lda_i(0).ldab_d(CH).ldbb_i(0x0A).sabb().bz("fs_sep_eat")
    a.jmp_abs("fs_grp")
    a.label("fs_sep_eat")
    _inc(a, TPTR)
    a.jmp_abs("fs_sep")
    a.label("fs_grp")
    a.jsr_abs("fs_num")
    a.lda_d(NDIG).ldb_i(0).sab().bz("fs_skip")
    a.lda_d(NUM).sta_d(GRP)
    a.jsr_abs("fs_peek")
    a.ldbb_i(0x2E).sabb().bnz("fs_skip")                        # dot
    _inc(a, TPTR)
    a.jsr_abs("fs_num")
    a.lda_d(NDIG).ldb_i(0).sab().bz("fs_skip")
    a.lda_d(NUM).sta_d(SUB)
    a.lda_d(SUB).ldb_i(99).sab().bz("fs_key")                   # == 99 ok
    a.lda_d(SUB).ldb_i(99).sab().bl("fs_skip")                  # > 99
    a.label("fs_key")
    a.lda_d(SUB).sta_d(TMP)  # plain sub: the dot is cosmetic
    a.label("fs_key_mk")
    a.lda_d(GRP).sta_d(MADD)
    a.lda_i(100).sta_d(MCNT)
    a.jsr_abs("fs_mul")
    a.lda_d(MRES).ldb_d(TMP).aab().stb_d(KEY)
    a.lda_d(KEY).ldb_i(0).sab().bz("fs_skip")
    a.lda_d(KEY).ldb_i(10000).sab().bl("fs_skip")
    # body: skip leading spaces and tabs
    a.label("fs_bsp")
    a.jsr_abs("fs_peek")
    a.ldbb_i(0x20).sabb().bz("fs_bsp_eat")
    a.lda_i(0).ldab_d(CH).ldbb_i(0x09).sabb().bnz("fs_body")
    a.label("fs_bsp_eat")
    _inc(a, TPTR)
    a.jmp_abs("fs_bsp")
    a.label("fs_body")
    a.lda_d(SPTR).xfr("A", "Y")
    a.ldb_d(KEY).stb_x("Y", disp=0)                             # slot key (BE word)
    a.lda_d(SPTR).ldb_i(2).aab().xfr("B", "Y")                  # Y = slot + 2
    a.lda_i(0).sta_d(BLEN)
    a.label("fs_body_l")
    a.lda_d(TPTR).ldb_d(TEND).sab().bl("fs_body_done")
    a.jsr_abs("fs_peek")
    a.ldbb_i(0x0D).sabb().bz("fs_body_done")
    a.lda_i(0).ldab_d(CH).ldbb_i(0x0A).sabb().bz("fs_body_done")
    _inc(a, TPTR)
    a.lda_d(BLEN).ldb_i(61).sab().bl("fs_body_l")               # truncate: consume only
    a.lda_i(0).ldab_d(CH).stab_x("Y", disp=0)
    _yinc(a)
    _inc(a, BLEN)
    a.jmp_abs("fs_body_l")
    a.label("fs_body_done")
    a.lda_i(0).ldab_i(0x0D).stab_x("Y", disp=0)
    _inc(a, CNT)
    _add(a, SPTR, 64)
    a.jmp_abs("fs_conv")
    a.label("fs_skip")
    a.lda_d(TPTR).ldb_d(TEND).sab().bl("fs_conv")
    a.jsr_abs("fs_peek")
    a.ldbb_i(0x0D).sabb().bz("fs_conv")
    a.lda_i(0).ldab_d(CH).ldbb_i(0x0A).sabb().bz("fs_conv")
    _inc(a, TPTR)
    a.jmp_abs("fs_skip")
    # ---------------- success line ----------------
    a.label("fs_loaded")
    a.print("\r\nLoaded H0:/")
    a.lda_d(PFX).ldb_i(0).sab().bnz("fs_ld_help")
    a.print("SYSTEM")
    a.jmp_abs("fs_ld_name")
    a.label("fs_ld_help")
    a.print("HELP")
    a.label("fs_ld_name")
    a.print("/")
    a.lda_i(NAME).xaz()
    a.lda_i(0).sta_d(J)
    a.label("fs_ld_nl")
    a.lda_d(J).ldb_d(NLEN).sab().bz("fs_ld_done")
    a.ldab_zinc().xfrb_al_bl().stbb_d(0xF201)
    _inc(a, J)
    a.jmp_abs("fs_ld_nl")
    a.label("fs_ld_done")
    a.print("\r\n")
    a.jmp_abs("jd_return")
    # ---------------- errors ----------------
    a.label("fs_nofile")
    a.print("\r\n?NO FILE\r\n")
    a.jmp_abs("jd_return")
    a.label("fs_loadwhat")
    a.print("\r\n?LOAD WHAT\r\n")
    a.jmp_abs("jd_return")
    a.label("fs_toobig")
    a.print("\r\n?TOO BIG\r\n")
    a.jmp_abs("jd_return")
    # ---------------- subroutines ----------------
    a.label("fs_mul")
    a.lda_i(0).sta_d(MRES)
    a.label("fs_mul_l")
    a.lda_d(MCNT).ldb_i(0).sab().bz("fs_mul_done")
    a.lda_d(MRES).ldb_d(MADD).aab().stb_d(MRES)
    a.lda_d(MCNT).ldb_i(1).sab().stb_d(MCNT)
    a.jmp_abs("fs_mul_l")
    a.label("fs_mul_done")
    a.rsr()
    a.label("fs_rsec")
    a.ldb_i(CB).jsr_abs(0x080C)
    a.ldbb_i(0).sabb().bnz("fs_nofile")
    a.rsr()
    # ---------------- library size from UAL ----------------
    a.label("fs_libset")
    a.lda_d(USEC).sta_d(CB)
    a.lda_i(STAGE).sta_d(CB + 2)
    a.jsr_abs("fs_rsec")
    a.lda_d(STAGE).ldb_i(1).aab().stb_d(MADD)                   # MADD = ual word + 1
    a.lda_i(2).sta_d(MCNT)
    a.jsr_abs("fs_mul")
    a.lda_d(MRES).sta_d(LIBP)
    # ---------------- directory size ----------------
    a.lda_d(DSEC).sta_d(CB)
    a.lda_i(STAGE).sta_d(CB + 2)
    a.jsr_abs("fs_rsec")
    a.lda_i(STAGE).xaz()
    _cmp_char(a, "Z", 10, 0x44, "fs_dir_small")                 # D
    _cmp_char(a, "Z", 11, 0x58, "fs_dir_small")                 # X
    a.lda_i(STAGE).xaz().lda_z(12).sta_d(MCNT)
    a.lda_i(400).sta_d(MADD)
    a.jsr_abs("fs_mul")
    a.lda_d(MRES).sta_d(DBYTES)
    a.rsr()
    a.label("fs_dir_small")
    a.lda_i(200).sta_d(DBYTES)
    a.rsr()
    a.label("fs_stage")
    # ---------------- stage the member ----------------
    a.lda_i(0).sta_d(FSERR)
    a.lda_d(PAGE).sta_d(MCNT)
    a.lda_i(200).sta_d(MADD)
    a.jsr_abs("fs_mul")
    a.lda_d(MRES).sta_d(TMP)                                    # TMP = page * 200
    a.lda_i(0).sta_d(SSEC)
    a.label("fs_div400")
    a.lda_d(TMP).ldb_i(400).sab().bnc("fs_div_done")            # TMP < 400
    a.lda_d(TMP).ldb_i(400).sab().stb_d(TMP)
    _inc(a, SSEC)
    a.jmp_abs("fs_div400")
    a.label("fs_div_done")
    a.lda_d(TMP).sta_d(SOFF)
    a.lda_d(SOFF).ldb_d(CAP).aab().stb_d(TMP)                   # TMP = total bytes
    a.lda_d(TMP).ldb_i(STAGE_MAX).sab().bz("fs_size_ok")        # == max ok
    a.lda_d(TMP).ldb_i(STAGE_MAX).sab().bl("fs_size_big")         # > max
    a.label("fs_size_ok")
    a.lda_i(0).sta_d(NSEC)
    a.label("fs_nsec_l")
    a.lda_d(TMP).ldb_i(400).sab().bnc("fs_nsec_tail")
    a.lda_d(TMP).ldb_i(400).sab().stb_d(TMP)
    _inc(a, NSEC)
    a.jmp_abs("fs_nsec_l")
    a.label("fs_nsec_tail")
    a.lda_d(TMP).ldb_i(0).sab().bz("fs_read_secs")
    _inc(a, NSEC)
    a.label("fs_read_secs")
    a.lda_i(0).sta_d(J)
    a.lda_i(STAGE).sta_d(BPTR)
    a.label("fs_rs_l")
    a.lda_d(J).ldb_d(NSEC).sab().bl("fs_staged")
    a.lda_d(DSEC).ldb_d(SSEC).aab().stb_d(TMP)
    a.lda_d(TMP).ldb_d(J).aab().stb_d(CB)
    a.lda_d(BPTR).sta_d(CB + 2)
    a.jsr_abs("fs_rsec")
    _add(a, BPTR, 400)
    _inc(a, J)
    a.jmp_abs("fs_rs_l")
    a.label("fs_staged")
    a.lda_i(STAGE).ldb_d(SOFF).aab().stb_d(TPTR)
    a.rsr()
    a.label("fs_size_big")
    a.lda_i(1).sta_d(FSERR)
    a.jmp_abs("fs_staged")
    a.label("fs_peek")
    a.lda_d(TPTR).xaz().lda_i(0).ldab_z(0).stab_d(CH).rsr()
    a.label("fs_num")
    a.lda_i(0).sta_d(NUM)
    a.lda_i(0).sta_d(NDIG)
    a.label("fs_num_l")
    a.jsr_abs("fs_peek")
    a.ldbb_i(0x30).sabb().bnc("fs_num_done")
    a.xfrb_bl_al().ldbb_i(10).sabb().bl("fs_num_done")
    a.stab_d(CH)
    a.lda_d(NUM).sta_d(MADD)
    a.lda_i(10).sta_d(MCNT)
    a.jsr_abs("fs_mul")
    a.lda_i(0).ldab_d(CH).xfr("A", "B").lda_d(MRES).aab().stb_d(NUM)
    _inc(a, TPTR)
    _inc(a, NDIG)
    a.jmp_abs("fs_num_l")
    a.label("fs_num_done")
    a.rsr()
    a.label("fs_cmplit")
    a.lda_i(0).sta_d(MATCH)
    a.lda_d(CL).ldb_d(LL).sab().bnz("fs_cmplit_r")
    a.lda_d(CA).xaz()
    a.lda_d(LA).xfr("A", "Y")
    a.lda_i(0).sta_d(J)
    a.label("fs_cmplit_l")
    a.lda_d(J).ldb_d(CL).sab().bz("fs_cmplit_ok")
    a.lda_i(0).ldab_z(0).stab_d(CH)
    a.lda_i(0).ldab_x("Y", disp=0).xfrb_al_bl()
    a.lda_i(0).ldab_d(CH).sabb().bnz("fs_cmplit_r")
    _zinc(a)
    _yinc(a)
    _inc(a, J)
    a.jmp_abs("fs_cmplit_l")
    a.label("fs_cmplit_ok")
    a.lda_i(1).sta_d(MATCH)
    a.label("fs_cmplit_r")
    a.rsr()
    # directory scan: PASS=1 finds PAGE, PASS=2 computes NEXTP
    a.label("fs_scan")
    a.lda_i(16).sta_d(ROW)
    a.lda_i(0).sta_d(RCNT)
    a.lda_i(0xFFFF).sta_d(DIDX)
    a.label("fs_scan_l")
    a.lda_d(ROW).ldb_d(DBYTES).sab().bl("fs_scan_r")
    a.lda_d(RCNT).ldb_i(0).sab().bnz("fs_scan_row")
    _inc(a, DIDX)
    a.lda_d(DSEC).ldb_d(DIDX).aab().stb_d(CB)
    a.lda_i(STAGE).sta_d(CB + 2)
    a.jsr_abs("fs_rsec")
    a.lda_i(STAGE).sta_d(RPTR)
    a.lda_d(DIDX).ldb_i(0).sab().bnz("fs_scan_rc25")
    a.lda_i(24).sta_d(RCNT)
    _add(a, RPTR, 16)
    a.jmp_abs("fs_scan_row")
    a.label("fs_scan_rc25")
    a.lda_i(25).sta_d(RCNT)
    a.label("fs_scan_row")
    a.lda_d(RPTR).xaz()
    a.lda_i(0).ldab_z(0).ldbb_i(0x84).sabb().bnz("fs_scan_act")
    a.lda_i(0).ldab_z(1).ldbb_i(0x8D).sabb().bz("fs_scan_term")
    a.label("fs_scan_act")
    a.lda_i(0).ldab_z(10).sta_d(RPAGE)
    a.lda_i(0).ldab_z(12).ldb_i(8).sab().bnc("fs_scan_pg")      # row[12] < 8: no high part
    a.lda_i(0).ldab_z(12).ldb_i(8).sab().stb_d(MCNT)
    a.lda_i(128).sta_d(MADD)
    a.jsr_abs("fs_mul")
    a.lda_d(RPAGE).ldb_d(MRES).aab().stb_d(RPAGE)
    a.label("fs_scan_pg")
    a.lda_d(PASS).ldb_i(1).sab().bz("fs_scan_p1")
    # pass 2: track smallest page greater than PAGE
    a.lda_d(RPAGE).ldb_d(PAGE).sab().bz("fs_scan_next")
    a.lda_d(RPAGE).ldb_d(PAGE).sab().bnc("fs_scan_next")
    a.lda_d(NEXTP).ldb_d(RPAGE).sab().bz("fs_scan_next")
    a.lda_d(NEXTP).ldb_d(RPAGE).sab().bnc("fs_scan_next")
    a.lda_d(RPAGE).sta_d(NEXTP)
    a.jmp_abs("fs_scan_next")
    a.label("fs_scan_p1")
    a.lda_d(RPTR).xaz()
    a.lda_i(0).sta_d(J)                                         # J = stored name length
    a.label("fs_scan_nl")
    a.lda_d(J).ldb_i(10).sab().bl("fs_scan_nc")
    a.lda_i(0).ldab_z(0).ldbb_i(0x7F).andb_bl_al().ldbb_i(0x20).sabb().bz("fs_scan_nc")
    _zinc(a)
    _inc(a, J)
    a.jmp_abs("fs_scan_nl")
    a.label("fs_scan_nc")
    a.lda_d(J).ldb_d(NLEN).sab().bnz("fs_scan_next")
    a.lda_d(RPTR).xaz()
    a.lda_i(NAME).xfr("A", "Y")
    a.lda_i(0).sta_d(TMP)
    a.label("fs_scan_ccl")
    a.lda_d(TMP).ldb_d(NLEN).sab().bz("fs_scan_match")
    a.lda_i(0).ldab_z(0).ldbb_i(0x7F).andb_bl_al().stab_d(CH)
    a.lda_i(0).ldab_x("Y", disp=0).xfrb_al_bl()
    a.lda_i(0).ldab_d(CH).sabb().bnz("fs_scan_next")
    _zinc(a)
    _yinc(a)
    _inc(a, TMP)
    a.jmp_abs("fs_scan_ccl")
    a.label("fs_scan_match")
    a.lda_i(1).sta_d(FOUND)
    a.lda_d(RPAGE).sta_d(PAGE)
    a.lda_d(DIDX).sta_d(SSEC)
    a.lda_d(RPTR).ldb_i(STAGE).sab().stb_d(SOFF)
    a.label("fs_scan_next")
    _add(a, ROW, 16)
    _add(a, RPTR, 16)
    a.lda_d(RCNT).ldb_i(1).sab().stb_d(RCNT)
    a.jmp_abs("fs_scan_l")
    a.label("fs_scan_term")
    a.lda_d(DIDX).sta_d(NSEC)
    a.lda_d(RPTR).ldb_i(STAGE).sab().stb_d(BPTR)
    a.jmp_abs("fs_scan_r")
    a.label("fs_scan_r")
    a.rsr()
    a.label("fs_sys").raw(*b"SYSTEM")
    a.label("fs_help").raw(*b"HELP")
