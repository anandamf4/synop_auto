# -*- coding: utf-8 -*-
"""
Uji rev 14 TANPA browser:  python tests/test_continue.py
  1. Jenis awan rendah gagal -> field berikutnya (jumlah, tinggi dasar, arah, menengah, tinggi, land_cond) TETAP diisi;
     baris baru dibatalkan di AKHIR (kecuali features.send_despite_detail_fail=true).
  2. pilih_ant_select_berlapis: cara pertama gagal / tidak menemukan -> cara berikutnya dicoba.
  3. pilih_opsi_ant_select pada combobox yang tidak bisa diinteraksi: tidak melempar exception (False + diagnosis).
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))
spec = importlib.util.spec_from_file_location("V7SATU_cont", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


# ---------------------------------------------------------------- 1. lanjut setelah gagal
print("== isi_data: Jenis awan rendah gagal -> pengisian dilanjutkan ==")
import pandas as pd  # noqa: E402

calls = []
M.pilih_dropdown_ant_select = lambda drv, i, n, **k: (calls.append(("select", i)) or True)
M.isi_input_text = lambda drv, i, n, timeout=12: (calls.append(("input", i)) or True)
M.isi_lapisan_tambahan = lambda drv, plan, layer=None: calls.append(("lapisan_tambahan_" + str(layer),))
for n in ("pilih_arah_Awan_Rendah", "pilih_arah_sebenarnya", "klik_switch_jika_type", "pilih_arah_2",
          "pilih_arah_sebenarnya_2", "pilih_arah_Awan_Menengah", "pilih_arah_Awan_Tinggi",
          "isi_jenis_dan_jumlah_awan_menengah", "isi_jenis_dan_jumlah_awan_Tinggi"):
    setattr(M, n, (lambda nm: (lambda *a, **k: (calls.append((nm,)) or True)))(n))


def jenis_gagal(drv, j, jm):
    M.GAGAL_WAJIB.append(f"Jenis Awan Rendah '{j}' gagal dipilih")
    calls.append(("jenis_jumlah_rendah",))
    return False


M.isi_jenis_dan_jumlah_awan_Rendah = jenis_gagal
row = pd.Series({
    "visibility": 10, "ww": "02 -", "w1": "2 -", "w2": "2 -", "cloud_cover_oktas_m": "7 okta", "land_cond": "0 -",
    "cloud_low_type_cl": "9 -", "cloud_low_cover_oktas": "4 okta", "awan_rendah_jenis": "9 - cumulonimbus (Cb)",
    "awan_rendah_jumlah": "1 okta", "cloud_low_base_1": 450, "cloud_low_peak_1": 9000,
    "cloud_arah_awan_rendah": "0 -", "cloud_elevation_1_angle_ec": "1 -", "cloud_arah_sebenarnya_1": "0 -",
    "awan_rendah_2_jenis": float("nan"), "cloud_med_type_cm": "7 -", "cloud_med_cover_oktas": "7 okta",
    "awan_menengah_jenis_1": "3 - altocumulus (Ac)", "awan_menengah_jumlah_1": "4 okta", "cloud_med_base_1": 3000,
    "cloud_arah_menengah_1": "0 -", "cloud_high_type_ch": "9 -", "cloud_high_cover_oktas": "3 okta",
    "awan_tinggi_jenis": "1 - cirrocumulus (Cc)", "awan_tinggi_jumlah": "2 okta", "cloud_high_base_1": 9000,
    "cloud_arah_tinggi": "0 -"})
M.CFG["features"]["send_despite_detail_fail"] = False
ok = M.isi_data(object(), row, plan={"extra": [], "extra_off": []})
ids = [c[1] if len(c) > 1 else c[0] for c in calls]
check("isi_data False di AKHIR (bukan di tengah)", ok is False and ids[-1] == "land_cond", ids[-3:])
check("tinggi dasar, puncak, elevasi tetap diisi setelah Jenis gagal",
      all(x in ids for x in ("cloud_low_base_1", "cloud_low_peak_1", "cloud_elevation_1_angle_ec")), ids)
check("arah awan rendah, menengah, tinggi, lapisan tambahan tetap dijalankan",
      all(x in ids for x in ("pilih_arah_Awan_Rendah", "cloud_med_type_cm", "cloud_high_type_ch", "lapisan_tambahan_low", "lapisan_tambahan_high")), ids)
check("kegagalan tercatat di GAGAL_WAJIB", len(M.GAGAL_WAJIB) == 1 and "Jenis Awan Rendah" in M.GAGAL_WAJIB[0], M.GAGAL_WAJIB)
calls.clear()
M.CFG["features"]["send_despite_detail_fail"] = True
ok = M.isi_data(object(), row, plan={"extra": [], "extra_off": []})
check("send_despite_detail_fail=true -> isi_data True", ok is True)
M.CFG["features"]["send_despite_detail_fail"] = False


# ---------------------------------------------------------------- 2. pencarian berlapis
print("== pilih_ant_select_berlapis ==")
log = []
M.pilih_opsi_ant_select = lambda drv, combo, t, nama: (log.append(combo) or combo == "B")
M._jeda = lambda *a, **k: None
ok = M.pilih_ant_select_berlapis(object(), "X", "t", [("a", lambda: None), ("b", lambda: "A"), ("c", lambda: "B")])
check("cara 1 kosong, cara 2 gagal, cara 3 berhasil", ok and log == ["A", "B"], log)
log.clear()
ok = M.pilih_ant_select_berlapis(object(), "X", "t", [("a", lambda: "A")], putaran=2)
check("semua gagal -> False setelah 2 putaran", ok is False and log == ["A", "A"], log)
log.clear()
def boom():
    raise RuntimeError("x")
ok = M.pilih_ant_select_berlapis(object(), "X", "t", [("a", boom), ("b", lambda: "B")])
check("cara yang error dilewati, cara berikutnya dipakai", ok is True)

# ---------------------------------------------------------------- 3. combobox tak bisa diinteraksi
print("== pilih_opsi_ant_select: combobox tidak bisa diinteraksi ==")
spec2 = importlib.util.spec_from_file_location("V7SATU_cont2", ROOT / "V7SATU.py")
M2 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(M2)
from selenium.common.exceptions import ElementNotInteractableException  # noqa: E402


class Combo:
    def get_attribute(self, n):
        return "menu-1" if n == "aria-controls" else None

    def find_elements(self, *a):
        return []

    def find_element(self, *a):
        raise ElementNotInteractableException("not interactable")

    def click(self):
        raise ElementNotInteractableException("not interactable")

    def send_keys(self, *a):
        raise ElementNotInteractableException("not interactable")


class Drv:
    def __init__(self, state):
        self.state = state

    def execute_script(self, js, *a):
        return self.state if "getBoundingClientRect" in js else None

    def find_elements(self, *a):
        return []


M2._jeda = lambda *a, **k: None
t0 = __import__("time").time()
r = M2.pilih_opsi_ant_select(Drv({"shown": False, "disabled": False, "w": 0, "h": 0, "cls": "x"}), Combo(), "9 - Cb", "Jenis")
check("tersembunyi -> False tanpa exception", r is False)
r = M2.pilih_opsi_ant_select(Drv({"shown": True, "disabled": True, "w": 10, "h": 10, "cls": "ant-select-disabled"}), Combo(), "9 - Cb", "Jenis")
check("disabled -> False tanpa exception", r is False)
M2._combo_siap = lambda *a, **k: True   # lolos pemeriksaan siap, tetapi klik/send_keys melempar exception
M2.attempt_click = lambda drv, el: True
M2.WebDriverWait = lambda drv, t: types.SimpleNamespace(until=lambda f: (_ for _ in ()).throw(M2.TimeoutException("t")))
r = M2.pilih_opsi_ant_select(Drv({"shown": True, "disabled": False}), Combo(), "9 - Cb", "Jenis")
check("menu tak terbuka + elemen tak bisa diinteraksi -> False (dulu: ElementNotInteractableException)", r is False)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
