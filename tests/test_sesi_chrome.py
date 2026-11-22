# -*- coding: utf-8 -*-
"""
Rev 28 - (1) login() memuat kredensial sendiri (bug jelajah: send_keys(None)), (2) Chrome dibuka dengan tangguh
(profil terkunci / Chrome terbuka tapi tidak ke BMKG Satu), (3) sesi BMKG Satu yang habis sendiri ditangani.
Tanpa browser/jaringan asli:   python tests/test_sesi_chrome.py
"""
import importlib.util
import sys
import time as _t
import types
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules["pyautogui"] = None            # tak perlu layar

passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


def muat():
    spec = importlib.util.spec_from_file_location("V7_rev28", ROOT / "V7SATU.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    M.time = types.SimpleNamespace(sleep=lambda s: None, time=_t.time)
    M.WebDriverWait = lambda drv, t: types.SimpleNamespace(
        until=lambda fn: fn(drv) or (_ for _ in ()).throw(M.TimeoutException("x")))
    M._buka_sinoptik = lambda drv: drv.urls.append("SINOPTIK")
    return M


LOGIN = "https://bmkgsatu.bmkg.go.id/login"
DASH = "https://bmkgsatu.bmkg.go.id/dashboard"


class DrvForm:
    """Tanpa sesi: /login menampilkan form; ENTER di kolom password -> dashboard."""
    def __init__(self, M):
        self.M, self.current_url, self.urls, self.diisi = M, "", [], {}

    def get(self, url):
        self.urls.append(url)
        self.current_url = url

    def _el(self, id_):
        drv = self

        class E:
            def send_keys(s, k):
                if k == drv.M.Keys.RETURN:
                    drv.current_url = DASH
                else:
                    drv.diisi[id_] = k
            def clear(s): pass
        return E()

    def find_elements(self, by, value):
        return [self._el(value)] if value in ("login-email", "login-password") and "/login" in self.current_url else []

    def find_element(self, by, value):
        r = self.find_elements(by, value)
        if not r:
            raise Exception("tidak ada " + value)
        return r[0]

    def execute_script(self, *a, **k): pass


# ---------------------------------------------------------------------------------------------------------------
print("== bug jelajah: login() dipanggil langsung tanpa main() ==")
M = muat()
M.STATION_ID = M.PASSWORD = None                      # keadaan saat tools/pantau_web.py memanggil login()
M.get_credentials = lambda interactive=True: ("96195", "rahasia")
d = DrvForm(M)
M.login(d)
check("kredensial dimuat otomatis (bukan None) dan dikirim ke kolom email", d.diisi.get("login-email") == "96195", d.diisi)
check("password juga terisi", d.diisi.get("login-password") == "rahasia", d.diisi)
M2 = muat()
M2.STATION_ID = M2.PASSWORD = None
M2.get_credentials = lambda interactive=True: ("", "")
try:
    M2.login(DrvForm(M2))
    ok = False
except RuntimeError as e:
    ok = "Kredensial kosong" in str(e)
check("kredensial kosong -> pesan jelas, bukan 'NoneType is not iterable'", ok)

print("== login: coba ulang bila gagal ==")
M = muat()
M.STATION_ID, M.PASSWORD = "id", "pw"
panggil = []
def sekali(drv):
    panggil.append(1)
    if len(panggil) == 1:
        raise TimeoutError("form belum siap")
M._login_sekali = sekali
d = DrvForm(M)
M.login(d)
check("percobaan 1 gagal, percobaan 2 berhasil -> lanjut ke sinoptik", len(panggil) == 2 and d.urls[-1] == "SINOPTIK", (panggil, d.urls))
panggil.clear()
M._login_sekali = lambda drv: (_ for _ in ()).throw(TimeoutError("selalu gagal"))
try:
    M.login(DrvForm(M)); ok = False
except TimeoutError:
    ok = True
check("gagal di semua percobaan -> galat dilempar (recovery/pemanggil yang memutuskan)", ok)
check("sesi terbukti hidup dicatat setelah login berhasil", (lambda m: (setattr(m, "_login_sekali", lambda drv: None), setattr(m, "SESI_TERAKHIR_OK", 0.0),
      m.login(DrvForm(m)), m.SESI_TERAKHIR_OK > 0)[-1])(M))

# ---------------------------------------------------------------------------------------------------------------
print("== _navigasi_aman: Chrome terbuka tetapi tidak menuju BMKG Satu ==")
M = muat()


class DrvTersasar:
    """driver.get() tidak berpengaruh (tetap about:blank) pada n percobaan pertama; window.location bisa menolong."""
    def __init__(self, get_gagal, js_ok):
        self.current_url, self.get_gagal, self.js_ok, self.js = "about:blank", get_gagal, js_ok, 0
    def get(self, url):
        if self.get_gagal > 0:
            self.get_gagal -= 1
            return
        self.current_url = url
    def execute_script(self, js, *a):
        if "location.href" in js:
            self.js += 1
            if self.js_ok:
                self.current_url = a[0]


d = DrvTersasar(get_gagal=1, js_ok=False)
check("get() pertama tersasar, get() kedua berhasil -> True", M._navigasi_aman(d, LOGIN) is True and "bmkgsatu" in d.current_url)
d = DrvTersasar(get_gagal=99, js_ok=True)
check("get() tak berpengaruh tetapi window.location berhasil -> True", M._navigasi_aman(d, LOGIN) is True and d.js >= 1, d.js)
d = DrvTersasar(get_gagal=99, js_ok=False)
try:
    M._navigasi_aman(d, LOGIN, percobaan=2); ok = False
except RuntimeError as e:
    ok = "tidak berhasil membuka" in str(e)
check("selalu tersasar -> RuntimeError jelas (tidak diam-diam lanjut ke login)", ok)


class DrvLambat:
    current_url = "about:blank"
    def get(self, url):
        self.current_url = url
        raise M.TimeoutException("page load timeout")
    def execute_script(self, *a): pass


check("get() timeout tetapi URL sudah benar -> dianggap berhasil", M._navigasi_aman(DrvLambat(), LOGIN) is True)

print("== _jendela_aktif: tab sisa profil ditutup ==")
log = []


class DrvTab:
    window_handles = ["a", "b", "c"]
    class switch_to:
        pass
    def __init__(self):
        outer = self
        class SW:
            def window(s, h): log.append(("sw", h)); outer.sekarang = h
        self.switch_to = SW()
    def close(self): log.append(("close", self.sekarang))


M._jendela_aktif(DrvTab())
check("tab b dan c ditutup, jendela a dipakai", [x for x in log if x[0] == "close"] == [("close", "b"), ("close", "c")] and log[-1] == ("sw", "a"), log)

# ---------------------------------------------------------------------------------------------------------------
print("== buat_driver: coba ulang, bebaskan profil, cadangan profil sementara ==")


def pasang_chrome(M, gagal_bila):
    """Chrome palsu. gagal_bila(opts, no) -> True bila pembukaan harus gagal (melempar). Mengembalikan catatan."""
    cat = {"opts": [], "bebas": 0, "quit": 0, "n": 0}

    class FakeChrome:
        def __init__(s, service=None, options=None):
            cat["n"] += 1
            cat["opts"].append(options)
            if gagal_bila(options, cat["n"]):
                raise M.WebDriverException("session not created: DevToolsActivePort file doesn't exist")
            s.current_url = "about:blank"
        def set_page_load_timeout(s, x): pass
        def get(s, url): s.current_url = url
        def execute_script(s, *a): pass
        def quit(s): cat["quit"] += 1

    M.webdriver = types.SimpleNamespace(Chrome=FakeChrome)
    M.Service = lambda: None
    M._bebaskan_profil = lambda folder: cat.__setitem__("bebas", cat["bebas"] + 1)
    return cat


def punya_profil(o):
    return any(a.startswith("--user-data-dir=") for a in o.arguments)


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    M = muat()
    M.CFG["chrome"] = {"profile_dir": "", "retry_buka": 3, "fallback_profil_sementara": True}
    cat = pasang_chrome(M, lambda o, n: False)
    drv = M.buat_driver()
    check("tanpa profil: sekali buka, langsung ke BMKG Satu, tidak ada pembebasan profil",
          cat["n"] == 1 and "bmkgsatu" in drv.current_url and cat["bebas"] == 0, cat["n"])

    M = muat()
    M.CFG["chrome"] = {"profile_dir": str(Path(tmp) / "prof"), "retry_buka": 3, "fallback_profil_sementara": True}
    cat = pasang_chrome(M, lambda o, n: n == 1)
    drv = M.buat_driver()
    check("profil terkunci pada percobaan 1 -> profil DIBEBASKAN lalu berhasil dengan profil yang sama",
          cat["n"] == 2 and cat["bebas"] == 1 and punya_profil(cat["opts"][-1]), (cat["n"], cat["bebas"]))

    M = muat()
    M.CFG["chrome"] = {"profile_dir": str(Path(tmp) / "prof"), "retry_buka": 2, "fallback_profil_sementara": True}
    cat = pasang_chrome(M, lambda o, n: punya_profil(o))
    drv = M.buat_driver()
    check("profil gagal terus -> cadangan: profil SEMENTARA (tanpa --user-data-dir)",
          cat["n"] == 3 and not punya_profil(cat["opts"][-1]) and "bmkgsatu" in drv.current_url, cat["n"])

    M = muat()
    M.CFG["chrome"] = {"profile_dir": str(Path(tmp) / "prof"), "retry_buka": 2, "fallback_profil_sementara": False}
    cat = pasang_chrome(M, lambda o, n: punya_profil(o))
    try:
        M.buat_driver(); ok = False
    except RuntimeError as e:
        ok = "tidak bisa dibuka" in str(e)
    check("fallback dimatikan -> RuntimeError (tidak diam-diam memakai profil lain)", ok and cat["n"] == 2, cat["n"])

    # Chrome terbuka tetapi tidak pernah sampai ke BMKG Satu (get() tak berpengaruh) -> dianggap gagal, Chrome ditutup
    M = muat()
    M.CFG["chrome"] = {"profile_dir": "", "retry_buka": 2, "fallback_profil_sementara": True}
    cat = pasang_chrome(M, lambda o, n: False)
    M.webdriver.Chrome.get = lambda s, url: None
    try:
        M.buat_driver(); ok = False
    except RuntimeError:
        ok = True
    check("Chrome terbuka tapi tak menuju link -> gagal, browser ditutup tiap percobaan, lalu RuntimeError",
          ok and cat["quit"] == 2, (ok, cat["quit"]))

    print("== recover_session memakai pembukaan yang sama ==")
    M = muat()
    M.CFG["chrome"] = {"profile_dir": "", "retry_buka": 1, "fallback_profil_sementara": True}
    M.STATION_ID, M.PASSWORD = "id", "pw"
    dibuat = []
    M.buat_driver = lambda: (dibuat.append(1), DrvForm(M))[1]
    M.login = lambda drv: None
    M.klik_tombol_oke_popup = lambda *a, **k: True
    M.memilih_stasiun = lambda drv: None
    M.memilih_tanggal = lambda drv, t=None: True
    lama = types.SimpleNamespace(quit=lambda: None)
    baru, ok = M.recover_session(lama, tanggal_utc="2026-11-22")
    check("recover_session -> buat_driver() dipakai dan berhasil", ok and baru is not None and dibuat == [1], (ok, dibuat))

print("== _matikan_proses_profil: hanya Chrome yang memakai profil bot ==")
M = muat()
mati = []


class P:
    def __init__(self, nama, cmd):
        self.info = {"name": nama, "cmdline": cmd}
    def kill(self): mati.append(self.info["cmdline"][0])


folder = Path(tempfile.gettempdir()) / "chrome_profile_uji28"
fake_psutil = types.ModuleType("psutil")
fake_psutil.process_iter = lambda attrs=None: [
    P("chrome.exe", ["bot1", f"--user-data-dir={folder}"]),
    P("chrome.exe", ["harian", "--user-data-dir=C:/Users/x/Chrome/User Data"]),
    P("chromedriver.exe", ["drv", "--port=1"]),
    P("notepad.exe", ["np", str(folder)]),
]
sys.modules["psutil"] = fake_psutil
n = M._matikan_proses_profil(folder)
del sys.modules["psutil"]
check("hanya chrome bot yang ditutup (Chrome harian, chromedriver, proses lain tidak)", n == 1 and mati == ["bot1"], (n, mati))

# ---------------------------------------------------------------------------------------------------------------
print("== deteksi & pemulihan sesi yang logout sendiri ==")
M = muat()


class DrvURL:
    def __init__(self, url, login_form=False, galat=False):
        self._u, self.lf, self.galat = url, login_form, galat
    @property
    def current_url(self):
        if self.galat:
            raise RuntimeError("browser mati")
        return self._u
    def find_elements(self, by, value):
        return [object()] if (self.lf and value == "login-email") else []


check("di halaman /login -> sesi_habis True", M.sesi_habis(DrvURL(LOGIN)) is True)
check("di dalam BMKG Satu -> sesi_habis False", M.sesi_habis(DrvURL("https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik")) is False)
check("URL tak berubah tapi kolom login muncul -> True", M.sesi_habis(DrvURL("https://bmkgsatu.bmkg.go.id/x", login_form=True)) is True)
check("browser mati -> None (tidak dianggap ter-logout)", M.sesi_habis(DrvURL("x", galat=True)) is None)

print("-- segarkan_sesi: urutan login -> popup -> stasiun --")
urut = []
M.login = lambda drv: urut.append("login")
M.klik_tombol_oke_popup = lambda *a, **k: urut.append("popup")
M.memilih_stasiun = lambda drv: urut.append("stasiun")
r = M.segarkan_sesi(DrvURL(LOGIN))
check("ter-logout -> login ulang, popup, stasiun; mengembalikan True", urut == ["login", "popup", "stasiun"] and r is True, (urut, r))
urut.clear()
r = M.segarkan_sesi(DrvURL("https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik"))
check("masih masuk -> tetap melewati login() (web yang memutuskan), mengembalikan False", urut[0] == "login" and r is False, (urut, r))

print("-- pastikan_sesi --")


class Notif:
    def __init__(self): self.pesan, self.rec = [], []
    def kirim(self, t, jenis): self.pesan.append((t, jenis))
    def recovery(self, slot, ok): self.rec.append((slot, ok))


SLOT = ("2026-11-22", "06:00")
M.driver = DrvURL(LOGIN)
panggil = []
M.segarkan_sesi = lambda drv: (panggil.append(1), True)[1]
n = Notif()
M.SESI_TERAKHIR_OK = _t.time()
check("sesi terbukti hidup < 10 menit lalu -> dilewati (tanpa reload)", M.pastikan_sesi(n, SLOT) == (True, False) and not panggil)
M.SESI_TERAKHIR_OK = _t.time() - 3600
r = M.pastikan_sesi(n, SLOT)
check("sesi lama tak dipastikan (1 jam) -> diperiksa; dimuat ulang", r == (True, True) and len(panggil) == 1, (r, panggil))
check("ter-logout lalu pulih otomatis -> notifikasi Telegram terkirim", len(n.pesan) == 1 and "habis sendiri" in n.pesan[0][0], n.pesan)
M.CFG["session"]["aktif"] = False
check("session.aktif=false -> tidak melakukan apa pun", M.pastikan_sesi(n, SLOT, paksa=True) == (True, False))
M.CFG["session"]["aktif"] = True

print("-- pastikan_sesi: pemeriksaan gagal -> browser baru --")
M.SESI_TERAKHIR_OK = 0.0
M.segarkan_sesi = lambda drv: (_ for _ in ()).throw(RuntimeError("Chrome mati"))
M.save_debug_snapshot = lambda drv, tag="x": None
baru_drv = DrvURL(DASH)
direcover = []
M.recover_session = lambda cur, max_attempts=3, tanggal_utc=None: (direcover.append(tanggal_utc), (baru_drv, True))[1]
n = Notif()
r = M.pastikan_sesi(n, SLOT)
check("recover_session dipanggil dengan tanggal slot; driver global diganti", r == (True, True) and direcover == ["2026-11-22"] and M.driver is baru_drv, (r, direcover))
check("hasil recovery diberitahukan lewat notifier", n.rec == [(SLOT, True)], n.rec)

print("== tools/pantau_web.py: jalur jelajah memuat kredensial sebelum membuka Chrome ==")
_sp = importlib.util.spec_from_file_location("pantau_web28", ROOT / "tools" / "pantau_web.py")
pw = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(pw)
urutan = []


def _chrome_gagal():
    urutan.append("chrome")
    raise RuntimeError("stop")


V = types.SimpleNamespace(_muat_kredensial=lambda: urutan.append("kredensial"), buat_driver=_chrome_gagal,
                          _profil_chrome_dir=lambda: None)
try:
    pw.mode_jelajah(V, types.SimpleNamespace(info={}), types.SimpleNamespace(tanggal=None, jam="00:00"))
except RuntimeError:
    pass
check("kredensial dimuat SEBELUM Chrome dibuka", urutan == ["kredensial", "chrome"], urutan)

print("== konfigurasi bawaan rev 28 ==")
from core.config import load_config
C = load_config()
check("chrome.retry_buka & fallback_profil_sementara tersedia", C["chrome"]["retry_buka"] >= 1 and C["chrome"]["fallback_profil_sementara"] is True)
check("session.cek_sebelum_detik & cek_ulang_menit tersedia", C["session"]["cek_sebelum_detik"] > 0 and C["session"]["cek_ulang_menit"] > 0)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
