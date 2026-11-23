# -*- coding: utf-8 -*-
"""
Rev 29 / F3.3 - pemangkasan waktu berdasarkan data nyata pantau_web (dry-run & jelajah 2026-11-22):
popup tak pernah muncul tetapi ditunggu 3 dtk; dropdown menunggu jeda tetap; opsi XPath bisa mengenai <li> tersembunyi;
Chrome melambat saat jendela tertutup. Tanpa browser asli:   python tests/test_f33_waktu.py
"""
import importlib.util
import sys
import time as _t
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules["pyautogui"] = None
passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


def muat():
    spec = importlib.util.spec_from_file_location("V7_f33", ROOT / "V7SATU.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    return M


M = muat()

print("== popup: tidak menunggu percuma ==")
check("bawaan popup_wait_seconds = 1 percobaan (bukan 3)", "get(\"popup_wait_seconds\", 1)" in (ROOT / "V7SATU.py").read_text(encoding="utf-8"))
tidur = []
M.time = types.SimpleNamespace(sleep=lambda s: tidur.append(s), time=_t.time, perf_counter=_t.perf_counter)
M.CFG["runtime"].pop("popup_wait_seconds", None)
M.CFG["features"]["popup_press_enter"] = False
M._klik_popup_oke_selenium_sekali = lambda drv: False
r = M.klik_tombol_oke_popup(image_path="tidak_ada.png", drv=object())
check("tanpa popup: 1 percobaan, TANPA tidur sama sekali", r is False and tidur == [], tidur)
tidur.clear()
r = M.klik_tombol_oke_popup(image_path="tidak_ada.png", max_wait=3, drv=object())
check("max_wait=3: tidur hanya di antara percobaan (2x, bukan 3x)", tidur == [1, 1], tidur)
M._klik_popup_oke_selenium_sekali = lambda drv: True
tidur.clear()
check("popup ada -> diklik segera tanpa tidur", M.klik_tombol_oke_popup(image_path="x.png", drv=object()) is True and tidur == [])

print("== dropdown: tunggu status terbuka, bukan jeda tetap ==")
M = muat()
M.time = types.SimpleNamespace(sleep=lambda s: None, time=_t.time, perf_counter=_t.perf_counter)


class D:
    def __init__(self, urut): self.urut, self.n = list(urut), 0
    def execute_script(self, js, *a):
        self.n += 1
        return self.urut.pop(0) if self.urut else self.urut_akhir
    urut_akhir = None


d = D(["closed", "closed", "open"])
check("terbuka setelah 2 kali polling -> True", M._tunggu_dropdown_terbuka(d, "x") is True and d.n == 3, d.n)
d = D([]); d.urut_akhir = None
check("driver tak mengembalikan status -> False segera (tidak menunggu percuma)", M._tunggu_dropdown_terbuka(d, "x") is False and d.n == 1, d.n)
d = D(["nf"])
check("elemen tak ada -> False segera", M._tunggu_dropdown_terbuka(d, "x") is False and d.n == 1)
d = D([]); d.urut_akhir = "closed"
t0 = _t.time()
check("tak pernah terbuka -> False setelah batas waktu (cadangan jeda lama dipakai pemanggil)",
      M._tunggu_dropdown_terbuka(d, "x", timeout=0.2) is False and (_t.time() - t0) < 1.5)


class DErr:
    def execute_script(self, *a): raise RuntimeError("x")


check("galat driver -> False (tidak melempar)", M._tunggu_dropdown_terbuka(DErr(), "x") is False)

print("== pilih_dropdown_ant_select memakai tunggu eksplisit; jeda lama hanya cadangan ==")
jeda = []
M._jeda = lambda s: jeda.append(s)
M.wait_for_presence = lambda drv, loc, timeout=10: object()
M.wait_for_clickable = lambda drv, loc, timeout=10: object()
M.safe_click = lambda drv, el: None
M._tunggu_nilai_terpilih = lambda *a, **k: True


class Inp:
    def clear(self): pass
    def send_keys(self, *a): pass


M.wait_for_presence = lambda drv, loc, timeout=10: Inp()


class DrvX:
    def execute_script(self, *a): return None


M._tunggu_dropdown_terbuka = lambda drv, id_div, timeout=1.0: True
ok = M.pilih_dropdown_ant_select(DrvX(), "ww", "21 - recent rain")
check("dropdown terbuka terdeteksi -> TIDAK ada jeda 0.5 setelah klik", ok is True and 0.5 not in jeda, jeda)
jeda.clear()
M._tunggu_dropdown_terbuka = lambda drv, id_div, timeout=1.0: False
M.pilih_dropdown_ant_select(DrvX(), "ww", "21 - recent rain")
check("status tak terbaca -> jeda 0.5 lama dipakai sebagai cadangan (perilaku aman)", 0.5 in jeda, jeda)

print("== pilih_opsi_unsur: utamakan <li> yang tampak ==")
M = muat()
M.time = types.SimpleNamespace(sleep=lambda s: None, time=_t.time)
klik = []


class Li:
    def __init__(self, teks, tampak=True): self.text, self._t = teks, tampak
    def is_displayed(self): return self._t


M.safe_click = lambda drv, el: klik.append(el.text or "<kosong>")
daftar = [Li("", False), Li("00:00", True)]
M.WebDriverWait = lambda drv, t: types.SimpleNamespace(until=lambda fn: daftar)
check("li tersembunyi (teks kosong) dilewati; yang tampak dipilih", M.pilih_opsi_unsur(object(), "00:00") is True and klik == ["00:00"], klik)
klik.clear()
daftar[:] = [Li("", False), Li("", False)]
check("semua tersembunyi -> cadangan elemen pertama (perilaku lama)", M.pilih_opsi_unsur(object(), "00:00") is True and len(klik) == 1)
klik.clear()


class LiTanpa:                                    # elemen tanpa is_displayed (tiruan lama) tetap dianggap tampak
    text = "03:00"


daftar[:] = [LiTanpa()]
check("elemen tanpa is_displayed -> dianggap tampak", M.pilih_opsi_unsur(object(), "03:00") is True and klik == ["03:00"])

print("== opsi Chrome anti-throttle ==")
from selenium.webdriver.chrome.options import Options
M = muat()
M.CFG["chrome"] = {"profile_dir": "", "anti_throttle": True}
o = Options(); M._terapkan_opsi_anti_popup(o, pakai_profil=False)
arg = o.arguments
fitur = [a for a in arg if a.startswith("--disable-features=")]
check("hanya SATU --disable-features (Chrome memakai yang terakhir) memuat password + occlusion",
      len(fitur) == 1 and "PasswordLeakDetection" in fitur[0] and "CalculateNativeWinOcclusion" in fitur[0], fitur)
check("flag renderer/timer/occluded dipasang",
      all(f in arg for f in ("--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows")), arg)
M.CFG["chrome"]["anti_throttle"] = False
o = Options(); M._terapkan_opsi_anti_popup(o, pakai_profil=False)
fitur = [a for a in o.arguments if a.startswith("--disable-features=")]
check("anti_throttle=false -> perilaku rev 28 (tanpa flag tambahan)",
      fitur == ["--disable-features=PasswordLeakDetection,PasswordCheck"] and "--disable-renderer-backgrounding" not in o.arguments, o.arguments)
from core.config import load_config
check("bawaan config: chrome.anti_throttle = True", load_config()["chrome"]["anti_throttle"] is True)

print("== ukur_latensi: hanya mengukur, tak pernah melempar ==")
M = muat()


class DL:
    def execute_script(self, js, *a):
        if "visibilityState" in js:
            return [1234, "visible", True]
        return 1
    def find_elements(self, by, v): return [object()] * 40


r = M.ukur_latensi(DL())
check("mengisi LATENSI: median, XPath, DOM, fokus",
      r["jumlah_dropdown"] == 40 and r["elemen_dom"] == 1234 and r["visibilityState"] == "visible" and r["jendela_fokus"] is True
      and r["execute_script_median_ms"] >= 0, r)
check("driver tiruan tak lengkap (None) -> LATENSI kosong, tanpa galat", M.ukur_latensi(types.SimpleNamespace(
    execute_script=lambda *a: None, find_elements=lambda *a: [])) == {})


class DMati:
    def execute_script(self, *a): raise RuntimeError("browser mati")


check("browser mati -> {} tanpa melempar", M.ukur_latensi(DMati()) == {})

print("== laporan pantau memuat latensi & anti_throttle ==")
src = (ROOT / "tools" / "pantau_web.py").read_text(encoding="utf-8")
check("pantau: latensi dicatat ke laporan & dipanggil pada jelajah", 'rek.info["latensi_driver"]' in src and "V.ukur_latensi(drv)" in src)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
