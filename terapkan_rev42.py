# -*- coding: utf-8 -*-
"""Rev 42: tombol, menu kiri, kolom isian (dropdown/teks), tab, dan tombol -/+ di panel ikut membesar/mengecil bersama layar.
Jalankan dari folder proyek:   python terapkan_rev42.py        (aman diulang, tahan CRLF)
Yang diubah HANYA panel/index.html (cadangan: panel/index.html.rev42.bak, dibuat sekali) + satu entri di docs/SYNOP_UPGRADE_HANDOFF.txt.
Bila dist/SynopOtomatis/_internal/panel/index.html ada (hasil build), berkas itu ikut diperbarui -> tidak perlu build ulang; cukup tutup lalu buka SynopOtomatis.exe."""
import re
import shutil
from pathlib import Path

TARGET = ["panel/index.html", "dist/SynopOtomatis/_internal/panel/index.html"]
MARK = "/* rev42"
CAT = ("  [2026-11-26] Rev 42 - panel/index.html: tombol/menu/kolom isian tampak kecil di monitor besar (PC kantor) padahal judul & teks sudah membesar. AKAR: 6 deklarasi CSS berbentuk\n"
       "               'font:600 0.8125rem inherit' (.bt, .nv, .tab button, .zm button, .chip-tombol, input/select) TIDAK VALID (kata 'inherit' tidak boleh jadi nama font di dalam singkatan font);\n"
       "               browser membuang seluruh deklarasi -> elemen memakai ukuran bawaan Chrome 13,33px TETAP (tidak ikut rem). Di laptop (skala 1) 13,33px kebetulan mendekati 13px rancangan,\n"
       "               jadi tampak benar; di monitor besar teks lain membesar sedangkan tombol tidak. (Kesalahan ini sudah ada sejak rev 38 dalam px; rev 39 baru memunculkannya.)\n"
       "               Perbaikan: 'font:W S inherit' -> 'font-weight:W;font-size:S' dan aturan baru 'input,select,textarea,.in{font-family:inherit}' (button sudah punya). Semua ukuran tetap rem sehingga\n"
       "               ikut skala otomatis + tombol -/+. Hanya panel/index.html yang berubah. CATATAN revisi berikutnya: JANGAN menulis 'font:... inherit'; pakai font-size/font-weight terpisah.\n")

FONT_RE = re.compile(r"font:\s*(?:(\d{3})\s+)?([\d.]+(?:rem|px))\s+inherit")
RULE_LAMA = "button{font-family:inherit}"
RULE_BARU = RULE_LAMA + "/* rev42 */input,select,textarea,.in{font-family:inherit}"


def terapkan(s):
    """Teks baru, atau None bila sudah beres. ValueError bila struktur tak dikenali (berkas tidak disentuh)."""
    if MARK in s and not FONT_RE.search(s):
        return None
    if s.count(RULE_LAMA) != 1:
        raise ValueError(RULE_LAMA)
    s = FONT_RE.sub(lambda m: ("font-weight:%s;" % m.group(1) if m.group(1) else "") + "font-size:" + m.group(2), s)
    return s.replace(RULE_LAMA, RULE_BARU, 1)


def baca(p):
    b = p.read_bytes().decode("utf-8"); return b.replace("\r\n", "\n"), ("\r\n" if "\r\n" in b else "\n")


def tulis(p, s, nl): p.write_bytes(s.replace("\n", nl).encode("utf-8"))


if __name__ == "__main__":
    gagal = 0
    for f in TARGET:
        p = Path(f)
        if not p.exists():
            if f == TARGET[0]:
                print("TIDAK ADA  ", f, "- jalankan dari folder proyek"); gagal += 1
            continue
        s, nl = baca(p)
        try:
            baru = terapkan(s)
        except ValueError as e:
            print("GAGAL      ", f, "- teks tidak dikenali (%s); berkas TIDAK diubah" % e); gagal += 1; continue
        if baru is None:
            print("sudah      ", f); continue
        bak = p.with_name(p.name + ".rev42.bak")
        if not bak.exists():
            shutil.copy2(p, bak)
        tulis(p, baru, nl); print("DIPASANG   ", f, "- cadangan:", bak.name)
    H = Path("docs/SYNOP_UPGRADE_HANDOFF.txt")
    if H.exists():
        s, nl = baca(H)
        if "Rev 42" in s:
            print("sudah       handoff")
        else:
            k = s.rfind("\n" + "#" * 80 + "\n#  AKHIR FILE")
            s = (s[:k].rstrip("\n") + "\n" + CAT + s[k:]) if k >= 0 else s.rstrip("\n") + "\n" + CAT
            s = re.sub(r"(Revisi catatan\s*:\s*)\d+", r"\g<1>42", s, count=1)
            tulis(H, s, nl); print("DIPASANG    handoff")
    print("\nSELESAI - tutup lalu buka lagi SynopOtomatis.exe (atau build_exe.bat bila dist belum ikut diperbarui)" if not gagal else "\n%d berkas GAGAL" % gagal)
