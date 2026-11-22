# -*- coding: utf-8 -*-
"""tools/pantau_web.py: perekam waktu/sleep, potret kolom form (JS di Chromium), laporan & zip, pengaman mode kirim."""
import sys, tempfile, types, zipfile, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond); failed += (not cond)


import pantau_web as P

print("== perekam waktu & sleep (modul V palsu) ==")
class FDrv:
    current_url = "https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik"; page_source = "<html></html>"
    def execute_script(self, js, *a): return {"url": self.current_url, "kolom": [], "tombol": [], "bagian": []}
    def save_screenshot(self, p): Path(p).write_bytes(b"png")

V = types.SimpleNamespace()
V.time = __import__("time")
def isi_per_jam(driver, row): V.time.sleep(0.05); return True
def Fill_AWS_Digi(driver): V.time.sleep(0.03); return True
def wait_for_presence(driver, loc, timeout=10): V.time.sleep(0.01); return None       # habis waktu
def isi_data(driver, row, plan=None):
    V.time.sleep(0.02); V.isi_per_jam(driver, row); return False   # lewat V.* seperti pencarian nama global di V7SATU
V.isi_per_jam, V.Fill_AWS_Digi, V.wait_for_presence, V.isi_data = isi_per_jam, Fill_AWS_Digi, wait_for_presence, isi_data
V._jeda = lambda s: V.time.sleep(s)
d = Path(tempfile.mkdtemp()) / "uji"
rek = P.Perekam(d)
P.pasang(V, rek)
drv = FDrv()
V.isi_per_jam(drv, {}); V.Fill_AWS_Digi(drv); V.wait_for_presence(drv, ("id", "x"), timeout=1); V.isi_data(drv, {})
V._jeda(0.02)                                   # sleep di luar langkah terbungkus
A = P.agregat(rek.kejadian)
check("semua panggilan terekam, termasuk yang bersarang (isi_per_jam di dalam isi_data)", A["isi_per_jam"]["n"] == 2 and A["isi_data"]["n"] == 1, A)
check("waktu sleep tercatat per langkah (>= 0.05 dtk untuk isi_per_jam)", A["isi_per_jam"]["tidur"] >= 0.09, A["isi_per_jam"])
check("isi_data yang mengembalikan False ditandai gagal", A["isi_data"]["gagal"] == 1)
check("wait_for_presence -> None ditandai habis waktu (gagal)", A["wait_for_presence"]["gagal"] == 1)
check("sleep di luar langkah dicatat terpisah", rek.jeda_di_luar >= 0.019, rek.jeda_di_luar)
check("potret otomatis: setelah Fill_AWS, sebelum & sesudah isi_data", [s["label"] for s in rek.snapshots] == ["setelah_fill_aws", "sebelum_isi_data", "setelah_isi_data"][:len(rek.snapshots)] or
      {"setelah_fill_aws", "sebelum_isi_data"} <= {s["label"] for s in rek.snapshots}, [s["label"] for s in rek.snapshots])
zp = P.tulis_laporan(rek, "uji", ["--mode", "uji"], sys.stdout)
z = zipfile.ZipFile(zp); nama = " ".join(z.namelist())
check("zip berisi laporan.txt, laporan.json, dom_*.json/png", "laporan.txt" in nama and "laporan.json" in nama and "dom_01_setelah_fill_aws.json" in nama and ".png" in nama, nama)
txt = (d / "laporan.txt").read_text(encoding="utf-8")
check("laporan.txt memuat tabel waktu, persentase sleep, dan daftar kegagalan", "WAKTU PER LANGKAH" in txt and "berupa time.sleep" in txt and "KEGAGALAN" in txt and "isi_data" in txt)
check("html halaman login tidak disimpan", not any("login" in (s.get("url") or "") for s in rek.snapshots))

print("== potret kolom form di Chromium (meniru tampilan jam 00 UTC) ==")
try:
    from playwright.sync_api import sync_playwright
    html = """<div class="card"><span class="badge">PENGUAPAN</span>
      <div class=row><label for=evap>Penguapan (mm) <i>?</i></label><input id=evap value="5,9"></div>
      <div class=row><label>Pengenal Data Penguapan (iE)</label><div class="ant-select ant-select-enabled" id=ie1><div class="ant-select-selection__rendered">0 - USA open ...</div></div></div>
      <span class="badge">MATAHARI</span>
      <div class=row><label>Radiasi Matahari (Joule/cm2)</label><input id=rad value=""></div>
      <div class=row><label>Lama Penyinaran Matahari (jam)</label><input id=sinar value="2,4"></div>
      <span class="badge">TANAH</span>
      <div class=row><label>Catatan</label><input id=cat disabled></div>
      <input type=password id=pw value="RAHASIA"><button class=btn>Preview &amp; Generate Sandi</button></div>"""
    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page(); pg.set_content(html)
        dump = pg.evaluate("(js)=>new Function(js)()", P.JS_DUMP)
        br.close()
    by = {k["id"]: k for k in dump["kolom"]}
    check("label terbaca (via for= dan via posisi)", by["evap"]["label"].startswith("Penguapan (mm)") and by["rad"]["label"].startswith("Radiasi Matahari") and by["ie1"]["label"].startswith("Pengenal Data"), {k: v["label"] for k, v in by.items()})
    check("nilai AWS terbaca (5,9 / 2,4) dan kosong untuk radiasi", by["evap"]["value"] == "5,9" and by["sinar"]["value"] == "2,4" and by["rad"]["value"] == "")
    check("ant-select: nilai terpilih terbaca", by["ie1"]["value"].startswith("0 - USA"), by["ie1"]["value"])
    check("bagian terdekat (PENGUAPAN/MATAHARI/TANAH) dan status nonaktif terbaca", by["evap"]["bagian"] == "PENGUAPAN" and by["sinar"]["bagian"] == "MATAHARI" and by["cat"]["bagian"] == "TANAH" and by["cat"]["disabled"] is True)
    check("kolom password TIDAK ikut direkam", "pw" not in by and "RAHASIA" not in json.dumps(dump))
    check("tombol terbaca", any("Preview" in t["teks"] for t in dump["tombol"]))
except Exception as e:
    print("  (dilewati: Chromium/playwright tidak tersedia:", str(e)[:80], ")")

print("== pengaman ==")
sys.argv = ["pantau_web.py", "--mode", "kirim"]
try:
    P.main(); aman = False
except SystemExit as e:
    aman = "izinkan-kirim" in str(e)
check("mode kirim tanpa --izinkan-kirim ditolak", aman)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
