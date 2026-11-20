# -*- coding: utf-8 -*-
"""
Uji logika pengisian form V7SATU (F1.9) dan override hujan (F1.8) TANPA browser:
    python tests/test_bot_fill.py
Fungsi pengisi level bawah (pilih dropdown / isi input) diganti perekam panggilan.
"""
import datetime as dt
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))

import pandas as pd  # noqa: E402
from core.validator import Validator  # noqa: E402

spec = importlib.util.spec_from_file_location("V7SATU_fill", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
V = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json")

COLS = ["ww", "w1", "w2", "visibility", "cloud_cover_oktas_m", "cloud_low_type_cl", "cloud_low_cover_oktas",
        "awan_rendah_jenis", "awan_rendah_jumlah", "cloud_low_base_1", "cloud_low_peak_1", "cloud_arah_awan_rendah",
        "cloud_elevation_1_angle_ec", "cloud_arah_sebenarnya_1", "awan_rendah_2_jenis", "awan_rendah_2_jumlah",
        "cloud_low_base_2", "cloud_low_peak_2", "cloud_arah_2", "cloud_elevation_2_angle_ec",
        "cloud_arah_sebenarnya_2", "cloud_med_type_cm", "cloud_med_cover_oktas", "awan_menengah_jenis_1",
        "awan_menengah_jumlah_1", "cloud_med_base_1", "cloud_arah_menengah_1", "cloud_high_type_ch",
        "cloud_high_cover_oktas", "awan_tinggi_jenis", "awan_tinggi_jumlah", "cloud_high_base_1",
        "cloud_arah_tinggi", "land_cond"]
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
calls = []


def install_recorders():
    rec = lambda name, ret=True: (lambda *a, **k: (calls.append((name,) + tuple(x for x in a[1:] if not callable(x))) or ret))
    M.pilih_dropdown_ant_select = lambda drv, id_div, nilai, **k: (calls.append(("select", id_div, nilai)) or True)
    M.isi_input_text = lambda drv, id_input, nilai, timeout=12: (calls.append(("input", id_input, nilai)) or True)
    for n in ("isi_jenis_dan_jumlah_awan_Rendah", "pilih_arah_Awan_Rendah", "pilih_arah_sebenarnya",
              "klik_switch_jika_type", "isi_jenis_dan_jumlah_awan_rendah_2", "pilih_arah_2",
              "pilih_arah_sebenarnya_2", "isi_jenis_dan_jumlah_awan_menengah", "pilih_arah_Awan_Menengah",
              "isi_jenis_dan_jumlah_awan_Tinggi", "pilih_arah_Awan_Tinggi"):
        setattr(M, n, rec(n))


install_recorders()
# isi_hujan_override asli diuji langsung di bawah; pada uji alur isi_data cukup direkam pemanggilannya
REAL_OVERRIDE = M.isi_hujan_override
M.isi_hujan_override = lambda drv, mm: (calls.append(("input", "rainfall_last_mm", M._fmt_angka(mm))) or True)


def fill(changes, jam=7):
    d = dict(BASE)
    d.update(changes)
    full = {c: float("nan") for c in COLS}
    full.update(d)
    row = pd.Series(full)
    meta = dict(d)
    meta["waktu_eksekusi"] = dt.datetime(2026, 11, 14) + dt.timedelta(hours=jam + 7, minutes=-2)
    meta["jam_input"] = f"{jam:02d}:00"
    rr = V.validate_row(meta, 2)
    calls.clear()
    ok = M.isi_data(object(), row, plan=rr.plan)
    return ok, list(calls), rr


def has(cs, kind, key=None):
    return any(c[0] == kind and (key is None or c[1] == key) for c in cs)


passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


print("== F1.9: total tutupan ==")
ok, cs, rr = fill({"cloud_cover_oktas_m": "9 -", "visibility": 0.5, "vertical_visibility": 100})
check("total 9: vertical visibility diisi '100'", ok and ("input", "cloud_vertical_vis", "100") in cs, cs)
check("total 9: tidak menyentuh CL/CM/CH", not has(cs, "select", "cloud_low_type_cl")
      and not has(cs, "select", "cloud_med_type_cm") and not has(cs, "select", "cloud_high_type_ch"), cs)
check("total 9: land_cond tetap diisi", has(cs, "select", "land_cond"), cs)
ok, cs, rr = fill({"cloud_cover_oktas_m": "9 -", "visibility": 0.5, "vertical_visibility": 0.5})
check("vertical visibility 0.5 -> '0.5'", ("input", "cloud_vertical_vis", "0.5") in cs, cs)
ok, cs, rr = fill({"cloud_cover_oktas_m": "0"})
check("total 0: awan dilewati, land_cond diisi", ok and not has(cs, "select", "cloud_low_type_cl")
      and not has(cs, "input", "cloud_vertical_vis") and has(cs, "select", "land_cond"), cs)
ok, cs, rr = fill({"cloud_cover_oktas_m": "/ -"})
check("total '/': awan dilewati", ok and not has(cs, "select", "cloud_low_type_cl"), cs)
ok, cs, rr = fill({"cloud_cover_oktas_m": "9 -", "visibility": 0.5})   # vertical_visibility tidak diisi
check("total 9 tanpa vertical visibility -> gagal (bukan crash)", ok is False, (ok, cs))

print("== F1.9: puncak awan rendah ==")
ok, cs, rr = fill({})
check("CL=2 Jenis 8: puncak diisi", ok and ("input", "cloud_low_peak_1", "2500") in cs, cs)
ok, cs, rr = fill({"cloud_low_type_cl": "1 -"})
check("CL=1 Jenis 8: puncak TIDAK diisi", ok and not has(cs, "input", "cloud_low_peak_1"), cs)
ok, cs, rr = fill({"cloud_low_type_cl": "5 -", "awan_rendah_jenis": "6 - stratocumulus (Sc)"})
check("Jenis 6: puncak TIDAK diisi", ok and not has(cs, "input", "cloud_low_peak_1"), cs)

print("== F1.9: kode lapisan 0 atau '/' ==")
ok, cs, rr = fill({"cloud_high_type_ch": "/ -"})
check("CH='/': detail awan tinggi dilewati", ok and has(cs, "select", "cloud_high_type_ch")
      and not has(cs, "select", "cloud_high_cover_oktas") and not has(cs, "isi_jenis_dan_jumlah_awan_Tinggi"), cs)
ok, cs, rr = fill({"cloud_med_type_cm": "/ -"})
check("CM='/': detail awan menengah dilewati", ok and not has(cs, "select", "cloud_med_cover_oktas")
      and not has(cs, "isi_jenis_dan_jumlah_awan_menengah"), cs)
ok, cs, rr = fill({"cloud_low_type_cl": "/ -"})
check("CL='/': detail awan rendah dilewati", ok and not has(cs, "select", "cloud_low_cover_oktas")
      and not has(cs, "isi_jenis_dan_jumlah_awan_Rendah"), cs)
ok, cs, rr = fill({"cloud_high_type_ch": "0 -"})
check("CH='0 -' tetap dilewati (perilaku V6)", ok and not has(cs, "select", "cloud_high_cover_oktas"), cs)

print("== F1.8: override hujan (jam 06 UTC, kelipatan 3) ==")
ok, cs, rr = fill({"hujan_override_aktif": "ya", "hujan_override_mm": 3.5}, jam=6)
check("override aktif: hujan 3.5 diisi", ok and ("input", "rainfall_last_mm", "3.5") in cs, cs)
order = [c[1] for c in cs if c[0] in ("select", "input")]
check("override dilakukan setelah tutupan total, sebelum awan",
      order.index("cloud_cover_oktas_m") < order.index("rainfall_last_mm") < order.index("cloud_low_type_cl"), order[:8])
ok, cs, rr = fill({"hujan_override_aktif": "ya", "hujan_override_mm": 3.5}, jam=7)
check("jam 07 UTC: override diabaikan (tidak ada input hujan)", ok and not has(cs, "input", "rainfall_last_mm"), cs)
ok, cs, rr = fill({}, jam=6)
check("tanpa override: kolom hujan tidak disentuh", not has(cs, "input", "rainfall_last_mm"), cs)


class El:
    def __init__(self, enabled=True, val="0"):
        self.enabled, self.val = enabled, val

    def is_enabled(self):
        return self.enabled

    def get_attribute(self, n):
        return self.val if n == "value" else None


class Drv:
    def __init__(self, el):
        self.el = el

    def find_element(self, by, id_):
        return self.el


M.wait_for_presence = lambda drv, loc, timeout=10: drv.el
print("== F1.8: isi_hujan_override langsung ==")
M.isi_hujan_override = REAL_OVERRIDE
el = El(True, "0")
M.isi_input_text = lambda drv, id_input, nilai, timeout=12: (setattr(drv.el, "val", nilai) or True)
r = M.isi_hujan_override(Drv(el), 3.5)
check("berhasil: nilai AWS lama dicatat, nilai baru diterapkan",
      r is True and M.HUJAN_OVERRIDE_LOG == {"override": "3.5", "applied": True, "aws": "0", "nilai_akhir": "3.5"},
      M.HUJAN_OVERRIDE_LOG)
el = El(False, "")
r = M.isi_hujan_override(Drv(el), 3.5)
check("kolom nonaktif: tidak diterapkan, pengiriman lanjut", r is True and M.HUJAN_OVERRIDE_LOG["applied"] is False
      and "nonaktif" in M.HUJAN_OVERRIDE_LOG["reason"], M.HUJAN_OVERRIDE_LOG)
el = El(True, "0")
M.isi_input_text = lambda drv, id_input, nilai, timeout=12: (setattr(drv.el, "val", "0") or True)   # nilai tidak berubah
M.CFG["features"]["rain_override_strict"] = False
r = M.isi_hujan_override(Drv(el), 3.5)
check("gagal diterapkan (non-strict): lanjut, tercatat applied=False", r is True and M.HUJAN_OVERRIDE_LOG["applied"] is False,
      M.HUJAN_OVERRIDE_LOG)
M.CFG["features"]["rain_override_strict"] = True
r = M.isi_hujan_override(Drv(el), 3.5)
check("gagal diterapkan (strict): baris dibatalkan", r is False, r)

print("== F1.5: field opsional gagal dicatat; switch lapisan 2 ==")
install_recorders()          # pulihkan perekam (uji override langsung di atas memakai pengganti khusus)
_orig_input = M.isi_input_text
M.isi_input_text = lambda drv, id_input, nilai, timeout=12: (calls.append(("input", id_input, nilai)) or id_input != "cloud_low_base_1")
M.GAGAL_OPSIONAL.clear()
ok, cs, rr = fill({})
check("tinggi dasar opsional gagal: baris tetap lanjut", ok is True, ok)
check("kegagalan dicatat di GAGAL_OPSIONAL", any("cloud_low_base_1" in g for g in M.GAGAL_OPSIONAL), M.GAGAL_OPSIONAL)
M.isi_input_text = _orig_input
M.GAGAL_OPSIONAL.clear()
ok, cs, rr = fill({})
check("tanpa kegagalan: GAGAL_OPSIONAL kosong", M.GAGAL_OPSIONAL == [], M.GAGAL_OPSIONAL)

_orig_sw, _orig_atur = M._switch_aktif, M._atur_switch
M._switch_aktif = lambda drv, i: True
M._atur_switch = lambda drv, i, aktif: (calls.append(("atur_switch", i, aktif)) or True)
ok, cs, rr = fill({})   # BASE tidak memuat awan_rendah_2_jenis (kosong) -> lapisan 2 tak diminta
check("Excel tanpa lapisan 2 & switch aktif (data lama): switch 775 DIMATIKAN", ("atur_switch", "775", False) in cs, cs)
M._switch_aktif = lambda drv, i: False
ok, cs, rr = fill({})
check("switch sudah mati: tidak disentuh", not has(cs, "atur_switch"), cs)
M._switch_aktif, M._atur_switch = _orig_sw, _orig_atur

print("== F3.10: isi_data memanggil lapisan tambahan sebelum keadaan tanah ==")
M.isi_lapisan_tambahan = lambda drv, plan, layer=None: calls.append(
    ("lapisan_tambahan_" + str(layer), len([x for x in ((plan or {}).get("extra") or []) if x.get("layer") == layer])))
MED2 = {"cloud_med_type_cm": "7 -", "awan_menengah_jenis_1": "4 - altostratus (As)",
        "awan_menengah_jenis_2": "3 - altocumulus (Ac)", "awan_menengah_jumlah_2": "2 okta", "cloud_med_base_2": 4500,
        "cloud_arah_menengah_2": "0 -"}
ok, cs, rr = fill(MED2)
names = [(c[1] if c[0] in ("select", "input") else c[0]) for c in cs]
check("menengah-2 dipanggil dengan 1 lapisan", ("lapisan_tambahan_med", 1) in cs, cs)
check("[rev 15] urutan: rendah(1,2,3) -> menengah(1,2) -> tinggi(1,2) -> tanah",
      names.index("cloud_low_type_cl") < names.index("lapisan_tambahan_low") < names.index("cloud_med_type_cm")
      < names.index("lapisan_tambahan_med") < names.index("cloud_high_type_ch")
      < names.index("lapisan_tambahan_high") < names.index("land_cond"), names)
check("menengah-2 dipanggil setelah menengah-1 (sebelum awan tinggi)",
      names.index("isi_jenis_dan_jumlah_awan_menengah") < names.index("lapisan_tambahan_med") < names.index("cloud_high_type_ch"), names)
ok, cs, rr = fill({"cloud_cover_oktas_m": "0"})
check("total 0: awan dilewati sehingga lapisan tambahan tidak dipanggil",
      not any(c[0].startswith("lapisan_tambahan") for c in cs), cs)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
