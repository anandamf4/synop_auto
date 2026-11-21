# -*- coding: utf-8 -*-
"""
Uji aturan QC konsistensi (F1.10), tanpa pytest:   python tests/test_qc.py
Tiap aturan: minimal 1 kasus LOLOS dan 1 kasus TERDETEKSI. Juga regresi pada Excel nyata
(legacy/INPUT_PARAMETER_baru.xlsx harus 0 ERROR dan 0 temuan QC) dan mode strict.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.validator import Validator, load_excel, ERROR, WARNING, INFO  # noqa: E402

V = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json")
VS = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json", qc_strict=True)
VOFF = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json", qc_enabled=False)

BASE = {  # baris sehat: total 7, CL=2/Cu, CM=1/As, CH=1/Ci; tidak boleh memicu QC apa pun
    "waktu_eksekusi": dt.datetime(2026, 11, 14, 13, 58), "jam_input": dt.time(7, 0),
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


def run(changes, v=V):
    row = dict(BASE)
    row.update(changes)
    return v.validate_row(row, 2)


def rules(r, level=None):
    return [i.rule for i in r.issues if i.rule.startswith("QC") and (level is None or i.level == level)]


def check(name, changes, expect=None, forbid=None, v=V, level=None):
    """expect = id aturan yang harus terpicu; forbid = id yang tidak boleh terpicu (None+None = tanpa QC)."""
    global passed, failed
    r = run(changes, v)
    got = rules(r)
    ok = True
    if expect and expect not in got:
        ok = False
    if expect and level and not any(i.rule == expect and i.level == level for i in r.issues):
        ok = False
    if forbid and forbid in got:
        ok = False
    if expect is None and forbid is None and got:
        ok = False
    print(("  OK   " if ok else "  GAGAL"), name, "" if ok else f"-> QC={got}")
    passed += ok
    failed += (not ok)
    return r


print("== QC konsistensi (F1.10) ==")
check("baris sehat: tidak ada temuan QC", {})
check("QC10 W1<W2 terdeteksi", {"w1": "2 -", "w2": "6 -"}, expect="QC10")
check("QC10 W1=W2 boleh (data nyata jam 07:00: 6/6)", {"w1": "6 -", "w2": "6 -"}, forbid="QC10")
check("QC10 W1>W2 boleh", {"w1": "6 -", "w2": "2 -"}, forbid="QC10")

# QC13: N=9 -> baris tanpa detail awan (web mengisi otomatis); vertical visibility wajib
N9 = {"cloud_cover_oktas_m": "9 - Sky obscured", "visibility": 0.5, "vertical_visibility": 100}
check("QC13 N=9 dengan ww=02 terdeteksi", dict(N9, ww="02 -"), expect="QC13")
check("QC13 N=9 dengan ww=45 (kabut, langit tak terlihat) boleh", dict(N9, ww="45 -"), forbid="QC13")
check("QC13 N=9 dengan ww=04 (smoke) dikecualikan", dict(N9, ww="04 -"), forbid="QC13")

check("QC-U1 ww hujan dengan N=0 terdeteksi",
      {"cloud_cover_oktas_m": "0", "ww": "61 -"}, expect="QC-U1")
check("QC-U1 ww cerah dengan N=0 boleh", {"cloud_cover_oktas_m": "0", "ww": "02 -"}, forbid="QC-U1")
check("QC-U2 tanah kering saat hujan -> INFO", {"ww": "61 -", "w1": "6 -", "w2": "6 -", "land_cond": "0 -"},
      expect="QC-U2", level=INFO)
check("QC-U2 tanah basah saat hujan boleh", {"ww": "61 -", "w1": "6 -", "w2": "6 -", "land_cond": "2 -"},
      forbid="QC-U2")
check("QC-U3 ww=21 tetapi W1/W2 tanpa hujan -> INFO", {"ww": "21 -", "w1": "2 -", "w2": "2 -"},
      expect="QC-U3", level=INFO)
check("QC-U3 ww=21 dengan W1=6 (data nyata) boleh", {"ww": "21 -", "w1": "6 -", "w2": "2 -"}, forbid="QC-U3")

check("QC35 N<8 dengan CH=7 terdeteksi",
      {"cloud_high_type_ch": "7 -", "awan_tinggi_jenis": "2 - cirrostratus (Cs)"}, expect="QC35")
check("QC35 N=8 dengan CH=7 boleh",
      {"cloud_cover_oktas_m": "8 okta", "cloud_high_type_ch": "7 -", "awan_tinggi_jenis": "2 - cirrostratus (Cs)",
       "awan_tinggi_jumlah": "8 okta", "cloud_high_cover_oktas": "8 okta"}, forbid="QC35")

N8 = {"cloud_cover_oktas_m": "8 okta", "cloud_low_cover_oktas": "8 okta", "awan_rendah_jumlah": "8 okta"}
check("QC44 awan rendah 8 okta tetapi CM terisi terdeteksi", N8, expect="QC44")
check("QC47 awan rendah 8 okta tetapi CH terisi terdeteksi", N8, expect="QC47")
check("QC44/47 awan rendah 8 okta dengan CM='/' dan CH='/' boleh",
      dict(N8, cloud_med_type_cm="/ -", cloud_high_type_ch="/ -"), forbid="QC44")
check("QC47 (lanjutan) CH='/' boleh", dict(N8, cloud_med_type_cm="/ -", cloud_high_type_ch="/ -"), forbid="QC47")

check("QC107 jumlah lapisan 8 okta dengan total 7 terdeteksi", {"awan_rendah_jumlah": "8 okta"}, expect="QC107")
check("QC107 jumlah 7 okta dengan total 7 boleh", {"awan_rendah_jumlah": "7 okta"}, forbid="QC107")

check("QC90 Cs dengan dasar 3000 m terdeteksi",
      {"cloud_high_type_ch": "7 -", "awan_tinggi_jenis": "2 - cirrostratus (Cs)", "cloud_high_base_1": 3000,
       "cloud_cover_oktas_m": "8 okta", "awan_tinggi_jumlah": "8 okta", "cloud_high_cover_oktas": "8 okta"},
      expect="QC90")
check("QC90 Ci dasar 3000 m boleh (hanya Cc/Cs dibatasi)", {"cloud_high_base_1": 3000}, forbid="QC90")
check("QC90 As dasar 1000 m terdeteksi", {"cloud_med_base_1": 1000}, expect="QC90")
check("QC90 Cu dasar 2500 m terdeteksi", {"cloud_low_base_1": 2500, "cloud_low_peak_1": 4000}, expect="QC90")
check("QC90 Cu dasar 450 m boleh", {}, forbid="QC90")
check("QC90 Ns dasar 7500 m terdeteksi",
      {"cloud_med_type_cm": "2 -", "awan_menengah_jenis_1": "5 - nimbostratus (Ns)", "cloud_med_base_1": 7500},
      expect="QC90")

check("QC121 awan rendah ke-2 lebih rendah dari ke-1 terdeteksi",
      {"awan_rendah_2_jenis": "6 - stratocumulus (Sc)", "awan_rendah_2_jumlah": "2 okta",
       "cloud_low_base_2": 300, "cloud_arah_2": "0 -"}, expect="QC121")
check("QC121 ke-2 setinggi ke-1 boleh (data nyata Cu+Sc 450 m)",
      {"awan_rendah_2_jenis": "6 - stratocumulus (Sc)", "awan_rendah_2_jumlah": "2 okta",
       "cloud_low_base_2": 450, "cloud_arah_2": "0 -"}, forbid="QC121")

check("QC-PK Cu dengan puncak 8000 m -> peringatan", {"cloud_low_peak_1": 8000}, expect="QC-PK")
check("QC-PK Cu puncak 4000 m boleh (data nyata)", {"cloud_low_peak_1": 4000}, forbid="QC-PK")
check("QC-PK Cb puncak 9000 m boleh (data nyata)",
      {"cloud_low_type_cl": "9 -", "awan_rendah_jenis": "9 - cumulonimbus (Cb)", "cloud_low_peak_1": 9000},
      forbid="QC-PK")
check("QC-PK Cb puncak 3000 m -> peringatan",
      {"cloud_low_type_cl": "9 -", "awan_rendah_jenis": "9 - cumulonimbus (Cb)", "cloud_low_peak_1": 3000},
      expect="QC-PK")

print("\n== tingkat keparahan ==")
r = run({"w1": "2 -", "w2": "6 -"})
ok = any(i.rule == "QC10" and i.level == WARNING for i in r.issues) and not r.errors
print(("  OK   " if ok else "  GAGAL"), "bawaan: QC10 hanya WARNING, baris tidak diblok")
passed += ok; failed += (not ok)
r = run({"w1": "2 -", "w2": "6 -"}, VS)
ok = any(i.rule == "QC10" and i.level == ERROR for i in r.issues) and not r.ok
print(("  OK   " if ok else "  GAGAL"), "qc_strict: QC10 menjadi ERROR, baris diblok")
passed += ok; failed += (not ok)
r = run({"cloud_low_peak_1": 8000}, VS)
ok = any(i.rule == "QC-PK" and i.level == WARNING for i in r.issues) and r.ok
print(("  OK   " if ok else "  GAGAL"), "qc_strict: aturan turunan (QC-PK) tetap WARNING")
passed += ok; failed += (not ok)
r = run({"w1": "2 -", "w2": "6 -"}, VOFF)
ok = not rules(r)
print(("  OK   " if ok else "  GAGAL"), "qc_enabled=false: tidak ada temuan QC")
passed += ok; failed += (not ok)

print("\n== regresi Excel nyata ==")
xl = ROOT / "legacy" / "INPUT_PARAMETER_baru.xlsx"
if xl.exists():
    df = load_excel(xl)
    for nama, v in (("bawaan", V), ("strict", VS)):
        _, res = v.validate_dataframe(df)
        n_err = sum(1 for x in res if x.errors)
        n_qc = sum(len(rules(x)) for x in res)
        ok = (n_err == 0 and n_qc == 0 and len(res) > 0)
        print(("  OK   " if ok else "  GAGAL"), f"Excel nyata ({len(res)} baris, mode {nama}): ERROR={n_err}, temuan QC={n_qc}")
        passed += ok; failed += (not ok)
else:
    print("  (lewati) legacy/INPUT_PARAMETER_baru.xlsx tidak ada")

print(f"\nTotal: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
