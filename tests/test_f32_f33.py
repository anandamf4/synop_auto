# -*- coding: utf-8 -*-
"""F3.2 (pyautogui opsional) & F3.3 (profil Chrome tetap + explicit wait di login). Tanpa browser/layar asli."""
import importlib.util, sys, types, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond); failed += (not cond)


def muat(pyautogui_ada):
    if pyautogui_ada:
        sys.modules["pyautogui"] = types.ModuleType("pyautogui")
    else:
        sys.modules["pyautogui"] = None          # import pyautogui -> ImportError (meniru tidak terpasang)
    spec = importlib.util.spec_from_file_location("V7_f32", ROOT / "V7SATU.py")
    M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
    M.time = types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time)
    return M


print("== F3.2: tanpa pyautogui ==")
M = muat(False)
check("modul tetap termuat tanpa pyautogui", M.pyautogui is None)


class Drv:
    def find_elements(self, by, value): return []


with tempfile.TemporaryDirectory() as d:
    img = Path(d) / "ok.png"; img.write_bytes(b"x")
    M.CFG["features"]["popup_press_enter"] = True       # bahkan dengan Enter aktif: tidak boleh crash
    r = M.klik_tombol_oke_popup(image_path=str(img), max_wait=2, drv=Drv())
    check("popup tak ada + tanpa pyautogui -> False, tanpa crash", r is False, r)

    class Btn:
        def is_displayed(self): return True
    class DrvOk:
        def find_elements(self, by, value): return [Btn()] if "swal2-confirm" in value else []
    klik = []
    M.safe_click = lambda drv, el: klik.append(el)
    check("popup web (swal) tetap diklik lewat Selenium tanpa pyautogui",
          M.klik_tombol_oke_popup(image_path=str(img), max_wait=2, drv=DrvOk()) is True and len(klik) == 1)

print("== F3.3: profil Chrome tetap ==")
from selenium.webdriver.chrome.options import Options
M = muat(True)
M.CFG["chrome"] = {"profile_dir": ""}
o = Options(); M._terapkan_opsi_anti_popup(o)
check("profile_dir kosong -> perilaku lama (tanpa --user-data-dir)", not any("user-data-dir" in a for a in o.arguments), o.arguments)
check("opsi anti-popup password tetap ada", "--disable-save-password-bubble" in o.arguments)
with tempfile.TemporaryDirectory() as d:
    M.CFG["chrome"] = {"profile_dir": str(Path(d) / "prof")}
    o = Options(); M._terapkan_opsi_anti_popup(o)
    check("profile_dir diisi -> --user-data-dir + Default + folder dibuat",
          f"--user-data-dir={Path(d) / 'prof'}" in o.arguments and "--profile-directory=Default" in o.arguments and (Path(d) / "prof").is_dir(), o.arguments)
    M.CFG["chrome"] = {"profile_dir": "chrome_profile_uji"}
    check("path relatif dihitung dari folder proyek", M._profil_chrome_dir() == ROOT / "chrome_profile_uji")

print("== F3.3: login memakai explicit wait ==")
M = muat(True)


class Elem:
    def __init__(self): self.keys = []
    def send_keys(self, k): self.keys.append(k)
    def clear(self): pass


class DrvLogin:
    """Meniru web: bila sesi tersimpan, /login langsung diarahkan ke /dashboard."""
    def __init__(self, sesi_tersimpan):
        self.sesi = sesi_tersimpan; self.current_url = ""; self.urls = []; self.logged = False
    def get(self, url):
        self.urls.append(url)
        self.current_url = ("https://bmkgsatu.bmkg.go.id/dashboard" if (self.sesi or self.logged) and url.endswith("/login") else url)
    def find_elements(self, by, value):
        if value in ("login-email", "login-password") and "/login" in self.current_url: return [Elem()]
        return []
    def find_element(self, by, value):
        if value in ("login-email", "login-password") and "/login" in self.current_url:
            e = Elem(); self.dipakai.append((value, e)); return e
        raise Exception("tidak ada " + value)
    dipakai = []
    def execute_script(self, *a, **k): pass


M.WebDriverWait = lambda drv, t: types.SimpleNamespace(until=lambda fn: fn(drv) or (_ for _ in ()).throw(M.TimeoutException("x")))
M._buka_sinoptik = lambda drv: drv.urls.append("SINOPTIK")
d1 = DrvLogin(True); M.login(d1)
check("sesi tersimpan: login dilewati, langsung ke sinoptik", d1.urls == ["https://bmkgsatu.bmkg.go.id/login", "SINOPTIK"], d1.urls)



class DrvNormal:
    """Tanpa sesi tersimpan: /login menampilkan form; ENTER di kolom password -> dashboard."""
    def __init__(self): self.current_url = ""; self.urls = []; self.diisi = {}
    def get(self, url): self.urls.append(url); self.current_url = url
    def _el(self, id_):
        drv = self
        class E:
            def send_keys(self, k):
                if k == M.Keys.RETURN: drv.current_url = "https://bmkgsatu.bmkg.go.id/dashboard"
                else: drv.diisi[id_] = k
            def clear(self): pass
        return E()
    def find_elements(self, by, value): return [self._el(value)] if value in ("login-email", "login-password") and "/login" in self.current_url else []
    def find_element(self, by, value):
        r = self.find_elements(by, value)
        if not r: raise Exception("tidak ada " + value)
        return r[0]
    def execute_script(self, *a, **k): pass


d2 = DrvNormal(); M.login(d2)
check("tanpa sesi: email+password diisi, ENTER, lalu ke sinoptik (tanpa sleep tetap)",
      set(d2.diisi) == {"login-email", "login-password"} and d2.urls[-1] == "SINOPTIK", (d2.diisi, d2.urls))

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
