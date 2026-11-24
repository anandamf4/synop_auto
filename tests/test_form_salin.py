# -*- coding: utf-8 -*-
"""rev 32: tombol 'Salin dari jam sebelumnya' harus berhasil dengan SATU klik; keadaan tanah di bagian bawah; iE dropdown.
Memakai server Flask nyata + jsdom (node). Dilewati bila node/jsdom tidak ada.   python tests/test_form_salin.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.pop("WEB_PIN", None)
from werkzeug.serving import make_server  # noqa: E402
from app import create_app  # noqa: E402
from core.config import load_config  # noqa: E402
from core.formschema import opsi_kolom  # noqa: E402

passed = failed = 0


def check(n, c, info=""):
    global passed, failed
    print(("  OK   " if c else "  GAGAL"), n, "" if c else f"-> {info}")
    passed += bool(c)
    failed += (not c)


def cari_jsdom():
    for d in (ROOT / "tests" / "js", ROOT, Path.home() / "jstest", Path("/home/claude/jstest")):
        if (d / "node_modules" / "jsdom").exists():
            return d
    return None


node, mod = shutil.which("node"), cari_jsdom()
if not node or not mod:
    print("  (dilewati: node/jsdom tidak tersedia -- npm install jsdom di folder tests/js)")
    print("\nHasil: 0 lulus, 0 gagal")
    sys.exit(0)

T = "2026-11-14"
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    cfg = load_config()
    os.environ.pop("WEB_PIN", None)
    app = create_app(cfg, db_path=str(Path(d) / "a.db"))

    def op(col, kode, awalan=None):
        return next(o for o in opsi_kolom(app.validator, col) if o.split(" ")[0] == kode and (awalan is None or awalan in o))

    # jam sebelumnya (06:00) berisi awan lengkap (tiga lapisan) -> disalin ke 07:00
    data = {"cloud_cover_oktas_m": op("cloud_cover_oktas_m", "7"), "visibility": 2, "ww": op("ww", "10"), "w1": op("w1", "2"),
            "w2": op("w2", "2"), "land_cond": op("land_cond", "0"),
            "cloud_low_type_cl": op("cloud_low_type_cl", "5"), "cloud_low_cover_oktas": op("cloud_low_cover_oktas", "3"),
            "awan_rendah_jenis": op("awan_rendah_jenis", "6"), "awan_rendah_jumlah": op("awan_rendah_jumlah", "3"),
            "cloud_low_base_1": 450, "cloud_arah_awan_rendah": op("cloud_arah_awan_rendah", "0"),
            "cloud_med_type_cm": op("cloud_med_type_cm", "3"), "cloud_med_cover_oktas": op("cloud_med_cover_oktas", "4"),
            "awan_menengah_jenis_1": op("awan_menengah_jenis_1", "3"), "awan_menengah_jumlah_1": op("awan_menengah_jumlah_1", "4"),
            "cloud_med_base_1": 3000, "cloud_arah_menengah_1": op("cloud_arah_menengah_1", "0"),
            "cloud_high_type_ch": op("cloud_high_type_ch", "1"), "cloud_high_cover_oktas": op("cloud_high_cover_oktas", "2"),
            "awan_tinggi_jenis": op("awan_tinggi_jenis", "0"), "awan_tinggi_jumlah": op("awan_tinggi_jumlah", "2"),
            "cloud_high_base_1": 9000, "cloud_arah_tinggi": op("cloud_arah_tinggi", "0")}
    app.obs.upsert(T, "06:00", data, "Tester")
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    port = srv.server_port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        env = dict(os.environ, NODE_PATH=str(mod / "node_modules"))
        p = subprocess.run([node, str(ROOT / "tests" / "js" / "form_jsdom.js"), f"http://127.0.0.1:{port}", T, "07:00"],
                           capture_output=True, text=True, timeout=90, env=env)
        check("jsdom berjalan tanpa galat", p.returncode == 0 and p.stdout.strip(), p.stderr[-300:])
        r = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
    finally:
        srv.shutdown()

    s1 = r.get("sesudah1", {})
    print("== salin dengan SATU klik ==")
    kolom = [k for k in data if k not in ()]
    hilang = [k for k in kolom if str(s1.get(k, "")) != str(data[k]).replace(".0", "")]
    check("semua kolom (termasuk NCL, Jenis, Jumlah, tinggi dasar, arah) terisi setelah SATU klik", not hilang, hilang)
    check("form kosong sebelum salin", not r.get("awal"), r.get("awal"))

    print("== letak & bentuk kolom ==")
    check("keadaan tanah ada di bagian paling bawah (bukan 'Umum')", "bag-penguapan" in (r.get("bagianTanah") or ""), r.get("bagianTanah"))
    check("urutan bagian bawah: penguapan, radiasi, tanah, iE, lama penyinaran",
          [k for k in r.get("urutan", [])] == ["penguapan_mm", "radiasi_kosongkan", "radiasi_matahari", "land_cond", "penguapan_ie", "lama_penyinaran_jam"],
          r.get("urutan"))
    check("jam 07: kolom khusus 00 UTC disembunyikan, keadaan tanah tetap tampil",
          "land_cond" not in r.get("hidden", []) and {"penguapan_mm", "penguapan_ie", "lama_penyinaran_jam"} <= set(r.get("hidden", [])), r.get("hidden"))
    check("iE = dropdown 5 pilihan (0-4) bernilai kode", [o.split("|")[0] for o in (r.get("ie") or [])] == ["", "0", "1", "2", "3", "4"], r.get("ie"))

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
