# -*- coding: utf-8 -*-
"""
Uji cepat validator & log status (tanpa pytest):   python tests/test_validator.py
Setiap kasus memeriksa bahwa aturan hasil F0.5 benar-benar ditegakkan.
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.validator import Validator, ERROR, WARNING  # noqa: E402
from core.db import SendLog  # noqa: E402

V = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json")

BASE = {  # baris sehat: total 7, CL=2/Jenis 8 (puncak aktif), CM=1/As, CH=1/Ci
    "waktu_eksekusi": dt.datetime(2026, 11, 14, 13, 58), "jam_input": dt.time(7, 0),   # 13:58 WIB = 06:58 UTC -> slot 07:00
    "visibility": 10, "ww": "02 -", "w1": "2 -", "w2": "2 -",
    "cloud_cover_oktas_m": "7 okta", "land_cond": "0 -",
    "cloud_low_type_cl": "2 -", "cloud_low_cover_oktas": "5 okta", "awan_rendah_jenis": "8 - cumulus (Cu)",
    "awan_rendah_jumlah": "5 okta", "cloud_low_base_1": 450, "cloud_low_peak_1": 2500,
    "cloud_arah_awan_rendah": "0 -", "cloud_elevation_1_angle_ec": "2 -", "cloud_arah_sebenarnya_1": "0 -",
    "cloud_med_type_cm": "1 -", "cloud_med_cover_oktas": "2 okta", "awan_menengah_jenis_1": "4 - altostratus (As)",
    "awan_menengah_jumlah_1": "2 okta", "cloud_med_base_1": 3000, "cloud_arah_menengah_1": "0 -",
    "cloud_high_type_ch": "1 -", "cloud_high_cover_oktas": "1 okta", "awan_tinggi_jenis": "0 - cirrus (Ci)",
    "awan_tinggi_jumlah": "1 okta", "cloud_high_base_1": 9000, "cloud_arah_tinggi": "0 -",
}
passed = failed = 0


def check(name, row_changes, expect_error=None, expect_warn=None, forbid_error=False, forbid_warn=None):
    global passed, failed
    row = dict(BASE)
    row.update(row_changes)
    r = V.validate_row(row, 2)
    errs = [i.rule for i in r.errors]
    warns = [i.rule for i in r.warnings]
    ok = True
    if expect_error and expect_error not in errs:
        ok = False
    if expect_warn and expect_warn not in warns:
        ok = False
    if forbid_error and errs:
        ok = False
    if forbid_warn and forbid_warn in warns:
        ok = False
    print(("  OK   " if ok else "  GAGAL"), name, "" if ok else f"-> error={errs} warn={warns}")
    passed += ok
    failed += (not ok)
    return r


print("== validator ==")
check("baris sehat tanpa ERROR", {}, forbid_error=True)
check("CL=1 Jenis 6 ditolak (R13)", {"cloud_low_type_cl": "1 -", "awan_rendah_jenis": "6 - stratocumulus (Sc)"}, expect_error="R13")
check("CL=6 Jenis 7 diterima", {"cloud_low_type_cl": "6 -", "awan_rendah_jenis": "7 - stratus (St)",
                               "cloud_low_peak_1": None, "cloud_elevation_1_angle_ec": None,
                               "cloud_arah_sebenarnya_1": None}, forbid_error=True)
check("CM=2 Jenis 3 ditolak (R13)", {"cloud_med_type_cm": "2 -", "awan_menengah_jenis_1": "3 - altocumulus (Ac)"}, expect_error="R13")
check("CH=5 Jenis 1 ditolak (R13)", {"cloud_high_type_ch": "5 -", "awan_tinggi_jenis": "1 - cirrostratus (Cs)"}, expect_error="R13")
check("puncak terisi saat CL=1/Jenis 8 -> WARNING (R23)", {"cloud_low_type_cl": "1 -"}, expect_warn="R23")
check("puncak terisi saat Jenis 6 -> WARNING (R23)", {"cloud_low_type_cl": "5 -", "awan_rendah_jenis": "6 - stratocumulus (Sc)"}, expect_warn="R23")
check("puncak kosong saat aktif -> WARNING (R23)", {"cloud_low_peak_1": None}, expect_warn="R23")
check("total 0 + kolom awan terisi -> WARNING (R20) tanpa ERROR", {"cloud_cover_oktas_m": "0"}, expect_warn="R20", forbid_error=True)
r = check("total 9 tanpa vertical visibility -> ERROR (R21)", {"cloud_cover_oktas_m": "9 -", "visibility": 0.5}, expect_error="R21")
check("total 9 + vertical visibility -> OK", {"cloud_cover_oktas_m": "9 -", "visibility": 0.5, "vertical_visibility": 100},
      forbid_error=True)
check("total 9 visibilitas 3.5 -> ERROR (R21, K8)", {"cloud_cover_oktas_m": "9 -", "visibility": 3.5, "vertical_visibility": 100},
      expect_error="R21")
check("total 9 visibilitas 0.9 lolos (batas < 1 km)", {"cloud_cover_oktas_m": "9 -", "visibility": 0.9, "vertical_visibility": 100},
      forbid_error=True)
check("total 9 visibilitas tepat 1.0 -> ERROR", {"cloud_cover_oktas_m": "9 -", "visibility": 1.0, "vertical_visibility": 100},
      expect_error="R21")
check("total '/' -> lapisan diabaikan", {"cloud_cover_oktas_m": "/ -"}, expect_warn="R20", forbid_error=True)
check("CH='/' + Jenis terisi -> WARNING (R20b)", {"cloud_high_type_ch": "/ -"}, expect_warn="R20b", forbid_error=True)
check("CL kosong saat total 7 -> ERROR (R9)", {"cloud_low_type_cl": None}, expect_error="R9")
check("jam tidak cocok waktu -> ERROR", {"jam_input": dt.time(9, 0)}, expect_error="R-JAM")
check("terlalu awal (30 menit) -> ERROR", {"waktu_eksekusi": dt.datetime(2026, 11, 14, 13, 30)}, expect_error="R-WKT")
check("nilai dropdown tak dikenal -> ERROR", {"ww": "999 -"}, expect_error="R-OPT")
check("visibilitas teks -> ERROR", {"visibility": "abc"}, expect_error="R-NUM")
check("NCL > total -> WARNING (R-NC1)", {"cloud_cover_oktas_m": "3 okta"}, expect_warn="R-NC1")
r = check("lapisan 2 menengah: Ac+As dengan CM=7", {"cloud_med_type_cm": "7 -", "awan_menengah_jenis_1": "4 - altostratus (As)",
      "awan_menengah_jenis_2": "3 - altocumulus (Ac)", "awan_menengah_jumlah_2": "2 okta", "cloud_med_base_2": 4500,
      "cloud_arah_menengah_2": "0 -"}, forbid_error=True, forbid_warn="F3.10")
ex = r.plan["extra"]
assert len(ex) == 1 and ex[0]["layer"] == "med" and ex[0]["n"] == 2 and ex[0]["toggle_ordinal"] == 1 \
    and ex[0]["jenis"].startswith("3 - altocumulus") and ex[0]["base"] == 4500 and ex[0]["base_id"] == "cloud_med_base_2", ex
print("  OK   plan['extra'] memuat lapisan menengah-2 lengkap (teks opsi penuh, id dasar, ordinal toggle)")
passed += 1
check("lapisan 2 menengah dengan CM=2 & Ac ditolak (R24)", {"cloud_med_type_cm": "2 -", "awan_menengah_jenis_1": "4 - altostratus (As)",
      "awan_menengah_jenis_2": "3 - altocumulus (Ac)", "awan_menengah_jumlah_2": "2 okta", "cloud_med_base_2": 4500,
      "cloud_arah_menengah_2": "0 -"}, expect_error="R24")
check("lapisan 2 tak lengkap -> ERROR (R14)", {"awan_menengah_jenis_2": "5 - nimbostratus (Ns)"}, expect_error="R14")
r = check("override hujan jam 07 UTC (bukan kelipatan 3) diabaikan", {"hujan_override_aktif": "ya", "hujan_override_mm": 3.5},
          expect_warn="R22", forbid_error=True)
assert r.plan["rain_override"] is None
r = check("override hujan jam 06 UTC berlaku", {"hujan_override_aktif": "ya", "hujan_override_mm": 3.5,
          "jam_input": dt.time(6, 0), "waktu_eksekusi": dt.datetime(2026, 11, 14, 12, 58)}, forbid_error=True)
assert r.plan["rain_override"] == {"mm": 3.5}
check("override aktif tanpa angka -> ERROR", {"hujan_override_aktif": "ya", "jam_input": dt.time(6, 0),
      "waktu_eksekusi": dt.datetime(2026, 11, 14, 12, 58)}, expect_error="R22")
check("baris hampir kosong -> ERROR (R9)", {"visibility": None, "ww": None, "w1": None, "w2": None, "cloud_cover_oktas_m": None}, expect_error="R9")

print("== lapisan tambahan (F3.10): rendah-3, menengah-2, tinggi-2 ==")
LOW3 = {"awan_rendah_3_jenis": "6 - stratocumulus (Sc)", "awan_rendah_3_jumlah": "1 okta", "cloud_low_base_3": 500,
        "cloud_arah_3": "0 -"}
r = check("rendah-3 valid (CL=2 -> Jenis 6 boleh)", dict(LOW3), forbid_error=True)
ex = r.plan["extra"]
assert len(ex) == 1 and ex[0]["layer"] == "low" and ex[0]["n"] == 3 and ex[0]["col"] == 3 \
    and ex[0]["toggle_ordinal"] == 2 and ex[0]["fallback_toggle_id"] == "776" and ex[0]["arah_row"] == 6, ex
print("  OK   plan['extra'] rendah-3: kolom 3, toggle urutan ke-2 (id 776), baris Arah 6")
passed += 1
check("rendah-3 Jenis 7 ditolak untuk CL=2 (R24)", dict(LOW3, awan_rendah_3_jenis="7 - stratus (St)"), expect_error="R24")
check("rendah-3 tak lengkap -> ERROR (R14)", {"awan_rendah_3_jenis": "6 - stratocumulus (Sc)"}, expect_error="R14")
HIGH2 = {"awan_tinggi_2_jenis": "2 - cirrostratus (Cs)", "awan_tinggi_2_jumlah": "1 okta", "cloud_high_base_2": 9500,
         "cloud_arah_tinggi_2": "0 -"}
r = check("tinggi-2 valid (CH=7 -> Cs boleh)", dict(HIGH2, cloud_high_type_ch="7 -"), forbid_error=True)
ex = r.plan["extra"]
assert len(ex) == 1 and ex[0]["layer"] == "high" and ex[0]["fallback_toggle_id"] == "778" and ex[0]["arah_row"] == 5, ex
print("  OK   plan['extra'] tinggi-2: toggle 778, baris Arah 5")
passed += 1
check("tinggi-2 Cs ditolak untuk CH=1 (R24)", dict(HIGH2), expect_error="R24")
check("lapisan 2 lebih rendah dari lapisan 1 -> WARNING (R-ORD)", {"cloud_med_type_cm": "7 -",
      "awan_menengah_jenis_2": "3 - altocumulus (Ac)", "awan_menengah_jumlah_2": "2 okta", "cloud_med_base_2": 2000,
      "cloud_arah_menengah_2": "0 -"}, expect_warn="R-ORD", forbid_error=True)
r = check("kolom lapisan tambahan ADA tetapi kosong -> extra_off (mati bila switch aktif)",
          {"awan_rendah_3_jenis": None, "awan_rendah_3_jumlah": None, "cloud_low_base_3": None, "cloud_arah_3": None,
           "awan_menengah_jenis_2": None, "awan_menengah_jumlah_2": None, "cloud_med_base_2": None,
           "cloud_arah_menengah_2": None, "awan_tinggi_2_jenis": None, "awan_tinggi_2_jumlah": None,
           "cloud_high_base_2": None, "cloud_arah_tinggi_2": None}, forbid_error=True)
offs = sorted((o["layer"], o["n"]) for o in r.plan["extra_off"])
assert offs == [("high", 2), ("low", 3), ("med", 2)], offs
print("  OK   extra_off memuat rendah-3, menengah-2, tinggi-2")
passed += 1
r = check("kolom lapisan tambahan TIDAK ADA di Excel -> tidak disentuh", {}, forbid_error=True)
assert r.plan["extra"] == [] and r.plan["extra_off"] == [], (r.plan["extra"], r.plan["extra_off"])
print("  OK   tanpa kolom: extra dan extra_off kosong (switch tidak diubah)")
passed += 1
V_off = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json", extra_layers_supported=False)
rr = V_off.validate_row(dict(BASE, **LOW3), 2)
assert "F3.10" in [i.rule for i in rr.warnings] and rr.plan["extra"] == [], (rr.warnings, rr.plan["extra"])
print("  OK   features.extra_layers=false: WARNING dan lapisan tidak masuk rencana")
passed += 1
r = check("total 0: kolom lapisan tambahan terisi diabaikan (R20)", dict(LOW3, cloud_cover_oktas_m="0"), expect_warn="R20", forbid_error=True)
assert r.plan["extra"] == []

print("== log status ==")
with tempfile.TemporaryDirectory() as d:
    log = SendLog(Path(d) / "t.db")
    s = ("2026-11-14", "07:00")
    assert log.should_send(*s)["send"] and not log.should_send(*s)["needs_web_check"]
    log.register(*s, waktu_eksekusi="2026-11-14 14:58", plan={"a": 1})
    log.start_attempt(*s, observer="X")
    d1 = log.should_send(*s)
    assert d1["send"] and d1["needs_web_check"], d1            # running -> perlu cek web
    log.mark_failed(*s, "timeout")
    assert log.should_send(*s)["needs_web_check"]
    log.start_attempt(*s)
    log.mark_sent(*s, kode_synop="AAXX 14064", diubah_otomatis={"ww": "10->05"})
    d2 = log.should_send(*s)
    assert not d2["send"], d2                                    # sent -> tidak kirim ulang
    assert log.get(*s)["percobaan"] == 2
    log.register(*s)                                             # register ulang tidak menimpa 'sent'
    assert log.get(*s)["status"] == "sent"
    log.mark_skipped(*s, "x")                                    # skip tidak menimpa 'sent'
    assert log.get(*s)["status"] == "sent"
    assert log.summary("2026-11-14")["sent"] == 1
    assert len(log.events(*s)) >= 4
    log.close()
    print("  OK   siklus pending->running->failed->running->sent, idempotensi, audit")
    passed += 1

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
