# -*- coding: utf-8 -*-
"""rev 32: jalur cepat dropdown (klik opsi tanpa mengetik), urutan pengisian bagian bawah (penguapan, radiasi, tanah, iE, lama
penyinaran SETELAH awan). Tanpa browser.   python tests/test_rev32_bot.py"""
import importlib.util
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))
import pandas as pd  # noqa: E402

spec = importlib.util.spec_from_file_location("V7SATU_r32", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

passed = failed = 0


def check(n, c, info=""):
    global passed, failed
    print(("  OK   " if c else "  GAGAL"), n, "" if c else f"-> {info}")
    passed += bool(c)
    failed += (not c)


print("== pemilihan opsi & pembanding ==")
OPS = [("10 - mist", False, True), ("0 - Stationary or No Clouds", False, True), ("1 - Lainnya", True, True), ("5 - tersembunyi", False, False)]
check("kode saja '0 -' memilih opsi berawalan 0, BUKAN '10 - mist'", M._pilih_indeks_opsi(OPS, "0 -") == 1)
check("teks persis menang atas awalan", M._pilih_indeks_opsi([("4 - 4 oktas", False, True), ("4", False, True)], "4") == 1)
check("'4 oktas' cocok dengan '4 - 4 oktas' (mengandung)", M._pilih_indeks_opsi([("3 - 3 oktas", False, True), ("4 - 4 oktas", False, True)], "4 oktas") == 1)
check("opsi nonaktif / tersembunyi tidak dipilih", M._pilih_indeks_opsi(OPS, "1 -") is None and M._pilih_indeks_opsi(OPS, "5 -") is None)
check("verifikasi: '0 -' tidak lolos untuk '10 - mist'", not M._sama_pilihan("10 - mist", "0 -") and M._sama_pilihan("0 - Stationary", "0 -"))
check("verifikasi: kosong tidak lolos; teks penuh lolos", not M._sama_pilihan("", "x") and M._sama_pilihan("4 - 4 oktas", "4 oktas"))


class Li:
    def __init__(self, drv, teks):
        self.drv, self.teks = drv, teks

    def click(self):
        if self.drv.sticky:
            self.drv.selected = self.teks
        self.drv.menu_open = False


class Combo:
    def __init__(self, drv):
        self.drv = drv

    def get_attribute(self, n):
        return "menu-1" if n == "aria-controls" else None

    def click(self):
        self.drv.klik += 1
        if self.drv.klik >= self.drv.buka_pada:
            self.drv.menu_open = True


class Drv:
    def __init__(self, opsi, selected="", buka_pada=1, sticky=True):
        self.opsi, self.selected, self.buka_pada, self.sticky = opsi, selected, buka_pada, sticky
        self.menu_open, self.klik, self.mengetik = False, 0, 0

    def find_element(self, by, v):
        return Combo(self)

    def execute_script(self, js, *a):
        if js == M._JS_STATE_COMBO:
            return {"shown": True, "disabled": False}
        if js == M._JS_NILAI_COMBO:
            return self.selected
        if js == M._JS_OPSI_MENU:
            return [[t, False, True] for t in self.opsi] if self.menu_open else None
        if js == M._JS_AMBIL_LI:
            return Li(self, self.opsi[a[1]])
        if js.startswith("arguments[0].click"):
            a[0].click()
        return None


M.ActionChains = lambda d: types.SimpleNamespace(send_keys=lambda *k: types.SimpleNamespace(perform=lambda: None))
print("== jalur cepat _pilih_cepat ==")
M.FAST_SELECT = True
JENIS = ["0 - cirrus (Ci)", "6 - stratocumulus (Sc)", "8 - cumulus (Cu)"]
d = Drv(JENIS)
t0 = time.time()
r = M._pilih_cepat(d, Combo(d), "6 - stratocumulus (Sc)", "Jenis")
check("memilih opsi lewat klik, terverifikasi, < 1 dtk, tanpa mengetik", r is True and d.selected == "6 - stratocumulus (Sc)" and time.time() - t0 < 1.0, (r, d.selected))
d = Drv(JENIS, selected="6 - stratocumulus (Sc)")
check("sudah terisi: True tanpa klik apa pun", M._pilih_cepat(d, Combo(d), "6 - stratocumulus (Sc)", "Jenis") is True and d.klik == 0)
d = Drv(JENIS)
check("opsi tidak ada -> None (jalur lama yang mencoba)", M._pilih_cepat(d, Combo(d), "9 - tidak ada", "Jenis") is None)
d = Drv(JENIS, buka_pada=2)
r = M._pilih_cepat(d, Combo(d), "8 - cumulus (Cu)", "Jenis")
check("klik pertama tak membuka menu -> cara berikutnya (JS) membuka; tak menutup menu yang sudah terbuka", r is True and d.selected == "8 - cumulus (Cu)", (r, d.klik))
d = Drv(JENIS, sticky=False)
check("klik opsi tak 'menempel' -> None (tidak pura-pura berhasil)", M._pilih_cepat(d, Combo(d), "8 - cumulus (Cu)", "Jenis") is None)
M.FAST_SELECT = False
d = Drv(JENIS)
check("speed.fast_select=false -> jalur cepat mati (None, tidak menyentuh halaman)", M._pilih_cepat(d, Combo(d), "8 - cumulus (Cu)", "Jenis") is None and d.klik == 0)
M.FAST_SELECT = True
d = Drv(JENIS)
check("pilih_dropdown_ant_select memakai jalur cepat (berid)", M.pilih_dropdown_ant_select(d, "cloud_low_type_cl", "8 - cumulus (Cu)") is True and d.selected == "8 - cumulus (Cu)")
d = Drv(JENIS)
check("pilih_opsi_ant_select (combobox tanpa id) memakai jalur cepat", M.pilih_opsi_ant_select(d, Combo(d), "0 - cirrus (Ci)", "Jenis") is True and d.selected == "0 - cirrus (Ci)")

print("== urutan pengisian bagian bawah (setelah awan) ==")
COLS = ["ww", "w1", "w2", "visibility", "cloud_cover_oktas_m", "cloud_low_type_cl", "cloud_low_cover_oktas", "awan_rendah_jenis",
        "awan_rendah_jumlah", "cloud_low_base_1", "cloud_low_peak_1", "cloud_arah_awan_rendah", "cloud_elevation_1_angle_ec",
        "cloud_arah_sebenarnya_1", "awan_rendah_2_jenis", "awan_rendah_2_jumlah", "cloud_low_base_2", "cloud_low_peak_2", "cloud_arah_2",
        "cloud_elevation_2_angle_ec", "cloud_arah_sebenarnya_2", "cloud_med_type_cm", "cloud_med_cover_oktas", "awan_menengah_jenis_1",
        "awan_menengah_jumlah_1", "cloud_med_base_1", "cloud_arah_menengah_1", "cloud_high_type_ch", "cloud_high_cover_oktas",
        "awan_tinggi_jenis", "awan_tinggi_jumlah", "cloud_high_base_1", "cloud_arah_tinggi", "land_cond"]
BASE = {"visibility": 2, "ww": "10 -", "w1": "2 -", "w2": "2 -", "cloud_cover_oktas_m": "7 okta", "land_cond": "0 -",
        "cloud_low_type_cl": "5 -", "cloud_low_cover_oktas": "3 okta", "awan_rendah_jenis": "6 - strat", "awan_rendah_jumlah": "3 okta",
        "cloud_low_base_1": 450, "cloud_arah_awan_rendah": "0 -", "cloud_med_type_cm": "3 -", "cloud_med_cover_oktas": "4 okta",
        "awan_menengah_jenis_1": "3 - alto", "awan_menengah_jumlah_1": "4 okta", "cloud_med_base_1": 3000, "cloud_arah_menengah_1": "0 -",
        "cloud_high_type_ch": "1 -", "cloud_high_cover_oktas": "2 okta", "awan_tinggi_jenis": "0 - cirrus", "awan_tinggi_jumlah": "2 okta",
        "cloud_high_base_1": 9000, "cloud_arah_tinggi": "0 -"}
calls = []
M.pilih_ant_select = lambda drv, k, v: (calls.append(("select", k)) or True)
M.isi_input = lambda drv, k, v: (calls.append(("input", k)) or True)
M.isi_penguapan_00 = lambda drv, pg, bagian=None: (calls.append(("penguapan", tuple(bagian or ()))) or True)
M.isi_lapisan_tambahan = lambda drv, plan, layer=None: None
M._switch_aktif = lambda drv, i: False
for n in ("isi_jenis_dan_jumlah_awan_Rendah", "pilih_arah_Awan_Rendah", "isi_jenis_dan_jumlah_awan_menengah", "pilih_arah_Awan_Menengah",
          "isi_jenis_dan_jumlah_awan_Tinggi", "pilih_arah_Awan_Tinggi"):
    setattr(M, n, (lambda nm: lambda *a, **k: (calls.append((nm,)) or True))(n))
PG = {"mm": 5.6, "radiasi": {"kosongkan": True}, "sinar_jam": 7.6, "ie": 0}


def isi(changes=None, plan=None):
    d = dict(BASE)
    d.update(changes or {})
    row = pd.Series({**{c: float("nan") for c in COLS}, **d})
    calls.clear()
    return M.isi_data(object(), row, plan=plan)


ok = isi(plan={"penguapan": PG})
nama = [c[1] if len(c) > 1 and c[0] in ("select", "input") else (c[0] + str(c[1]) if c[0] == "penguapan" else c[0]) for c in calls]
akhir = nama[nama.index("cloud_high_type_ch"):]
check("jam 00: lengkap & berhasil", ok is True, calls)
check("penguapan TIDAK dikerjakan sebelum awan", nama.index("penguapan('mm', 'radiasi')") > nama.index("cloud_high_type_ch") > nama.index("cloud_low_type_cl"), nama)
check("urutan akhir: ...awan tinggi -> penguapan+radiasi -> keadaan tanah -> iE+lama penyinaran",
      [x for x in akhir if x in ("penguapan('mm', 'radiasi')", "land_cond", "penguapan('ie', 'sinar_jam')")]
      == ["penguapan('mm', 'radiasi')", "land_cond", "penguapan('ie', 'sinar_jam')"] and nama[-1] == "penguapan('ie', 'sinar_jam')", nama)
check("urutan default isi_penguapan_00 = urutan web (penguapan, radiasi, iE, lama penyinaran)", M.URUTAN_PENGUAPAN_WEB == ("mm", "radiasi", "ie", "sinar_jam"))
ok = isi({"cloud_cover_oktas_m": "0"}, plan={"penguapan": PG, "skip_clouds": True})
nama = [c[1] if len(c) > 1 and c[0] in ("select", "input") else (c[0] + str(c[1]) if c[0] == "penguapan" else c[0]) for c in calls]
check("tutupan 0 (awan dilewati): bagian bawah tetap urut", ok is True and nama[-3:] == ["penguapan('mm', 'radiasi')", "land_cond", "penguapan('ie', 'sinar_jam')"], nama)
ok = isi(plan={})
nama = [c[1] for c in calls if c[0] in ("select", "input")]
check("jam bukan 00 (tanpa rencana penguapan): hanya keadaan tanah, di akhir", ok is True and nama[-1] == "land_cond" and not any(c[0] == "penguapan" for c in calls), calls)
M.isi_penguapan_00 = lambda drv, pg, bagian=None: (calls.append(("penguapan", tuple(bagian or ()))) or bagian != ("mm", "radiasi"))
check("penguapan/radiasi gagal -> jam dibatalkan sebelum keadaan tanah", isi(plan={"penguapan": PG}) is False and ("select", "land_cond") not in calls, calls)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
