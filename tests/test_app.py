# -*- coding: utf-8 -*-
"""Uji F2.2/F2.3/F2.5/F2.6: API web (Flask test client), tanpa jaringan.   python tests/test_app.py"""
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.pop("WEB_PIN", None)
import pandas as pd  # noqa: E402
from app import create_app  # noqa: E402
from core.config import load_config  # noqa: E402
from core.formschema import opsi_kolom  # noqa: E402

passed = failed = 0


def check(n, c, info=""):
    global passed, failed
    print(("  OK   " if c else "  GAGAL"), n, "" if c else f"-> {info}")
    passed += bool(c)
    failed += (not c)


T, J = "2026-11-14", "07:00"


def op(app, col, kode):
    return next(o for o in opsi_kolom(app.validator, col) if o.split(" ")[0] == kode)


with tempfile.TemporaryDirectory() as d:
    app = create_app(load_config(), db_path=str(Path(d) / "a.db"))
    c = app.test_client()
    cerah = {"cloud_cover_oktas_m": op(app, "cloud_cover_oktas_m", "0"), "visibility": 10, "ww": op(app, "ww", "00"),
             "w1": op(app, "w1", "0"), "w2": op(app, "w2", "0"), "land_cond": op(app, "land_cond", "0")}

    print("== halaman & status ==")
    check("dashboard, form, skema terbuka", all(c.get(u).status_code == 200 for u in ("/", f"/form/{T}/{J}", "/api/skema")))
    check("slot dengan format salah -> 400", c.get("/form/2026-13-99/07:00").status_code == 400 and c.get(f"/form/{T}/07:30").status_code == 400)
    j = c.get(f"/api/status?tanggal={T}").get_json()
    check("status: 24 jam, semua 'kosong' di awal", len(j["baris"]) == 24 and all(b["level"] == "kosong" for b in j["baris"]))

    print("\n== validasi & simpan ==")
    r = c.post("/api/validasi", json={"tanggal": T, "jam": J, "data": cerah}).get_json()
    check("data cerah lengkap: ok, tanpa ERROR", r["ok"] and not [t for t in r["temuan"] if t["level"] == "ERROR"], r["temuan"])
    r = c.post("/api/validasi", json={"tanggal": T, "jam": J, "data": {"visibility": 10}}).get_json()
    check("data belum lengkap: ok=false (wajib diisi)", not r["ok"])
    r = c.post("/api/simpan", json={"tanggal": T, "jam": J, "data": cerah})
    check("simpan tanpa observer -> 422", r.status_code == 422)
    bad = dict(cerah, cloud_cover_oktas_m=op(app, "cloud_cover_oktas_m", "9"))
    r = c.post("/api/simpan", json={"tanggal": T, "jam": J, "data": bad, "observer": "Tester"})
    check("kombinasi melanggar aturan (N=9 tanpa vertical visibility, vis 10 km) DITOLAK 422 dan tidak tersimpan",
          r.status_code == 422 and app.obs.get(T, J) is None, r.get_json())
    r = c.post("/api/simpan", json={"tanggal": T, "jam": J, "data": dict(cerah, cloud_low_type_cl=op(app, "cloud_low_type_cl", "3"),
                                                                           awan_rendah_jenis="8 - cumulus (Cu)"), "observer": "Tester"})
    d1 = app.obs.get(T, J)
    check("simpan OK (kolom awan yang nonaktif saat total 0 TIDAK ikut tersimpan)", r.status_code == 200 and d1 and
          "cloud_low_type_cl" not in d1 and "awan_rendah_jenis" not in d1, (r.get_json(), d1))
    j = c.get(f"/api/slot/{T}/{J}").get_json()
    check("buka lagi: data utuh + siapa pengisinya", j["ada"] and j["data"] == d1 and j["info"]["diubah_oleh"] == "Tester")
    st = {b["jam"]: b for b in c.get(f"/api/status?tanggal={T}").get_json()["baris"]}
    check("status jam 07: hijau", st["07:00"]["level"] == "hijau" and st["07:00"]["oleh"] == "Tester", st["07:00"])

    print("\n== salin jam sebelumnya ==")
    check("tidak ada data jam sebelumnya -> 404", c.get(f"/api/salin?tanggal={T}&jam=09:00").status_code == 404)
    app.obs.upsert(T, "06:00", dict(cerah, hujan_override_aktif=True, hujan_override_mm=5), "Tester")
    j = c.get(f"/api/salin?tanggal={T}&jam={J}").get_json()
    check("salin dari 06:00; override hujan TIDAK ikut tersalin", j["ada"] and j["dari"] == [T, "06:00"] and
          "hujan_override_mm" not in j["data"] and j["data"]["ww"] == cerah["ww"], j)
    app.obs.upsert("2026-11-13", "23:00", cerah, "Tester")
    check("salin dari 23:00 hari sebelumnya (lintas hari UTC)", c.get("/api/salin?tanggal=2026-11-14&jam=00:00").get_json()["dari"] == ["2026-11-13", "23:00"])

    print("\n== slot yang sudah terkirim ==")
    app.log.register(T, J)
    app.log.start_attempt(T, J)
    app.log.mark_sent(T, J, kode_synop="AAXX ...")
    r = c.post("/api/simpan", json={"tanggal": T, "jam": J, "data": cerah, "observer": "Tester"})
    check("ubah jam yang sudah terkirim -> 409 minta konfirmasi", r.status_code == 409 and r.get_json()["perlu_konfirmasi"])
    r = c.post("/api/simpan", json={"tanggal": T, "jam": J, "data": cerah, "observer": "Tester", "paksa": True})
    check("dengan konfirmasi (paksa) -> tersimpan", r.status_code == 200)
    check("hapus jam yang sudah terkirim ditolak 409", c.post("/api/hapus", json={"tanggal": T, "jam": J}).status_code == 409)
    c.post("/api/hapus", json={"tanggal": T, "jam": "06:00"})
    check("hapus jam biasa berhasil", app.obs.get(T, "06:00") is None)
    st = {b["jam"]: b for b in c.get(f"/api/status?tanggal={T}").get_json()["baris"]}
    check("status memuat status kirim & sandi", st["07:00"]["kirim"] == "sent" and st["07:00"]["sandi"] == "AAXX ...")

    print("\n== Excel (F2.6) ==")
    xl = ROOT / "legacy" / "INPUT_PARAMETER_baru.xlsx"
    if xl.exists():
        r = c.post("/api/impor", data={"berkas": (open(xl, "rb"), "in.xlsx"), "observer": "Tester"}, content_type="multipart/form-data")
        j = r.get_json()
        check("impor Excel nyata: 24 baris masuk, 0 ditolak", j["ok"] and j["masuk"] == 24 and not j["ditolak"], j)
        r = c.get(f"/ekspor/{T}.xlsx")
        df = pd.read_excel(io.BytesIO(r.data))
        check("ekspor: berkas Excel berisi 24 baris dengan kolom lengkap", len(df) == 24 and "waktu_eksekusi" in df.columns and "cloud_low_type_cl" in df.columns, len(df))
    r = c.post("/api/impor", data={"berkas": (io.BytesIO(b"ini bukan berkas excel"), "x.xlsx")}, content_type="multipart/form-data")
    check("berkas rusak ditolak dengan pesan (bukan crash)", r.status_code == 400 and not r.get_json()["ok"])

print("\n== PIN ==")
os.environ["WEB_PIN"] = "4321"
with tempfile.TemporaryDirectory() as d:
    app2 = create_app(load_config(), db_path=str(Path(d) / "b.db"))
    c2 = app2.test_client()
    check("tanpa PIN: halaman diarahkan ke /login, API 401", c2.get("/").status_code == 302 and c2.get("/api/status").status_code == 401)
    check("PIN salah ditolak", c2.post("/login", data={"pin": "0000"}).status_code == 401)
    check("PIN benar: akses terbuka", c2.post("/login", data={"pin": "4321"}).status_code == 302 and c2.get("/").status_code == 200)
os.environ.pop("WEB_PIN", None)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
