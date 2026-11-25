# -*- coding: utf-8 -*-
"""
Uji alur V7SATU.main() TANPA browser:  python tests/test_bot_flow.py

Browser, jam, dan klik di web diganti tiruan (fake). Yang diuji adalah logika baru:
validasi per baris, log status (sent / skipped / failed), tanggal per slot, dry-run,
mode Update, recovery sesi, idempotensi (sent tidak dikirim ulang), override hujan.
"""
import datetime as dt
import importlib.util
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))   # tidak perlu layar

import pandas as pd  # noqa: E402

spec = importlib.util.spec_from_file_location("V7SATU", ROOT / "V7SATU.py")
V7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V7)

from core.db import SendLog  # noqa: E402


class StopMain(Exception):
    pass


BASE = {
    "visibility": 10, "ww": "02 -", "w1": "2 -", "w2": "2 -", "cloud_cover_oktas_m": "7 okta", "land_cond": "0 -",
    "cloud_low_type_cl": "2 -", "cloud_low_cover_oktas": "5 okta", "awan_rendah_jenis": "8 - cumulus (Cu)",
    "awan_rendah_jumlah": "5 okta", "cloud_low_base_1": 450, "cloud_low_peak_1": 2500,
    "cloud_arah_awan_rendah": "0 -", "cloud_elevation_1_angle_ec": "2 -", "cloud_arah_sebenarnya_1": "0 -",
    "cloud_med_type_cm": "1 -", "cloud_med_cover_oktas": "2 okta", "awan_menengah_jenis_1": "4 - altostratus (As)",
    "awan_menengah_jumlah_1": "2 okta", "cloud_med_base_1": 3000, "cloud_arah_menengah_1": "0 -",
    "cloud_high_type_ch": "1 -", "cloud_high_cover_oktas": "1 okta", "awan_tinggi_jenis": "0 - cirrus (Ci)",
    "awan_tinggi_jumlah": "1 okta", "cloud_high_base_1": 9000, "cloud_arah_tinggi": "0 -",
}
UTC_DAY = dt.datetime(2026, 11, 14)


def make_row(jam_utc, **kw):
    r = dict(BASE)
    # eksekusi = (jam UTC + 7 jam) - 2 menit, seperti Excel asli
    r["waktu_eksekusi"] = UTC_DAY + dt.timedelta(hours=jam_utc + 7, minutes=-2)
    r["jam_input"] = f"{jam_utc:02d}:00"
    r.update(kw)
    return r


class Recorder:
    def __init__(self):
        self.calls = []

    def add(self, name, *a):
        self.calls.append((name,) + a)

    def names(self, n):
        return [c for c in self.calls if c[0] == n]


def run_main(rows, argv, db_path, update_mode=False, fail_form_once=False, isi_data_result=True,
             allow_update=True, start_wib=None, pasca_fn=None, db_rows=None, hook_isi=None, pra=None):
    """Jalankan V7.main() dengan semua interaksi browser dipalsukan. Return Recorder."""
    rec = Recorder()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        xlsx = Path(d) / "in.xlsx"
        pd.DataFrame(rows).to_excel(xlsx, index=False)
        V7.EXCEL_PATH = xlsx
        V7.CFG["paths"]["db"] = str(db_path)
        V7.CFG["features"]["allow_update"] = allow_update
        V7.DRY_RUN = False
        # [F2.7] db_rows != None -> bot membaca data dari database form web (bukan Excel)
        V7.SUMBER_DATA = "db" if db_rows is not None else "excel"
        V7._OBS_STORE = None
        if db_rows is not None:
            from core.obsdb import ObsStore
            st = ObsStore(db_path, tz_hours=7, menit_sebelum=2)
            for r in db_rows:
                st.upsert("2026-11-14", r["jam_input"], {k: v for k, v in r.items()
                                                         if k not in ("waktu_eksekusi", "jam_input")}, "Tester")

        clock = {"now": start_wib or (UTC_DAY + dt.timedelta(hours=7 + 6, minutes=40))}   # 13:40 WIB

        class FakeDT(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return (clock["now"] - dt.timedelta(hours=7)).replace(tzinfo=tz)
                return clock["now"]

        def fake_sleep(s):
            if s == 10:
                raise StopMain()
            clock["now"] += dt.timedelta(seconds=max(float(s), 1.0))

        V7.datetime = FakeDT
        V7.time = types.SimpleNamespace(sleep=fake_sleep, time=__import__("time").time)

        state = {"tanggal": None, "form_fail_left": 1 if fail_form_once else 0}

        class FakeDriver:
            def find_elements(self, *a, **k):
                return []

        V7.get_credentials = lambda interactive=True: ("id", "pw")
        V7.buat_driver = lambda: FakeDriver()
        V7.login = lambda drv: rec.add("login")
        V7.klik_tombol_oke_popup = lambda *a, **k: True
        V7.memilih_stasiun = lambda drv: None
        V7.sesi_habis = lambda drv=None: False   # [rev 35] bawaan: sesi sehat (pemeriksaan pasif tak memuat ulang apa pun)

        def f_tanggal(drv, utc_date=None):
            state["tanggal"] = utc_date
            rec.add("tanggal", utc_date)
            return True
        V7.memilih_tanggal = f_tanggal
        V7.tanggal_di_web = lambda drv: state["tanggal"]
        def f_isi(drv, row):
            rec.add("jam", str(row["jam_input"]))
            if db_rows is not None and hook_isi:
                hook_isi(str(row["jam_input"]), st)
            return True
        V7.isi_per_jam = f_isi
        V7.Fill_AWS_Digi = lambda drv: True
        V7.memilih_observer = lambda drv: True
        V7.wait_for_clickable = lambda *a, **k: object()

        def f_presence(drv, loc, timeout=10):
            if state["form_fail_left"] > 0:
                state["form_fail_left"] -= 1
                return None
            return object()
        V7.wait_for_presence = f_presence

        def f_isi(drv, row, plan=None):
            rec.add("isi_data", str(row["jam_input"]), plan)
            return isi_data_result
        V7.isi_data = f_isi
        V7.Preview = lambda drv: True
        V7.Preview_OK = lambda drv: True
        V7.baca_sandi = lambda drv: "SNID52 WIJJ TEST"
        V7._ada_tombol = lambda drv, teks: (update_mode and "update" in teks)
        V7.SEND_SEND_SUBMIT = lambda drv: (rec.add("send_submit") or True)
        V7.SEND_INASWITCH_SUBMIT = lambda drv: True
        V7.SEND_GTS = lambda drv: True
        V7.SEND_GTS_OK = lambda drv: True
        # [F3.11] pengawas popup susulan diganti tiruan (jam palsu di tes ini maju tiap sleep);
        # perilaku popup diuji terpisah di tests/test_koreksi_qc.py
        V7.selesaikan_pasca_kirim = pasca_fn or (lambda drv: (True, ""))
        V7.save_debug_snapshot = lambda drv, tag="debug": f"snap_{tag}.png"

        def f_recover(cur, max_attempts=3, tanggal_utc=None):
            rec.add("recover", tanggal_utc)
            state["tanggal"] = tanggal_utc
            return FakeDriver(), True
        V7.recover_session = f_recover

        sys.argv = ["V7SATU.py"] + argv
        if pra:
            pra(rec)    # [rev 28] tiruan tambahan (mis. pemeriksaan sesi) yang perlu mencatat ke Recorder yang sama
        try:
            V7.main()
        except StopMain:
            pass
    return rec


passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


def slots(db_path):
    log = SendLog(db_path)
    out = {(r["tanggal_utc"], r["jam"]): r for r in log.history(limit=100)}
    log.close()
    return out


print("== alur normal: sent / skipped(ERROR) / sent ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db1 = Path(d) / "a.db"
    rows = [make_row(7), make_row(8, cloud_cover_oktas_m="9 -", visibility=3.5, vertical_visibility=100),
            make_row(9, cloud_cover_oktas_m="0")]
    rec = run_main(rows, ["--observer", "Tester", "--no-gui"], db1)
    s = slots(db1)
    check("jam 07:00 -> sent + sandi tersimpan", s[("2026-11-14", "07:00")]["status"] == "sent"
          and s[("2026-11-14", "07:00")]["kode_synop"] == "SNID52 WIJJ TEST", s.get(("2026-11-14", "07:00")))
    check("jam 08:00 (total 9, visibilitas 3.5) -> skipped ERROR, tidak dikirim",
          s[("2026-11-14", "08:00")]["status"] == "skipped" and "validasi ERROR" in s[("2026-11-14", "08:00")]["pesan"])
    check("jam 09:00 (total 0) -> sent", s[("2026-11-14", "09:00")]["status"] == "sent")
    check("hanya 2 kali kirim (jam 07 & 09)", len(rec.names("send_submit")) == 2, rec.names("send_submit"))
    plans = {c[1]: c[2] for c in rec.names("isi_data")}
    check("plan total 0 -> skip_clouds", plans["09:00"]["skip_clouds"] is True, plans.get("09:00"))
    check("plan total 7 -> awan diisi, puncak aktif", plans["07:00"]["skip_clouds"] is False
          and plans["07:00"]["layers"]["low"]["peak_active"] is True, plans.get("07:00"))
    check("tanggal dipilih sesuai slot UTC (14/11), sekali saja", [c[1] for c in rec.names("tanggal")] == ["2026-11-14"],
          rec.names("tanggal"))
    ev = SendLog(db1).events(limit=50)
    check("audit mencatat mulai & terkirim", {e["event"] for e in ev} >= {"mulai", "terkirim", "dilewati"}, ev[:3])

    print("== jalan ulang: sent tidak dikirim lagi ==")
    rec2 = run_main(rows, ["--observer", "Tester", "--no-gui"], db1)
    check("tidak ada pengiriman ulang", len(rec2.names("send_submit")) == 0, rec2.names("send_submit"))
    check("tidak ada pengisian ulang", len(rec2.names("isi_data")) == 0, rec2.names("isi_data"))

print("== dry-run ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db2 = Path(d) / "b.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui", "--dry-run"], db2)
    s = slots(db2)[("2026-11-14", "07:00")]
    check("dry-run: tidak mengirim", len(rec.names("send_submit")) == 0)
    check("dry-run: sandi disimpan, status skipped", s["status"] == "skipped" and s["kode_synop"] == "SNID52 WIJJ TEST"
          and "dry-run" in s["pesan"], s)

print("== gagal isi data ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db3 = Path(d) / "c.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], db3, isi_data_result=False)
    s = slots(db3)[("2026-11-14", "07:00")]
    check("isi_data gagal -> status failed + pesan + screenshot", s["status"] == "failed" and "Gagal isi data" in s["pesan"]
          and (s["screenshot_path"] or "").endswith(".png"), s)
    check("tidak dikirim", len(rec.names("send_submit")) == 0)

print("== recovery sesi ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db4 = Path(d) / "d.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], db4, fail_form_once=True)
    s = slots(db4)[("2026-11-14", "07:00")]
    check("recover_session dipanggil dengan tanggal slot", rec.names("recover") == [("recover", "2026-11-14")], rec.names("recover"))
    check("setelah recovery tetap terkirim", s["status"] == "sent" and s["percobaan"] == 1, s)
    check("tanggal dipilih ulang setelah recovery", len(rec.names("tanggal")) >= 2, rec.names("tanggal"))

print("== mode Update (data jam sudah ada di web) ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db5 = Path(d) / "e.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], db5, update_mode=True)
    s = slots(db5)[("2026-11-14", "07:00")]
    ev = [e["event"] for e in SendLog(db5).events(limit=50)]
    check("allow_update=true: tetap terkirim & tercatat mode_update", s["status"] == "sent" and "mode_update" in ev, (s["status"], ev))
    db6 = Path(d) / "f.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], db6, update_mode=True, allow_update=False)
    s = slots(db6)[("2026-11-14", "07:00")]
    check("allow_update=false: dilewati, tidak dikirim", s["status"] == "skipped" and len(rec.names("send_submit")) == 0, s)

print("== waktu sudah lewat & check-only ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db7 = Path(d) / "g.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], db7,
                   start_wib=UTC_DAY + dt.timedelta(hours=7 + 8))      # 15:00 WIB, jadwal 13:58 sudah lewat
    s = slots(db7)[("2026-11-14", "07:00")]
    check("baris lewat waktu -> skipped, tidak dikirim", s["status"] == "skipped" and "lewat" in s["pesan"]
          and len(rec.names("send_submit")) == 0, s)
    db8 = Path(d) / "h.db"
    rec = run_main([make_row(7)], ["--check-only"], db8)
    check("--check-only: tidak membuka browser/login", len(rec.names("login")) == 0, rec.calls)

print("== --process-past dan --jam ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db9 = Path(d) / "i.db"
    rows = [make_row(7), make_row(8)]
    late = UTC_DAY + dt.timedelta(hours=7 + 9)      # 16:00 WIB: kedua jadwal sudah lewat
    rec = run_main(rows, ["--observer", "Tester", "--no-gui", "--dry-run", "--process-past"], db9, start_wib=late)
    s = slots(db9)
    check("--process-past: baris lewat waktu tetap diproses (dry-run)",
          s[("2026-11-14", "07:00")]["kode_synop"] == "SNID52 WIJJ TEST" and s[("2026-11-14", "08:00")]["kode_synop"] == "SNID52 WIJJ TEST"
          and len(rec.names("send_submit")) == 0, s)
    db10 = Path(d) / "j.db"
    rec = run_main(rows, ["--observer", "Tester", "--no-gui", "--dry-run", "--process-past", "--jam", "08:00"], db10, start_wib=late)
    s = slots(db10)
    check("--jam 08:00: hanya jam itu diproses", s[("2026-11-14", "08:00")]["kode_synop"] == "SNID52 WIJJ TEST"
          and s[("2026-11-14", "07:00")]["status"] == "pending", {k: v["status"] for k, v in s.items()})
    db11 = Path(d) / "k.db"
    rec = run_main(rows, ["--observer", "Tester", "--no-gui", "--dry-run"], db11, start_wib=late)
    check("tanpa --process-past: baris lewat waktu dilewati (perilaku aman)",
          len(rec.names("isi_data")) == 0, rec.names("isi_data"))

print("== [F3.11] popup susulan setelah OK (Koreksi QC) ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    db12 = Path(d) / "l.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], db12,
                   pasca_fn=lambda drv: (False, "popup Koreksi QC tidak dapat dikonfirmasi: pressure_qff"))
    s = slots(db12)[("2026-11-14", "07:00")]
    check("popup tak bisa dikonfirmasi -> status failed (BUKAN sent)", s["status"] == "failed"
          and "BELUM terkirim" in s["pesan"] and "Koreksi QC" in s["pesan"], s)
    db13 = Path(d) / "m.db"

    def pasca_qc(drv):
        V7.PERUBAHAN_OTOMATIS["koreksi_qc"] = "Submit dikonfirmasi: temp_drybulb_c Step Check"
        return True, ""
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], db13, pasca_fn=pasca_qc)
    s = slots(db13)[("2026-11-14", "07:00")]
    ev = {e["event"]: e["detail"] for e in SendLog(db13).events(limit=50)}
    check("Koreksi QC dikonfirmasi -> sent + tercatat di diubah_otomatis", s["status"] == "sent"
          and "koreksi_qc" in (s["diubah_otomatis"] or ""), s)
    check("Koreksi QC dicatat sebagai event audit", "koreksi_qc" in ev and "Step Check" in ev["koreksi_qc"], ev)

print("== [F2.7] data dari database (form web) ==")
import pandas as pd  # noqa: E402
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    V7.SUMBER_DATA = "db"
    k = lambda jam, tgl="2026-11-14": (tgl, jam)
    mk = lambda jam, wib_menit_utc: pd.Series({"waktu_eksekusi": pd.Timestamp(UTC_DAY + dt.timedelta(hours=jam + 7, minutes=-2))})
    df3 = pd.DataFrame([{"waktu_eksekusi": UTC_DAY + dt.timedelta(hours=h + 7, minutes=-2), "jam_input": f"{h:02d}:00"} for h in (7, 8, 9)])
    check("_kunci_baris: slot dari waktu_eksekusi (13:58 WIB -> 07:00 UTC)", V7._kunci_baris(df3.iloc[0]) == ("2026-11-14", "07:00"))
    check("_posisi mode DB: baris ditemukan menurut slot walau posisinya bergeser",
          V7._posisi(df3, ("2026-11-14", "09:00"), 1) == 2)
    check("_posisi mode DB: slot yang hilang -> None (tidak jatuh ke nomor urut)", V7._posisi(df3, ("2026-11-14", "12:00"), 1) is None)
    V7.SUMBER_DATA = "excel"
    check("_posisi mode Excel: slot tidak ketemu -> nomor urut lama (perilaku V7)", V7._posisi(df3, ("2026-11-14", "12:00"), 1) == 1)
    check("_posisi mode Excel: nomor urut di luar jangkauan -> None", V7._posisi(df3, ("2026-11-14", "12:00"), 9) is None)
    check("_posisi: df None -> None", V7._posisi(None, ("2026-11-14", "07:00"), 0) is None)

    dbA = Path(d) / "a.db"
    rec = run_main([], ["--observer", "Tester", "--no-gui"], dbA, db_rows=[make_row(7), make_row(9)])
    sl = slots(dbA)
    check("DB: dua slot dari form dikirim (07 dan 09 UTC)", sl.get(("2026-11-14", "07:00"), {}).get("status") == "sent"
          and sl.get(("2026-11-14", "09:00"), {}).get("status") == "sent", sl)
    check("DB: urutan pengisian di web 07 lalu 09", [c[1] for c in rec.calls if c[0] == "jam"] == ["07:00", "09:00"], rec.calls)

    dbB = Path(d) / "b.db"

    def sisip(jam, st):                     # pengamat mengisi jam 08 di form SAAT bot sedang memproses jam 07
        if jam == "07:00":
            r = make_row(8)
            st.upsert("2026-11-14", "08:00", {k: v for k, v in r.items() if k not in ("waktu_eksekusi", "jam_input")}, "Tester")
    rec = run_main([], ["--observer", "Tester", "--no-gui"], dbB, db_rows=[make_row(7), make_row(9)], hook_isi=sisip)
    urut = [c[1] for c in rec.calls if c[0] == "jam"]
    check("DB: jam 08 disisipkan di tengah pass TIDAK menggeser baris — jam 09 tetap benar (bukan 08 di waktu 09)",
          urut == ["07:00", "09:00"], urut)
    check("DB: jam 08 yang baru diisi tidak hilang (menunggu pass berikutnya)", slots(dbB).get(("2026-11-14", "09:00"), {}).get("status") == "sent")
    V7.SUMBER_DATA = "excel"
    V7._OBS_STORE = None

print("== [rev 28] sesi BMKG Satu diperiksa menjelang eksekusi & logout di tengah baris ==")
_seg_asli, _habis_asli = V7.segarkan_sesi, V7.sesi_habis
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    V7.SESI_TERAKHIR_OK = 0.0
    def pra_seg(rec):
        habis = {"v": True}
        V7.sesi_habis = lambda drv=None: habis["v"]                           # [rev 35] ter-logout sampai login ulang dilakukan
        V7.segarkan_sesi = lambda drv: (rec.add("segarkan"), habis.update(v=False), True)[2]
    dbS = Path(d) / "s.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbS, pra=pra_seg)
    nama = [c[0] for c in rec.calls]
    check("sesi diperiksa tepat sekali untuk slot ini", nama.count("segarkan") == 1, nama)
    check("pemeriksaan sesi terjadi SEBELUM halaman jam diisi", nama.index("segarkan") < nama.index("jam"), nama)
    check("setelah halaman dimuat ulang, tanggal slot dipilih ulang", "tanggal" in nama[nama.index("segarkan"):], nama)
    check("slot tetap terkirim", slots(dbS)[("2026-11-14", "07:00")]["status"] == "sent")
    import sqlite3 as _sq
    _c = _sq.connect(str(dbS)); _ev = [r[0] for r in _c.execute("SELECT event FROM events WHERE jam='07:00'")]; _c.close()
    check("[F3.3] waktu pengisian per jam dicatat sebagai kejadian 'waktu_isi' (tampil di Riwayat)", "waktu_isi" in _ev, _ev)

    V7.SESI_TERAKHIR_OK = V7.time.time()       # [rev 35] sesi sehat -> tidak ada pemuatan ulang
    dbT = Path(d) / "t.db"
    def pra_seg2(rec):
        V7.segarkan_sesi = lambda drv: (rec.add("segarkan"), True)[1]
        V7.SESI_TERAKHIR_OK = __import__("time").time()
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbT, pra=pra_seg2)
    check("sesi baru terbukti hidup -> tidak diperiksa ulang", rec.names("segarkan") == [], rec.names("segarkan"))

    dbU = Path(d) / "u.db"
    def pra_logout(rec):
        V7.segarkan_sesi = lambda drv: False
        V7.SESI_TERAKHIR_OK = __import__("time").time()
        V7.sesi_habis = lambda drv=None: True                              # meniru: BMKG Satu ter-logout saat baris diisi
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbU, isi_data_result=False, pra=pra_logout)
    check("gagal isi data + halaman login terdeteksi -> recovery sesi dijalankan", len(rec.names("recover")) >= 1, rec.calls[-6:])
    V7.sesi_habis = _habis_asli
    dbV = Path(d) / "v.db"
    def pra_normal(rec):
        V7.segarkan_sesi = lambda drv: False
        V7.SESI_TERAKHIR_OK = __import__("time").time()
        V7.sesi_habis = lambda drv=None: False
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbV, isi_data_result=False, pra=pra_normal)
    check("[rev 30] gagal isi data biasa -> diulang bertingkat: percobaan 3 membuka browser baru (1 recover), lalu gagal",
          len(rec.names("recover")) == 1 and len(rec.names("isi_data")) == 3, (rec.names("recover"), len(rec.names("isi_data"))))
V7.segarkan_sesi, V7.sesi_habis = _seg_asli, _habis_asli

print("== [rev 30] cadangan: tangga percobaan ulang & cegah kirim ganda ==")
from core.notify import Notifier as _Notif
_seg0, _hab0, _isi_asli_cfg = V7.segarkan_sesi, V7.sesi_habis, V7.CFG["runtime"].get("max_row_attempts", 3)


def _pasang_notif(rec):
    """Notifier tiruan: mencatat gagal / perlu_cek_manual / kirim ke Recorder yang sama."""
    class N:
        aktif = False
        def __init__(self, *a, **k): pass
        def gagal(self, slot, pesan, **k): rec.add("N_gagal", slot, pesan)
        def perlu_cek_manual(self, slot, pesan, **k): rec.add("N_cek_manual", slot, pesan)
        def recovery(self, slot, ok, **k): rec.add("N_recovery", ok)
        def sukses(self, *a, **k): pass
        def kirim(self, teks, jenis="info", **k): rec.add("N_kirim", teks)
        def rekap_jika_waktunya(self, db): pass
        def fatal(self, *a, **k): pass
        @classmethod
        def from_config(cls, *a, **k): return cls()
    V7.Notifier = N


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    # A) isi_data gagal TERUS: 3 percobaan (normal -> muat ulang halaman -> browser baru), lalu gagal + notifikasi
    def pra_A(rec):
        _pasang_notif(rec)
        V7.CFG["runtime"]["max_row_attempts"] = 3
        V7.sesi_habis = lambda drv=None: False
        V7.SESI_TERAKHIR_OK = __import__("time").time()
        V7.segarkan_sesi = lambda drv: (rec.add("segarkan"), False)[1]
    dbA = Path(d) / "A.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbA, isi_data_result=False, pra=pra_A)
    sA = slots(dbA)[("2026-11-14", "07:00")]
    check("A: isi_data dicoba 3x", len(rec.names("isi_data")) == 3, len(rec.names("isi_data")))
    check("A: percobaan 2 = MUAT ULANG halaman (segarkan_sesi), percobaan 3 = browser baru (recover)",
          len(rec.names("segarkan")) == 1 and len(rec.names("recover")) == 1, (rec.names("segarkan"), rec.names("recover")))
    check("A: sesudah semua habis -> status failed + SATU notifikasi gagal", sA["status"] == "failed" and len(rec.names("N_gagal")) == 1, sA)
    check("A: tidak ada pengiriman (data tidak lengkap tidak dikirim)", rec.names("send_submit") == [])
    ev = [e["event"] for e in SendLog(dbA).events(limit=50)]
    check("A: jejak audit mencatat 2 percobaan_gagal + gagal akhir", ev.count("percobaan_gagal") == 2 and ev.count("gagal") == 1, ev)
    check("A: pemberitahuan Telegram tiap percobaan ulang", len([c for c in rec.names("N_kirim") if "Mencoba ulang" in c[1]]) == 2, rec.names("N_kirim"))
    check("A: observer & tanggal dipilih ulang setelah tiap reset (halaman baru)", len(rec.names("tanggal")) >= 3, rec.names("tanggal"))

    # B) gagal sekali, percobaan ke-2 (setelah muat ulang halaman) berhasil -> TERKIRIM, tanpa browser baru
    def pra_B(rec):
        _pasang_notif(rec)
        V7.CFG["runtime"]["max_row_attempts"] = 3
        V7.sesi_habis = lambda drv=None: False
        V7.SESI_TERAKHIR_OK = __import__("time").time()
        V7.segarkan_sesi = lambda drv: (rec.add("segarkan"), False)[1]
        n = {"x": 0}
        def isi(drv, row, plan=None):
            n["x"] += 1
            rec.add("isi_data", str(row["jam_input"]))
            return n["x"] >= 2
        V7.isi_data = isi
    dbB = Path(d) / "B.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbB, pra=pra_B)
    check("B: gagal 1x lalu berhasil -> status SENT", slots(dbB)[("2026-11-14", "07:00")]["status"] == "sent")
    check("B: hanya muat ulang halaman (tanpa browser baru) & tanpa notifikasi gagal akhir",
          len(rec.names("segarkan")) == 1 and rec.names("recover") == [] and rec.names("N_gagal") == [])
    check("B: dikirim tepat sekali", len(rec.names("send_submit")) == 1, rec.names("send_submit"))

    # C) max_row_attempts=1 -> perilaku lama (tanpa ulang)
    def pra_C(rec):
        _pasang_notif(rec)
        V7.CFG["runtime"]["max_row_attempts"] = 1
        V7.sesi_habis = lambda drv=None: False
        V7.SESI_TERAKHIR_OK = __import__("time").time()
        V7.segarkan_sesi = lambda drv: (rec.add("segarkan"), False)[1]
    dbC = Path(d) / "C.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbC, isi_data_result=False, pra=pra_C)
    check("C: max_row_attempts=1 -> hanya 1 percobaan, tanpa reset", len(rec.names("isi_data")) == 1 and rec.names("segarkan") == [] and rec.names("recover") == [])

    # D) gagal SETELAH tombol kirim akhir: TIDAK dikirim ulang, ditandai cek-manual
    def pra_D(rec):
        _pasang_notif(rec)
        V7.CFG["runtime"]["max_row_attempts"] = 3
        V7.sesi_habis = lambda drv=None: False
        V7.SESI_TERAKHIR_OK = __import__("time").time()
        V7.segarkan_sesi = lambda drv: (rec.add("segarkan"), False)[1]
        V7.SEND_GTS = lambda drv: (rec.add("send_gts"), True)[1]
        V7.SEND_GTS_OK = lambda drv: False                  # tombol OK akhir tidak berhasil diklik -> status tak pasti
    dbD = Path(d) / "D.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbD, pra=pra_D)
    sD = slots(dbD)[("2026-11-14", "07:00")]
    check("D: SEND final hanya SEKALI (tidak dikirim ulang)", len(rec.names("send_gts")) == 1, rec.names("send_gts"))
    check("D: status failed bertanda [CEK-MANUAL]", sD["status"] == "failed" and sD["pesan"].startswith("[CEK-MANUAL]"), sD)
    check("D: notifikasi 'perlu cek manual' (bukan 'gagal biasa')", len(rec.names("N_cek_manual")) == 1 and rec.names("N_gagal") == [])
    check("D: tanpa reset/ulang", rec.names("segarkan") == [] and rec.names("recover") == [])
    from core.db import SendLog as _SL
    _l = _SL(dbD)
    check("D: slot ini TIDAK dikirim ulang oleh putaran berikutnya (should_send=False)", _l.should_send("2026-11-14", "07:00")["send"] is False)
    _l.close()

    # E) pasca-kirim error (stale), web menyatakan BERHASIL -> dicatat TERKIRIM (kasus nyata jam 18 UTC)
    def pra_E(rec):
        _pasang_notif(rec)
        V7.CFG["runtime"]["max_row_attempts"] = 3
        V7.sesi_habis = lambda drv=None: False
        V7.SESI_TERAKHIR_OK = __import__("time").time()
        def pasca(drv):
            V7.BERHASIL_TERLIHAT = True
            raise V7.StaleElementReferenceException("stale element reference")
        V7.selesaikan_pasca_kirim = pasca
    dbE = Path(d) / "E.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbE, pra=pra_E)
    sE = slots(dbE)[("2026-11-14", "07:00")]
    check("E: galat pasca-kirim + web 'berhasil' -> status SENT (bukan gagal)", sE["status"] == "sent", sE)
    check("E: tidak ada notifikasi gagal", rec.names("N_gagal") == [] and rec.names("N_cek_manual") == [])

    # F) pasca-kirim error tanpa bukti berhasil -> cek manual (bukan gagal-ulang)
    def pra_F(rec):
        pra_E(rec)
        def pasca(drv):
            V7.BERHASIL_TERLIHAT = False
            raise V7.StaleElementReferenceException("stale element reference")
        V7.selesaikan_pasca_kirim = pasca
    dbF = Path(d) / "F.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbF, pra=pra_F)
    sF = slots(dbF)[("2026-11-14", "07:00")]
    check("F: galat pasca-kirim tanpa bukti -> [CEK-MANUAL], tidak dikirim ulang",
          sF["status"] == "failed" and sF["pesan"].startswith("[CEK-MANUAL]") and len(rec.names("send_submit")) == 1, sF)

    # G) kegagalan yang DIKETAHUI pasca-kirim (popup galat) -> aman diulang (data belum terkirim)
    def pra_G(rec):
        pra_E(rec)
        V7.selesaikan_pasca_kirim = lambda drv: (False, "popup galat setelah SEND: Gagal")
        V7.segarkan_sesi = lambda drv: (rec.add("segarkan"), False)[1]
    dbG = Path(d) / "G.db"
    rec = run_main([make_row(7)], ["--observer", "Tester", "--no-gui"], dbG, pra=pra_G)
    sG = slots(dbG)[("2026-11-14", "07:00")]
    check("G: popup galat pasca-kirim yang diketahui -> diulang (3 percobaan), bukan cek-manual",
          len(rec.names("send_submit")) == 3 and not str(sG["pesan"]).startswith("[CEK-MANUAL]"), (len(rec.names("send_submit")), sG["pesan"]))

V7.segarkan_sesi, V7.sesi_habis = _seg0, _hab0
V7.CFG["runtime"]["max_row_attempts"] = _isi_asli_cfg

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
