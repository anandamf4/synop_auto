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



def cfg_tanpa_pin():
    cfg = load_config()                  # membaca .env -> bisa mengisi WEB_PIN; harus dibuang SESUDAH ini, bukan sebelum
    os.environ.pop("WEB_PIN", None)
    return cfg


def op(app, col, kode):
    return next(o for o in opsi_kolom(app.validator, col) if o.split(" ")[0] == kode)


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    _cfg = load_config()                 # load_config() membaca .env -> bisa mengisi WEB_PIN lagi
    os.environ.pop("WEB_PIN", None)      # tes ini mengukur perilaku TANPA PIN
    app = create_app(_cfg, db_path=str(Path(d) / "a.db"))
    c = app.test_client()
    cerah = {"cloud_cover_oktas_m": op(app, "cloud_cover_oktas_m", "0"), "visibility": 10, "ww": op(app, "ww", "00"),
             "w1": op(app, "w1", "0"), "w2": op(app, "w2", "0"), "land_cond": op(app, "land_cond", "0")}

    print("== halaman & status ==")
    check("dashboard, form, skema terbuka", all(c.get(u).status_code == 200 for u in ("/", f"/form/{T}/{J}", "/api/skema")))
    dash = c.get("/").get_data(as_text=True)
    check("picker tanggal hanya satu: ikon kalender ekstra tidak ada", 'id="buka-tgl"' not in dash)
    check("slot dengan format salah -> 400", c.get("/form/2026-13-99/07:00").status_code == 400 and c.get(f"/form/{T}/07:30").status_code == 400)
    j = c.get(f"/api/status?tanggal={T}").get_json()
    check("status: 24 jam, semua 'kosong' di awal", len(j["baris"]) == 24 and all(b["level"] == "kosong" for b in j["baris"]))

    print("\n== validasi & simpan ==")
    r = c.post("/api/validasi", json={"tanggal": T, "jam": J, "data": cerah}).get_json()
    check("data cerah lengkap: ok, tanpa ERROR", r["ok"] and not [t for t in r["temuan"] if t["level"] == "ERROR"], r["temuan"])
    r = c.post("/api/validasi", json={"tanggal": T, "jam": J, "data": {"visibility": 10}}).get_json()
    check("data belum lengkap: ok=false (wajib diisi)", not r["ok"])
    r = c.post("/api/simpan", json={"tanggal": T, "jam": J, "data": cerah})
    check("[rev 28] simpan tanpa observer BERHASIL (observer opsional)", r.status_code == 200 and r.get_json()["ok"], r.get_json())
    check("tanpa observer: pengubah kosong (bukan teks 'None')", app.obs.info(T, J)["diubah_oleh"] in (None, ""), app.obs.info(T, J))
    app.obs.delete(T, J)      # bersihkan agar pengujian berikutnya (penolakan data buruk) mulai dari slot kosong
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
        # tanggal slot diturunkan dari waktu_eksekusi di Excel (bukan T tetap), jadi ekspor semua tanggal yang masuk
        with app.obs._conn() as _c:
            _tgl = [x[0] for x in _c.execute("SELECT DISTINCT tanggal_utc FROM observasi ORDER BY 1")]
            _n_db = _c.execute("SELECT COUNT(*) FROM observasi").fetchone()[0]   # DB tes juga memuat baris dari tes sebelumnya
        df = pd.concat([pd.read_excel(io.BytesIO(c.get(f"/ekspor/{t}.xlsx").data)) for t in _tgl], ignore_index=True)
        check("ekspor: semua baris di DB (24 dari Excel + sisa tes lain) dengan kolom lengkap", len(df) == _n_db >= 24 and "waktu_eksekusi" in df.columns and "cloud_low_type_cl" in df.columns, len(df))
    r = c.post("/api/impor", data={"berkas": (io.BytesIO(b"ini bukan berkas excel"), "x.xlsx")}, content_type="multipart/form-data")
    check("berkas rusak ditolak dengan pesan (bukan crash)", r.status_code == 400 and not r.get_json()["ok"])

    print("\n== nilai Excel (kode saja) tampil di dropdown form ==")
    mentah = {"cloud_cover_oktas_m": 0, "visibility": 10, "ww": "00", "w1": 0, "w2": 0, "land_cond": 0,
              "hujan_override_aktif": "ya", "hujan_override_mm": 2}
    hook, app.obs.kanonik = app.obs.kanonik, None          # simpan MENTAH seperti hasil impor lama
    app.obs.upsert("2026-12-05", "09:00", mentah, "import Excel")
    app.obs.kanonik = hook
    j = c.get("/api/slot/2026-12-05/09:00").get_json()["data"]
    cocok = all(j[k] in opsi_kolom(app.validator, k) for k in ("cloud_cover_oktas_m", "ww", "w1", "w2", "land_cond"))
    check("data mentah (0, '00', 'ya') dikembalikan sebagai teks opsi persis dropdown", cocok and j["hujan_override_aktif"] is True, j)
    check("nilai angka (visibilitas, curah hujan) tidak berubah", j["visibility"] == 10 and j["hujan_override_mm"] == 2, j)
    app.obs.upsert("2026-12-05", "10:00", {"cloud_cover_oktas_m": 0, "ww": "00", "w1": 0, "w2": 0, "land_cond": 0, "visibility": 10}, "x")
    check("simpan lewat app menyimpan teks opsi (bukan kode mentah)", app.obs.get("2026-12-05", "10:00")["ww"] == cerah["ww"])
    check("salin jam sebelumnya juga memakai teks opsi", c.get("/api/salin?tanggal=2026-12-05&jam=11:00").get_json()["data"]["ww"] == cerah["ww"])

    print("\n== salin dari tanggal lain (rentang jam) ==")
    S, K = "2026-12-01", "2026-12-02"
    for h in (6, 7, 8):
        app.obs.upsert(S, f"{h:02d}:00", dict(cerah, **({"hujan_override_aktif": True, "hujan_override_mm": 3} if h == 6 else {})), "Tester")
    def salin(**kw):
        b = {"dari_tanggal": S, "ke_tanggal": K, "seharian": True, "mode": "lewati", "observer": "Tester"}
        b.update(kw)
        return c.post("/api/salin_rentang", json=b)
    r = salin(pratinjau=True).get_json()
    check("pratinjau seharian: 3 jam akan disalin, TIDAK menulis apa pun", r["ok"] and len(r["disalin"]) == 3 and r["pratinjau"] and app.obs.get(K, "06:00") is None, r)
    check("tanpa data sumber dilaporkan (21 jam)", len(r["tanpa_sumber"]) == 21, r)
    r = salin(seharian=False, jam_dari=6, jam_sampai=8).get_json()
    check("salin rentang 06-08: 3 jam masuk", len(r["disalin"]) == 3 and all(app.obs.get(K, f"{h:02d}:00") for h in (6, 7, 8)), r)
    j = c.get(f"/api/slot/{K}/06:00").get_json()
    check("hasil salinan terbuka lengkap di form & override hujan TIDAK ikut", j["ada"] and j["data"]["ww"] == cerah["ww"] and "hujan_override_mm" not in j["data"], j["data"])
    check("diubah_oleh = observer yang menyalin", j["info"]["diubah_oleh"] == "Tester")
    r = salin().get_json()
    check("mode lewati: jam yang sudah terisi tidak disentuh", r["lewati_terisi"] == ["06:00", "07:00", "08:00"] and not r["disalin"], r)
    app.obs.upsert(K, "08:00", dict(cerah, visibility=4), "Tester")
    r = salin(mode="timpa").get_json()
    check("mode timpa: menimpa 3 jam, ditandai menimpa", len(r["disalin"]) == 3 and all(x["menimpa"] for x in r["disalin"]), r)
    check("timpa benar-benar mengganti isi (visibilitas 4 -> 10)", app.obs.get(K, "08:00")["visibility"] == 10)
    app.log.register(K, "07:00"); app.log.start_attempt(K, "07:00"); app.log.mark_sent(K, "07:00", kode_synop="AAXX")
    app.obs.upsert(K, "07:00", dict(cerah, visibility=2), "Tester")
    r = salin(mode="timpa").get_json()
    check("jam yang sudah TERKIRIM tidak diubah sama sekali", r["lewati_terkirim"] == ["07:00"] and len(r["disalin"]) == 2
          and app.obs.get(K, "07:00")["visibility"] == 2, r)
    check("[rev 28] salin tanpa observer diterima (opsional)", salin(observer="").status_code == 200)
    check("pratinjau tanpa observer boleh", salin(observer="", pratinjau=True).status_code == 200)
    check("tanggal sumber = tujuan -> 400", salin(ke_tanggal=S).status_code == 400)
    check("rentang terbalik -> 400", salin(seharian=False, jam_dari=9, jam_sampai=3).status_code == 400)
    check("jam di luar 00-23 -> 400", salin(seharian=False, jam_dari=0, jam_sampai=24).status_code == 400)
    check("format tanggal salah -> 400", salin(dari_tanggal="2026-13-99").status_code == 400)
    check("mode tak dikenal -> 400", salin(mode="hapus").status_code == 400)

print("\n== status tertahan: berjalan macet / atur ulang (rev 23) ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    _cfg = load_config()
    os.environ.pop("WEB_PIN", None)
    app3 = create_app(_cfg, db_path=str(Path(d) / "c.db"))
    c3 = app3.test_client()
    L = app3.log
    L.register(T, "01:00")
    L.start_attempt(T, "01:00", observer="Tester")          # meniru bot yang mati saat slot berjalan
    b = {x["jam"]: x for x in c3.get(f"/api/status?tanggal={T}").get_json()["baris"]}["01:00"]
    check("baru mulai: status berjalan, BELUM macet", b["kirim"] == "running" and b["macet"] is False, b)
    L.conn.execute("UPDATE send_log SET waktu_mulai='2020-01-01T00:00:00' WHERE tanggal_utc=? AND jam='01:00'", (T,))
    L.conn.commit()
    b = {x["jam"]: x for x in c3.get(f"/api/status?tanggal={T}").get_json()["baris"]}["01:00"]
    check("berjalan > 15 menit: ditandai macet", b["kirim"] == "running" and b["macet"] is True, b)
    r = c3.post("/api/atur_ulang", json={"tanggal": T, "jam": "01:00", "aksi": "ulang"})
    check("atur ulang -> pending + tercatat di events", r.status_code == 200 and L.get(T, "01:00")["status"] == "pending"
          and any(e["event"] == "diatur_ulang" for e in L.events(T, "01:00")), r.get_json())
    check("sesudah diatur ulang bot boleh kirim lagi", L.should_send(T, "01:00")["send"] is True)
    check("atur ulang saat sudah 'menunggu' -> 409", c3.post("/api/atur_ulang", json={"tanggal": T, "jam": "01:00"}).status_code == 409)
    L.register(T, "02:00"); L.start_attempt(T, "02:00"); L.mark_failed(T, "02:00", "contoh gagal")
    r = c3.post("/api/atur_ulang", json={"tanggal": T, "jam": "02:00", "aksi": "terkirim"})
    check("tandai 'sudah terkirim' manual (setelah pengguna cek web)", r.status_code == 200 and L.get(T, "02:00")["status"] == "sent")
    check("slot terkirim tidak bisa diatur ulang (409)", c3.post("/api/atur_ulang", json={"tanggal": T, "jam": "02:00"}).status_code == 409)
    check("slot tanpa status -> 404", c3.post("/api/atur_ulang", json={"tanggal": T, "jam": "05:00"}).status_code == 404)
    check("aksi asing ditolak 400", (L.register(T, "03:00"), L.start_attempt(T, "03:00"),
          c3.post("/api/atur_ulang", json={"tanggal": T, "jam": "03:00", "aksi": "hapus"}).status_code)[2] == 400)
    L.register(T, "04:00"); L.start_attempt(T, "04:00")
    hasil = L.pulihkan_terhenti("uji")
    check("start bot: semua 'berjalan' sisa jadi gagal (jujur), 'sent' tak tersentuh",
          sorted(hasil) == [(T, "03:00"), (T, "04:00")] and L.get(T, "04:00")["status"] == "failed" and L.get(T, "02:00")["status"] == "sent", hasil)
    check("slot gagal hasil pemulihan tetap boleh dicoba ulang (mode Update bila ada di web)",
          L.should_send(T, "04:00")["send"] and L.should_send(T, "04:00")["needs_web_check"])
    check("dashboard memuat ringkasan 'berjalan' & halaman dirender", "berjalan" in c3.get(f"/api/status?tanggal={T}").get_json()["ringkas"]
          and c3.get("/").status_code == 200 and c3.get(f"/form/{T}/01:00").status_code == 200)

print("\n== PIN ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    _cfg = load_config()
    os.environ["WEB_PIN"] = "4321"
    app2 = create_app(_cfg, db_path=str(Path(d) / "b.db"))
    c2 = app2.test_client()
    check("tanpa PIN: halaman diarahkan ke /login, API 401", c2.get("/").status_code == 302 and c2.get("/api/status").status_code == 401)
    check("PIN salah ditolak", c2.post("/login", data={"pin": "0000"}).status_code == 401)
    check("PIN benar: akses terbuka", c2.post("/login", data={"pin": "4321"}).status_code == 302 and c2.get("/").status_code == 200)
os.environ.pop("WEB_PIN", None)

print("\n== [rev 28] observer opsional & diingat ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    os.environ.pop("WEB_PIN", None)
    app4 = create_app(cfg_tanpa_pin(), db_path=str(Path(d) / "o.db"))
    c4 = app4.test_client()
    cer = {"cloud_cover_oktas_m": op(app4, "cloud_cover_oktas_m", "0"), "visibility": 10, "ww": op(app4, "ww", "00"),
           "w1": op(app4, "w1", "0"), "w2": op(app4, "w2", "0"), "land_cond": op(app4, "land_cond", "0")}
    nama = next((o for o in __import__("json").load(open(ROOT / "core" / "options.json", encoding="utf-8")).get("observer", [])
                 if " " in o.get("name", "")), {}).get("name")
    check("ada nama observer berspasi di options.json untuk uji cookie", bool(nama))
    # 1) simpan pertama dengan nama; 2) ubah lagi TANPA nama -> pengubah sebelumnya dipertahankan (tidak dihapus)
    r = c4.post("/api/simpan", json={"tanggal": T, "jam": J, "data": cer, "observer": nama})
    check("simpan dengan nama -> tercatat", r.status_code == 200 and app4.obs.info(T, J)["diubah_oleh"] == nama, r.get_json())
    r = c4.post("/api/simpan", json={"tanggal": T, "jam": J, "data": dict(cer, visibility=8), "observer": ""})
    check("edit berikutnya TANPA mengisi nama: berhasil & nama pengubah sebelumnya tetap", r.status_code == 200
          and app4.obs.info(T, J)["diubah_oleh"] == nama and app4.obs.get(T, J)["visibility"] == 8, r.get_json())
    # cookie dikodekan-persen oleh JS ("Nama%20Lengkap"): server harus men-decode agar cocok dengan opsi dropdown
    from urllib.parse import quote
    c5 = app4.test_client()
    c5.set_cookie("observer", quote(nama), domain="localhost")
    html = c5.get(f"/form/{T}/{J}").get_data(as_text=True)
    check("cookie ber-spasi (%20) di-decode: opsi observer terpilih di form", f"<option selected>{nama}</option>" in html, nama)
    check("dashboard juga memilih observer dari cookie", f"<option selected>{nama}</option>" in c5.get("/").get_data(as_text=True))
    r = c5.post("/api/simpan", json={"tanggal": T, "jam": "08:00", "data": cer})
    check("tanpa nama di isian, cookie dipakai sebagai pengubah", r.status_code == 200 and app4.obs.info(T, "08:00")["diubah_oleh"] == nama, r.get_json())
    ev = [e["detail"] for e in app4.log.events(T, "08:00", limit=10)]
    check("jejak audit memuat nama dari cookie", any(nama in x for x in ev), ev)
    f = c4.get(f"/form/{T}/{J}").get_data(as_text=True)
    check("form: label Observer bertanda (opsional) & tombol Simpan tidak lagi diwajibkan observer",
          "(opsional)" in f and "!$(\"#observer\").value" not in f and "Pilih observer dulu" not in f)

print("\n== [rev 28] Riwayat jam ini (sebelumnya Internal Server Error) ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    app5 = create_app(cfg_tanpa_pin(), db_path=str(Path(d) / "r.db"))
    c6 = app5.test_client()
    app5.log.log_event(T, "07:00", "form_simpan", "Tester: data baru")
    app5.log.log_event(T, "07:00", "terkirim", "sandi AAXX")
    app5.log.log_event(T, "08:00", "gagal", "form tidak muncul_100%")
    app5.log.log_event("2026-11-13", "07:00", "form_hapus", "lama")
    r = c6.get(f"/riwayat?dari={T}&sampai={T}&jam=07:00")
    check("/riwayat terbuka (200), bukan 500", r.status_code == 200, r.status_code)
    check("halaman riwayat memuat filter & tabel", "Riwayat" in r.get_data(as_text=True) and "id=\"isi\"" in r.get_data(as_text=True))
    check("link 'Riwayat jam ini' dari form mengarah ke /riwayat dengan tanggal & jam",
          f"/riwayat?dari={T}&sampai={T}&jam=07:00" in c6.get(f"/form/{T}/07:00").get_data(as_text=True))
    check("menu Riwayat ada di bilah atas", 'href="/riwayat"' in c6.get("/").get_data(as_text=True))
    j = c6.get(f"/api/riwayat?dari={T}&sampai={T}&jam=07:00").get_json()
    check("filter jam: 2 kejadian jam 07:00 hari itu, terbaru dulu", j["total"] == 2 and [b["event"] for b in j["baris"]] == ["terkirim", "form_simpan"], j)
    j = c6.get("/api/riwayat").get_json()
    check("tanpa filter: semua (4) & daftar jenis kejadian untuk dropdown", j["total"] == 4 and "form_hapus" in j["jenis"], j)
    check("filter rentang tanggal", c6.get(f"/api/riwayat?dari={T}").get_json()["total"] == 3)
    check("filter jenis kejadian", c6.get("/api/riwayat?event=gagal").get_json()["total"] == 1)
    check("cari teks; karakter % dan _ dianggap huruf biasa", c6.get("/api/riwayat?q=100%25").get_json()["total"] == 1
          and c6.get("/api/riwayat?q=%25").get_json()["total"] == 1 and c6.get("/api/riwayat?q=xyz").get_json()["total"] == 0)
    check("limit membatasi baris tetapi total tetap jumlah cocok", (lambda x: len(x["baris"]) == 1 and x["total"] == 4)(c6.get("/api/riwayat?limit=1").get_json()))
    check("format tanggal salah -> 400 (bukan 500)", c6.get("/api/riwayat?dari=2026-13-99").status_code == 400)
    xr = c6.get(f"/ekspor_riwayat.xlsx?dari={T}&sampai={T}")
    check("ekspor Excel riwayat berfungsi", xr.status_code == 200 and xr.data[:2] == b"PK", xr.status_code)

print("\n== [rev 28] tata letak bagian jam 00 UTC ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    app5 = create_app(cfg_tanpa_pin(), db_path=str(Path(d) / "l.db"))
    sk = app5.test_client().get("/api/skema").get_json()
    pg = next(b for b in sk["bagian"] if b["id"] == "penguapan")
    check("bagian penguapan punya catatan tunggal (kosong = pakai nilai AWS)", pg.get("catatan") and "AWS" in pg["catatan"], pg.get("catatan"))
    check("[rev 33] keadaan tanah berada di kolom paling kanan",
          [f["kolom"] for f in pg["field"]] == ["penguapan_mm", "radiasi_kosongkan", "radiasi_matahari", "penguapan_ie", "lama_penyinaran_jam", "land_cond"],
          [(f["kolom"], f["sub"]) for f in pg["field"]])
    check("[rev 32] keadaan tanah TIDAK lagi di bagian Umum; iE = dropdown (pilih_kode) 0-4; kolom jam 00 bertanda hanya00",
          "land_cond" not in [f["kolom"] for b in sk["bagian"] if b["id"] == "umum" for f in b["field"]]
          and next(f for f in pg["field"] if f["kolom"] == "penguapan_ie")["jenis"] == "pilih_kode"
          and [o[0] for o in next(f for f in pg["field"] if f["kolom"] == "penguapan_ie")["opsi"]] == ["0", "1", "2", "3", "4"]
          and not next(f for f in pg["field"] if f["kolom"] == "land_cond").get("hanya00")
          and all(f.get("hanya00") for f in pg["field"] if f["kolom"] != "land_cond"), pg["field"])
    check("label tidak ada tanda kurung ganda", all(not (f.get("satuan") and "(" in f["label"]) for f in pg["field"]), [f["label"] for f in pg["field"]])
    S0 = app5.test_client().get("/api/slot/%s/00:00" % T).get_json()["state"]
    check("jam 00: tidak ada teks alasan berulang 'kosong = pakai nilai AWS' di tiap kolom",
          not any("pakai nilai AWS" in (S0[k]["alasan"] or "") for k in ("penguapan_mm", "penguapan_ie", "radiasi_kosongkan", "radiasi_matahari", "lama_penyinaran_jam")))
    fh = app5.test_client().get(f"/form/{T}/00:00").get_data(as_text=True)
    check("form memakai kelas bag-<id> & catatan bagian & menyembunyikan bagian ini di jam lain",
          "bag-${esc(b.id)}" in fh and "b.catatan" in fh and 'JAM!=="00:00"?" hidden"' in fh)

print("\n== [rev 30] jadwal pengiriman (dashboard) ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    app7 = create_app(cfg_tanpa_pin(), db_path=str(Path(d) / "j.db"))
    c7 = app7.test_client()
    J = lambda **k: c7.post("/api/jadwal", json=k)
    g = c7.get("/api/jadwal?tanggal=2026-11-22").get_json()
    check("default awal = config web.menit_sebelum (2) dan batas (-25 .. 10)", g["default"] == 2 and g["batas"] == [-25, 10], g)
    st = c7.get("/api/status?tanggal=2026-11-22").get_json()
    b7 = next(b for b in st["baris"] if b["jam"] == "07:00")
    check("status memuat jadwal tiap jam: 07:00 UTC = 14:00 WIB, mulai 13:58", b7["jadwal"]["mulai"] == "13:58" and b7["jadwal"]["khusus"] is False and st["zona"] == "WIB", b7["jadwal"])
    r = J(default=5)
    check("ubah default -> 5 menit sebelum; berlaku ke semua jam", r.status_code == 200 and c7.get("/api/status?tanggal=2026-11-22").get_json()["baris"][7]["jadwal"]["mulai"] == "13:55")
    r = J(tanggal="2026-11-22", jam="07:00", menit=-3)
    st = c7.get("/api/status?tanggal=2026-11-22").get_json()
    b7, b8 = st["baris"][7], st["baris"][8]
    check("pengecualian jam 07:00 = 3 menit SESUDAH -> mulai 14:03, bertanda khusus; jam lain tetap default", r.status_code == 200
          and b7["jadwal"] == {"menit": -3, "khusus": True, "mulai": "14:03", "mulai_tanggal": "2026-11-22"} and b8["jadwal"]["mulai"] == "14:55", (b7["jadwal"], b8["jadwal"]))
    # bot membaca dari DB yang sama: waktu_eksekusi berubah TANPA restart
    app7.obs.upsert("2026-11-22", "07:00", {"visibility": 8}, "T")
    app7.obs.upsert("2026-11-22", "08:00", {"visibility": 8}, "T")
    w7 = app7.obs.to_row("2026-11-22", "07:00")["waktu_eksekusi"]
    w8 = app7.obs.to_row("2026-11-22", "08:00")["waktu_eksekusi"]
    check("ObsStore.to_row (yang dibaca bot) memakai jadwal: 07:00 -> 14:03, 08:00 -> 14:55 (default 5)",
          (w7.hour, w7.minute) == (14, 3) and (w8.hour, w8.minute) == (14, 55) + (), (w7, w8))
    df = app7.obs.to_dataframe()
    ws = {str(r["jam_input"]): r["waktu_eksekusi"] for _, r in df.iterrows()}
    check("to_dataframe (jalur bot) juga memakai jadwal", (ws["07:00"].hour, ws["07:00"].minute) == (14, 3) and (ws["08:00"].minute) == 55, ws)
    r = J(tanggal="2026-11-22", jam="07:00", menit=None)
    check("hapus pengecualian -> kembali mengikuti default", r.status_code == 200 and c7.get("/api/status?tanggal=2026-11-22").get_json()["baris"][7]["jadwal"]["khusus"] is False)
    for nama, body in [("terlalu awal (11 > batas web 10)", dict(default=11)), ("terlalu lambat (-26)", dict(default=-26)),
                       ("bukan angka", dict(default="abc")), ("jam bukan HH:00", dict(tanggal="2026-11-22", jam="07:30", menit=1)),
                       ("tanggal salah", dict(tanggal="2026-13-01", jam="07:00", menit=1))]:
        check(f"validasi: {nama} -> 400", J(**body).status_code == 400, J(**body).status_code)
    check("batas persis diterima: 10 sebelum & 25 sesudah", J(default=10).status_code == 200 and J(default=-25).status_code == 200)
    ev = [e["event"] for e in c7.get("/api/riwayat").get_json()["baris"]]
    check("perubahan jadwal masuk jejak audit", "jadwal_default" in ev and "jadwal_diubah" in ev, ev)
    c7.set_cookie("observer", "Nama%20Uji", domain="localhost")
    J(default=3)
    det = [e["detail"] for e in c7.get("/api/riwayat?event=jadwal_default").get_json()["baris"]][0]
    check("audit mencatat nama (dari cookie ber-spasi) & nilai", "Nama Uji" in det and "3 menit" in det, det)
    html = c7.get("/").get_data(as_text=True)
    check("dashboard memuat tombol & dialog jadwal", 'id="buka-jadwal"' in html and 'id="dlg-jadwal"' in html and "barisJadwal" in html)

print("\n== [rev 30] riwayat berhalaman ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    app8 = create_app(cfg_tanpa_pin(), db_path=str(Path(d) / "p.db"))
    c8 = app8.test_client()
    for i in range(60):
        app8.log.log_event("2026-11-22", "07:00", "form_simpan", f"baris-{i:02d}")
    g1 = c8.get("/api/riwayat?hal=1&per=25").get_json()
    g3 = c8.get("/api/riwayat?hal=3&per=25").get_json()
    check("60 kejadian / 25 per halaman = 3 halaman; halaman 1 = 25 baris terbaru dulu",
          g1["total"] == 60 and g1["halaman_total"] == 3 and len(g1["baris"]) == 25 and g1["baris"][0]["detail"] == "baris-59", (g1["total"], g1["halaman_total"], len(g1["baris"])))
    check("halaman terakhir berisi sisa 10 baris, berakhir di kejadian tertua", len(g3["baris"]) == 10 and g3["baris"][-1]["detail"] == "baris-00" and g3["hal"] == 3)
    ids = [b["id"] for h in (1, 2, 3) for b in c8.get(f"/api/riwayat?hal={h}&per=25").get_json()["baris"]]
    check("tiga halaman tidak tumpang-tindih & lengkap (60 id unik)", len(ids) == 60 and len(set(ids)) == 60)
    check("halaman melebihi batas -> dijepit ke halaman terakhir", c8.get("/api/riwayat?hal=99&per=25").get_json()["hal"] == 3)
    check("per dijepit 5..200", c8.get("/api/riwayat?hal=1&per=1").get_json()["per"] == 5 and c8.get("/api/riwayat?hal=1&per=999").get_json()["per"] == 200)
    check("hal bukan angka -> 400", c8.get("/api/riwayat?hal=x").status_code == 400)
    check("filter + halaman: total mengikuti filter", c8.get("/api/riwayat?hal=1&per=10&q=baris-0").get_json()["total"] == 10)
    check("tanpa hal/per -> perilaku lama (limit) tetap", len(c8.get("/api/riwayat?limit=7").get_json()["baris"]) == 7)
    html = c8.get("/riwayat").get_data(as_text=True)
    check("halaman riwayat memuat pager & tidak lagi memakai header lengket", 'id="pager"' in html and "position:sticky;top:64px" not in html)
    check("ekspor tetap memuat SEMUA yang cocok (bukan hanya satu halaman)", c8.get("/ekspor_riwayat.xlsx").status_code == 200)

print("\n== [rev 30] navigasi jam di form ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    app9 = create_app(cfg_tanpa_pin(), db_path=str(Path(d) / "n.db"))
    c9 = app9.test_client()
    f = c9.get("/form/2026-11-22/07:00").get_data(as_text=True)
    check("tombol jam sebelumnya (06:00) & berikutnya (08:00)", 'href="/form/2026-11-22/06:00"' in f and 'href="/form/2026-11-22/08:00"' in f)
    check("tombol 'Simpan & ke 08:00' tersedia", "Simpan &amp; ke 08:00" in f and 'id="simpan-lanjut"' in f)
    f = c9.get("/form/2026-11-22/23:00").get_data(as_text=True)
    check("23:00 -> berikutnya = 00:00 hari berikutnya", 'href="/form/2026-11-23/00:00"' in f and "(2026-11-23)" in f)
    f = c9.get("/form/2026-11-22/00:00").get_data(as_text=True)
    check("00:00 -> sebelumnya = 23:00 hari sebelumnya", 'href="/form/2026-11-21/23:00"' in f)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
