# -*- coding: utf-8 -*-
"""
F3.1 / rev 31 - peta field (core/fields.py), fungsi generik pilih_ant_select / isi_input, percobaan ulang PER LANGKAH
(sebelum jam dianggap gagal), dan dua set label tombol kirim (T21). Tanpa browser:   python tests/test_fields.py
"""
import importlib.util
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules["pyautogui"] = None
import pandas as pd  # noqa: E402
from core.fields import FIELDS, TOMBOL_KIRIM  # noqa: E402
from core.config import load_config  # noqa: E402

passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


def muat():
    spec = importlib.util.spec_from_file_location("V7_f31", ROOT / "V7SATU.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    M.SPEED_SCALE = 0.0   # jeda minimum
    return M


M = muat()
SRC = (ROOT / "V7SATU.py").read_text(encoding="utf-8")

print("== peta field ==")
pakai = set(re.findall(r'(?:pilih_ant_select|isi_input)\(driver, "([^"]+)"', SRC))
check("semua field yang dipanggil di V7SATU ada di FIELDS", pakai <= set(FIELDS), pakai - set(FIELDS))
check("setiap entri punya tipe, nama, wajib, aktif", all({"tipe", "nama", "wajib", "aktif"} <= set(f) for f in FIELDS.values()))
check("tipe valid & combo punya cara cari", all(f["tipe"] in ("pilih", "isi", "combo") and (f["tipe"] != "combo" or "cari" in f)
                                                for f in FIELDS.values()))
check("Arah Awan Rendah: XPath sama dengan skrip lama",
      FIELDS["cloud_arah_awan_rendah"]["cari"]["xpath"]
      == "//input[@id='cloud_low_peak_1']/parent::div/following-sibling::div//div[@role='combobox']")
check("Arah Sebenarnya 2: XPath sama dengan skrip lama",
      FIELDS["cloud_arah_sebenarnya_2"]["cari"]["xpath"]
      == "//div[@id='cloud_elevation_2_angle_ec']/ancestor::div[contains(@class,'row')]/following-sibling::div//div[@role='combobox']")
check("Jumlah Awan Tinggi: XPath relatif-id 2 sama dengan lama",
      FIELDS["awan_tinggi_jumlah"]["cari"]["xpath_lama"]
      == "//div[@id='cloud_high_cover_oktas']/ancestor::div[contains(@class,'row')]/following-sibling::div[contains(@class,'row')][2]//div[@role='combobox']")
lama = ["safe_click", "attempt_click", "wait_for_presence", "wait_for_clickable", "save_debug_snapshot", "pilih_opsi_unsur",
        "pilih_dropdown_ant_select", "pilih_opsi_ant_select", "isi_input_text", "click_button_by_text",
        "click_button_containing_words", "isi_jenis_dan_jumlah_awan_Rendah", "isi_jenis_dan_jumlah_awan_rendah_2",
        "isi_jenis_dan_jumlah_awan_menengah", "isi_jenis_dan_jumlah_awan_Tinggi", "pilih_arah_sebenarnya",
        "pilih_arah_sebenarnya_2", "pilih_arah_2", "pilih_arah_Awan_Rendah", "pilih_arah_Awan_Menengah",
        "pilih_arah_Awan_Tinggi", "klik_switch_jika_type", "SEND_SEND_SUBMIT", "SEND_GTS", "SEND_INASWITCH"]
check("zero-loss: semua nama fungsi lama masih ada", all(callable(getattr(M, n, None)) for n in lama),
      [n for n in lama if not callable(getattr(M, n, None))])
pembungkus = {"pilih_arah_sebenarnya": "cloud_arah_sebenarnya_1", "pilih_arah_sebenarnya_2": "cloud_arah_sebenarnya_2",
              "pilih_arah_2": "cloud_arah_2", "pilih_arah_Awan_Rendah": "cloud_arah_awan_rendah",
              "pilih_arah_Awan_Menengah": "cloud_arah_menengah_1", "pilih_arah_Awan_Tinggi": "cloud_arah_tinggi"}
rec = []
M.pilih_ant_select = lambda drv, fid, nilai: (rec.append((fid, nilai)) or True)
check("6 fungsi pilih_arah_* meneruskan ke field yang benar",
      all(getattr(M, fn)(None, "0 -") and rec[-1] == (fid, "0 -") for fn, fid in pembungkus.items()), rec)
M = muat()

print("== percobaan ulang per langkah ==")
n = {"c": 0}


def gagal_dulu(k):
    def f(drv, id_div, nilai, **kw):
        n["c"] += 1
        return n["c"] > k
    return f


M.pilih_dropdown_ant_select = gagal_dulu(2)
n["c"] = 0
check("dropdown wajib gagal 2x lalu berhasil -> True pada percobaan ke-3", M.pilih_ant_select(None, "cloud_low_type_cl", "2 -") and n["c"] == 3, n)
M.pilih_dropdown_ant_select = gagal_dulu(99)
n["c"] = 0
check("dropdown wajib selalu gagal -> False setelah 3 percobaan (tidak melompat)", not M.pilih_ant_select(None, "land_cond", "0 -") and n["c"] == 3, n)
n["c"] = 0
check("dropdown opsional selalu gagal -> 2 percobaan", not M.pilih_ant_select(None, "cloud_med_cover_oktas", "2 okta") and n["c"] == 2, n)
M.CFG["runtime"]["max_field_attempts"] = 1
n["c"] = 0
M.pilih_ant_select(None, "land_cond", "0 -")
check("max_field_attempts=1 -> perilaku tanpa ulang", n["c"] == 1, n)
M.CFG["runtime"]["max_field_attempts"] = 3

isi = {"c": 0, "nilai": ["", "", "450"]}
M.isi_input_text = lambda drv, i, v, timeout=12: (isi.__setitem__("c", isi["c"] + 1) or True)
M._input_terisi = lambda drv, i: bool(isi["nilai"][isi["c"] - 1])
check("input terisi tetapi kotak tetap kosong -> diulang sampai terisi", M.isi_input(None, "visibility_vv", 10) and isi["c"] == 3, isi)

M.pilih_dropdown_ant_select = lambda *a, **k: (_ for _ in ()).throw(M.NoSuchWindowException("x"))
try:
    M.pilih_ant_select(None, "land_cond", "0 -")
    check("jendela mati tidak ditelan (diteruskan ke recovery sesi)", False)
except M.NoSuchWindowException:
    check("jendela mati tidak ditelan (diteruskan ke recovery sesi)", True)

print("== combobox (Arah Awan Rendah, kasus 22:00 UTC) ==")
M = muat()
panggil = []
hasil = iter([False, False, True])
M.pilih_ant_select_berlapis = lambda drv, nama, target, kandidat, putaran=2: (panggil.append((nama, putaran)) or next(hasil))
M.save_debug_snapshot = lambda drv, tag="debug": panggil.append(("snap", tag))
check("Arah Awan Rendah gagal 2x lalu kena pada ke-3 -> True", M.pilih_arah_Awan_Rendah(None, "0 -") is True, panggil)
check("tiap percobaan memakai putaran=1 (cari ulang elemen segar)", [p for p in panggil if p[0] != "snap"] == [("Arah Awan Rendah", 1)] * 3, panggil)
panggil.clear()
M.pilih_ant_select_berlapis = lambda drv, nama, target, kandidat, putaran=2: (panggil.append(nama) or False)
check("gagal total: snapshot gagal_ untuk field wajib", not M.pilih_arah_Awan_Rendah(None, "0 -")
      and any(isinstance(p, tuple) and p[0] == "snap" for p in panggil), panggil)

print("== Jenis/Jumlah terpisah + catatan gagal ==")
M = muat()
urut = []
M.pilih_ant_select = lambda drv, fid, v: (urut.append(fid) or fid != "awan_rendah_jenis")
M.GAGAL_WAJIB.clear()
ok = M.isi_jenis_dan_jumlah_awan_Rendah(None, "8 - cumulus (Cu)", "5 okta")
check("Jenis gagal tidak menghentikan Jumlah; dicatat di GAGAL_WAJIB",
      ok is False and urut == ["awan_rendah_jenis", "awan_rendah_jumlah"]
      and M.GAGAL_WAJIB == ["Jenis Awan Rendah '8 - cumulus (Cu)' gagal dipilih"], (ok, urut, M.GAGAL_WAJIB))
M.GAGAL_OPSIONAL.clear()
M.GAGAL_WAJIB.clear()
M.pilih_ant_select = lambda drv, fid, v: False
M.isi_jenis_dan_jumlah_awan_Tinggi(None, "0 - cirrus (Ci)", "1 okta")
check("awan tinggi gagal dicatat di GAGAL_OPSIONAL (bukan wajib)", len(M.GAGAL_OPSIONAL) == 2 and not M.GAGAL_WAJIB, M.GAGAL_OPSIONAL)

print("== isi_data end-to-end: Arah Awan Rendah gagal dulu, jam TIDAK dilompati ==")
M = muat()
COLS = ["ww", "w1", "w2", "visibility", "cloud_cover_oktas_m", "cloud_low_type_cl", "cloud_low_cover_oktas", "awan_rendah_jenis",
        "awan_rendah_jumlah", "cloud_low_base_1", "cloud_low_peak_1", "cloud_arah_awan_rendah", "cloud_elevation_1_angle_ec",
        "cloud_arah_sebenarnya_1", "awan_rendah_2_jenis", "awan_rendah_2_jumlah", "cloud_low_base_2", "cloud_low_peak_2",
        "cloud_arah_2", "cloud_elevation_2_angle_ec", "cloud_arah_sebenarnya_2", "cloud_med_type_cm", "cloud_med_cover_oktas",
        "awan_menengah_jenis_1", "awan_menengah_jumlah_1", "cloud_med_base_1", "cloud_arah_menengah_1", "cloud_high_type_ch",
        "cloud_high_cover_oktas", "awan_tinggi_jenis", "awan_tinggi_jumlah", "cloud_high_base_1", "cloud_arah_tinggi", "land_cond"]
BASE = {"visibility": 10, "ww": "02 -", "w1": "2 -", "w2": "2 -", "cloud_cover_oktas_m": "7 okta", "land_cond": "0 -",
        "cloud_low_type_cl": "2 -", "cloud_low_cover_oktas": "5 okta", "awan_rendah_jenis": "6 - stratus (St)",
        "awan_rendah_jumlah": "3 okta", "cloud_low_base_1": 450, "cloud_arah_awan_rendah": "0 -",
        "cloud_med_type_cm": "1 -", "cloud_med_cover_oktas": "4 okta", "awan_menengah_jenis_1": "4 - altostratus (As)",
        "awan_menengah_jumlah_1": "4 okta", "cloud_med_base_1": 3000, "cloud_arah_menengah_1": "0 -",
        "cloud_high_type_ch": "1 -", "cloud_high_cover_oktas": "1 okta", "awan_tinggi_jenis": "0 - cirrus (Ci)",
        "awan_tinggi_jumlah": "1 okta", "cloud_high_base_1": 9000, "cloud_arah_tinggi": "0 -"}
full = {c: float("nan") for c in COLS}
full.update(BASE)
row = pd.Series(full)
M.pilih_dropdown_ant_select = lambda *a, **k: True
M.isi_input_text = lambda *a, **k: True
sebut = {"arah": 0}


def berlapis(drv, nama, target, kandidat, putaran=2):
    if nama == "Arah Awan Rendah":
        sebut["arah"] += 1
        return sebut["arah"] >= 3
    return True


M.pilih_ant_select_berlapis = berlapis
ok = M.isi_data(object(), row)
check("Arah Awan Rendah gagal 2x lalu berhasil: isi_data True, tanpa GAGAL_WAJIB", ok is True and not M.GAGAL_WAJIB and sebut["arah"] == 3,
      (ok, M.GAGAL_WAJIB, sebut))
sebut["arah"] = -99
ok = M.isi_data(object(), row)
check("Arah Awan Rendah gagal terus: isi_data False & tercatat (tangga per jam rev 30 yang mengambil alih)",
      ok is False and any("Arah Awan Rendah" in g for g in M.GAGAL_WAJIB), (ok, M.GAGAL_WAJIB))

print("== T21: dua set label tombol kirim ==")
M = muat()
klik = []
M.click_button_by_text = lambda drv, t, timeout=10, exact=False: (klik.append(t) or True)
M.click_button_containing_words = lambda drv, w, timeout=10: (klik.append(tuple(w)) or True)
M.wait_for_submit_progress = lambda drv, timeout=10: True
M.time = types.SimpleNamespace(sleep=lambda s: None, time=lambda: 0.0)
M._ada_tombol = lambda drv, t: t == "send & update"
check("hanya 'Send & Update' ada -> mode update", M._mode_kirim(None) == "update")
check("mode update mengklik 'send & update'", M.SEND_SEND_SUBMIT(None) and klik[-1] == "send & update", klik)
M._ada_tombol = lambda drv, t: t == "send & submit"
check("'Send & Submit' ada -> mode submit", M._mode_kirim(None) == "submit")
M._ada_tombol = lambda drv, t: True
check("keduanya ada -> submit (data belum ada)", M._mode_kirim(None) == "submit")
klik.clear()
M.click_button_by_text = lambda drv, t, timeout=10, exact=False: False
check("submit: teks persis tak ketemu -> cadangan kata 'send'+'submit'", M.SEND_SEND_SUBMIT(None) and klik == [("send", "submit")], klik)
klik.clear()
M._ada_tombol = lambda drv, t: t == "send & update"
check("update: tidak ada cadangan kata (gagal klik -> False)", M.SEND_SEND_SUBMIT(None) is False and klik == [], klik)
check("TOMBOL_KIRIM memuat dua set", set(TOMBOL_KIRIM) == {"submit", "update"})

print("== konfigurasi ==")
check("runtime.max_field_attempts bawaan 3", load_config()["runtime"]["max_field_attempts"] == 3)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
