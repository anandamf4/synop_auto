# -*- coding: utf-8 -*-
"""
Uji klik popup OK (klik_tombol_oke_popup) TANPA layar/browser:  python tests/test_popup.py
Mereproduksi masalah pyautogui/pyscreeze versi baru yang MELEMPAR ImageNotFoundException
(versi lama mengembalikan None), yang membuat V6/V7 awal crash di Python 3.13.
"""
import importlib.util
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class ImageNotFoundException(Exception):
    pass


state = {"locate_calls": 0, "found_after": 3, "clicked": False}


def locate(path, confidence=None):
    state["locate_calls"] += 1
    if state["locate_calls"] < state["found_after"]:
        raise ImageNotFoundException("Could not locate the image (highest confidence = 0.508)")
    return (1, 2, 3, 4)


pg = types.ModuleType("pyautogui")
pg.locateOnScreen = locate
pg.center = lambda box: types.SimpleNamespace(x=10, y=20)
pg.moveTo = lambda *a, **k: None
pg.click = lambda: state.update(clicked=True)
sys.modules["pyautogui"] = pg

spec = importlib.util.spec_from_file_location("V7SATU_popup", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
M.time = types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time)
M.has_opencv = lambda: True

passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


class Btn:
    def is_displayed(self):
        return True


class Drv:
    def __init__(self, tombol=False):
        self.tombol = tombol

    def find_elements(self, by, value):
        return [Btn()] if (self.tombol and "swal2-confirm" in value) else []


clicked_btns = []
M.safe_click = lambda drv, el: clicked_btns.append(el)
snaps = []
M.save_debug_snapshot = lambda drv, tag="debug": snaps.append(tag)

with tempfile.TemporaryDirectory() as d:
    img = Path(d) / "ok.png"
    img.write_bytes(b"x")

    print("== gambar ada, pyautogui melempar ImageNotFoundException dulu ==")
    state.update(locate_calls=0, found_after=3, clicked=False)
    r = M.klik_tombol_oke_popup(image_path=str(img), max_wait=10, drv=Drv(False))
    check("tidak crash; akhirnya ditemukan & diklik", r is True and state["clicked"], r)
    check("polling berulang sampai gambar muncul (3 kali)", state["locate_calls"] == 3, state["locate_calls"])

    print("== Selenium menemukan tombol lebih dulu ==")
    state.update(locate_calls=0, found_after=1, clicked=False)
    clicked_btns.clear()
    r = M.klik_tombol_oke_popup(image_path=str(img), max_wait=5, drv=Drv(True))
    check("diklik lewat Selenium, pyautogui tidak dipakai", r is True and len(clicked_btns) == 1
          and state["locate_calls"] == 0, (r, state))

    print("== popup tidak pernah muncul ==")
    state.update(locate_calls=0, found_after=999, clicked=False)
    snaps.clear()
    r = M.klik_tombol_oke_popup(image_path=str(img), max_wait=3, drv=Drv(False))
    check("kembali False tanpa crash (proses boleh lanjut)", r is False)
    check("tidak membuang waktu untuk snapshot", snaps == [], snaps)

    print("== gambar tidak ada: hanya Selenium ==")
    state.update(locate_calls=0, found_after=1)
    clicked_btns.clear()
    r = M.klik_tombol_oke_popup(image_path=str(Path(d) / "tidak_ada.png"), max_wait=3, drv=Drv(True))
    check("Selenium dipakai, pyautogui tidak dipanggil", r is True and state["locate_calls"] == 0, (r, state))

    print("== exception lain dari pyautogui tidak mematikan proses ==")
    pg.locateOnScreen = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("layar tidak tersedia"))
    r = M.klik_tombol_oke_popup(image_path=str(img), max_wait=2, drv=Drv(False))
    check("RuntimeError ditangani, kembali False", r is False, r)

print("== opsi anti-popup Chrome (password manager / data breach) ==")
prefs = M.chrome_options.experimental_options.get("prefs", {})
check("prefs mematikan password manager & deteksi kebocoran",
      prefs.get("credentials_enable_service") is False and prefs.get("profile.password_manager_enabled") is False
      and prefs.get("profile.password_manager_leak_detection") is False, prefs)
check("argumen Chrome menonaktifkan fitur cek password",
      any(a.startswith("--disable-features=PasswordLeakDetection,PasswordCheck") for a in M.chrome_options.arguments), M.chrome_options.arguments)
src = (ROOT / "V7SATU.py").read_text(encoding="utf-8")
# [rev 28] recovery membuka browser lewat buat_driver() -> _opsi_chrome_baru() -> _terapkan_opsi_anti_popup()
check("opsi yang sama dipakai saat recovery sesi (browser baru)",
      "new_driver = buat_driver()" in src and "_terapkan_opsi_anti_popup(o, pakai_profil=pakai_profil)" in src)

print("== waktu tunggu dari config & cadangan tekan Enter ==")
sleeps = []
M.time = types.SimpleNamespace(sleep=lambda s: sleeps.append(s), time=__import__("time").time)
M.CFG["runtime"]["popup_wait_seconds"] = 2
M.CFG["features"]["popup_press_enter"] = False
r = M.klik_tombol_oke_popup(image_path="tidak_ada.png", drv=Drv(False))
# [rev 29] 2 percobaan = 1 tidur di antaranya (tidak tidur lagi setelah percobaan terakhir)
check("tanpa max_wait memakai runtime.popup_wait_seconds (2 percobaan) lalu lanjut", r is False and len(sleeps) == 1, (r, sleeps))
pressed = []
pg.press = lambda k: pressed.append(k)
M.CFG["features"]["popup_press_enter"] = True
r = M.klik_tombol_oke_popup(image_path="tidak_ada.png", max_wait=1, drv=Drv(False))
check("popup_press_enter=true: Enter ditekan sebagai cadangan", r is True and pressed == ["enter"], (r, pressed))
M.CFG["features"]["popup_press_enter"] = False
pressed.clear()
r = M.klik_tombol_oke_popup(image_path="tidak_ada.png", max_wait=1, drv=Drv(False))
check("default (false): tidak menekan tombol apa pun", r is False and pressed == [], (r, pressed))

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
