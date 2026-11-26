# -*- coding: utf-8 -*-
"""Perbaikan tes rev 38b. Jalankan dari folder proyek:  python terapkan_rev38b.py   (aman diulang, tahan CRLF)"""
from pathlib import Path
EDITS=[["tests/test_panel.py", "passed = failed = 0\n", "passed = failed = 0\nWEB_PIN_AWAL = os.environ.get(\"WEB_PIN\")      # bisa sudah ada di Windows pengguna (setx / $env:WEB_PIN); yang diuji: tes TIDAK mengubahnya\n"], ["tests/test_panel.py", "      and post(\"/api/rahasia\", {\"kunci\": \"WEB_PIN\", \"nilai\": \"a\\nb\"}).status_code == 400)\ncheck(\"load_config(muat_env=False) tidak mengotori environment panel\", \"WEB_PIN\" not in os.environ)\n", "      and post(\"/api/rahasia\", {\"kunci\": \"WEB_PIN\", \"nilai\": \"a\\nb\"}).status_code == 400)\ncheck(\"load_config(muat_env=False) tidak mengotori environment panel\", os.environ.get(\"WEB_PIN\") == WEB_PIN_AWAL)\n"]]
CAT="  [2026-11-26] Rev 38b - tests/test_panel.py: tes 'tidak mengotori environment' kini membandingkan WEB_PIN sebelum/sesudah (bukan 'tidak ada'), karena WEB_PIN bisa sudah ada\n               sebagai variabel environment Windows pengguna. Aplikasi tidak berubah.\n"
def baca(p):
    b=p.read_bytes().decode("utf-8");return b.replace("\r\n","\n"),("\r\n" if "\r\n" in b else "\n")
def tulis(p,s,nl):p.write_bytes(s.replace("\n",nl).encode("utf-8"))
gagal=0
for f,lama,baru in EDITS:
    p=Path(f)
    if not p.exists():print("TIDAK ADA ",f);gagal+=1;continue
    s,nl=baca(p)
    if baru in s:print("sudah      ",f)
    elif lama in s:tulis(p,s.replace(lama,baru,1),nl);print("DIPASANG   ",f)
    else:print("GAGAL      ",f,"- teks asli tidak ditemukan");gagal+=1
H=Path("docs/SYNOP_UPGRADE_HANDOFF.txt")
if H.exists():
    s,nl=baca(H)
    if "Rev 38b" in s:print("sudah       handoff")
    else:
        k=s.rfind("\n"+"#"*80+"\n#  AKHIR FILE");s=(s[:k].rstrip("\n")+"\n"+CAT+s[k:]) if k>=0 else s.rstrip("\n")+"\n"+CAT
        tulis(H,s,nl);print("DIPASANG    handoff")
print("\nSELESAI - jalankan: python tests\\test_panel.py" if not gagal else "\n%d bagian GAGAL"%gagal)
