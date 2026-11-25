"""
V7SATU.py  -  SYNOP otomatis ke BMKGSoft v2  (turunan V6SATU.py)

PERUBAHAN dari V6SATU (SEMUA fungsi V6 dipertahankan; penambahan ditandai [F1.x]):
  [F1.1] Kredensial dari .env, path & pengaturan dari config.yaml (tidak ada password di kode)
  [F1.3] Excel divalidasi (core/validator.py) saat start dan sebelum tiap baris dikirim;
         baris ber-ERROR dilewati dan dicatat
  [F1.4/F1.5] Log status per slot (core/db.py): sent tidak dikirim ulang; gagal/dilewati tercatat;
         tanggal web dipilih PER SLOT (UTC) sehingga tidak basi saat melewati pergantian hari
  [F1.5/T21] Tombol "Send & Update" dikenali bila data jam itu sudah ada di web
  [F1.6] Launcher: pilih observer dari daftar (tidak mengetik di terminal)
  [F1.7] Mode dry-run: isi form sampai Preview, simpan sandi, TIDAK mengirim
  [F1.8] Override curah hujan (kolom hujan_override_aktif / hujan_override_mm)
  [F1.9] isi_data: total tutupan 0 / 9 / "/" melewati awan; vertical visibility saat total 9;
         CL/CM/CH berkode 0 atau "/" dilewati; puncak awan rendah tidak diisi bila CL=1

Cara pakai (di folder proyek):
    python V7SATU.py                       # launcher observer, kirim sungguhan
    python V7SATU.py --dry-run             # uji: sampai Preview saja
    python V7SATU.py --observer "Nama" --no-gui
    python V7SATU.py --check-only          # hanya validasi Excel, tanpa browser
"""
from core import health as _health
from core import status as _status
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (StaleElementReferenceException, TimeoutException, WebDriverException,
                                        InvalidSessionIdException, NoSuchWindowException)
from datetime import datetime, timezone, timedelta
import time
import pandas as pd
try:
    import pyautogui   # [F3.2] OPSIONAL: hanya dipakai sebagai cadangan klik gambar/Enter; bot tetap jalan tanpanya
except Exception:      # tidak terpasang / tidak ada layar -> fitur cadangan dinonaktifkan, bukan crash
    pyautogui = None
import os
import traceback
import argparse
import json
import re
import sys
import subprocess
from urllib.parse import urlparse
from pathlib import Path

# [F1.x] modul proyek: konfigurasi, validator, log status
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core.paths import ROOT, BUNDLE  # noqa: E402  [rev 36] mode .exe: ROOT = folder tulis di samping program; BUNDLE = sumber daya terkemas
from core.config import load_config, resolve_path, get_credentials  # noqa: E402
from core.fields import FIELDS, TOMBOL_KIRIM  # noqa: E402   [F3.1] peta field sebagai data
from core.validator import Validator, load_excel, format_report  # noqa: E402
from core.db import SendLog, TANDA_CEK_MANUAL  # noqa: E402
from core.notify import Notifier  # noqa: E402   [F3.7] notifikasi Telegram
from core.obsdb import ObsStore  # noqa: E402   [F2.7] data dari form web
from core.synop_check import verifikasi as verifikasi_sandi, format_hasil as format_hasil_sandi  # noqa: E402

# 🔑 Data login dan pilihan  [F1.1: tidak ada kredensial di kode; dibaca dari .env / config.yaml]
CFG = load_config()
STATION_ID = None        # diisi di main() dari .env
PASSWORD = None          # diisi di main() dari .env
STASIUN_YANG_DIPILIH = CFG["station"]["name"]
nama_observer = None     # diisi di main() lewat launcher (F1.6) atau --observer
DRY_RUN = bool(CFG["features"].get("dry_run", False))   # [F1.7]
EXCEL_PATH = resolve_path(CFG, "excel")
SNAPSHOT_DIR = resolve_path(CFG, "snapshots")
OK_IMAGE_PATH = str(resolve_path(CFG, "ok_image"))

# [speed] pengaturan kecepatan (opsional di config.yaml, bagian 'speed:')
_SPEED = CFG.get("speed", {}) or {}
SPEED_SCALE = float(_SPEED.get("scale", 0.5))                 # 1.0 = jeda asli V6; 0.5 = setengahnya
_T_OPSI = float(_SPEED.get("optional_timeout", 3))            # batas tunggu field OPSIONAL (V6: 5 detik)
SNAPSHOT_OPTIONAL = bool(_SPEED.get("snapshot_optional", False))   # snapshot saat field opsional gagal
GAGAL_OPSIONAL = []   # field opsional yang gagal diisi pada baris berjalan (dicatat ke log)
GAGAL_WAJIB = []      # [rev 14] field WAJIB (Jenis/Jumlah/Arah dst.) yang gagal: pengisian tetap DILANJUTKAN, baris dibatalkan di akhir


def _terapkan_opsi_anti_popup(opts, pakai_profil=True):
    # [F1.1] Popup "Change your password" (Google Password Manager: password ditemukan di data breach)
    # adalah JENDELA CHROME, bukan bagian halaman web -> tidak terlihat Selenium/snapshot dan gambar
    # ok.PNG mudah meleset karena skala layar. Cara andal: cegah munculnya.
    opts.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.password_manager_leak_detection": False,
    })
    # [rev 29] Windows menurunkan prioritas render/timer jendela yang tertutup jendela lain (mis. saat bot jalan di belakang VS Code):
    # halaman Vue/Ant Design jadi lambat merespons, tiap kolom 1-3 dtk. Flag di bawah mematikan penurunan itu (chrome.anti_throttle).
    anti = bool((CFG.get("chrome", {}) or {}).get("anti_throttle", True))
    fitur = "PasswordLeakDetection,PasswordCheck" + (",CalculateNativeWinOcclusion" if anti else "")
    opts.add_argument(f"--disable-features={fitur}")
    if anti:
        opts.add_argument("--disable-background-timer-throttling")
        opts.add_argument("--disable-renderer-backgrounding")
        opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-save-password-bubble")
    opts.add_argument("--disable-notifications")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    # [F3.3] Profil Chrome TETAP (opsional; config.yaml -> chrome.profile_dir). Kosong = perilaku lama (profil sementara).
    # [rev 28] cegah Chrome memulihkan tab lama / menampilkan halaman sambutan (penyebab "Chrome terbuka tapi tidak ke BMKG Satu")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-session-crashed-bubble")
    folder = _profil_chrome_dir() if pakai_profil else None
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
        opts.add_argument(f"--user-data-dir={folder}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--hide-crash-restore-bubble")


def _profil_chrome_dir():
    """[F3.3] Folder profil Chrome khusus bot (BUKAN profil Chrome harian Anda), atau None bila fitur nonaktif."""
    p = str((CFG.get("chrome", {}) or {}).get("profile_dir", "") or "").strip()
    if not p:
        return None
    folder = Path(p)
    return folder if folder.is_absolute() else ROOT / folder


# ============================================================================================================
#  [rev 28] Chrome tangguh: buka + pastikan benar-benar menuju BMKG Satu, bebaskan profil yang terkunci,
#           cadangan profil sementara. (Keluhan: kadang Chrome terbuka tetapi kosong / tidak ke link BMKG Satu.)
# ============================================================================================================
def _cfg_chrome():
    return CFG.get("chrome", {}) or {}


def _opsi_chrome_baru(pakai_profil=True):
    """Opsi Chrome siap pakai (dipakai buat_driver & recover_session)."""
    o = Options()
    o.add_argument("--start-maximized")
    _terapkan_opsi_anti_popup(o, pakai_profil=pakai_profil)
    return o


def _matikan_proses_profil(folder):
    """Tutup proses chrome.exe yang MASIH memakai folder profil bot ini (sisa run sebelumnya / crash). Mengembalikan jumlahnya.
    Hanya proses yang baris perintahnya memuat folder profil bot; Chrome harian Anda tidak disentuh."""
    kunci = str(Path(folder).resolve()).lower()
    jumlah = 0
    try:
        import psutil
    except ImportError:
        psutil = None
    try:
        if psutil is not None:
            for pr in psutil.process_iter(["name", "cmdline"]):
                try:
                    if "chrome" not in (pr.info.get("name") or "").lower():
                        continue
                    if kunci in " ".join(pr.info.get("cmdline") or []).lower():
                        pr.kill()
                        jumlah += 1
                except Exception:
                    continue
        elif os.name == "nt":
            ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                  "Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains('" + kunci.replace("'", "''") + "') } | "
                  "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=25)
            jumlah = len([x for x in (r.stdout or "").split() if x.strip().isdigit()])
    except Exception as e:
        print(f"⚠️ Gagal memeriksa proses Chrome yatim: {type(e).__name__}: {e}")
    return jumlah


def _bebaskan_profil(folder):
    """Bebaskan profil bot: tutup Chrome yatim lalu hapus berkas kunci sisa."""
    n = _matikan_proses_profil(folder)
    print(f"🧹 Membebaskan profil Chrome bot ({n} proses Chrome yatim ditutup)")
    time.sleep(1.5)
    for nama in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        f = Path(folder) / nama
        try:
            if f.exists() or f.is_symlink():
                f.unlink()
        except OSError:
            pass


def _jendela_aktif(driver):
    """Profil tetap bisa memulihkan tab lama; pakai SATU jendela saja agar driver tidak mengendalikan tab yang salah."""
    try:
        h = list(driver.window_handles)
    except Exception:
        return
    for x in h[1:]:
        try:
            driver.switch_to.window(x)
            driver.close()
        except Exception:
            pass
    try:
        driver.switch_to.window(h[0])
    except Exception:
        pass


def _navigasi_aman(driver, url, percobaan=3):
    """Buka url dan PASTIKAN browser benar-benar sampai ke situsnya (bukan about:blank/halaman sambutan Chrome).
    Urutan: driver.get -> bila macet/tersasar: hentikan muat -> window.location -> ulangi. Gagal semua -> RuntimeError."""
    host = urlparse(url).netloc
    for ke in range(1, percobaan + 1):
        _jendela_aktif(driver)
        try:
            driver.get(url)
        except TimeoutException:
            print(f"⚠️ Halaman {host} lambat dimuat (percobaan {ke}/{percobaan}); memuat dihentikan lalu diperiksa")
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
        except WebDriverException as e:
            print(f"⚠️ driver.get gagal (percobaan {ke}/{percobaan}): {type(e).__name__}: {str(e)[:120]}")
        try:
            sekarang = driver.current_url or ""
        except Exception:
            sekarang = ""
        if host in sekarang:
            return True
        print(f"⚠️ Chrome terbuka tetapi belum di {host} (sekarang: {sekarang[:70]!r}); mencoba lagi {ke}/{percobaan}")
        try:
            driver.execute_script("window.location.href = arguments[0];", url)
        except Exception:
            pass
        time.sleep(3)
        try:
            if host in (driver.current_url or ""):
                return True
        except Exception:
            pass
    raise RuntimeError(f"Chrome tidak berhasil membuka {url} setelah {percobaan} percobaan")


def _muat_kredensial():
    """Isi STATION_ID/PASSWORD dari .env bila belum (sebelumnya hanya diisi di main(), sehingga alat lain yang
    memanggil login() langsung -- mis. tools/pantau_web.py -- mengirim None ke kolom email)."""
    global STATION_ID, PASSWORD
    if not STATION_ID or not PASSWORD:
        STATION_ID, PASSWORD = get_credentials()
    if not STATION_ID or not PASSWORD:
        raise RuntimeError("Kredensial kosong: isi BMKG_STATION_ID dan BMKG_PASSWORD di file .env")
    return STATION_ID, PASSWORD


# === BACA DATA (Excel atau database form web) ===
SUMBER_DATA = str(CFG["features"].get("data_source", "excel")).lower()   # [F2.7] "excel" | "db"
_OBS_STORE = None


def _obs_store():
    """[F2.7] penyimpanan observasi yang diisi lewat form web (app.py)."""
    global _OBS_STORE
    if _OBS_STORE is None:
        _OBS_STORE = ObsStore(resolve_path(CFG, "db"), tz_hours=CFG["runtime"]["timezone_offset_hours"],
                              menit_sebelum=int((CFG.get("web", {}) or {}).get("menit_sebelum", 2)))
    return _OBS_STORE


def _kunci_baris(row):
    """Kunci slot (tanggal UTC, jam UTC) sebuah baris; stabil walau baris lain disisipkan/dihapus."""
    try:
        w = pd.to_datetime(row["waktu_eksekusi"]).to_pydatetime()
    except Exception:
        return None
    utc = w - timedelta(hours=CFG["runtime"]["timezone_offset_hours"])
    n = (utc + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    return (n.strftime("%Y-%m-%d"), f"{n.hour:02d}:00")


def _posisi(df, kunci, index):
    """
    [F2.7] Posisi baris dengan slot `kunci` di df. Mode DB: hanya berdasarkan slot (pengamat bisa menambah
    jam baru kapan saja sehingga nomor urut bergeser). Mode Excel: bila slot tidak ditemukan (waktu/jam
    diubah di Excel) dipakai nomor urut lama, seperti perilaku V6/V7.
    """
    if df is None:
        return None
    if kunci is not None:
        for pos in range(len(df)):
            if _kunci_baris(df.iloc[pos]) == kunci:
                return pos
    if SUMBER_DATA != "db" and index < len(df):
        return index
    return None


def baca_data_terbaru(silent=False):
    """Fungsi untuk membaca data terbaru (Excel, atau DB form web bila features.data_source = db)"""
    if not silent:
        print("\n🔍 Memuat data terbaru dari " + ("database (form web)..." if SUMBER_DATA == "db" else "file..."))
    try:
        if SUMBER_DATA == "db":
            now = datetime.now(timezone.utc)
            df = _obs_store().to_dataframe((now - timedelta(days=1)).strftime("%Y-%m-%d"),
                                           (now + timedelta(days=1)).strftime("%Y-%m-%d"))
        else:
            df = load_excel(EXCEL_PATH)   # [F1.1] path dari config.yaml; kolom dirapikan, baris kosong dibuang
        df['waktu_eksekusi'] = pd.to_datetime(df['waktu_eksekusi'])
        df['jam_input'] = df['jam_input'].astype(str).str.zfill(5)
        if not silent:
            print("✅ Data berhasil dimuat")
        return df
    except Exception as e:
        print(f"❌ Gagal memuat data: {str(e)}")
        return None

# 🔧 Setup driver
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
_terapkan_opsi_anti_popup(chrome_options)   # [F1.1] cegah popup password Chrome
service = Service()
driver = None   # [F1.6] browser dibuat di main() setelah launcher (lihat buat_driver)

#=============================== GENERAL ======================================#
def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    try:
        element.click()
    except:
        driver.execute_script("arguments[0].click();", element)


def wait_for_presence(driver, locator, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))
    except Exception as e:
        print(f"❌ Timeout menunggu keberadaan elemen {locator}: {e}")
        return None


def wait_for_clickable(driver, locator, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
    except Exception as e:
        print(f"❌ Timeout menunggu elemen dapat diklik {locator}: {e}")
        return None


SLOT_AKTIF = None   # [rev 30] (tanggal_utc, jam) slot yang sedang diproses; dipakai untuk menamai snapshot


def set_slot_aktif(slot):
    global SLOT_AKTIF
    SLOT_AKTIF = (slot[0], slot[1]) if slot and slot[0] else None


def _nama_snapshot(tag):
    """[rev 30] <TANGGAL>_<JAM>UTC__<keterangan>__<waktu lokal>, mis. 20261122_2200UTC__gagal-percobaan1__20261123-050117WIB.
    Slot (jam observasi UTC) ada DI DEPAN sehingga terurut per jam & langsung terlihat jam berapa yang bermasalah; waktu di
    belakang = kapan snapshot direkam (zona lokal PC)."""
    zona = "WIB" if int(CFG["runtime"].get("timezone_offset_hours", 7)) == 7 else "LOKAL"
    waktu = datetime.now().strftime("%Y%m%d-%H%M%S") + zona
    if SLOT_AKTIF and SLOT_AKTIF[0]:
        awal = f"{SLOT_AKTIF[0].replace('-', '')}_{SLOT_AKTIF[1].replace(':', '')}UTC"
    else:
        awal = "tanpa-slot"
    ket = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(tag)).strip("-") or "debug"
    return f"{awal}__{ket}__{waktu}"


def save_debug_snapshot(driver, tag="debug"):
    png = None   # [F1.4] dikembalikan agar bisa dicatat di log status
    if not SNAPSHOT_OPTIONAL and str(tag).startswith(("isi_input_", "pilih_arah_")):
        return None   # [speed] field opsional gagal tidak perlu snapshot (hemat 1-2 detik tiap kali)
    try:
        base = str(SNAPSHOT_DIR)
        os.makedirs(base, exist_ok=True)
        nama = _nama_snapshot(tag)
        png = os.path.join(base, f"{nama}.png")
        html = os.path.join(base, f"{nama}.html")
        try:
            driver.save_screenshot(png)
            print(f"📸 Screenshot saved: {png}")
        except Exception as e:
            print(f"⚠️ Gagal simpan screenshot: {e}")
        try:
            with open(html, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"📄 HTML snapshot saved: {html}")
        except Exception as e:
            print(f"⚠️ Gagal simpan page source: {e}")
    except Exception as e:
        print(f"⚠️ save_debug_snapshot error: {e}\n{traceback.format_exc()}")
    return png


def pilih_opsi_unsur(driver, unsur):
    try:
        opsi_list = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, f"//li[contains(text(), '{unsur}')]"))
        )
        if opsi_list:
            # [rev 29] XPath //li[...] bisa mengenai <li> tersembunyi (jelajah 230249: nama opsi jam 00:00 tercatat kosong);
            # utamakan yang tampak, baru cadangan elemen pertama.
            terlihat = [o for o in opsi_list if _tampak(o)]
            pilih = (terlihat or opsi_list)[0]
            safe_click(driver, pilih)
            print(f"✅ Opsi dipilih (mengandung '{unsur}'): {pilih.text}")
            return True
        print(f"❌ Tidak ada opsi mengandung '{unsur}' ditemukan")
        return False
    except Exception as e:
        print(f"❌ Gagal pilih opsi '{unsur}': {e}")
        return False


# ===================== [rev 32] JALUR CEPAT dropdown & input =====================
# Bukti dry-run 24 Nov: 104 dari 146 dtk isi_data habis di combobox Jenis/Jumlah/Arah (+-11,5 dtk/combobox) dan tiap
# dropdown berid +-2-3 dtk (mengetik teks panjang: tiap ketikan memicu render ulang halaman, +-0,7 dtk/karakter).
# Jalur cepat: buka menu -> baca SEMUA opsi dalam SATU panggilan JS -> pilih lewat KLIK opsi (tanpa mengetik) -> baca
# nilai terpilih untuk verifikasi. Bila apa pun tak cocok, fungsi mengembalikan None dan jalur LAMA (lambat tapi teruji)
# dijalankan persis seperti sebelumnya. Dimatikan lewat config.yaml: speed.fast_select: false / speed.fast_input: false.
FAST_SELECT = bool(_SPEED.get("fast_select", True))
FAST_INPUT = bool(_SPEED.get("fast_input", False))   # bawaan mati: aktifkan setelah dry-run membuktikan sandi tetap sesuai

_JS_OPSI_MENU = r"""
const n = s => (s || '').replace(/\s+/g, ' ').trim();
const m = document.getElementById(arguments[0]); if (!m) return null;
return Array.from(m.querySelectorAll('li')).map(l => [n(l.innerText || l.textContent),
        l.getAttribute('aria-disabled') === 'true', l.offsetParent !== null]);
"""
_JS_AMBIL_LI = ("var m=document.getElementById(arguments[0]); if(!m) return null;"
                "var l=m.querySelectorAll('li')[arguments[1]]; return l||null;")
_JS_NILAI_COMBO = ("var c=arguments[0]; var v=c.querySelector('.ant-select-selection-selected-value');"
                   "return v ? (v.getAttribute('title')||v.textContent||'') : '';")
_JS_KLIK_MOUSE = ("var e=arguments[0];['mousedown','mouseup','click'].forEach(function(t){"
                  "e.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window}));});")
_JS_SET_INPUT = r"""
const e = arguments[0], v = arguments[1];
e.scrollIntoView({block: 'center'}); e.focus();
Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, v);
e.dispatchEvent(new Event('input', {bubbles: true}));
e.dispatchEvent(new Event('change', {bubbles: true}));
e.blur();
return e.value;
"""


def _pilih_indeks_opsi(opsi, target):
    """opsi = [(teks, disabled, tampak)]. Prioritas: teks PERSIS > diawali target > mengandung target (hanya opsi tampak & aktif)."""
    t = " ".join(str(target).split())
    kandidat = [(i, x[0]) for i, x in enumerate(opsi) if x[2] and not x[1]]
    for cocok in (lambda s: s == t, lambda s: s.startswith(t), lambda s: t in s):
        for i, teks in kandidat:
            if cocok(teks):
                return i
    return None


def _sama_pilihan(terpilih, target):
    """Nilai yang tampil di kotak pilihan sudah sesuai target? Target berupa kode saja ('0 -') dibandingkan sebagai awalan."""
    a, b = " ".join(str(terpilih or "").split()).lower(), " ".join(str(target or "").split()).lower()
    if not a or not b:
        return False
    if b.endswith("-"):
        return a.startswith(b)
    return a == b or a.startswith(b) or b in a


def _tunggu_poll(kondisi, timeout, poll=0.04):
    """Ulangi kondisi() tiap `poll` dtk sampai hasilnya benar (dikembalikan) atau waktu habis (None). Sesi mati dilempar."""
    akhir = time.time() + timeout
    while True:
        try:
            r = kondisi()
        except (InvalidSessionIdException, NoSuchWindowException):
            raise
        except Exception:
            r = None
        if r:
            return r
        if time.time() >= akhir:
            return None
        time.sleep(poll)


def _nilai_combo(driver, combobox):
    try:
        return " ".join(str(driver.execute_script(_JS_NILAI_COMBO, combobox) or "").split())
    except (InvalidSessionIdException, NoSuchWindowException):
        raise
    except Exception:
        return ""


def _buka_combo(driver, combobox, cara):
    if cara == "klik":
        attempt_click(driver, combobox)
    elif cara == "js":
        driver.execute_script("arguments[0].click();", combobox)
    else:
        driver.execute_script(_JS_KLIK_MOUSE, combobox)


def _menu_opsi(driver, aria_id):
    o = driver.execute_script(_JS_OPSI_MENU, aria_id)
    return o if o and any(x[2] for x in o) else None


def _pilih_cepat(driver, combobox, target, nama):
    """True = terpilih & terverifikasi. None = tidak bisa lewat jalur cepat (pemanggil memakai jalur lama). Tidak pernah mengetik."""
    if not FAST_SELECT:
        return None
    t0 = time.time()
    try:
        aria_id = combobox.get_attribute("aria-controls")
        if not aria_id:
            return None
        if _sama_pilihan(_nilai_combo(driver, combobox), target):
            return True
        if not _combo_siap(driver, combobox, tunggu=1.5):
            return None
        opsi = None
        for cara in ("klik", "js", "mouse"):
            if _menu_opsi(driver, aria_id) is None:       # jangan menekan lagi bila menu SUDAH terbuka (akan menutupnya)
                _buka_combo(driver, combobox, cara)
            opsi = _tunggu_poll(lambda: _menu_opsi(driver, aria_id), 0.8)
            if opsi:
                break
        if not opsi:
            return None
        idx = _pilih_indeks_opsi(opsi, target)
        if idx is None:
            _pulihkan_ui(driver)
            return None
        li = driver.execute_script(_JS_AMBIL_LI, aria_id, idx)
        if li is None or not attempt_click(driver, li):
            _pulihkan_ui(driver)
            return None
        if _tunggu_poll(lambda: _sama_pilihan(_nilai_combo(driver, combobox), target), 1.5):
            _CEPAT_LOG.append((nama, round(time.time() - t0, 2)))
            return True
        _pulihkan_ui(driver)
        return None
    except (InvalidSessionIdException, NoSuchWindowException):
        raise
    except Exception:
        return None


_CEPAT_LOG = []   # (nama field, detik) pilihan yang berhasil lewat jalur cepat; dipakai tes/laporan


def _pilih_cepat_id(driver, id_div, nilai):
    if not FAST_SELECT:
        return None
    try:
        combo = driver.find_element(By.XPATH, f"//div[@id='{id_div}']//div[@role='combobox']")
    except (InvalidSessionIdException, NoSuchWindowException):
        raise
    except Exception:
        return None
    return _pilih_cepat(driver, combo, nilai, id_div)


def _isi_input_cepat(driver, id_input, nilai):
    """Isi kotak angka lewat SATU render ulang (bukan satu per karakter), lalu baca ulang. None = pakai jalur lama."""
    if not FAST_INPUT:
        return None
    try:
        el = driver.find_element(By.ID, id_input)
        if not el.is_enabled():
            return None
        driver.execute_script(_JS_SET_INPUT, el, str(nilai))
        def cocok():
            a = (el.get_attribute("value") or "").strip()
            return a == str(nilai) or _angka_sama(a, nilai)
        return True if _tunggu_poll(cocok, 1.0) else None
    except (InvalidSessionIdException, NoSuchWindowException):
        raise
    except Exception:
        return None


def pilih_dropdown_ant_select(driver, id_div, nilai, timeout=12, max_attempts=2):
    if _pilih_cepat_id(driver, id_div, nilai):   # [rev 32] jalur cepat (klik opsi, tanpa mengetik); gagal -> jalur lama di bawah
        print(f"✅ {id_div} dipilih dengan '{nilai}'")
        return True
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            container = wait_for_presence(driver, (By.ID, id_div), timeout=timeout)
            if not container:
                print(f"⚠️ [{attempt}] Container {id_div} tidak ditemukan")
                _jeda(0.6)
                continue
            driver.execute_script("arguments[0].scrollIntoView(true);", container)

            dropdown = wait_for_clickable(driver, (By.XPATH, f"//div[@id='{id_div}']//div[contains(@class,'ant-select-selection__rendered')]"), timeout=timeout)
            if not dropdown:
                print(f"⚠️ [{attempt}] Dropdown {id_div} tidak clickable")
                _jeda(0.6)
                continue
            safe_click(driver, dropdown)
            if not _tunggu_dropdown_terbuka(driver, id_div):   # [rev 29] eksplisit; cadangan jeda lama bila status tak terbaca
                _jeda(0.5)

            search_input = wait_for_presence(driver, (By.XPATH, f"//div[@id='{id_div}']//input[contains(@class,'ant-select-search__field')]"), timeout=timeout)
            if search_input:
                search_input.clear()
                search_input.send_keys(nilai)
                _jeda(0.3)
                search_input.send_keys(Keys.ENTER)
                _tunggu_nilai_terpilih(driver, id_div, nilai)   # [speed] ganti sleep tetap 0.8 dtk
                _jeda(0.1)
                print(f"✅ {id_div} dipilih dengan '{nilai}'")
                return True

            opsi = wait_for_clickable(driver, (By.XPATH, f"//div[@id='{id_div}']//li[contains(normalize-space(.),'{nilai}')]"), timeout=timeout)
            if opsi:
                safe_click(driver, opsi)
                print(f"✅ {id_div} dipilih dengan '{nilai}' (fallback tanpa input search)")
                _jeda(0.8)
                return True

            print(f"⚠️ [{attempt}] Tidak menemukan input atau opsi untuk {id_div} dengan nilai '{nilai}'")
            _jeda(0.6)
        except Exception as e:
            print(f"⚠️ [{attempt}] Gagal pilih {id_div} dengan '{nilai}': {e}")
            _jeda(0.6)
    try:
        save_debug_snapshot(driver, f"pilih_dropdown_{id_div}_{nilai}")
    except Exception:
        pass
    print(f"❌ Gagal pilih {id_div} dengan '{nilai}' setelah {max_attempts} percobaan")
    return False


def isi_input_text(driver, id_input, nilai, timeout=12):
    if _isi_input_cepat(driver, id_input, nilai):   # [rev 32] opsional (speed.fast_input); gagal -> jalur lama di bawah
        print(f"✅ {id_input} diisi dengan {nilai}")
        return True
    try:
        input_field = wait_for_presence(driver, (By.ID, id_input), timeout=timeout)
        if not input_field:
            return False
        driver.execute_script("arguments[0].scrollIntoView(true);", input_field)
        input_field.clear()
        input_field.send_keys(str(nilai))
        input_field.send_keys(Keys.RETURN)
        print(f"✅ {id_input} diisi dengan {nilai}")
        return True
    except Exception as e:
        print(f"❌ Gagal isi {id_input}: {e}")
        try:
            save_debug_snapshot(driver, f"isi_input_{id_input}")
        except Exception:
            pass
        return False


def attempt_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        try:
            element.click()
            return True
        except Exception:
            try:
                ActionChains(driver).move_to_element(element).pause(0.1).click().perform()
                return True
            except Exception:
                driver.execute_script("arguments[0].click();", element)
                return True
    except Exception as e:
        print(f"⚠️ attempt_click gagal: {e}")
        return False


_JS_STATE_COMBO = r"""
const c = arguments[0]; if (!c) return null;
const s = c.closest('.ant-select') || c;
const r = c.getBoundingClientRect();
const cs = window.getComputedStyle(c);
return {shown: r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none',
        disabled: s.classList.contains('ant-select-disabled') || c.getAttribute('aria-disabled') === 'true',
        cls: (s.className || '').toString().slice(0, 120), w: Math.round(r.width), h: Math.round(r.height)};
"""


def _state_combo(driver, combobox):
    try:
        return driver.execute_script(_JS_STATE_COMBO, combobox)
    except Exception:
        return None


def _diag_combobox(driver, combobox, nama_field):
    """[rev 14] Cetak keadaan combobox yang gagal (terlihat? disabled? ukuran?) agar penyebab mudah dilacak."""
    st = _state_combo(driver, combobox)
    try:
        aria = combobox.get_attribute("aria-controls")
    except Exception:
        aria = "?"
    print(f"🔬 DIAG {nama_field}: aria-controls={aria} state={st}")


def _combo_siap(driver, combobox, tunggu=4.0):
    """[rev 14] Tunggu sampai combobox TERLIHAT dan TIDAK disabled (web mengaktifkannya setelah CL/NCL dipilih)."""
    akhir = time.time() + tunggu
    while True:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", combobox)
        except Exception:
            pass
        st = _state_combo(driver, combobox)
        if st and st.get("shown") and not st.get("disabled"):
            return True
        if time.time() > akhir:
            return False
        time.sleep(0.15)


def pilih_opsi_ant_select(driver, combobox, target_teks, nama_field):
    try:
        aria_id = combobox.get_attribute("aria-controls")
    except Exception as e:
        print(f"❌ {nama_field}: elemen tidak bisa dibaca ({type(e).__name__})")
        return False
    if not aria_id:
        print(f"❌ {nama_field}: aria-controls tidak ditemukan")
        return False

    def nilai_terpilih():
        values = combobox.find_elements(
            By.CSS_SELECTOR, ".ant-select-selection-selected-value"
        )
        if not values:
            return ""
        return (values[0].get_attribute("title") or values[0].text).strip()

    if _pilih_cepat(driver, combobox, target_teks, nama_field):   # [rev 32] jalur cepat; gagal -> jalur lama di bawah
        print(f"✅ {nama_field} dipilih: {target_teks}")
        return True
    try:
        if target_teks in nilai_terpilih():
            print(f"✅ {nama_field} sudah berisi '{target_teks}'")
            return True

        # [rev 14] ElementNotInteractable sebelumnya: combobox belum aktif / tidak terlihat. Tunggu dulu,
        # dan jangan pernah memakai element.send_keys() pada elemen yang tak bisa diinteraksi.
        if not _combo_siap(driver, combobox):
            print(f"❌ {nama_field}: combobox tidak terlihat atau masih nonaktif")
            _diag_combobox(driver, combobox, nama_field)
            return False

        target_normalized = " ".join(target_teks.split())
        for attempt in range(3):
            klik_pada = combobox
            if attempt:   # [rev 31] menu percobaan sebelumnya bisa masih terbuka: tutup dulu agar klik tidak malah MENUTUPNYA
                _pulihkan_ui(driver)
            if attempt == 1:   # percobaan ke-2: klik bagian dalam (sama dengan pilih_dropdown_ant_select)
                try:
                    klik_pada = combobox.find_element(By.CSS_SELECTOR, ".ant-select-selection__rendered")
                except Exception:
                    klik_pada = combobox
            if attempt == 2:   # percobaan ke-3: klik lewat JavaScript langsung
                try:
                    driver.execute_script("arguments[0].click();", combobox)
                except Exception:
                    pass
            elif not attempt_click(driver, klik_pada):
                continue

            try:
                WebDriverWait(driver, 3).until(
                    EC.visibility_of_element_located((By.ID, aria_id))
                )
            except TimeoutException:
                if attempt == 0:
                    try:
                        ActionChains(driver).send_keys(Keys.SPACE).perform()
                    except Exception:
                        pass
                continue

            def _cari_item(d):
                # [rev 15] prioritas: teks PERSIS > diawali target > mengandung target (hindari salah pilih opsi mirip)
                items = [i for i in d.find_elements(By.XPATH, f"//div[@id='{aria_id}']//li")
                         if i.is_displayed() and i.get_attribute("aria-disabled") != "true"]
                teks = [(i, " ".join(i.text.split())) for i in items]
                for cocok in (lambda t: t == target_normalized,
                              lambda t: t.startswith(target_normalized),
                              lambda t: target_normalized in t):
                    for i, t in teks:
                        if cocok(t):
                            return i
                return False

            opsi = WebDriverWait(driver, 5).until(_cari_item)
            if attempt:   # [rev 31] kasus 22:00: menu lengkap tetapi klik biasa tak 'kena' -> klik opsi lewat JavaScript
                driver.execute_script("arguments[0].click();", opsi)
            elif not attempt_click(driver, opsi):
                continue

            WebDriverWait(driver, 3).until(
                lambda _: target_normalized in " ".join(nilai_terpilih().split())
            )
            print(f"✅ {nama_field} dipilih: {target_teks}")
            return True

        print(
            f"❌ {nama_field}: menu '{aria_id}' tidak terbuka "
            f"atau opsi '{target_teks}' tidak berhasil dipilih"
        )
        _diag_combobox(driver, combobox, nama_field)
    except Exception as e:
        print(
            f"❌ {nama_field}: gagal memilih '{target_teks}': "
            f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
        )
        _diag_combobox(driver, combobox, nama_field)
    return False


# --- [rev 14] pencarian combobox berlapis: posisi (terbukti di web asli) -> relatif ke id -> XPath lama ---
_JS_SELECT_DARI_ID = r"""
const e = document.getElementById(arguments[0]); if (!e) return null;
const k = arguments[1];
let a = e.parentElement;
while (a) {
  if (a.classList.contains('row') && a.parentElement) {
    const baris = Array.from(a.parentElement.children).filter(x => x.classList.contains('row'));
    const t = baris[baris.indexOf(a) + k];
    if (t) { const s = t.querySelector('.ant-select'); if (s && s.offsetParent !== null) return s; }
  }
  a = a.parentElement;
}
return null;
"""


def _combo_dari_select(sel):
    return sel.find_element(By.CSS_SELECTOR, "[role='combobox']") if sel is not None else None


def _kandidat_combobox(driver, section, col, row_idx, id_ref, k, xpath_lama):
    def posisi():
        return _combo_dari_select(driver.execute_script(_JS_SELECT_POSISI, section, col, row_idx))

    def dari_id():
        return _combo_dari_select(driver.execute_script(_JS_SELECT_DARI_ID, id_ref, k))

    def xpath_lama_terlihat():   # XPath lama mengambil kecocokan PERTAMA (bisa elemen tersembunyi) -> pilih yang terlihat
        for el in driver.find_elements(By.XPATH, xpath_lama):
            try:
                if el.is_displayed():
                    return el
            except Exception:
                pass
        return None

    return [("posisi", posisi), ("relatif-id", dari_id), ("xpath-lama", xpath_lama_terlihat)]


def pilih_ant_select_berlapis(driver, nama_field, target, kandidat, putaran=2):
    """Coba tiap cara mencari combobox sampai ada yang berhasil memilih opsi `target` (maks `putaran` kali)."""
    for putar in range(putaran):
        for label, fn in kandidat:
            try:
                combo = fn()
            except Exception as e:
                print(f"ℹ️ {nama_field}: cara '{label}' error {type(e).__name__}")
                continue
            if combo is None:
                print(f"ℹ️ {nama_field}: cara '{label}' tidak menemukan combobox")
                continue
            if pilih_opsi_ant_select(driver, combo, target, nama_field):
                if putar or label != kandidat[0][0]:
                    print(f"ℹ️ {nama_field}: berhasil lewat cara '{label}' (putaran {putar + 1})")
                return True
        if putar + 1 < putaran:
            _jeda(1.0)   # beri waktu web selesai me-render ulang lalu ulangi
    return False


# ===================== [F3.1 / rev 31] FUNGSI GENERIK + PERCOBAAN ULANG PER LANGKAH =====================
def _pulihkan_ui(driver):
    """Tutup menu dropdown yang menggantung & lepas fokus sebelum langkah diulang (aman: tidak mengubah nilai)."""
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        driver.execute_script("if (document.activeElement) document.activeElement.blur();")
    except Exception:
        pass


def _percobaan_field(f):
    """Jumlah percobaan per langkah: runtime.max_field_attempts (wajib), satu lebih sedikit untuk opsional."""
    n = max(1, int(CFG["runtime"].get("max_field_attempts", 3)))
    return n if f["wajib"] else max(1, n - 1)


def _ulangi(driver, nama, sekali, percobaan):
    """Jalankan sekali() (True/False) sampai berhasil, maks `percobaan` kali; antar percobaan halaman dipulihkan.
    Sesi/jendela mati TIDAK diulang di sini (dilempar ke recovery sesi di main)."""
    for ke in range(1, percobaan + 1):
        try:
            if sekali():
                if ke > 1:
                    print(f"ℹ️ {nama}: berhasil pada percobaan {ke}/{percobaan}")
                return True
        except (InvalidSessionIdException, NoSuchWindowException):
            raise
        except Exception as e:
            print(f"⚠️ {nama}: percobaan {ke}/{percobaan} galat {type(e).__name__}")
        if ke < percobaan:
            print(f"🔁 {nama}: gagal, mengulang langkah ini ({ke + 1}/{percobaan})...")
            _pulihkan_ui(driver)
            _jeda(0.8 * ke)
    return False


def _input_terisi(driver, id_input):
    """Kotak tidak kosong setelah diisi? Tak terbaca -> dianggap terisi (tidak menambah kegagalan baru)."""
    try:
        return bool(str(driver.execute_script(
            "var e=document.getElementById(arguments[0]); return e ? e.value : 'x';", id_input)).strip())
    except Exception:
        return True


def _kandidat_dari_peta(driver, f):
    c = f["cari"]
    if "xpath" in c:
        return [("xpath", lambda: WebDriverWait(driver, _T_OPSI).until(
            EC.presence_of_element_located((By.XPATH, c["xpath"]))))]
    return _kandidat_combobox(driver, c["bagian"], c["kol"], c["baris"], c["ref"], c["k"], c["xpath_lama"])


def pilih_ant_select(driver, field_id, nilai):
    """Satu pintu memilih dropdown Ant Design mana pun di peta core/fields.py, dengan percobaan ulang per langkah."""
    f = FIELDS[field_id]
    nilai = str(nilai)

    def sekali():
        if f["tipe"] == "pilih":
            return pilih_dropdown_ant_select(driver, field_id, nilai, max_attempts=1)
        return pilih_ant_select_berlapis(driver, f["nama"], nilai, _kandidat_dari_peta(driver, f), putaran=1)

    ok = _ulangi(driver, f["nama"], sekali, _percobaan_field(f))
    if f["tipe"] == "combo":
        if ok:
            _jeda(0.5)
        elif f["wajib"] or SNAPSHOT_OPTIONAL:
            try:
                save_debug_snapshot(driver, f"gagal_{field_id}_{nilai}")
            except Exception:
                pass
    return ok


def isi_input(driver, field_id, nilai):
    """Satu pintu mengisi kotak teks/angka di peta core/fields.py; gagal atau kotak tetap kosong -> diulang."""
    f = FIELDS[field_id]
    return _ulangi(driver, f["nama"],
                   lambda: isi_input_text(driver, field_id, str(nilai)) and _input_terisi(driver, field_id),
                   _percobaan_field(f))


def _isi_jenis_jumlah(driver, k_jenis, k_jumlah, jenis, jumlah, daftar=None):
    """Jenis & Jumlah dicoba TERPISAH (gagal satu tidak menghentikan yang lain); kegagalan dicatat di `daftar` bila ada."""
    hasil = []
    for k, v in ((k_jenis, jenis), (k_jumlah, jumlah)):
        ok = pilih_ant_select(driver, k, v)
        if not ok and daftar is not None:
            daftar.append(f"{FIELDS[k]['nama']} '{v}' gagal dipilih")
        hasil.append(ok)
    return all(hasil)


def click_button_by_text(driver, button_text, timeout=10, exact=False):
    normalized = button_text.strip().lower()
    if exact:
        xpath = f"//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='{normalized}']"
    else:
        xpath = f"//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{normalized}')]"
    try:
        button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        if not attempt_click(driver, button):
            raise Exception("click action gagal")
        print(f"✅ Tombol '{button_text}' berhasil diklik")
        return True
    except Exception as e:
        print(f"❌ Gagal klik tombol '{button_text}': {e}")
        return False


def wait_for_modal_to_disappear(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(
                "return document.querySelectorAll('div.swal2-container.swal2-center.swal2-backdrop-show, div.ant-modal-wrap').length === 0;"
            )
        )
        return True
    except Exception:
        return False


# ──────────────────────────── [F3.11] Pop-up "Koreksi QC" ────────────────────────────
# Web menampilkan "Koreksi QC" (SweetAlert2: judul + daftar 'Step Check' + tombol Submit / Cek Data)
# bila nilai AWS melonjak dibanding jam sebelumnya. Tanpa klik Submit data TIDAK jadi terkirim.
# Keputusan pengguna 2026-11-20: data tetap dikirim (klik Submit); kejadian dicatat + diberitahukan.
_LOW = "translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
QC_POPUP_XPATHS = [
    "//div[contains(@class,'swal2-popup')][.//*[contains(@class,'swal2-title')]"
    f"[contains({_LOW},'koreksi qc')]]",
    "//div[@role='dialog' or @role='alertdialog' or contains(@class,'ant-modal-content')]"
    f"[.//*[contains({_LOW},'koreksi qc')]]",          # cadangan bila bukan SweetAlert2
]
SWAL_POPUP_XPATH = "//div[contains(@class,'swal2-popup')]"


def _tampak(el):
    try:
        return bool(el.is_displayed())
    except Exception:
        return False


def _popup_koreksi_qc(driver):
    """Elemen popup 'Koreksi QC' yang sedang tampil, atau None."""
    for xp in QC_POPUP_XPATHS:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if _tampak(el):
                    return el
        except Exception:
            continue
    return None


def _ringkas_teks_qc(teks):
    t = re.sub(r"\s+", " ", teks or "").strip()
    t = re.sub(r"^koreksi qc\s*", "", t, flags=re.I)
    t = re.sub(r"\s*((submit|cek data)\s*)+$", "", t, flags=re.I)
    return t[:400]


def tangani_popup_koreksi_qc(driver, tunggu=0.0):
    """
    Cari popup 'Koreksi QC' (menunggu sampai `tunggu` detik) lalu klik tombol Submit DI DALAM
    popup itu (bukan tombol Submit halaman). Return dict(muncul, diklik, teks).
    Mati-kan klik otomatis dengan features.qc_popup_auto_submit=false (hanya catat + screenshot).
    """
    hasil = {"muncul": False, "diklik": False, "teks": ""}
    batas = time.time() + max(0.0, tunggu)
    while True:
        popup = _popup_koreksi_qc(driver)
        if popup is not None:
            break
        if time.time() >= batas:
            return hasil
        time.sleep(0.3)
    hasil["muncul"] = True
    try:
        hasil["teks"] = _ringkas_teks_qc(popup.text)
    except Exception:
        pass
    print(f"⚠️ Popup 'Koreksi QC' muncul: {hasil['teks']}")
    try:
        save_debug_snapshot(driver, "koreksi_qc")     # bukti: screenshot + HTML
    except Exception:
        pass
    auto = bool(CFG["features"].get("qc_popup_auto_submit", True))
    PERUBAHAN_OTOMATIS["koreksi_qc"] = (("Submit dikonfirmasi: " if auto else "BUTUH KONFIRMASI MANUAL: ")
                                        + hasil["teks"])
    if not auto:
        print("⛔ features.qc_popup_auto_submit=false: popup dibiarkan; konfirmasi manual diperlukan")
        return hasil
    try:
        tombol = [b for b in popup.find_elements(By.XPATH, f".//button[{_LOW}='submit']")
                  if _tampak(b) and b.is_enabled()]
    except Exception:
        tombol = []
    if not tombol:
        print("❌ Tombol Submit di dalam popup Koreksi QC tidak ditemukan")
        return hasil
    if not attempt_click(driver, tombol[0]):
        print("❌ Tombol Submit pada popup Koreksi QC gagal diklik")
        return hasil
    print("✅ Popup Koreksi QC: tombol Submit berhasil diklik")
    tutup = time.time() + 10
    while time.time() < tutup:                        # pastikan popup YANG TADI DIKLIK menutup
        if not _tampak(popup):                        # (popup QC berikutnya boleh langsung muncul)
            hasil["diklik"] = True
            return hasil
        time.sleep(0.3)
    print("⚠️ Popup Koreksi QC belum menutup setelah Submit")
    return hasil


def _popup_swal_lain(driver):
    """Popup SweetAlert2 lain yang tampil: (elemen, teks, apakah_galat) atau None."""
    try:
        for el in driver.find_elements(By.XPATH, SWAL_POPUP_XPATH):
            if not _tampak(el):
                continue
            teks = re.sub(r"\s+", " ", el.text or "").strip()
            galat = bool(el.find_elements(By.XPATH, ".//div[contains(@class,'swal2-icon-error')]")) or \
                any(k in teks.lower() for k in ("gagal", "error", "failed", "tidak berhasil"))
            return el, teks, galat
    except Exception:
        pass
    return None


BERHASIL_TERLIHAT = False   # [rev 30] True bila popup web berisi "berhasil" terlihat pada pemeriksaan pasca-kirim terakhir


def selesaikan_pasca_kirim(driver):
    """
    Dipanggil SETELAH tombol OK terakhir diklik: awasi popup susulan sampai layar tenang.
      - 'Koreksi QC' -> klik Submit (data BARU terkirim setelah ini)
      - popup SweetAlert lain berisi OK -> ditutup; bila isinya galat -> dianggap GAGAL
    Return (berhasil, pesan). Layar dianggap tenang bila tidak ada popup selama
    features.qc_popup_tenang detik; batas total features.qc_popup_tunggu detik.
    """
    global BERHASIL_TERLIHAT
    ft = CFG["features"]
    batas = float(ft.get("qc_popup_tunggu", 12))
    tenang = float(ft.get("qc_popup_tenang", 4))
    mulai = time.time()
    aktif_terakhir = mulai
    n_qc = 0
    n_stale = 0
    BERHASIL_TERLIHAT = False
    while True:
        try:
            h = tangani_popup_koreksi_qc(driver, tunggu=0)
            if h["muncul"]:
                n_qc += 1
                if not h["diklik"]:
                    return False, "popup Koreksi QC tidak dapat dikonfirmasi: " + h["teks"]
                if n_qc > 3:
                    return False, "popup Koreksi QC muncul berulang (>3x): " + h["teks"]
                aktif_terakhir = time.time()
                continue
            lain = _popup_swal_lain(driver)
            if lain:
                el, teks, galat = lain
                print(f"ℹ️ Popup susulan: {teks[:120]}")
                if galat:
                    try:
                        save_debug_snapshot(driver, "popup_galat_setelah_kirim")
                    except Exception:
                        pass
                    return False, "popup galat setelah SEND: " + teks[:160]
                if re.search(r"berhasil|success", teks or "", re.I):
                    BERHASIL_TERLIHAT = True   # [rev 30] web sendiri menyatakan data terkirim
                for b in el.find_elements(By.XPATH, f".//button[{_LOW}='ok']"):
                    if _tampak(b):
                        attempt_click(driver, b)
                        print("✅ Popup susulan ditutup (OK)")
                        break
                aktif_terakhir = time.time()
                time.sleep(0.4)
                continue
        except StaleElementReferenceException:
            # [rev 30] popup SweetAlert menutup dirinya sendiri saat dibaca (jam 18 UTC 2026-11-22: data TERKIRIM, tetapi galat stale
            # ini membuat baris dicatat gagal). Cukup baca ulang layar.
            n_stale += 1
            if n_stale > 8:
                return BERHASIL_TERLIHAT, "popup susulan terus berubah (stale element); " + (
                    "web menyatakan berhasil" if BERHASIL_TERLIHAT else "status tidak dapat dipastikan")
            time.sleep(0.3)
            continue
        sekarang = time.time()
        if sekarang - aktif_terakhir >= tenang or sekarang - mulai >= batas + tenang * 3:
            return True, ""
        time.sleep(0.4)


def wait_for_send_ok_button(driver, timeout=12):
    """Setelah klik SEND di modal GTS: tunggu popup Koreksi QC (-> Submit) atau tombol OK normal."""
    ok_xpath = f"//button[{_LOW}='ok']"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            h = tangani_popup_koreksi_qc(driver, tunggu=0)
            if h["muncul"]:
                return bool(h["diklik"])
            for button in driver.find_elements(By.XPATH, ok_xpath):
                if button.is_displayed():
                    print("✅ Popup Koreksi QC tidak muncul; tombol OK alur normal terdeteksi")
                    return True
        except Exception as e:
            print(f"⚠️ Error saat memeriksa konfirmasi setelah SEND: {e}")
        time.sleep(0.5)
    print(f"⚠️ Popup Koreksi QC maupun tombol OK tidak muncul setelah SEND ({timeout}s)")
    return False


def click_button_containing_words(driver, words, timeout=10):
    try:
        buttons = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.XPATH, "//button"))
        )
        words = [w.strip().lower() for w in words if w.strip()]
        for btn in buttons:
            try:
                text = btn.text.strip().lower()
                if text and all(word in text for word in words):
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    try:
                        btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)
                    print(f"✅ Tombol dengan teks '{text}' berhasil diklik")
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        print(f"❌ Gagal mencari tombol berdasarkan kata: {e}")
        return False


def wait_for_submit_progress(driver, timeout=10):
    start = time.time()
    print(f"⏳ Menunggu progress submit selama {timeout}s...")
    while time.time() - start < timeout:
        try:
            if _popup_koreksi_qc(driver) is not None:          # [F3.11] QC muncul lebih awal
                print("✅ Deteksi popup Koreksi QC setelah klik")
                return bool(tangani_popup_koreksi_qc(driver)["diklik"])
            if driver.find_elements(By.XPATH, "//div[contains(@id,'send-gts-message')]"):
                print("✅ Deteksi modal send-gts-message muncul")
                return True
            if driver.find_elements(By.XPATH, "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send to inaswitching')]"):
                print("✅ Deteksi tombol 'Send to INASwitching' muncul")
                return True
            if driver.find_elements(By.XPATH, "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"):
                print("✅ Deteksi tombol 'Send' muncul")
                return True
            if driver.find_elements(By.XPATH, "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']"):
                print("✅ Deteksi tombol 'OK' muncul")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    print("⚠️ Tidak ada progress submit terdeteksi setelah klik")
    return False


#========= AWAN: fungsi lama = pembungkus tipis atas pilih_ant_select (peta di core/fields.py; F3.1, rev 31) =========#
def isi_jenis_dan_jumlah_awan_Rendah(driver, jenis_target, jumlah_target):
    """Gagal dicatat di GAGAL_WAJIB (jam dibatalkan di akhir isi_data, bukan di tengah)."""
    ok = _isi_jenis_jumlah(driver, "awan_rendah_jenis", "awan_rendah_jumlah", jenis_target, jumlah_target, GAGAL_WAJIB)
    if not ok:
        print("⚠️ Jenis/Jumlah Awan Rendah tidak lengkap; pengisian field berikutnya tetap dilanjutkan")
    return ok


def isi_jenis_dan_jumlah_awan_rendah_2(driver, jenis_target, jumlah_target):
    return _isi_jenis_jumlah(driver, "awan_rendah_2_jenis", "awan_rendah_2_jumlah", jenis_target, jumlah_target)


def isi_jenis_dan_jumlah_awan_menengah(driver, jenis_target, jumlah_target):
    return _isi_jenis_jumlah(driver, "awan_menengah_jenis_1", "awan_menengah_jumlah_1", jenis_target, jumlah_target, GAGAL_OPSIONAL)


def isi_jenis_dan_jumlah_awan_Tinggi(driver, jenis_target, jumlah_target):
    return _isi_jenis_jumlah(driver, "awan_tinggi_jenis", "awan_tinggi_jumlah", jenis_target, jumlah_target, GAGAL_OPSIONAL)


def pilih_arah_sebenarnya(driver, target_teks):
    return pilih_ant_select(driver, "cloud_arah_sebenarnya_1", target_teks)


def pilih_arah_sebenarnya_2(driver, target_teks):
    return pilih_ant_select(driver, "cloud_arah_sebenarnya_2", target_teks)


def pilih_arah_2(driver, target_teks):
    return pilih_ant_select(driver, "cloud_arah_2", target_teks)


def pilih_arah_Awan_Rendah(driver, target_teks):
    return pilih_ant_select(driver, "cloud_arah_awan_rendah", target_teks)


def pilih_arah_Awan_Menengah(driver, target_teks):
    return pilih_ant_select(driver, "cloud_arah_menengah_1", target_teks)


def pilih_arah_Awan_Tinggi(driver, target_teks):
    return pilih_ant_select(driver, "cloud_arah_tinggi", target_teks)


def klik_switch_jika_type(driver, id_div_cloud_type="cloud_low_type_cl", id_label_switch="775"):
    try:
        selected = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, f"//div[@id='{id_div_cloud_type}']//div[contains(@class,'ant-select-selection-selected-value')]"))
        )
        nilai = selected.get_attribute("title").strip()
        print(f"✅ Tipe awan rendah terpilih: {nilai}")

        if nilai.startswith("2") or nilai.startswith("3") or nilai.startswith("9"):
            print(f"🔔 Tipe awan {nilai} memerlukan klik switch.")
            label = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, f"//label[@for='{id_label_switch}']"))
            )
            # [F1.5/T19] JANGAN menekan switch yang SUDAH aktif: mode Update memuat data lama dengan
            # switch aktif; menekannya justru mematikan lapisan 2 (field jadi tidak bisa diisi).
            if _switch_aktif(driver, id_label_switch) is True:
                print(f"ℹ️ Switch '{id_label_switch}' sudah aktif; tidak diklik.")
            else:
                safe_click(driver, label)
                print(f"✅ Switch dengan label for='{id_label_switch}' diklik.")
                _atur_switch(driver, id_label_switch, True)   # pastikan benar-benar aktif
            return True

        print(f"ℹ️ Tipe awan {nilai} tidak memerlukan klik switch.")
        return False

    except Exception as e:
        print(f"❌ Gagal cek & klik switch: {e}")
        return False


#=================================================Pengiriman=========================================================# 
def submit_with_retry(driver, action_name, action_func, max_attempts=3):
    """
    Retry logic untuk submission actions dengan exponential backoff.
    Jika semua attempt gagal, save debug snapshot.
    """
    start_time = time.time()
    for attempt in range(1, max_attempts + 1):
        try:
            attempt_start = time.time()
            print(f"🔄 [{attempt}/{max_attempts}] Mencoba {action_name}...")
            if action_func():
                elapsed = time.time() - attempt_start
                print(f"✅ {action_name} berhasil pada attempt {attempt} ({elapsed:.2f}s)")
                return True
            else:
                elapsed = time.time() - attempt_start
                wait_time = 1 + (attempt - 1) * 0.5
                if attempt < max_attempts:
                    print(f"⏳ {action_name} gagal ({elapsed:.2f}s), menunggu {wait_time}s sebelum retry...")
                    time.sleep(wait_time)
        except Exception as e:
            elapsed = time.time() - attempt_start
            wait_time = 1 + (attempt - 1) * 0.5
            print(f"⚠️ [{attempt}] Exception saat {action_name} ({elapsed:.2f}s): {e}")
            if attempt < max_attempts:
                print(f"⏳ Menunggu {wait_time}s sebelum retry...")
                time.sleep(wait_time)

    total_elapsed = time.time() - start_time
    print(f"❌ {action_name} gagal setelah {max_attempts} percobaan (total {total_elapsed:.2f}s)")
    try:
        save_debug_snapshot(driver, f"failed_{action_name}")
    except Exception:
        pass
    return False


def wait_for_preview_modal(driver, timeout=10):
    modal_xpaths = [
        "//div[@id='modal-preview' and contains(@class,'show') and contains(@class,'modal') and @aria-modal='true']",
        "//div[contains(@class,'swal2-container') and contains(@class,'swal2-center')]",
        "//div[contains(@class,'ant-modal-wrap') and not(contains(@style,'display: none'))]",
    ]
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: any(
                el.is_displayed()
                for xpath in modal_xpaths
                for el in d.find_elements(By.XPATH, xpath)
            )
        )
        return True
    except Exception:
        return False

def Preview(driver):
    try:
        preview_xpath = "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='preview & generate sandi']"
        try:
            fill_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, preview_xpath))
            )
        except Exception:
            fill_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn.mr-1.btn-warning.btn-sm"))
            )

        if not attempt_click(driver, fill_button):
            raise Exception("Klik Preview gagal")

        print("✅ Tombol Preview berhasil diklik")
        time.sleep(0.5)
        if not wait_for_preview_modal(driver, timeout=10):
            print("⚠️ Tombol Preview diklik, tetapi preview modal tidak muncul dalam 10 detik")
            save_debug_snapshot(driver, "preview_clicked_no_modal")
            return False
        return True
    except Exception as e:
        print(f"❌ Gagal klik tombol Preview: {e}")
        return False


def Preview_OK(driver):
    ok_xpath = (By.XPATH, "//div[@id='modal-preview']//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']")
    try:
        ok_btn = wait_for_clickable(driver, ok_xpath, timeout=12)
        if not ok_btn:
            print("❌ Tombol Preview OK tidak ditemukan di modal preview berdasarkan teks")
            return False

        if not attempt_click(driver, ok_btn):
            print("❌ Tombol Preview OK ditemukan tetapi klik gagal")
            save_debug_snapshot(driver, "preview_ok_click_failed")
            return False

        print("✅ Tombol Preview OK berhasil diklik")
        return True
    except Exception as e:
        print(f"❌ Gagal klik tombol 'ok': {e}")
        try:
            save_debug_snapshot(driver, "preview_ok_exception")
        except Exception:
            pass
        return False


def SEND_GTS(driver):
    # [FIX] Tambah pre-wait modal + verifikasi in_modal untuk mencegah klik tombol yang salah
    modal_send_xpath = "//div[contains(@id,'send-gts-message')]//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"
    modal_xpath = "//div[contains(@class,'swal2-container') or contains(@class,'ant-modal-wrap')]//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"
    send_exact_xpath = "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"
    timeout = 15
    poll = 0.25
    start = time.time()

    # Pre-wait: tunggu modal GTS benar-benar muncul sebelum mencari tombol SEND
    print(f"⏳ Menunggu modal GTS muncul sebelum mencari tombol SEND (maks 10s)...")
    modal_appeared = False
    modal_indicators = [
        "//div[contains(@id,'send-gts-message')]",
        "//div[contains(@class,'swal2-container') and contains(@class,'swal2-backdrop-show')]",
        "//div[contains(@class,'ant-modal-wrap') and not(contains(@style,'display: none'))]",
    ]
    wait_modal_start = time.time()
    while time.time() - wait_modal_start < 10:
        for xpath in modal_indicators:
            try:
                els = driver.find_elements(By.XPATH, xpath)
                if els and any(e.is_displayed() for e in els):
                    print(f"✅ Modal GTS terdeteksi ({xpath.split(']')[0]}...)")
                    modal_appeared = True
                    break
            except Exception:
                pass
        if modal_appeared:
            time.sleep(0.5)
            break
        time.sleep(0.3)

    if not modal_appeared:
        print("⚠️ Modal GTS tidak terdeteksi dalam 10s, tetap mencoba cari tombol SEND...")

    print(f"⏳ Mencari tombol SEND (poll {poll}s) sampai {timeout}s...")
    try:
        while time.time() - start < timeout:
            try:
                # 1) Prioritas: tombol SEND di modal send-gts-message
                try:
                    modal_buttons = driver.find_elements(By.XPATH, modal_send_xpath)
                except Exception as e:
                    print(f"⚠️ Error mencari tombol SEND di modal send-gts-message: {e}")
                    modal_buttons = []
                for btn in modal_buttons:
                    try:
                        if btn and btn.is_displayed():
                            elapsed = time.time() - start
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            print(f"✅ Tombol SEND berhasil diklik (modal send-gts-message) setelah {elapsed:.2f}s")
                            if wait_for_send_ok_button(driver, timeout=12):
                                return True
                            print("⚠️ Tombol OK belum muncul setelah klik SEND di modal; menunggu ekstra sebelum retry...")
                            time.sleep(2)
                            continue
                    except Exception:
                        continue

                # 2) Cari tombol SEND hanya di dalam modal dengan verifikasi JS
                try:
                    modal_only_candidates = driver.find_elements(By.XPATH, modal_xpath)
                except Exception:
                    modal_only_candidates = []

                for btn in modal_only_candidates:
                    try:
                        if btn and btn.is_displayed():
                            text = btn.text.strip().lower()
                            if text != 'send':
                                continue
                            in_modal = driver.execute_script(
                                """
                                var el = arguments[0];
                                while (el) {
                                    var cls = (el.className || '').toString();
                                    if (cls.includes('swal2-container') ||
                                        cls.includes('ant-modal-wrap') ||
                                        (el.id && el.id.includes('send-gts-message'))) {
                                        return true;
                                    }
                                    el = el.parentElement;
                                }
                                return false;
                                """, btn
                            )
                            if not in_modal:
                                print(f"⚠️ Tombol '{text}' ditemukan tapi bukan di modal, dilewati")
                                continue
                            elapsed = time.time() - start
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            print(f"✅ Tombol SEND berhasil diklik (modal verified) setelah {elapsed:.2f}s")
                            if wait_for_send_ok_button(driver, timeout=12):
                                return True
                            print("⚠️ Tombol OK belum muncul setelah klik SEND modal verified; retry...")
                            time.sleep(2)
                    except Exception:
                        continue

                # 3) Fallback: cari by text dengan verifikasi in_modal
                candidates = []
                try:
                    candidates.extend(driver.find_elements(By.XPATH, send_exact_xpath))
                except Exception:
                    pass

                for btn in candidates:
                    try:
                        if btn and btn.is_displayed():
                            text = btn.text.strip().lower()
                            if text != 'send':
                                continue
                            in_modal = driver.execute_script(
                                """
                                var el = arguments[0];
                                while (el) {
                                    var cls = (el.className || '').toString();
                                    if (cls.includes('swal2-container') ||
                                        cls.includes('ant-modal-wrap') ||
                                        (el.id && el.id.includes('send-gts-message'))) {
                                        return true;
                                    }
                                    el = el.parentElement;
                                }
                                return false;
                                """, btn
                            )
                            if not in_modal:
                                print(f"⚠️ Tombol 'send' di luar modal, dilewati untuk menghindari klik salah")
                                continue
                            elapsed = time.time() - start
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            print(f"✅ Tombol SEND berhasil diklik (by text, in modal) setelah {elapsed:.2f}s")
                            if wait_for_send_ok_button(driver, timeout=12):
                                return True
                            print("⚠️ Tombol OK belum muncul setelah klik SEND; retry...")
                            time.sleep(2)
                    except Exception:
                        continue

            except Exception as e:
                print(f"⚠️ Exception selama polling SEND_GTS loop: {e}")
            time.sleep(poll)
    except Exception as e:
        print(f"⚠️ Exception saat polling SEND_GTS: {e}")

    print("❌ Tombol SEND tidak ditemukan berdasarkan teks maupun modal XPath")
    try:
        save_debug_snapshot(driver, "failed_send_gts")
    except Exception:
        pass
    return False


def SEND_INASWITCH(driver):
    try:
        buttons = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//button"))
        )
        for btn in buttons:
            text = btn.text.strip().lower()
            if "send to inaswitching" in text:
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                print("✅ Tombol 'Send to INASwitching' berhasil diklik")
                return True
        print("❌ Tombol 'Send to INASwitching' tidak ditemukan berdasarkan teks")
        return False
    except Exception as e:
        print(f"❌ Gagal klik tombol 'Send to INASwitching': {e}")
        return False

def _mode_kirim(driver):
    """[T21] 'update' bila data jam ini SUDAH ADA di web (tombol Send & Update), selain itu 'submit'."""
    return "update" if (_ada_tombol(driver, TOMBOL_KIRIM["update"]["teks"])
                        and not _ada_tombol(driver, TOMBOL_KIRIM["submit"]["teks"])) else "submit"


def SEND_SEND_SUBMIT(driver):
    # [F1.5/T21 -> F3.1] dua set label di core.fields.TOMBOL_KIRIM
    tb = TOMBOL_KIRIM[_mode_kirim(driver)]
    label = tb["teks"].title()
    klik = click_button_by_text(driver, tb["teks"], timeout=8, exact=False)
    cadangan = False
    if not klik and tb["fallback"]:
        klik = cadangan = click_button_containing_words(driver, tb["fallback"], timeout=8)
    if not klik:
        print(f"❌ Tombol '{label}' tidak ditemukan atau gagal diklik")
        return False
    time.sleep(1)
    if wait_for_submit_progress(driver, timeout=8):
        print(f"✅ Tombol '{label}' berhasil diklik{' (fallback)' if cadangan else ''} dan progress terdeteksi")
        return True
    print(f"⚠️ Tombol '{label}' diklik{' (fallback)' if cadangan else ''} tetapi progress tidak terdeteksi")
    return False


def SEND_INASWITCH_SUBMIT(driver):
    if click_button_by_text(driver, "send to inaswitching", timeout=8, exact=False):
        time.sleep(1)
        if wait_for_submit_progress(driver, timeout=8):
            print("✅ Tombol 'Send to INASwitching' berhasil diklik dan progress terdeteksi")
            return True
        print("⚠️ Tombol 'Send to INASwitching' diklik tetapi progress tidak terdeteksi")
        return False
    if click_button_containing_words(driver, ["send", "inaswitching"], timeout=8):
        time.sleep(1)
        if wait_for_submit_progress(driver, timeout=8):
            print("✅ Tombol 'Send to INASwitching' berhasil diklik (fallback) dan progress terdeteksi")
            return True
        print("⚠️ Tombol 'Send to INASwitching' diklik (fallback) tetapi progress tidak terdeteksi")
        return False
    print("❌ Tombol 'Send to INASwitching' tidak ditemukan")
    return False


def SEND_GTS_OK(driver):
    try:
        qc = tangani_popup_koreksi_qc(driver, tunggu=0)       # [F3.11] jangan klik OK menembus popup QC
        if qc["muncul"] and not qc["diklik"]:
            return False
        ok_btn = wait_for_clickable(driver, (
            By.XPATH,
            "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']"
        ), timeout=10)
        if ok_btn:
            driver.execute_script("arguments[0].scrollIntoView(true);", ok_btn)
            try:
                ok_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", ok_btn)
            print("✅ Tombol SEND GTS OK berhasil diklik")
            return True
        print("❌ Tombol GTS OK tidak ditemukan berdasarkan teks")
        return False
    except Exception as e:
        print(f"❌ Gagal klik tombol 'ok': {e}")
        return False


#=================================================Main Browser=======================================================#
SESI_TERAKHIR_OK = 0.0   # [rev 28] waktu (time.time) terakhir sesi BMKG Satu terbukti masih berlaku


def _tandai_sesi_ok():
    global SESI_TERAKHIR_OK
    SESI_TERAKHIR_OK = time.time()
    _status.tulis("sesi", ok=True, ket="sesi BMKG Satu aktif")   # [rev 36] untuk panel


def _di_halaman_login(driver):
    try:
        if "/login" in (driver.current_url or ""):
            return True
        return bool(driver.find_elements(By.ID, "login-email"))
    except Exception:
        return False


def _sudah_masuk(driver):
    """Sudah di dalam BMKG Satu (bukan halaman login, bukan about:blank)."""
    try:
        u = driver.current_url or ""
    except Exception:
        return False
    return urlparse(CFG["urls"]["login"]).netloc in u and "/login" not in u


KATA_POPUP_SESI = ("sesi", "session", "expired", "kedaluwarsa", "kadaluarsa", "berakhir", "login ulang", "login kembali", "masuk kembali",
                   "unauthorized", "unauthenticated")
_JS_TEKS_POPUP = ("var r=[];document.querySelectorAll('div.swal2-popup, div.ant-modal-wrap, div.modal.show, [role=dialog]').forEach(function(e){"
                  "var b=e.getBoundingClientRect(); if(b.width>0&&b.height>0) r.push((e.innerText||'').trim());}); return r;")


def popup_sesi_habis(drv):
    """[rev 35] Teks popup 'sesi habis' yang sedang tampil (bertombol OK); None bila tak ada. Hanya membaca DOM, tidak memuat ulang apa pun."""
    kata = tuple((CFG.get("session", {}) or {}).get("kata_popup") or KATA_POPUP_SESI)
    try:
        for t in drv.execute_script(_JS_TEKS_POPUP) or []:
            if t and any(k in t.lower() for k in kata):
                return t
    except Exception:
        pass
    return None


def sesi_habis(drv=None):
    """[rev 35] True = sesi habis (halaman login ATAU popup 'sesi habis' tampil); False = tampak masih masuk; None = tak bisa dipastikan (browser mati).
    Murni membaca DOM: aman dipanggil sering-sering tanpa mengganggu halaman."""
    drv = drv if drv is not None else driver
    if drv is None:
        return None
    try:
        if "/login" in (drv.current_url or "") or drv.find_elements(By.ID, "login-email"):
            return True
    except Exception:
        return None
    return True if popup_sesi_habis(drv) else False


def _login_sekali(driver):
    print("🌐 Membuka halaman login...")
    _navigasi_aman(driver, CFG["urls"]["login"])
    # [F3.3] tunggu sampai kolom email muncul ATAU web langsung mengarahkan ke dalam (sesi profil tetap masih berlaku)
    try:
        WebDriverWait(driver, 15).until(lambda d: d.find_elements(By.ID, "login-email") or _sudah_masuk(d))
    except TimeoutException:
        pass
    if _sudah_masuk(driver) and not driver.find_elements(By.ID, "login-email"):
        print("✅ Sesi login tersimpan masih berlaku — langkah login dilewati")
        return

    try:
        print("⏳ Menunggu email field...")
        email_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "login-email"))
        )
        print("✅ Email field ditemukan")
        driver.execute_script("arguments[0].scrollIntoView(true);", email_input)
        time.sleep(0.2)
        email_input.clear()
        time.sleep(0.2)
        email_input.send_keys(STATION_ID)
        print(f"✅ Email ({STATION_ID}) diisi")
        time.sleep(0.2)
    except Exception as e:
        print(f"❌ Error saat mengisi email: {e}")
        raise

    try:
        print("⏳ Menunggu password field...")
        password_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "login-password"))
        )
        print("✅ Password field ditemukan")
        driver.execute_script("arguments[0].scrollIntoView(true);", password_input)
        time.sleep(0.2)
        password_input.clear()
        time.sleep(0.2)
        password_input.send_keys(PASSWORD)
        print("✅ Password dimasukkan")
        time.sleep(0.2)
    except Exception as e:
        print(f"❌ Error saat mengisi password: {e}")
        raise

    try:
        print("⏳ Mencari tombol login atau menekan ENTER...")
        password_input.send_keys(Keys.RETURN)
        print("✅ ENTER ditekan")
    except Exception as e:
        print(f"⚠️ ENTER tidak berhasil: {e}")
        try:
            print("⏳ Mencari tombol submit...")
            submit_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            driver.execute_script("arguments[0].click();", submit_button)
            print("✅ Tombol login diklik via JavaScript")
            time.sleep(2)
        except Exception as e2:
            print(f"❌ Gagal klik tombol login: {e2}")
            raise

    WebDriverWait(driver, 20).until(lambda d: _sudah_masuk(d))
    print("✅ Login berhasil")


def login(driver, percobaan=2):
    """Login ke BMKG Satu. [rev 28] kredensial dimuat otomatis; dicoba ulang bila gagal (mis. form belum siap)."""
    print("\n" + "="*60)
    print("🌐 MEMULAI PROSES LOGIN")
    print("="*60)
    _muat_kredensial()
    for ke in range(1, percobaan + 1):
        try:
            _login_sekali(driver)
            break
        except Exception as e:
            if ke >= percobaan:
                raise
            print(f"🔁 Login gagal ({type(e).__name__}: {str(e)[:100]}); mengulang {ke + 1}/{percobaan}...")
            time.sleep(3)
    _tandai_sesi_ok()
    _buka_sinoptik(driver)


def segarkan_sesi(drv):
    """[rev 35] Dipanggil HANYA bila sesi terdeteksi habis. Alur seperti pengguna: popup 'sesi habis' -> klik OK -> web kembali ke halaman
    login -> user & password stasiun diisi ulang -> popup awal + stasiun. Mengembalikan True bila tadinya ter-logout."""
    teks = popup_sesi_habis(drv)
    habis = sesi_habis(drv)
    print("🔐 Sesi BMKG Satu habis — login ulang" + (f" (popup: {teks[:80]!r})" if teks else "") + "...")
    if teks:
        try:
            save_debug_snapshot(drv, "popup_sesi_habis")
        except Exception:
            pass
        klik_tombol_oke_popup(drv=drv)
        try:
            WebDriverWait(drv, 8).until(lambda d: _di_halaman_login(d))
        except TimeoutException:
            print("ℹ️ Setelah OK web belum ke halaman login; login() akan membukanya sendiri")
    login(drv)
    klik_tombol_oke_popup(drv=drv)
    memilih_stasiun(drv)
    _status.tulis("sesi", ok=True, ket="login ulang otomatis berhasil")   # [rev 36] untuk panel
    return bool(habis)


def pastikan_sesi(notifier=None, slot=None, paksa=False):
    """[rev 35] Pemeriksaan sesi PASIF: tidak memuat ulang halaman bila sesi masih berlaku (dulu tiap jam login()/buka ulang halaman).
    Login ulang hanya bila terdeteksi habis (halaman login / popup). Mengembalikan (ok, dimuat_ulang).
    dimuat_ulang=True -> halaman dimuat ulang: pemanggil harus memilih ulang observer & tanggal. Gagal total -> recover_session."""
    global driver
    if not (CFG.get("session", {}) or {}).get("aktif", True):
        return True, False
    if not paksa and sesi_habis(driver) is False:
        _tandai_sesi_ok()
        return True, False
    try:
        habis = segarkan_sesi(driver)
        if habis and notifier is not None and slot is not None:
            try:
                notifier.kirim(f"🔐 Sesi BMKG Satu habis sendiri — login ulang otomatis berhasil (slot {slot[0]} {slot[1]} UTC).", "recovery")
            except Exception:
                pass
        return True, True
    except Exception as e:
        print(f"⚠️ Pemeriksaan sesi gagal ({type(e).__name__}: {str(e)[:120]}); memulihkan dengan browser baru...")
        try:
            save_debug_snapshot(driver, "pastikan_sesi_gagal")
        except Exception:
            pass
        baru, ok = recover_session(driver, tanggal_utc=(slot[0] if slot else None))
        if notifier is not None and slot is not None:
            try:
                notifier.recovery(slot, ok)
            except Exception:
                pass
        if ok:
            driver = baru
        return ok, True


# ---- [rev 35 / F3.9] health check selector: hanya membaca halaman, melapor bila struktur web berubah ----
_SELECTOR_TERAKHIR = {"t": 0.0, "hilang": None}


def _lapor_selector(notifier, slot, hilang, tahap):
    """Cetak + Telegram sekali per perubahan daftar yang hilang (tidak membanjiri notifikasi)."""
    hilang = [h for h in hilang if not h.startswith("(tidak terbaca")]   # halaman tak terbaca = bukan bukti web berubah
    kunci = (tahap, tuple(sorted(hilang)))
    _status.tulis("selector", tahap=tahap, hilang=list(hilang))   # [rev 36] untuk baris 'Struktur web' di panel
    if _SELECTOR_TERAKHIR["hilang"] == kunci:
        return
    _SELECTOR_TERAKHIR["hilang"] = kunci if hilang else None
    if not hilang:
        return
    pesan = f"⚠️ Struktur web BMKG Satu tampak berubah ({tahap}): tidak ditemukan {', '.join(hilang)}. Periksa sebelum jam kirim."
    print(pesan)
    if notifier is not None:
        try:
            notifier.kirim(pesan, "selector")
        except Exception:
            pass


def cek_selector_berkala(drv, notifier=None, slot=None):
    """Kerangka halaman sinoptik, paling sering tiap health.cek_detik (bawaan 600). Dilewati bila tidak sedang di halaman sinoptik."""
    h = CFG.get("health", {}) or {}
    if not h.get("aktif", True) or time.time() - _SELECTOR_TERAKHIR["t"] < float(h.get("cek_detik", 600)):
        return
    _SELECTOR_TERAKHIR["t"] = time.time()
    try:
        if _di_halaman_login(drv) or "sinoptik" not in (drv.current_url or ""):
            return
    except Exception:
        return
    _lapor_selector(notifier, slot, _health.periksa(lambda *a: drv.execute_script(*a)), "kerangka")


def cek_selector_form(drv, notifier=None, slot=None):
    """Sesudah jam dipilih, SEBELUM pengisian & SEND: kerangka + field wajib berid. Tidak pernah menggagalkan jam (hanya melapor)."""
    if not (CFG.get("health", {}) or {}).get("aktif", True):
        return []
    hilang = _health.periksa(lambda *a: drv.execute_script(*a), form=True)
    _lapor_selector(notifier, slot, hilang, "form")
    return hilang


def _buka_sinoptik(driver):
    """[F3.3] Buka halaman sinoptik lalu TUNGGU form-nya siap (menggantikan time.sleep(2) tetap)."""
    print("🌐 Membuka halaman sinoptik...")
    driver.get("https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((
            By.XPATH, "//label[contains(text(), 'Stasiun')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]")))
    except TimeoutException:
        print("⚠️ Form sinoptik belum terlihat setelah 15 detik; proses dilanjutkan (langkah berikutnya punya tunggu sendiri)")


def has_opencv():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def _klik_popup_oke_selenium_sekali(drv):
    # [F1.1] Satu kali coba klik tombol konfirmasi popup (swal2 / modal) lewat Selenium.
    try:
        kandidat = list(drv.find_elements(By.CSS_SELECTOR, "button.swal2-confirm"))
        kandidat += drv.find_elements(
            By.XPATH,
            "//*[contains(@class,'swal2-container') or contains(@class,'modal') "
            "or contains(@class,'ant-modal-wrap') or @role='dialog']"
            "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok' "
            "or translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='oke']")
        for b in kandidat:
            if b.is_displayed():
                safe_click(drv, b)
                return True
    except Exception:
        pass
    return False


def klik_tombol_oke_popup(image_path=None, max_wait=None, drv=None):
    # [F1.1] Urutan: (1) Selenium (tidak bergantung resolusi/skala layar), (2) gambar via pyautogui (cara V6),
    # (3) opsional: tekan Enter (features.popup_press_enter; dialog Chrome fokusnya sudah di tombol OK)
    if max_wait is None:
        # [rev 29] bawaan 3 -> 1: pada 4 dari 4 run nyata (dry-run & jelajah) popup TIDAK pernah muncul sejak F1.1, tetapi tetap
        # ditunggu 3 dtk + 3x pindai layar (4,3-4,8 dtk tiap run).
        max_wait = CFG["runtime"].get("popup_wait_seconds", 1)
    drv = drv if drv is not None else driver
    if image_path is None:
        image_path = OK_IMAGE_PATH          # dari config.yaml (paths.ok_image)
    pakai_gambar = pyautogui is not None and os.path.exists(image_path)
    print("🔍 Mendeteksi tombol Oke pada popup...")
    if pyautogui is None:
        print("ℹ️ pyautogui tidak terpasang (opsional): cadangan klik gambar & Enter dinonaktifkan; hanya Selenium.")
    elif not pakai_gambar:
        print(f"ℹ️ Gambar tombol OK tidak ditemukan ({image_path}); hanya memakai Selenium.")
    use_confidence = has_opencv() if pakai_gambar else False
    if pakai_gambar and not use_confidence:
        print("⚠️ OpenCV tidak ditemukan. Mencoba tanpa confidence parameter.")
    for i in range(max_wait):
        if drv is not None and _klik_popup_oke_selenium_sekali(drv):
            print("✅ Tombol OK popup berhasil diklik lewat Selenium")
            return True
        if pakai_gambar:
            lokasi = None
            try:
                if use_confidence:
                    lokasi = pyautogui.locateOnScreen(image_path, confidence=0.8)
                else:
                    lokasi = pyautogui.locateOnScreen(image_path)
            except Exception as e:
                # pyautogui/pyscreeze versi baru MELEMPAR ImageNotFoundException bila gambar belum
                # terlihat di layar (versi lama mengembalikan None) -> perlakukan sebagai "belum ada".
                if "ImageNotFound" not in type(e).__name__:
                    print(f"⚠️ pyautogui: {type(e).__name__}: {e}")
                lokasi = None
            if lokasi:
                center = pyautogui.center(lokasi)
                pyautogui.moveTo(center.x, center.y, duration=0.3)
                pyautogui.click()
                print(f"✅ Tombol OK berhasil diklik pada {center}")
                return True
        print(f"⏳ Menunggu tombol OK muncul... ({i+1}/{max_wait})")
        if i < max_wait - 1:        # [rev 29] tidak tidur lagi setelah percobaan terakhir
            time.sleep(1)
    if CFG["features"].get("popup_press_enter", False) and pyautogui is not None:
        try:
            pyautogui.press("enter")
            print("⌨️ Enter ditekan untuk menutup dialog Chrome (features.popup_press_enter=true)")
            return True
        except Exception as e:
            print(f"⚠️ Gagal menekan Enter: {e}")
    print("ℹ️ Tombol OK popup tidak ditemukan (popup Chrome 'Change your password' bukan bagian halaman web; "
          "biasanya tidak muncul lagi setelah opsi anti-popup). Proses dilanjutkan.")
    return False


def memilih_stasiun(driver):
    print("🏢 Memilih stasiun...")
    stasiun_dropdown = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Stasiun')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"))
    )
    safe_click(driver, stasiun_dropdown)
    _jeda(0.3)
    pilih_opsi_unsur(driver, STASIUN_YANG_DIPILIH)
    print("✅ Stasiun dipilih")


def memilih_observer(driver):
    print("🏢 Memilih nama observer...")
    for attempt in range(1, 4):
        try:
            observer_dropdown = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//label[contains(text(), 'Nama Observer')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"
                ))
            )
            safe_click(driver, observer_dropdown)
            _jeda(1.5)  # tambah delay agar opsi dropdown sempat muncul

            if pilih_opsi_unsur(driver, nama_observer):
                print("✅ Observer dipilih")
                return True  # [FIX] hanya print sukses kalau benar-benar berhasil

            print(f"⚠️ Attempt {attempt}/3: Opsi observer tidak ditemukan, retry...")
            _jeda(1)

        except Exception as e:
            print(f"⚠️ Attempt {attempt}/3: Exception saat pilih observer: {e}")
            save_debug_snapshot(driver, f"observer_attempt_{attempt}_failed")
            _jeda(1)

    print("❌ Gagal memilih observer setelah 3 percobaan")
    save_debug_snapshot(driver, "observer_gagal_total")
    return False  # [FIX] return False agar caller tahu gagal


_JS_BULAN_KALENDER = ("var c=[].slice.call(document.querySelectorAll(\"[role='button'][data-date]\")); if(!c.length) return null;"
                      "return c[Math.floor(c.length/2)].getAttribute('data-date');")


def _kalender_terbuka(driver):
    try:
        return driver.find_element(By.ID, "input-datepicker").get_attribute("aria-expanded") == "true"
    except Exception:
        return False


def _buka_kalender(driver, tombol):
    """[rev 30] Buka kalender dan PASTIKAN terbuka (aria-expanded). Mengklik lagi kalender yang sudah terbuka justru menutupnya,
    jadi klik hanya dilakukan bila belum terbuka."""
    for cara in ("js", "biasa"):
        if _kalender_terbuka(driver):
            return True
        try:
            if cara == "js":
                driver.execute_script("arguments[0].click();", tombol)
                print("Datepicker button clicked via JavaScript.")
            else:
                tombol.click()
                print("Datepicker button clicked (klik biasa).")
        except Exception as e:
            print(f"Failed to click datepicker button ({cara}): {e}")
        akhir = time.time() + 3
        while time.time() < akhir:
            if _kalender_terbuka(driver):
                return True
            time.sleep(0.1)
    return _kalender_terbuka(driver)


def _navigasi_bulan_kalender(driver, target):
    """Pindahkan kalender ke bulan `target` (date). Sebelumnya hanya bulan berjalan yang bisa dipilih -> slot tanggal akhir bulan
    yang dieksekusi pagi tanggal 1 pasti gagal."""
    for _ in range(14):
        try:
            tampil = driver.execute_script(_JS_BULAN_KALENDER)
        except Exception:
            return
        if not tampil:
            return
        selisih = (target.year - int(tampil[:4])) * 12 + (target.month - int(tampil[5:7]))
        if selisih == 0:
            return
        judul = "Previous month" if selisih < 0 else "Next month"
        tombol = [b for b in driver.find_elements(By.XPATH, f"//button[@title='{judul}']") if _tampak(b)]
        if not tombol or tombol[0].get_attribute("aria-disabled") == "true":
            print(f"⚠️ Tombol '{judul}' tidak tersedia; bulan {target:%Y-%m} tidak bisa dicapai")
            return
        driver.execute_script("arguments[0].click();", tombol[0])
        _jeda(0.3)


def _pilih_tanggal_sekali(driver, utc_date):
    datepicker_button = driver.find_element(By.ID, "input-datepicker")
    try:
        WebDriverWait(driver, 15).until(
            EC.invisibility_of_element_located((By.XPATH, "//div[contains(@class, 'position-absolute') and contains(@class, 'bg-light')]"))
        )
        print("Overlay disappeared, proceeding to click datepicker...")
    except Exception as e:
        print(f"Overlay still present or not found: {e}")
        try:
            overlay = driver.find_element(By.XPATH, "//div[contains(@class, 'position-absolute') and contains(@class, 'bg-light')]")
            driver.execute_script("arguments[0].style.display = 'none';", overlay)
            print("Overlay dismissed via JavaScript.")
        except Exception as e:
            print(f"Could not dismiss overlay: {e}")

    if not _buka_kalender(driver, datepicker_button):
        raise RuntimeError("kalender tidak terbuka")
    target = datetime.strptime(utc_date, "%Y-%m-%d")
    _navigasi_bulan_kalender(driver, target)

    xpath_date = f"//div[@role='button' and @data-date='{utc_date}']"
    # [rev 30] cukup ADA di DOM (jelajah 23:00: sel aktif & kalender terbuka tetapi 'clickable' tak pernah terpenuhi 10 dtk)
    sel = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath_date)))
    if sel.get_attribute("aria-disabled") == "true":
        raise RuntimeError(f"tanggal {utc_date} dinonaktifkan di kalender (di luar rentang yang boleh dipilih)")
    # [rev 35] SUMBER BUG 24 Nov 11:00 UTC: dulu klik dianggap berhasil bila tanggal tak terbaca (tombol datepicker tak punya nilai),
    # padahal kalender masih terbuka & 'No date selected'. Kini tiap cara klik DIVERIFIKASI (label/kalender), lalu cara berikutnya.
    for cara in CARA_KLIK_TANGGAL:
        try:
            _klik_sel_tanggal(driver, xpath_date, utc_date, cara)
        except Exception as e:
            print(f"   ↪ cara klik '{cara}' error: {type(e).__name__}: {str(e)[:90]}")
            continue
        if _tunggu_tanggal(driver, utc_date, 2.5):
            if _kalender_terbuka(driver):
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                except Exception:
                    pass
            print(f"   ✔ tanggal terverifikasi (cara '{cara}')")
            return True
        print(f"   ↪ cara klik '{cara}' belum memilih tanggal; mencoba cara lain...")
    raise RuntimeError(f"tanggal {utc_date} tidak terpilih setelah cara klik: {', '.join(CARA_KLIK_TANGGAL)}")


CARA_KLIK_TANGGAL = ("biasa", "js", "aksi", "vue")
_JS_KLIK_SEL = "var s=arguments[0].querySelector('span.btn'); (s||arguments[0]).click();"
# shortcut: cara 'vue' memakai internal bootstrap-vue (localYMD); hanya cadangan terakhir, ganti bila web mengubah komponen tanggal
_JS_VUE_TANGGAL = ("var o=document.getElementById('input-datepicker__outer_'), v=o&&o.__vue__;"
                   "if(v&&!('localYMD' in v)) v=v.$parent;"
                   "if(!v||!('localYMD' in v)) return false; v.localYMD=arguments[0]; return true;")


def _klik_sel_tanggal(driver, xpath_date, utc_date, cara):
    """Satu cara memilih sel tanggal. Sel dicari ULANG tiap cara (kalender dirender ulang Vue -> elemen lama bisa stale)."""
    if cara == "vue":
        driver.execute_script(_JS_VUE_TANGGAL, utc_date)
        return
    sel = driver.find_element(By.XPATH, xpath_date)
    if cara == "biasa":
        sel.click()
    elif cara == "js":
        driver.execute_script(_JS_KLIK_SEL, sel)
    else:   # aksi: gerakan mouse sungguhan (menembus elemen yang menghalangi klik biasa)
        ActionChains(driver).move_to_element(sel).pause(0.1).click().perform()


def _tunggu_tanggal(driver, utc_date, timeout):
    """True bila web menampilkan utc_date terpilih. Label terisi tetapi formatnya tak dikenali + kalender sudah menutup = terpilih."""
    akhir = time.time() + timeout
    while True:
        t = tanggal_di_web(driver)
        if t == utc_date:
            return True
        if t is None and not _kalender_terbuka(driver) and _label_tanggal(driver):
            return True
        if time.time() >= akhir:
            return False
        time.sleep(0.15)


def memilih_tanggal(driver, utc_date=None, percobaan=3):
    """utc_date 'YYYY-MM-DD' = tanggal slot (F1.5). None = perilaku V6 (tanggal UTC saat ini).
    [rev 30] Dicoba sampai `percobaan` kali; kalender dibuka dengan benar & bisa pindah bulan."""
    if utc_date is None:
        local_now = datetime.now()
        utc_target_time = local_now - timedelta(hours=7)
        utc_date = utc_target_time.strftime("%Y-%m-%d")
    print(f"Memilih tanggal: {utc_date}...")
    for ke in range(1, percobaan + 1):
        try:
            if _pilih_tanggal_sekali(driver, utc_date):
                print(f"✅ Tanggal '{utc_date}' berhasil dipilih.")
                _jeda(0.5)
                return True
        except Exception as e:
            print(f"⚠️ Gagal memilih tanggal {utc_date} (percobaan {ke}/{percobaan}): {type(e).__name__}: {str(e)[:120]}")
        try:
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        if ke < percobaan:
            _jeda(1.0)
    print(f"❌ Tanggal {utc_date} tidak berhasil dipilih setelah {percobaan} percobaan")
    return False


def isi_per_jam(driver, row):
    try:
        print(f"\n⏰ Memilih jam {row['jam_input']}...")
        jam_wrap = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Jam')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"))
        )
        safe_click(driver, jam_wrap)
        _jeda(1)

        jam_raw = str(row['jam_input'])
        if ":" in jam_raw:
            jam_str = jam_raw.strip()[:2] + ":00"
        else:
            jam_str = str(int(float(jam_raw))).zfill(2) + ":00"

        if not pilih_opsi_unsur(driver, jam_str):
            print(f"❌ Opsi jam {jam_str} tidak bisa dipilih")
            return False
        print(f"✅ Jam {jam_str} dipilih")
        return True
    except Exception as e:
        print(f"❌ Gagal pilih jam: {e}")
        return False


def Fill_AWS_Digi(driver):
    try:
        fill_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.swal2-confirm.btn.btn-primary"))
        )
        fill_button.click()
        print("✅ Tombol Fill pada popup berhasil diklik")
        return True
    except Exception:
        print("ℹ️ Tidak ada popup AWS Digi atau tombol Fill tidak muncul")
        return False


#=============================== TAMBAHAN V7 (F1.x) ==============================#
PERUBAHAN_OTOMATIS = {}   # [F1.4] perubahan data otomatis (mis. ww 10->05) untuk dicatat di log
HUJAN_OVERRIDE_LOG = {}   # [F1.8] hasil override hujan untuk dicatat di log


def _fmt_angka(v):
    """Angka -> teks untuk diketik ke web (3.0 -> '3', 3.5 -> '3.5')."""
    f = float(v)
    return str(int(f)) if f == int(f) else ("%g" % f)


def _ada_tombol(driver, teks):
    """True jika ada tombol tampak yang teksnya memuat `teks` (tidak peka huruf besar/kecil)."""
    low = teks.strip().lower()
    xp = ("//button[contains(translate(normalize-space(.),"
          "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'" + low + "')]")
    try:
        return any(b.is_displayed() for b in driver.find_elements(By.XPATH, xp))
    except Exception:
        return False


_BULAN = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7, "agustus": 8, "september": 9,
          "oktober": 10, "november": 11, "desember": 12, "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
          "august": 8, "october": 10, "december": 12}
_JS_TANGGAL_WEB = ("var o=document.querySelector('output[data-selected]'), l=document.getElementById('input-datepicker__value_');"
                   "return [o?(o.getAttribute('data-selected')||''):'', l?(l.textContent||'').trim():null];")


def _tgl_dari_teks(teks):
    """'24/11/2026' | '2026-11-24' | 'Selasa, 24 November 2026' -> 'YYYY-MM-DD'; tak dikenali -> None."""
    t = (teks or "").lower()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", t)
    if m and m.group(2) in _BULAN:
        return f"{m.group(3)}-{_BULAN[m.group(2)]:02d}-{int(m.group(1)):02d}"
    return None


def _label_tanggal(driver):
    """Teks label nilai datepicker (#input-datepicker__value_); kosong = belum ada tanggal. None = tak terbaca."""
    try:
        return driver.execute_script(_JS_TANGGAL_WEB)[1]
    except Exception:
        return None


def tanggal_di_web(driver):
    """[rev 35] Tanggal terpilih di datepicker -> 'YYYY-MM-DD'; '' = belum ada tanggal terpilih; None = tak terbaca/format tak dikenali.
    Dulu membaca value TOMBOL #input-datepicker (selalu kosong) sehingga selalu None -> semua pemeriksaan tanggal tak berarti."""
    try:
        sel, label = driver.execute_script(_JS_TANGGAL_WEB)
    except Exception:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sel or ""):
        return sel
    if label is None:
        return None
    return _tgl_dari_teks(label) or ("" if not label else None)


def baca_sandi(driver):
    """Isi kolom sandi (hasil Preview & Generate Sandi)."""
    try:
        el = driver.find_element(By.ID, "textarea-sandi")
        return (el.get_attribute("value") or el.text or "").strip()
    except Exception:
        return ""


def isi_hujan_override(driver, mm):
    """
    [F1.8] Timpa 'Hujan takaran terakhir' (rainfall_last_mm) dengan angka pengguna.
    Nilai asli dari Fill AWS Digi dicatat. Kolom ini hanya terbuka tiap 3 jam UTC;
    bila nonaktif, override tidak diterapkan (dicatat) dan pengiriman tetap lanjut.
    Return: True = diterapkan atau tidak berlaku; False = kolom aktif tetapi gagal diisi.
    """
    global HUJAN_OVERRIDE_LOG
    nilai = _fmt_angka(mm)
    HUJAN_OVERRIDE_LOG = {"override": nilai, "applied": False}
    try:
        el = wait_for_presence(driver, (By.ID, "rainfall_last_mm"), timeout=5)
        if el is None:
            HUJAN_OVERRIDE_LOG["reason"] = "kolom hujan tidak ditemukan"
            print("⚠️ Override hujan: kolom rainfall_last_mm tidak ditemukan; nilai AWS dipakai")
            return True
        if not el.is_enabled():
            HUJAN_OVERRIDE_LOG["reason"] = "kolom hujan nonaktif (bukan jam kelipatan 3 UTC)"
            print("⚠️ Override hujan: kolom hujan NONAKTIF pada jam ini; override tidak diterapkan")
            return True
        lama = (el.get_attribute("value") or "").strip()
        HUJAN_OVERRIDE_LOG["aws"] = lama
        ok = isi_input_text(driver, "rainfall_last_mm", nilai)
        baru = (driver.find_element(By.ID, "rainfall_last_mm").get_attribute("value") or "").strip()
        try:
            sama = float(baru.replace(",", ".")) == float(nilai)
        except ValueError:
            sama = False
        HUJAN_OVERRIDE_LOG["nilai_akhir"] = baru
        if ok and sama:
            HUJAN_OVERRIDE_LOG["applied"] = True
            print(f"✅ Override hujan diterapkan: {lama or '(kosong)'} (AWS) → {nilai} mm")
            return True
        HUJAN_OVERRIDE_LOG["reason"] = f"nilai akhir '{baru}' tidak sama dengan {nilai}"
        print(f"❌ Override hujan gagal: nilai akhir '{baru}' ≠ '{nilai}'")
        return not CFG["features"].get("rain_override_strict", False)
    except Exception as e:
        HUJAN_OVERRIDE_LOG["reason"] = f"error: {e}"
        print(f"❌ Override hujan error: {e}")
        return not CFG["features"].get("rain_override_strict", False)


# ---- [rev 27] bagian bawah form jam 00 UTC: penguapan, radiasi, lama penyinaran, pengenal data penguapan (iE) ----
PENGUAPAN_LOG = {}
# label persis di web (diawali teks ini, tak peka huruf besar/kecil). ID bisa dipaksa lewat config.yaml -> web_ids.
LABEL_PENGUAPAN = {"mm": "penguapan (mm)", "ie": "pengenal data penguapan", "radiasi": "radiasi matahari",
                   "sinar_jam": "lama penyinaran matahari"}
_JS_CARI_LABEL = r"""
const t = arguments[0];
const norm = x => (x || '').replace(/\s+/g, ' ').trim().toLowerCase();
for (const l of document.querySelectorAll('label')) {
  if (!norm(l.textContent).startsWith(t)) continue;
  if (l.htmlFor) { const e = document.getElementById(l.htmlFor); if (e) return e; }
  let box = l.parentElement;
  for (let i = 0; i < 4 && box; i++, box = box.parentElement) {
    const sel = box.querySelector('.ant-select[id], .ant-select');
    const inp = [...box.querySelectorAll('input, textarea')].find(x => !x.classList.contains('ant-select-search__field')
        && (l.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING));
    if (sel && (l.compareDocumentPosition(sel) & Node.DOCUMENT_POSITION_FOLLOWING)) return sel;
    if (inp) return inp;
  }
}
return null;
"""


def _cari_kolom_penguapan(driver, kunci):
    """Cari elemen kolom lewat ID dari config (web_ids) atau lewat teks label di web."""
    id_cfg = ((CFG.get("web_ids", {}) or {}).get(f"penguapan_{kunci}") or "").strip()
    try:
        if id_cfg:
            return driver.find_element(By.ID, id_cfg)
        return driver.execute_script(_JS_CARI_LABEL, LABEL_PENGUAPAN[kunci])
    except Exception:
        return None


def _set_input_vue(driver, el, nilai):
    """Kosongkan/isi <input> dan beri tahu framework (Vue) lewat event input+change."""
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    el.click()
    el.send_keys(Keys.CONTROL, "a")
    el.send_keys(Keys.BACKSPACE)
    if nilai != "":
        el.send_keys(nilai)
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el)
    el.send_keys(Keys.TAB)


def _angka_sama(teks_web, nilai):
    try:
        return abs(float(str(teks_web).replace(",", ".")) - float(nilai)) < 1e-9
    except ValueError:
        return False


URUTAN_PENGUAPAN_WEB = ("mm", "radiasi", "ie", "sinar_jam")   # urutan kolom di web: penguapan, radiasi, [tanah], iE, lama penyinaran


def isi_penguapan_00(driver, rencana, bagian=None):
    """
    Terapkan isian bagian bawah form jam 00 UTC. Nilai kosong di rencana = biarkan hasil Fill AWS Digi.
      rencana = {mm, ie, radiasi:{kosongkan|nilai}, sinar_jam}
    STRICT (default, features.penguapan_strict): kolom diminta tapi gagal diisi/diverifikasi -> return False (jam TIDAK dikirim).
    Setiap kolom dibaca ulang dari web setelah diisi; nilai AWS asli dan nilai akhir dicatat di PENGUAPAN_LOG.
    """
    if bagian is None:
        PENGUAPAN_LOG.clear()
    strict = CFG["features"].get("penguapan_strict", True)
    semua_ok = True

    def gagal(kunci, alasan):
        nonlocal semua_ok
        PENGUAPAN_LOG.setdefault(kunci, {})["applied"] = False
        PENGUAPAN_LOG[kunci]["reason"] = alasan
        print(f"❌ Penguapan/matahari [{kunci}]: {alasan}")
        semua_ok = False

    for kunci in (bagian or URUTAN_PENGUAPAN_WEB):   # [rev 32] urutan = urutan di web; `bagian` = subset (dipanggil dua kali, tanah di antaranya)
        if kunci not in rencana:
            continue
        log = PENGUAPAN_LOG.setdefault(kunci, {"applied": False})
        el = _cari_kolom_penguapan(driver, kunci)
        if el is None:
            gagal(kunci, f"kolom '{LABEL_PENGUAPAN[kunci]}' tidak ditemukan di web (jam ini mungkin tidak membukanya)")
            continue
        try:
            if kunci == "ie":
                kode = str(rencana["ie"])
                eid = el.get_attribute("id") or ""
                if "ant-select" not in (el.get_attribute("class") or "") or not eid:
                    gagal(kunci, "kolom iE bukan dropdown ant-select ber-ID; isi ID-nya di config.yaml (web_ids.penguapan_ie)")
                    continue
                log["aws"] = (driver.execute_script("return (arguments[0].innerText||'').trim();", el) or "")[:60]
                if not pilih_dropdown_ant_select(driver, eid, f"{kode} -"):
                    gagal(kunci, f"pilihan '{kode} -' tidak bisa dipilih")
                    continue
                akhir = (driver.execute_script("return (arguments[0].innerText||'').trim();", el) or "").strip()
                log["nilai_akhir"] = akhir[:60]
                if akhir.startswith(f"{kode} -") or akhir.startswith(kode):
                    log["applied"] = True
                    print(f"✅ iE: {log['aws'] or '(kosong)'} (AWS) → {akhir}")
                else:
                    gagal(kunci, f"nilai akhir '{akhir}' tidak diawali kode {kode}")
                continue

            if not el.is_enabled():
                gagal(kunci, "kolom NONAKTIF di web pada jam ini")
                continue
            log["aws"] = (el.get_attribute("value") or "").strip()
            if kunci == "radiasi" and rencana["radiasi"].get("kosongkan"):
                _set_input_vue(driver, el, "")
                akhir = (el.get_attribute("value") or "").strip()
                log["nilai_akhir"] = akhir
                if akhir == "":
                    log["applied"] = True
                    print(f"✅ Radiasi matahari dikosongkan (AWS: {log['aws'] or '(sudah kosong)'})")
                else:
                    gagal(kunci, f"radiasi tidak berhasil dikosongkan (masih '{akhir}')")
                continue
            nilai = rencana["radiasi"]["nilai"] if kunci == "radiasi" else rencana[kunci]
            teks = _fmt_angka(nilai)
            _set_input_vue(driver, el, teks)
            akhir = (el.get_attribute("value") or "").strip()
            log["nilai_akhir"] = akhir
            if _angka_sama(akhir, nilai):
                log["applied"] = True
                print(f"✅ {LABEL_PENGUAPAN[kunci]}: {log['aws'] or '(kosong)'} (AWS) → {teks}")
            else:
                gagal(kunci, f"nilai akhir '{akhir}' tidak sama dengan {teks}")
        except Exception as e:
            gagal(kunci, f"error: {e}")
            try:
                save_debug_snapshot(driver, f"penguapan_{kunci}")
            except Exception:
                pass
    if not semua_ok and not strict:
        print("⚠️ penguapan_strict=false: pengiriman dilanjutkan meski ada isian penguapan/matahari yang gagal")
        return True
    return semua_ok


def buat_driver():
    """[F1.6] Buka Chrome (dipanggil di main setelah launcher).
    [rev 28] Tangguh: setelah Chrome terbuka, dipastikan benar-benar sampai ke BMKG Satu. Bila gagal: tutup, bebaskan profil
    (Chrome yatim + berkas kunci), coba lagi; terakhir -- bila chrome.fallback_profil_sementara -- pakai profil sementara."""
    folder = _profil_chrome_dir()
    maks = max(1, int(_cfg_chrome().get("retry_buka", 3)))
    rencana = [True] * maks if folder is not None else [False] * maks
    if folder is not None and _cfg_chrome().get("fallback_profil_sementara", True):
        rencana.append(False)
    terakhir = None
    for no, pakai_profil in enumerate(rencana, 1):
        drv = None
        try:
            if pakai_profil and no > 1:
                _bebaskan_profil(folder)
            if folder is not None and not pakai_profil:
                print("⚠️ Profil Chrome tetap gagal terus -> memakai PROFIL SEMENTARA (login akan dilakukan dari awal)")
            drv = webdriver.Chrome(service=Service(), options=_opsi_chrome_baru(pakai_profil))
            try:
                drv.set_page_load_timeout(60)
            except Exception:
                pass
            _navigasi_aman(drv, CFG["urls"]["login"])
            return drv
        except Exception as e:
            terakhir = e
            print(f"❌ Gagal membuka Chrome (percobaan {no}/{len(rencana)}): {type(e).__name__}: {str(e)[:160]}")
            try:
                if drv is not None:
                    drv.quit()
            except Exception:
                pass
            time.sleep(2 * no)
    raise RuntimeError(f"Chrome tidak bisa dibuka/menuju BMKG Satu setelah {len(rencana)} percobaan: {terakhir}")


def parse_args():
    ap = argparse.ArgumentParser(description="SYNOP otomatis V7 (BMKGSoft v2)")
    ap.add_argument("--observer", help="nama observer persis seperti di web (tanpa dialog)")
    ap.add_argument("--no-gui", action="store_true", help="tanya observer lewat terminal")
    ap.add_argument("--dry-run", action="store_true", help="isi form sampai Preview, tidak mengirim")
    ap.add_argument("--check-only", action="store_true", help="validasi Excel saja lalu keluar")
    ap.add_argument("--process-past", action="store_true",
                    help="baris yang waktu eksekusinya sudah lewat TETAP diproses sekarang (untuk uji / susul kirim)")
    ap.add_argument("--jam", help="hanya proses jam UTC tertentu, contoh: 07:00 atau 07:00,08:00")
    return ap.parse_args()


def daftar_observer_aktif():
    """Observer aktif dari core/options.json (dibatasi observers.allowed di config.yaml bila diisi)."""
    try:
        with open(resolve_path(CFG, "options"), encoding="utf-8") as f:
            obs = json.load(f).get("observer", [])
    except Exception:
        obs = []
    aktif = [o["name"] for o in obs if o.get("active")]
    boleh = CFG.get("observers", {}).get("allowed") or []
    if boleh:
        aktif = [n for n in aktif if n in boleh] or list(boleh)
    return aktif


def pilih_observer_gui(daftar, dry_run_awal=False):
    """
    [F1.6/F1.7] Dialog kecil: pilih observer + centang dry-run.
    Return: (nama, dry_run) | "BATAL" | None (tkinter/display tidak tersedia).
    """
    try:
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
    except Exception:
        return None
    hasil = {"v": "BATAL"}
    root.title("SYNOP Otomatis")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.grid()
    ttk.Label(frm, text="Nama observer:").grid(column=0, row=0, sticky="w")
    var_obs = tk.StringVar(value=daftar[0] if daftar else "")
    cb = ttk.Combobox(frm, textvariable=var_obs, values=daftar, width=38,
                      state="readonly" if daftar else "normal")
    cb.grid(column=0, row=1, pady=(2, 10))
    var_dry = tk.BooleanVar(value=dry_run_awal)
    ttk.Checkbutton(frm, text="Mode uji (DRY-RUN): isi form sampai Preview, tidak mengirim",
                    variable=var_dry).grid(column=0, row=2, sticky="w")

    def mulai():
        if not var_obs.get().strip():
            return
        hasil["v"] = (var_obs.get().strip(), bool(var_dry.get()))
        root.destroy()

    def batal():
        root.destroy()

    btn = ttk.Frame(frm)
    btn.grid(column=0, row=3, pady=(12, 0), sticky="e")
    ttk.Button(btn, text="Batal", command=batal).grid(column=0, row=0, padx=4)
    ttk.Button(btn, text="Mulai", command=mulai).grid(column=1, row=0)
    root.protocol("WM_DELETE_WINDOW", batal)
    root.mainloop()
    return hasil["v"]


LATENSI = {}   # [rev 29] hasil ukur_latensi terakhir (dibaca tools/pantau_web.py untuk laporan)


def ukur_latensi(driver, n=12):
    """[rev 29] Diagnosa kenapa pengisian lambat: latensi round-trip driver, ukuran DOM, biaya XPath, dan apakah jendela
    Chrome sedang tersembunyi/tidak fokus (penyebab throttling). Hanya mengukur; tidak mengubah apa pun. Tak pernah melempar galat."""
    global LATENSI
    try:
        t = []
        for _ in range(n):
            s = time.perf_counter()
            driver.execute_script("return 1;")
            t.append((time.perf_counter() - s) * 1000)
        t.sort()
        s = time.perf_counter()
        n_dd = len(driver.find_elements(By.XPATH, "//div[contains(@class,'ant-select-selection__rendered')]"))
        xp = (time.perf_counter() - s) * 1000
        info = driver.execute_script("return [document.getElementsByTagName('*').length, document.visibilityState, document.hasFocus()];")
        LATENSI = {"execute_script_median_ms": round(t[len(t) // 2], 1), "execute_script_maks_ms": round(t[-1], 1),
                   "xpath_dropdown_ms": round(xp, 1), "jumlah_dropdown": n_dd,
                   "elemen_dom": info[0], "visibilityState": info[1], "jendela_fokus": bool(info[2])}
        print(f"📶 Latensi driver: median {LATENSI['execute_script_median_ms']} ms (maks {LATENSI['execute_script_maks_ms']} ms) | "
              f"XPath {n_dd} dropdown {LATENSI['xpath_dropdown_ms']} ms | DOM {info[0]} elemen | halaman {info[1]}, "
              f"fokus={'ya' if info[2] else 'TIDAK'}")
    except Exception as e:
        LATENSI = {}
        print(f"ℹ️ Latensi driver tidak terukur ({type(e).__name__}); dilewati")
    return LATENSI


def _jeda(detik):
    """[speed] time.sleep yang diskalakan SPEED_SCALE (config.yaml: speed.scale)."""
    time.sleep(max(0.05, float(detik) * SPEED_SCALE))


_WAKTU_MARK = [0.0]


def _catat_waktu(nama):
    """[rev 15] Cetak lama pengisian tiap bagian (⏱️) untuk melacak bagian yang lambat."""
    sekarang = time.time()
    if _WAKTU_MARK[0]:
        print(f"⏱️ {nama}: {sekarang - _WAKTU_MARK[0]:.1f} dtk")
    _WAKTU_MARK[0] = sekarang


def _tunggu_dropdown_terbuka(driver, id_div, timeout=0.4):
    """[rev 29] Tunggu sampai dropdown Ant Design benar-benar terbuka (ant-select-open / aria-expanded) -- pengganti jeda tetap.
    True = terbuka (lanjut segera). False = tak terbaca/belum terbuka -> pemanggil memakai jeda lama (perilaku sebelumnya)."""
    akhir = time.time() + timeout
    js = ("var c=document.getElementById(arguments[0]); if(!c) return 'nf';"
          "return (c.classList.contains('ant-select-open')||c.querySelector('.ant-select-open')||"
          "c.querySelector('[aria-expanded=\"true\"]')) ? 'open' : 'closed';")
    while True:
        try:
            r = driver.execute_script(js, id_div)
        except Exception:
            return False
        if r == "open":
            return True
        if r != "closed":
            return False          # elemen tak ada / driver tak mengembalikan status -> jangan menunggu percuma
        if time.time() >= akhir:
            return False
        time.sleep(0.03)


def _tunggu_nilai_terpilih(driver, id_div, nilai, timeout=2.0):
    """[speed] Tunggu sampai dropdown menampilkan nilai terpilih (pengganti sleep tetap)."""
    kunci = " ".join(str(nilai).split()).lower()
    akhir = time.time() + timeout
    while time.time() < akhir:
        try:
            teks = driver.execute_script(
                "var c=document.getElementById(arguments[0]); if(!c) return '';"
                "var v=c.querySelector('.ant-select-selection-selected-value');"
                "return v ? (v.getAttribute('title') || v.textContent || '') : '';", id_div) or ""
            teks = " ".join(str(teks).split()).lower()
            if teks and (kunci in teks or teks.split(" ")[0] == kunci.split(" ")[0]):
                return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def _switch_aktif(driver, id_switch):
    """True/False = status switch lapisan (checkbox id numerik); None bila tidak terbaca."""
    try:
        return driver.execute_script(
            "var e=document.getElementById(arguments[0]); return e ? !!e.checked : null;", str(id_switch))
    except Exception:
        return None


def _atur_switch(driver, id_switch, aktif):
    """
    [F1.5/T19] Pastikan switch lapisan berada pada status `aktif`. Hanya diklik bila statusnya
    berbeda (mode Update memuat data lama dengan switch sudah aktif; menekannya akan mematikannya).
    Return True bila status akhir sesuai.
    """
    sekarang = _switch_aktif(driver, id_switch)
    if sekarang is not None and bool(sekarang) == bool(aktif):
        return True
    for _ in range(2):
        try:
            label = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, f"//label[@for='{id_switch}']")))
            safe_click(driver, label)
        except Exception as e:
            print(f"⚠️ Gagal klik switch '{id_switch}': {e}")
            return False
        akhir = time.time() + 1.5
        while time.time() < akhir:
            st = _switch_aktif(driver, id_switch)
            if st is not None and bool(st) == bool(aktif):
                return True
            time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
#  [F3.10] LAPISAN TAMBAHAN: awan rendah ke-3, menengah ke-2, tinggi ke-2
#  Dicari lewat POSISI di kartu (seksi -> kolom -> baris), bukan XPath global/id tetap.
# ---------------------------------------------------------------------------
_JS_SELECT_POSISI = r"""
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const sec = arguments[0], col = arguments[1], row = arguments[2];
const h = Array.from(document.querySelectorAll('h5')).find(x => norm(x.innerText) === sec);
if (!h) return null;
const body = h.closest('.card-body'); if (!body) return null;
const cols = body.querySelector('.collapse > .row'); if (!cols) return null;
const c = cols.children[col]; if (!c) return null;
const r = c.children[row]; if (!r) return null;
return r.querySelector('.ant-select');
"""
_JS_TOGGLE_IDS = r"""
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const h = Array.from(document.querySelectorAll('h5')).find(x => norm(x.innerText) === arguments[0]);
if (!h) return [];
const body = h.closest('.card-body'); if (!body) return [];
return Array.from(body.querySelectorAll("input.custom-control-input[name='check-button']")).map(e => e.id);
"""
_JS_MENU_TERBUKA = r"""
const e = document.getElementById(arguments[0]);
return !!e && e.offsetParent !== null && e.querySelectorAll('li').length > 0;
"""
_JS_CARI_LI = r"""
const n = s => (s || '').replace(/\s+/g, ' ').trim();
const e = document.getElementById(arguments[0]); if (!e) return null;
const li = Array.from(e.querySelectorAll('li')).find(
  x => n(x.innerText) === arguments[1] && x.getAttribute('aria-disabled') !== 'true');
return li || null;
"""


def _sama_teks(a, b):
    a, b = " ".join(str(a).split()), " ".join(str(b).split())
    return bool(a) and bool(b) and (a == b or a.startswith(b) or b.startswith(a))


def _id_toggle(driver, section, ordinal, fallback_id):
    """Id switch lapisan: urutan ke-`ordinal` di kartu `section`; bila gagal, id terakhir terlihat."""
    try:
        ids = driver.execute_script(_JS_TOGGLE_IDS, section) or []
        if len(ids) >= ordinal and ids[ordinal - 1]:
            return str(ids[ordinal - 1])
    except Exception:
        pass
    return str(fallback_id)


def pilih_dropdown_posisi(driver, section, col, row, text, timeout=4):
    """
    Pilih opsi dropdown pada posisi (seksi, kolom, baris) di kartu awan.
    [rev 15] Dulu menunggu menu lewat cek offsetParent (gagal DIAM-DIAM di web asli setelah 2x4 detik per field).
    Kini memakai pilih_opsi_ant_select (jalur yang sama dengan Jenis/Jumlah lapisan 1, terbukti jalan) dan
    mencetak alasan kegagalan.
    """
    nama = f"{section} kolom {col} baris {row}"
    try:
        sel = driver.execute_script(_JS_SELECT_POSISI, section, col, row)
        if sel is None:
            print(f"❌ Dropdown posisi ({nama}) tidak ditemukan")
            return False
        combo = sel.find_element(By.CSS_SELECTOR, "[role='combobox']")
        return bool(pilih_opsi_ant_select(driver, combo, " ".join(str(text).split()), nama))
    except Exception as e:
        print(f"❌ pilih_dropdown_posisi gagal ({nama}): {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")
        return False


def _isi_satu_lapisan_tambahan(driver, item):
    nama = f"{item['section']} lapisan {item['n']}"
    tid = _id_toggle(driver, item["section"], item["toggle_ordinal"], item["fallback_toggle_id"])
    if not _atur_switch(driver, tid, True):
        GAGAL_OPSIONAL.append(f"{nama}: switch '{tid}' gagal diaktifkan")
        print(f"⚠️ {nama}: switch '{tid}' gagal diaktifkan")
        return False
    try:   # tunggu kolom lapisan aktif (input tinggi dasar enabled)
        WebDriverWait(driver, 3).until(lambda d: d.find_element(By.ID, item["base_id"]).is_enabled())
    except Exception:
        GAGAL_OPSIONAL.append(f"{nama}: kolom tidak aktif setelah switch dinyalakan")
        print(f"⚠️ {nama}: kolom tidak aktif setelah switch dinyalakan")
        return False
    ok = True
    for label, baris, teks in (("Jenis", 2, item.get("jenis")), ("Jumlah", 3, item.get("jumlah")),
                               ("Arah", item["arah_row"], item.get("arah"))):
        if not teks:
            continue
        if pilih_dropdown_posisi(driver, item["section"], item["col"], baris, teks):
            print(f"✅ {nama}: {label} = {teks}")
        else:
            GAGAL_OPSIONAL.append(f"{nama}: {label} '{teks}' gagal dipilih")
            ok = False
    if item.get("base") is not None:
        if isi_input_text(driver, item["base_id"], _fmt_angka(item["base"])):
            print(f"✅ {nama}: tinggi dasar = {_fmt_angka(item['base'])}")
        else:
            GAGAL_OPSIONAL.append(f"{nama}: tinggi dasar ({item['base_id']}) gagal diisi")
            ok = False
    return ok


def _matikan_lapisan_tambahan(driver, off):
    """Kolom lapisan ada di Excel tetapi kosong: matikan switch bila masih aktif (sisa data lama)."""
    nama = f"{off['section']} lapisan {off['n']}"
    tid = _id_toggle(driver, off["section"], off["toggle_ordinal"], off["fallback_toggle_id"])
    if _switch_aktif(driver, tid) is True:
        print(f"ℹ️ {nama} aktif (data lama) tetapi Excel kosong -> dimatikan")
        if not _atur_switch(driver, tid, False):
            GAGAL_OPSIONAL.append(f"{nama}: switch '{tid}' gagal dimatikan")


def isi_lapisan_tambahan(driver, plan, layer=None):
    """[F3.10] Isi lapisan tambahan sesuai plan['extra'] dan matikan yang sisa di plan['extra_off'].
    [rev 15] layer = 'low' | 'med' | 'high' -> hanya lapisan jenis itu (dipanggil tepat setelah awan jenis tsb,
    agar urutan isi: rendah 1,2,3 -> menengah 1,2 -> tinggi 1,2). layer=None -> semua."""
    if not plan or not CFG["features"].get("extra_layers", True):
        return
    for item in plan.get("extra") or []:
        if layer and item.get("layer") != layer:
            continue
        try:
            _isi_satu_lapisan_tambahan(driver, item)
        except Exception as e:
            GAGAL_OPSIONAL.append(f"{item.get('section')} lapisan {item.get('n')}: error {e}")
            print(f"⚠️ Lapisan tambahan {item.get('section')} {item.get('n')} error: {e}")
    for off in plan.get("extra_off") or []:
        if layer and off.get("layer") != layer:
            continue
        try:
            _matikan_lapisan_tambahan(driver, off)
        except Exception as e:
            print(f"⚠️ Gagal mematikan lapisan {off.get('section')} {off.get('n')}: {e}")


def _isi_bagian_bawah(driver, row, plan):
    """[rev 32] Bagian paling bawah form, DIKERJAKAN SETELAH AWAN, persis urutan di web BMKG Satu:
    penguapan -> radiasi matahari -> keadaan tanah -> pengenal data penguapan (iE) -> lama penyinaran -> (Preview oleh pemanggil).
    Jam selain 00 UTC tidak punya rencana penguapan: hanya keadaan tanah. False = jam dibatalkan (field wajib gagal)."""
    pg = plan.get("penguapan") if plan else None
    PENGUAPAN_LOG.clear()
    if pg and not isi_penguapan_00(driver, pg, bagian=("mm", "radiasi")):
        return False
    if not pilih_ant_select(driver, "land_cond", str(row['land_cond'])):
        return False  # WAJIB
    _catat_waktu("Keadaan tanah")
    if pg and not isi_penguapan_00(driver, pg, bagian=("ie", "sinar_jam")):
        return False
    if pg:
        _catat_waktu("Penguapan & matahari")
    return True


def isi_data(driver, row, plan=None):
    # plan = keputusan dari core.validator (F1.9); None = perilaku V6 (tanpa plan)
    try:
        print("📝 Mengisi data parameter...")
        GAGAL_WAJIB.clear()   # [rev 14]
        _WAKTU_MARK[0] = time.time()

        # ── WAJIB (abort jika gagal) ──────────────────────────────────────────
        if not pilih_ant_select(driver, "present_weather_ww", str(row['ww']).zfill(2)):
            return False
        if not pilih_ant_select(driver, "past_weather_w1", str(row['w1'])):
            return False
        if not pilih_ant_select(driver, "past_weather_w2", str(row['w2'])):
            return False
        if not isi_input(driver, "visibility_vv", str(row['visibility'])):
            return False
        cloud_cover_oktas_m = str(row['cloud_cover_oktas_m']).strip()
        if not pilih_ant_select(driver, "cloud_cover_oktas_m", cloud_cover_oktas_m):
            return False

        # [F1.8] override curah hujan (hanya bila diminta di Excel & lolos validasi)
        if plan and plan.get("rain_override"):
            if not isi_hujan_override(driver, plan["rain_override"]["mm"]):
                return False

        # [rev 32] penguapan / radiasi / iE / lama penyinaran (jam 00 UTC) kini dikerjakan DI AKHIR, sesudah awan
        # (lihat _isi_bagian_bawah); sebelumnya di sini, sebelum awan.

        # [F1.9] total tutupan 0 / 9 / "/" : web mengisi CL/CM/CH otomatis & menonaktifkan detail awan
        skip_clouds = bool(plan and plan.get("skip_clouds"))
        if skip_clouds or cloud_cover_oktas_m in {"/ - Cloud", "/ -"}:
            print(
                f"ℹ️ cloud_cover_oktas_m = '{cloud_cover_oktas_m}', "
                "melewati pengisian awan dan langsung mengisi land_cond"
            )
            # [F1.9] total 9 (langit tertutup): vertical visibility wajib, diisi manual dari Excel
            if plan and plan.get("total") == "9":
                vv = plan.get("vertical_visibility")
                if vv is None:
                    print("❌ Tutupan total 9 tetapi vertical_visibility kosong di Excel")
                    return False
                if not isi_input(driver, "cloud_vertical_vis", _fmt_angka(vv)):
                    print("❌ cloud_vertical_vis gagal diisi")
                    return False
            if not _isi_bagian_bawah(driver, row, plan):
                return False
            print("✅ Data berhasil diisi")
            return True

        _catat_waktu("Cuaca, visibilitas, tutupan total")
        # ================ AWAN RENDAH ========================================#
        cloud_low_type = str(row['cloud_low_type_cl']).strip()
        cloud_low_type_code = cloud_low_type.split("-", 1)[0].strip()
        if not pilih_ant_select(driver, "cloud_low_type_cl", cloud_low_type):
            return False  # WAJIB

        if cloud_low_type_code in ("0", "/"):   # [F1.9] "/" juga dinonaktifkan web
            print(f"⚠️ Awan rendah tidak diisi karena cloud_low_type_cl = '{cloud_low_type}'")
        else:
            required_low_fields = (
                "cloud_low_cover_oktas",
                "awan_rendah_jenis",
                "awan_rendah_jumlah",
                "cloud_arah_awan_rendah",
            )
            missing_low_fields = [
                field
                for field in required_low_fields
                if pd.isna(row[field]) or not str(row[field]).strip()
            ]
            if missing_low_fields:
                print(
                    "❌ Data awan rendah wajib kosong: "
                    + ", ".join(missing_low_fields)
                )
                return False

            # [rev 14] kegagalan di bagian awan rendah TIDAK lagi menghentikan pengisian: dicatat di
            # GAGAL_WAJIB, field berikutnya (Jumlah, tinggi dasar, puncak, arah, lapisan lain) tetap diisi.
            if not pilih_ant_select(driver, "cloud_low_cover_oktas", str(row['cloud_low_cover_oktas'])):
                print("❌ cloud_low_cover_oktas gagal dipilih (pengisian dilanjutkan)")
                GAGAL_WAJIB.append(f"cloud_low_cover_oktas '{row['cloud_low_cover_oktas']}' gagal dipilih")

            n_wajib_sebelum = len(GAGAL_WAJIB)
            if not isi_jenis_dan_jumlah_awan_Rendah(driver, str(row['awan_rendah_jenis']), str(row['awan_rendah_jumlah'])):
                print("❌ Jenis/Jumlah Awan Rendah gagal diisi (pengisian dilanjutkan)")
                if len(GAGAL_WAJIB) == n_wajib_sebelum:   # fungsi tidak mencatat sendiri
                    GAGAL_WAJIB.append("Jenis/Jumlah Awan Rendah gagal diisi")

            jenis_awan_rendah = str(row['awan_rendah_jenis']).strip()
            kode_jenis_awan_rendah = jenis_awan_rendah.split("-", 1)[0].strip()
            # [F1.9/R23] aktif jika Jenis 8/9 DAN CL bukan 1 (CL=1: puncak nonaktif di web)
            peak_dan_arah_sebenarnya_aktif = (kode_jenis_awan_rendah in {"8", "9"}
                                              and cloud_low_type_code != "1")

            if pd.notna(row['cloud_low_base_1']):
                if not isi_input(driver, "cloud_low_base_1", str(int(float(row['cloud_low_base_1'])))):
                    GAGAL_OPSIONAL.append("cloud_low_base_1 gagal diisi (field tidak aktif), dilewati")   # [F1.5] dicatat ke log
                    print("⚠️ cloud_low_base_1 gagal diisi (field tidak aktif), dilewati")
            else:
                print("⚠️ cloud_low_base_1 kosong di Excel, dilewati")

            if peak_dan_arah_sebenarnya_aktif:
                if pd.notna(row['cloud_low_peak_1']):
                    peak_1_ok = isi_input(driver, "cloud_low_peak_1", str(int(float(row['cloud_low_peak_1']))))
                    if not peak_1_ok:
                        GAGAL_OPSIONAL.append("cloud_low_peak_1 gagal diisi (field tidak aktif untuk jenis awan ini), dilewati")   # [F1.5] dicatat ke log
                        print("⚠️ cloud_low_peak_1 gagal diisi (field tidak aktif untuk jenis awan ini), dilewati")
                else:
                    peak_1_ok = False
                    print("⚠️ cloud_low_peak_1 kosong di Excel, dilewati")

                # Elevasi hanya dicoba jika peak berhasil
                if peak_1_ok and pd.notna(row['cloud_elevation_1_angle_ec']):
                    if not pilih_ant_select(driver, "cloud_elevation_1_angle_ec", str(row['cloud_elevation_1_angle_ec'])):
                        GAGAL_OPSIONAL.append("cloud_elevation_1_angle_ec gagal dipilih (field tidak aktif), dilewati")   # [F1.5] dicatat ke log
                        print("⚠️ cloud_elevation_1_angle_ec gagal dipilih (field tidak aktif), dilewati")
                elif not peak_1_ok and pd.notna(row['cloud_elevation_1_angle_ec']):
                    print("⚠️ cloud_elevation_1_angle_ec dilewati karena cloud_low_peak_1 tidak aktif")

                # Arah sebenarnya tetap dicoba terlepas dari peak
                if pd.notna(row['cloud_arah_sebenarnya_1']):
                    if not pilih_arah_sebenarnya(driver, str(row['cloud_arah_sebenarnya_1'])):
                        GAGAL_OPSIONAL.append("cloud_arah_sebenarnya_1 gagal dipilih (field tidak aktif), dilewati")   # [F1.5] dicatat ke log
                        print("⚠️ cloud_arah_sebenarnya_1 gagal dipilih (field tidak aktif), dilewati")
            else:
                print(
                    f"ℹ️ cloud_low_peak_1 dan cloud_arah_sebenarnya_1 dilewati karena "
                    f"jenis awan rendah '{jenis_awan_rendah}' bukan 8/9 atau CL=1"
                )

            if pd.notna(row['cloud_arah_awan_rendah']):
                if not pilih_arah_Awan_Rendah(driver, str(row['cloud_arah_awan_rendah'])):
                    print("❌ cloud_arah_awan_rendah gagal dipilih (pengisian dilanjutkan)")
                    GAGAL_WAJIB.append(f"Arah Awan Rendah '{row['cloud_arah_awan_rendah']}' gagal dipilih")

            # [TOLERAN] Awan rendah kedua
            if pd.notna(row['awan_rendah_2_jenis']):
                if not klik_switch_jika_type(driver):
                    GAGAL_OPSIONAL.append("klik_switch_jika_type gagal, dilewati")   # [F1.5] dicatat ke log
                    print("⚠️ klik_switch_jika_type gagal, dilewati")

                if pd.notna(row['cloud_low_base_2']):
                    cloud_low_base_2 = str(int(float(row['cloud_low_base_2'])))
                else:
                    cloud_low_base_2 = ""

                if not isi_jenis_dan_jumlah_awan_rendah_2(driver, str(row['awan_rendah_2_jenis']), str(row['awan_rendah_2_jumlah'])):
                    GAGAL_OPSIONAL.append("Jenis/Jumlah Awan Rendah 2 gagal diisi, dilewati")   # [F1.5] dicatat ke log
                    print("⚠️ Jenis/Jumlah Awan Rendah 2 gagal diisi, dilewati")

                if cloud_low_base_2:
                    if not isi_input(driver, "cloud_low_base_2", cloud_low_base_2):
                        GAGAL_OPSIONAL.append("cloud_low_base_2 gagal diisi (field tidak aktif), dilewati")   # [F1.5] dicatat ke log
                        print("⚠️ cloud_low_base_2 gagal diisi (field tidak aktif), dilewati")

                if cloud_low_type_code != "1":
                    if pd.notna(row['cloud_low_peak_2']):
                        cloud_low_peak_2 = str(int(float(row['cloud_low_peak_2'])))
                    else:
                        cloud_low_peak_2 = ""

                    if cloud_low_peak_2:
                        peak_2_ok = isi_input(driver, "cloud_low_peak_2", cloud_low_peak_2)
                        if not peak_2_ok:
                            GAGAL_OPSIONAL.append("cloud_low_peak_2 gagal diisi (field tidak aktif untuk jenis awan ini), dilewati")   # [F1.5] dicatat ke log
                            print("⚠️ cloud_low_peak_2 gagal diisi (field tidak aktif untuk jenis awan ini), dilewati")
                    else:
                        peak_2_ok = False
                        print("⚠️ cloud_low_peak_2 kosong di Excel, dilewati")

                    # Elevasi hanya dicoba jika peak berhasil
                    if peak_2_ok and pd.notna(row['cloud_elevation_2_angle_ec']):
                        if not pilih_ant_select(driver, "cloud_elevation_2_angle_ec", str(row['cloud_elevation_2_angle_ec'])):
                            GAGAL_OPSIONAL.append("cloud_elevation_2_angle_ec gagal dipilih (field tidak aktif), dilewati")   # [F1.5] dicatat ke log
                            print("⚠️ cloud_elevation_2_angle_ec gagal dipilih (field tidak aktif), dilewati")
                    elif not peak_2_ok and pd.notna(row['cloud_elevation_2_angle_ec']):
                        print("⚠️ cloud_elevation_2_angle_ec dilewati karena cloud_low_peak_2 tidak aktif")

                    # Arah sebenarnya 2 tetap dicoba
                    if pd.notna(row['cloud_arah_sebenarnya_2']):
                        if not pilih_arah_sebenarnya_2(driver, str(row['cloud_arah_sebenarnya_2'])):
                            GAGAL_OPSIONAL.append("cloud_arah_sebenarnya_2 gagal dipilih (field tidak aktif), dilewati")   # [F1.5] dicatat ke log
                            print("⚠️ cloud_arah_sebenarnya_2 gagal dipilih (field tidak aktif), dilewati")

                if pd.notna(row['cloud_arah_2']):
                    if not pilih_arah_2(driver, str(row['cloud_arah_2'])):
                        GAGAL_OPSIONAL.append("cloud_arah_2 gagal dipilih, dilewati")   # [F1.5] dicatat ke log
                        print("⚠️ cloud_arah_2 gagal dipilih, dilewati")
            else:
                # [F1.5] Excel tanpa lapisan 2: matikan switch bila aktif (sisa data lama pada mode Update)
                if _switch_aktif(driver, "775") is True:
                    print("ℹ️ Switch lapisan 2 awan rendah aktif (data lama) tetapi Excel kosong -> dimatikan")
                    _atur_switch(driver, "775", False)
                print("ℹ️ Awan rendah kedua dilewati karena awan_rendah_2_jenis kosong (NaN)")

            # [rev 15] awan rendah ke-3 langsung setelah lapisan 1 & 2 (urutan: rendah 1,2,3)
            isi_lapisan_tambahan(driver, plan, layer="low")
        _catat_waktu("Awan rendah")

        # ================ AWAN MENENGAH ======================================#
        cloud_med_type = str(row['cloud_med_type_cm'])
        cloud_med_type_code = cloud_med_type.split("-", 1)[0].strip()   # [F1.9]
        if not pilih_ant_select(driver, "cloud_med_type_cm", cloud_med_type):
            return False  # WAJIB

        if cloud_med_type == "0 -" or cloud_med_type_code in ("0", "/"):
            print("⚠️ Awan menengah tidak diisi karena cloud_med_type_cm = '0 -'")
        else:
            # [TOLERAN] detail awan menengah
            if not pilih_ant_select(driver, "cloud_med_cover_oktas", str(row['cloud_med_cover_oktas'])):
                GAGAL_OPSIONAL.append("cloud_med_cover_oktas gagal dipilih, dilewati")   # [F1.5] dicatat ke log
                print("⚠️ cloud_med_cover_oktas gagal dipilih, dilewati")

            if not isi_jenis_dan_jumlah_awan_menengah(driver, str(row['awan_menengah_jenis_1']), str(row['awan_menengah_jumlah_1'])):
                GAGAL_OPSIONAL.append("Jenis/Jumlah Awan Menengah gagal diisi, dilewati")   # [F1.5] dicatat ke log
                print("⚠️ Jenis/Jumlah Awan Menengah gagal diisi, dilewati")

            if pd.notna(row['cloud_med_base_1']):
                if not isi_input(driver, "cloud_med_base_1", str(int(float(row['cloud_med_base_1'])))):
                    GAGAL_OPSIONAL.append("cloud_med_base_1 gagal diisi (field tidak aktif), dilewati")   # [F1.5] dicatat ke log
                    print("⚠️ cloud_med_base_1 gagal diisi (field tidak aktif), dilewati")
            else:
                print("⚠️ cloud_med_base_1 kosong di Excel, dilewati")

            if pd.notna(row['cloud_arah_menengah_1']):
                if not pilih_arah_Awan_Menengah(driver, str(row['cloud_arah_menengah_1'])):
                    GAGAL_OPSIONAL.append("cloud_arah_menengah_1 gagal dipilih, dilewati")   # [F1.5] dicatat ke log
                    print("⚠️ cloud_arah_menengah_1 gagal dipilih, dilewati")

            isi_lapisan_tambahan(driver, plan, layer="med")   # [rev 15] menengah ke-2 tepat setelah menengah ke-1
        _catat_waktu("Awan menengah")

        # ================ AWAN TINGGI ========================================#
        cloud_high_type = str(row['cloud_high_type_ch'])
        cloud_high_type_code = cloud_high_type.split("-", 1)[0].strip()   # [F1.9]
        if not pilih_ant_select(driver, "cloud_high_type_ch", cloud_high_type):
            return False  # WAJIB

        if cloud_high_type == "0 -" or cloud_high_type_code in ("0", "/"):
            print("⚠️ Awan tinggi tidak diisi karena cloud_high_type_ch = '0 -'")
        else:
            cover_val = str(row.get('cloud_high_cover_oktas', '')).strip()
            if cover_val in ("", "-", "nan", "NaN"):
                print("⚠️ cloud_high_cover_oktas kosong atau '-', melewati pengisian awan tinggi")
            else:
                if not pilih_ant_select(driver, "cloud_high_cover_oktas", cover_val):
                    GAGAL_OPSIONAL.append(f"Gagal pilih cloud_high_cover_oktas='{cover_val}', melewati detail awan tinggi")   # [F1.5] dicatat ke log
                    print(f"⚠️ Gagal pilih cloud_high_cover_oktas='{cover_val}', melewati detail awan tinggi")
                else:
                    if not isi_jenis_dan_jumlah_awan_Tinggi(driver, str(row['awan_tinggi_jenis']), str(row['awan_tinggi_jumlah'])):
                        GAGAL_OPSIONAL.append("Gagal isi jenis/jumlah awan tinggi, dilewati")   # [F1.5] dicatat ke log
                        print("⚠️ Gagal isi jenis/jumlah awan tinggi, dilewati")

                    if pd.notna(row.get('cloud_high_base_1')) and str(row.get('cloud_high_base_1')).strip() not in ("", "-", "nan", "NaN"):
                        if not isi_input(driver, "cloud_high_base_1", str(int(float(row['cloud_high_base_1'])))):
                            GAGAL_OPSIONAL.append("Gagal isi cloud_high_base_1, dilewati")   # [F1.5] dicatat ke log
                            print("⚠️ Gagal isi cloud_high_base_1, dilewati")
                    else:
                        print("⚠️ cloud_high_base_1 kosong, dilewati")

                    arah_tinggi = row.get('cloud_arah_tinggi')
                    if pd.notna(arah_tinggi) and str(arah_tinggi).strip() not in ("", "-", "nan", "NaN"):
                        if not pilih_arah_Awan_Tinggi(driver, str(arah_tinggi)):
                            GAGAL_OPSIONAL.append("Gagal pilih arah awan tinggi, dilewati")   # [F1.5] dicatat ke log
                            print("⚠️ Gagal pilih arah awan tinggi, dilewati")

            isi_lapisan_tambahan(driver, plan, layer="high")   # [rev 15] tinggi ke-2 tepat setelah tinggi ke-1
        _catat_waktu("Awan tinggi")

        # ============ PENGUAPAN, RADIASI, KEADAAN TANAH, iE, LAMA PENYINARAN (urutan web) ============#
        if not _isi_bagian_bawah(driver, row, plan):
            return False

        # [rev 15] lapisan tambahan yang diminta Excel tetapi gagal diisi = field merah di web (form tidak valid,
        # Preview pasti gagal) -> diperlakukan sebagai kegagalan wajib agar tidak membuang waktu mencoba Preview
        for _g in GAGAL_OPSIONAL:
            if (_g.startswith(("AWAN RENDAH lapisan", "AWAN MENENGAH lapisan", "AWAN TINGGI lapisan"))
                    and _g not in GAGAL_WAJIB):
                GAGAL_WAJIB.append(_g)

        # [rev 14] ringkasan kegagalan wajib: semua field SUDAH dicoba; baris dibatalkan di sini (bukan di tengah)
        if GAGAL_WAJIB:
            print(f"❌ {len(GAGAL_WAJIB)} field WAJIB gagal diisi (field lain sudah dilanjutkan):")
            for _g in GAGAL_WAJIB:
                print(f"   - {_g}")
            if not CFG["features"].get("send_despite_detail_fail", False):
                return False
            print("⚠️ features.send_despite_detail_fail=true: pengiriman TETAP dilanjutkan")

        print("✅ Data berhasil diisi")
        return True

    except Exception as e:
        print(f"❌ Gagal mengisi data: {e}")
        return False

# Sinyal khusus untuk trigger recovery (bukan error biasa)
SESSION_RECOVERY_NEEDED = "SESSION_RECOVERY_NEEDED"
MAX_ROW_RECOVERY = 2  # maksimal berapa kali recovery per baris


def recover_session(current_driver, max_attempts=3, tanggal_utc=None):
    """
    Tutup browser saat ini, buka baru, login ulang, pilih stasiun & tanggal.
    Return: (new_driver, success_bool)
    """
    print("\n" + "="*60)
    print("🔄 MEMULAI PEMULIHAN SESI BROWSER")
    print("="*60)

    # Tutup browser lama
    try:
        current_driver.quit()
        print("✅ Browser lama berhasil ditutup")
    except Exception as e:
        print(f"⚠️ Gagal tutup browser lama (mungkin sudah crash): {e}")

    time.sleep(3)

    for attempt in range(1, max_attempts + 1):
        print(f"\n🔄 Recovery attempt {attempt}/{max_attempts}...")
        new_driver = None
        try:
            # Buka browser baru
            new_driver = buat_driver()   # [rev 28] pembukaan tangguh yang sama dengan awal (profil dibebaskan bila terkunci)
            print("✅ Browser baru berhasil dibuka")

            # Login, popup, stasiun, tanggal
            login(new_driver)
            klik_tombol_oke_popup(drv=new_driver)
            memilih_stasiun(new_driver)
            memilih_tanggal(new_driver, tanggal_utc)

            print("✅ Sesi berhasil dipulihkan — siap melanjutkan pengisian")
            return new_driver, True

        except Exception as e:
            print(f"❌ Recovery attempt {attempt} gagal: {e}")
            try:
                if new_driver:
                    save_debug_snapshot(new_driver, f"recovery_attempt_{attempt}_failed")
                    new_driver.quit()
            except Exception:
                pass

            if attempt < max_attempts:
                wait_time = 5 * attempt  # 5s, 10s, 15s
                print(f"⏳ Menunggu {wait_time}s sebelum retry recovery...")
                time.sleep(wait_time)

    print("❌ Semua attempt recovery gagal, baris akan dilewati")
    return None, False

def cek_ww_field_error(driver):
    """
    Cek apakah field present_weather_ww dalam kondisi error/merah di form.
    Ant Design menambahkan class 'has-error' pada wrapper field yang tidak valid.
    """
    try:
        error_els = driver.find_elements(
            By.XPATH,
            "//div[@id='present_weather_ww']/ancestor::div[contains(@class,'has-error')]"
        )
        return bool(error_els)
    except Exception:
        return False


def fallback_ww_mist_ke_haze(driver, row):
    """
    Fallback otomatis: jika ww=10 (Mist) dan Preview gagal karena RH < 95%,
    ganti ww ke 05 (Haze) lalu klik Preview ulang.

    Return:
        True  → fallback berhasil, Preview OK sudah diklik
        False → fallback tidak berlaku atau tetap gagal
    """
    ww_val = str(row.get('ww', '')).zfill(2)

    # Hanya berlaku jika ww=10
    if ww_val != "10":
        print(f"ℹ️ ww={ww_val}, bukan Mist (10) — fallback tidak berlaku")
        return False

    # Cek konfirmasi: apakah field ww memang merah di form?
    ww_error = cek_ww_field_error(driver)
    print(f"🔍 Status error field ww di form: {'MERAH ❌' if ww_error else 'tidak terdeteksi'}")

    print("\n⚠️ FALLBACK WW MIST→HAZE:")
    print("   ww=10 (Mist) kemungkinan ditolak karena RH < 95%")
    print("   Mengganti ww 10 → 05 (Haze) secara otomatis...")

    # Ganti ww ke 05
    if not pilih_dropdown_ant_select(driver, "present_weather_ww", "05"):
        print("❌ Gagal mengganti ww ke 05, fallback dibatalkan")
        save_debug_snapshot(driver, "fallback_ww_ganti_gagal")
        return False

    print("✅ ww berhasil diganti ke 05 (Haze)")
    time.sleep(0.5)

    # Klik Preview ulang
    print("🔄 Mengklik Preview ulang setelah ganti ww...")
    if not submit_with_retry(driver, "Preview_fallback_ww", lambda: Preview(driver), max_attempts=3):
        print("❌ Preview masih gagal setelah ganti ww ke 05")
        save_debug_snapshot(driver, "fallback_ww_preview_gagal")
        return False

    time.sleep(1)

    # Klik Preview OK
    if not submit_with_retry(driver, "Preview_OK_fallback_ww", lambda: Preview_OK(driver), max_attempts=3):
        print("❌ Preview OK masih gagal setelah ganti ww ke 05")
        save_debug_snapshot(driver, "fallback_ww_preview_ok_gagal")
        return False

    print("✅ Fallback ww 10→05 berhasil, Preview OK sudah diklik")
    PERUBAHAN_OTOMATIS["ww"] = "10->05 (Mist->Haze, RH<95%)"   # [F1.4] dicatat di log
    return True

def gerbang_persetujuan(slot, sandi, tampil=True):
    """[F3.5] Jendela hitung-mundur sebelum SEND. True = kirim (bawaan: tanpa tindakan, ditutup, atau tanpa layar TETAP kirim);
    False = pengamat menekan Batalkan. Galat apa pun pada jendela -> True (gerbang tidak boleh menggagalkan kirim)."""
    g = CFG.get("gerbang", {})
    detik = int(g.get("detik", 20))
    if not (g.get("aktif", True) and tampil and detik > 0):
        return True
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("SYNOP: konfirmasi kirim")
        root.attributes("-topmost", True)
        hasil = {"kirim": True}
        teks = tk.StringVar()
        tk.Label(root, text=f"Jam {slot[1]} UTC akan dikirim:", font=("Segoe UI", 11, "bold")).pack(padx=16, pady=(14, 4))
        tk.Label(root, text=sandi or "(sandi tidak terbaca)", font=("Consolas", 10), justify="left").pack(padx=16)
        tk.Label(root, textvariable=teks).pack(pady=6)

        def batal():
            hasil["kirim"] = False
            root.destroy()

        def tick(n):
            if n <= 0:
                root.destroy()
                return
            teks.set(f"Terkirim otomatis dalam {n} dtk")
            root.after(1000, tick, n - 1)

        tk.Button(root, text="Batalkan", command=batal).pack(side="left", padx=16, pady=12)
        tk.Button(root, text="Kirim sekarang", command=root.destroy).pack(side="right", padx=16, pady=12)
        root.protocol("WM_DELETE_WINDOW", root.destroy)   # menutup jendela = kirim (bawaan)
        tick(detik)
        root.mainloop()
        return hasil["kirim"]
    except Exception as e:
        print(f"ℹ️ Gerbang persetujuan tidak tampil ({type(e).__name__}); data tetap dikirim")
        return True


def main():
    global driver, STATION_ID, PASSWORD, nama_observer, DRY_RUN  # driver global: bisa diganti setelah recovery

    args = parse_args()
    if args.dry_run:
        DRY_RUN = True
    filter_jam = {j.strip() for j in args.jam.split(",") if j.strip()} if args.jam else None

    validator = Validator.from_config(CFG, BUNDLE)
    db = SendLog(resolve_path(CFG, "db"))
    for _t, _j in db.pulihkan_terhenti():   # [rev 23] sisa status 'berjalan' dari proses yang terhenti -> 'gagal' (jujur)
        print(f"🩹 Slot {_t} {_j} UTC tertinggal 'berjalan' (proses sebelumnya berhenti) -> dicatat GAGAL; bisa dicoba ulang")

    # [F1.3] validasi seluruh Excel saat start (laporan; baris ERROR dilewati saat waktunya)
    df_cek = baca_data_terbaru(silent=True)
    if df_cek is None:
        print(f"❌ Excel tidak bisa dibaca: {EXCEL_PATH}")
        return
    file_issues, hasil_cek = validator.validate_dataframe(df_cek)
    print("\n" + "=" * 70 + "\n🔎 VALIDASI EXCEL\n" + "=" * 70)
    print(format_report(file_issues, hasil_cek, show_info=False))
    for rr0 in hasil_cek:
        if rr0.slot[0]:
            db.register(rr0.slot[0], rr0.slot[1], waktu_eksekusi=rr0.waktu_eksekusi, plan=rr0.plan)
    if args.check_only:
        return

    # [F1.1] kredensial dari .env
    STATION_ID, PASSWORD = get_credentials()

    # [F1.6] launcher observer (+ opsi dry-run)
    if args.observer:
        nama_observer = args.observer.strip()
    else:
        pilihan = None if args.no_gui else pilih_observer_gui(daftar_observer_aktif(), DRY_RUN)
        if pilihan == "BATAL":
            print("Dibatalkan.")
            return
        if pilihan is None:
            nama_observer = input("Masukkan nama observer: ").strip()
        else:
            nama_observer, DRY_RUN = pilihan
    print(f"👤 Observer: {nama_observer} | mode: {'DRY-RUN (tidak mengirim)' if DRY_RUN else 'KIRIM'}")

    print(f"📥 Sumber data: {'DATABASE (form web: python app.py)' if SUMBER_DATA == 'db' else 'file Excel'}")

    # [F3.7] notifikasi Telegram (aman: error notifikasi tidak pernah menggagalkan pengiriman)
    notifier = Notifier.from_config(CFG, dry_run=DRY_RUN)
    print("📣 Telegram:", "aktif" if notifier.aktif else
          "nonaktif (isi TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID di .env untuk mengaktifkan)")

    driver = buat_driver()
    login(driver)
    klik_tombol_oke_popup(drv=driver)
    memilih_stasiun(driver)
    if _SPEED.get("ukur_latensi", True):
        ukur_latensi(driver)
    tanggal_aktif = None   # [F1.5] tanggal UTC yang sedang dipilih di web; dipilih per slot

    df_sebelumnya = None
    last_check_time = time.time()
    observer_selected = False

    while True:
        df_awal = baca_data_terbaru(silent=True)
        if df_awal is None:
            print("🔄 Menunggu 30 detik sebelum mencoba lagi...")
            time.sleep(30)
            continue

        df_sebelumnya = df_awal.copy()

        for index in range(len(df_awal)):
            kunci_slot = _kunci_baris(df_awal.iloc[index])   # [F2.7] baris dikenali dari slotnya, bukan nomor urut
            print(f"\n🔄 Membaca ulang data sebelum memproses baris {index+1}")
            df = baca_data_terbaru(silent=True)
            pos = _posisi(df, kunci_slot, index)
            if df is None or pos is None:
                print(f"⚠️ Data tidak valid untuk baris {index+1}, melewati...")
                continue

            pos0 = _posisi(df_sebelumnya, kunci_slot, index)
            if pos0 is None or not df.iloc[pos].equals(df_sebelumnya.iloc[pos0]):
                print(f"\n⚠️ PERHATIAN: Data baris {index+1} berubah!")
                if pos0 is not None:
                    for col in df.columns:
                        if col in df_sebelumnya.columns and str(df.iloc[pos][col]) != str(df_sebelumnya.iloc[pos0][col]):
                            print(f"📌 {col}: {df_sebelumnya.iloc[pos0][col]} → {df.iloc[pos][col]}")
                df_sebelumnya = df.copy()

            row = df.iloc[pos]
            waktu_eksekusi = row['waktu_eksekusi'].to_pydatetime()
            sekarang = datetime.now()

            # [F1.4/F1.5] slot & status log: sudah terkirim -> jangan kirim ulang
            rr0 = validator.validate_row(row, index + 2)
            slot0 = rr0.slot
            keputusan = db.should_send(*slot0) if slot0[0] else {"send": True, "reason": "", "needs_web_check": False}
            if filter_jam and slot0[1] not in filter_jam:   # --jam: abaikan jam lain tanpa mencatat
                continue
            if slot0[0] and not keputusan["send"]:
                print(f"⏩ Melewati baris {index+1} ({slot0[1]} UTC): {keputusan['reason']}")
                continue

            if waktu_eksekusi < sekarang:
                terlambat_menit = (sekarang - waktu_eksekusi).total_seconds() / 60.0
                batas_retry = CFG["runtime"].get("retry_past_minutes", 0)
                if args.process_past:
                    print(f"⏪ Baris {index+1} ({slot0[1]} UTC) sudah lewat {terlambat_menit:.0f} menit; diproses sekarang (--process-past)")
                elif slot0[0] and keputusan.get("needs_web_check") and 0 < batas_retry and terlambat_menit <= batas_retry:
                    print(f"🔁 Baris {index+1} ({slot0[1]} UTC) dicoba ulang ({terlambat_menit:.0f} menit setelah jadwal): {keputusan['reason']}")
                else:
                    print(f"⏩ Melewati baris {index+1} karena waktu eksekusi {waktu_eksekusi} sudah lewat")
                    if slot0[0] and (db.get(*slot0) or {}).get("status") == "pending":
                        db.mark_skipped(*slot0, "waktu eksekusi sudah lewat")
                    continue

            waktu_tunggu = (waktu_eksekusi - sekarang).total_seconds()
            print(f"\n⏳ Menunggu sampai {waktu_eksekusi} untuk eksekusi baris {index+1}...")
            sesi_dicek = False   # [rev 28] sesi BMKG Satu diperiksa sekali per slot, menjelang eksekusi
            pra_cek = float((CFG.get("session", {}) or {}).get("cek_sebelum_detik", 180))
            pasif_detik = float((CFG.get("session", {}) or {}).get("pantau_pasif_detik", 60))
            tick_sesi = 0.0

            # Countdown + monitoring perubahan Excel
            while waktu_tunggu > 0:
                sekarang = datetime.now()
                waktu_tunggu = (waktu_eksekusi - sekarang).total_seconds()

                if time.time() - last_check_time >= 2:
                    df_baru = baca_data_terbaru(silent=True)
                    pos_baru = _posisi(df_baru, kunci_slot, index)
                    if df_baru is not None and pos_baru is not None:
                        if not df_baru.iloc[pos_baru].equals(df.iloc[pos]):
                            print(f"\n⚠️ PERHATIAN: Data baris {index+1} berubah selama countdown!")
                            for col in df.columns:
                                if col in df_baru.columns and str(df_baru.iloc[pos_baru][col]) != str(df.iloc[pos][col]):
                                    print(f"📌 {col}: {df.iloc[pos][col]} → {df_baru.iloc[pos_baru][col]}")
                            row = df_baru.iloc[pos_baru]
                            waktu_eksekusi = row['waktu_eksekusi'].to_pydatetime()
                            df = df_baru
                            pos = pos_baru
                            df_sebelumnya = df.copy()
                            sekarang = datetime.now()
                            waktu_tunggu = (waktu_eksekusi - sekarang).total_seconds()
                    notifier.rekap_jika_waktunya(db)   # [F3.7] rekap harian (sekali/hari, dibatasi 1x/menit)
                    last_check_time = time.time()

                if time.time() - tick_sesi >= pasif_detik:   # [rev 35] pantau pasif (baca DOM saja): popup 'sesi habis' ditangani segera
                    tick_sesi = time.time()
                    if sesi_habis(driver) is True:
                        _ok_s, _muat = pastikan_sesi(notifier, slot0, paksa=True)
                        if _muat:
                            observer_selected = False
                            tanggal_aktif = None
                    cek_selector_berkala(driver, notifier, slot0)

                if not sesi_dicek and waktu_tunggu <= pra_cek:
                    sesi_dicek = True
                    print()
                    _ok_s, _muat = pastikan_sesi(notifier, slot0)
                    if _muat:
                        observer_selected = False   # halaman dimuat ulang: observer & tanggal dipilih ulang di langkah baris
                        tanggal_aktif = None
                    sekarang = datetime.now()
                    waktu_tunggu = (waktu_eksekusi - sekarang).total_seconds()

                mins, secs = divmod(max(0, waktu_tunggu), 60)
                print(f"\r⏳ Akan dieksekusi dalam: {int(mins):02d}:{int(secs):02d}", end="", flush=True)
                time.sleep(1)

            if not sesi_dicek:   # tidak ada waktu tunggu (mis. --process-past): periksa sesi sekarang bila sudah lama tidak dipastikan
                _ok_s, _muat = pastikan_sesi(notifier, slot0)
                if _muat:
                    observer_selected = False
                    tanggal_aktif = None

            print("\n🚀 Eksekusi dimulai...")

            # [F1.3/F1.5] validasi ulang data TERBARU (Excel bisa berubah saat countdown)
            rr = validator.validate_row(row, index + 2)
            slot = rr.slot
            for isu in rr.issues:
                if isu.level != "INFO":
                    print(f"   {isu}")
            if rr.errors:
                alasan = "validasi ERROR: " + "; ".join(i.message for i in rr.errors[:2])
                print(f"⛔ Baris {index+1} DILEWATI — {alasan}")
                if slot[0]:
                    db.mark_skipped(*slot, alasan)
                    notifier.dilewati_validasi(slot, alasan)   # [F3.7] data TIDAK terkirim -> beri tahu
                continue
            if slot[0]:
                db.register(slot[0], slot[1], waktu_eksekusi=waktu_eksekusi, plan=rr.plan)
                if not db.should_send(*slot)["send"]:
                    print(f"⏩ Melewati baris {index+1}: sudah terkirim")
                    continue
                db.start_attempt(*slot, observer=nama_observer)
            PERUBAHAN_OTOMATIS.clear()
            HUJAN_OVERRIDE_LOG.clear()
            PENGUAPAN_LOG.clear()
            GAGAL_OPSIONAL.clear()
            GAGAL_WAJIB.clear()

            # ── LOOP RECOVERY PER BARIS ───────────────────────────────────────
            row_recovery_count = 0
            row_processed = False
            gagal_terakhir = None   # [F3.7] (pesan, screenshot) kegagalan terakhir baris ini
            # [rev 30] tangga percobaan ulang: gagal SEBELUM tombol kirim akhir -> aman diulang (muat ulang halaman, lalu browser baru)
            rt = CFG["runtime"]
            max_percobaan = max(1, int(rt.get("max_row_attempts", 3)))
            max_menit_baris = float(rt.get("max_row_menit", 25))
            percobaan_umum = 0          # berapa kali baris ini sudah diulang karena galat biasa
            baris_menyerah = False
            tak_pasti = False           # gagal SETELAH tombol kirim akhir -> kemungkinan sudah terkirim (tidak boleh dikirim ulang)
            t_mulai_baris = datetime.now()
            set_slot_aktif(slot)        # [rev 30] snapshot dinamai dengan slot ini

            while row_recovery_count <= MAX_ROW_RECOVERY and not row_processed and not baris_menyerah:
                titik_tak_kembali = False   # menjadi True setelah tombol SEND final diklik

                if row_recovery_count > 0:
                    print(f"\n🔁 Mengulang baris {index+1} setelah recovery "
                          f"(attempt {row_recovery_count}/{MAX_ROW_RECOVERY})...")

                try:
                    print(f"\n🚀 Memproses baris {index+1} pada {datetime.now()}")
                    print(f"🔎 observer_selected: {observer_selected}")

                    # [F1.5] pilih tanggal UTC sesuai slot (bukan tanggal saat script dimulai)
                    # [rev 35] dipilih (ulang) bila belum pernah, ATAU tampilan web tak cocok (kosong/tanggal lain; mis. halaman dimuat ulang diam-diam)
                    if slot[0] and (tanggal_aktif != slot[0] or tanggal_di_web(driver) not in (None, slot[0])):
                        if memilih_tanggal(driver, slot[0]) is False:
                            raise Exception(f"Gagal memilih tanggal {slot[0]} di web")
                        tanggal_aktif = slot[0]
                    if slot[0]:
                        terpilih = tanggal_di_web(driver)
                        if terpilih is not None and terpilih != slot[0]:
                            tanggal_aktif = None
                            raise Exception(f"Tanggal di web ({terpilih}) tidak sama dengan slot ({slot[0]})")

                    if not isi_per_jam(driver, row):
                        raise Exception("Gagal pilih jam")

                    _jeda(2)
                    Fill_AWS_Digi(driver)
                    _jeda(1)
                    cek_selector_form(driver, notifier, slot)   # [F3.9] lapor bila struktur web berubah, sebelum pengisian & SEND

                    if not observer_selected:
                        # Tambah wait eksplisit: tunggu dropdown observer benar-benar siap
                        print("⏳ Menunggu form dan dropdown observer siap...")
                        wait_for_clickable(
                            driver,
                            (By.XPATH, "//label[contains(text(), 'Nama Observer')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"),
                            timeout=15
                        )
                        if memilih_observer(driver):
                            observer_selected = True
                        else:
                            # Observer gagal tapi tidak fatal — form masih bisa diisi
                            # observer_selected tetap False agar dicoba ulang di baris berikutnya
                            print("⚠️ Observer gagal dipilih, melanjutkan pengisian tanpa observer...")

                    # ── TITIK DETEKSI UTAMA ──────────────────────────────────
                    # Jika form pengisian tidak muncul = web/sesi bermasalah
                    form_appeared = wait_for_presence(
                        driver, (By.ID, "present_weather_ww"), timeout=15
                    )
                    if not form_appeared:
                        save_debug_snapshot(
                            driver,
                            f"form_not_appeared_row_{index+1}_recovery_{row_recovery_count}"
                        )
                        raise Exception(
                            f"{SESSION_RECOVERY_NEEDED}: Form pengisian tidak muncul "
                            f"setelah Fill_AWS_Digi pada baris {index+1}. "
                            f"Kemungkinan web error, popup tidak muncul, atau sesi expired."
                        )
                    # ────────────────────────────────────────────────────────

                    wait_for_clickable(
                        driver,
                        (By.XPATH, "//div[@id='present_weather_ww']//div[contains(@class,'ant-select-selection__rendered')]"),
                        timeout=15
                    )

                    _t_isi = time.time()
                    if not isi_data(driver, row, plan=rr.plan):
                        _detail = ("; ".join(GAGAL_WAJIB))[:300] if GAGAL_WAJIB else "lihat log di atas"
                        raise Exception(f"Gagal isi data; membatalkan pengiriman untuk baris ini ({_detail})")
                    _dur_isi = time.time() - _t_isi
                    print(f"⏱️ Pengisian data jam ini: {_dur_isi:.0f} dtk")   # [rev 29/F3.3] pantau waktu per jam
                    if slot[0]:
                        db.log_event(*slot, "waktu_isi", f"{_dur_isi:.0f} dtk")

                    # [F1.5] rangkum field opsional yang gagal diisi (sebelumnya hanya peringatan di layar)
                    if GAGAL_OPSIONAL:
                        print(f"⚠️ {len(GAGAL_OPSIONAL)} field opsional GAGAL diisi (data tidak lengkap):")
                        for _g in GAGAL_OPSIONAL:
                            print(f"   - {_g}")
                        PERUBAHAN_OTOMATIS["gagal_opsional"] = list(GAGAL_OPSIONAL)
                        if slot[0]:
                            db.log_event(*slot, "gagal_opsional", "; ".join(GAGAL_OPSIONAL)[:400])
                        if CFG["features"].get("fail_on_optional", False):
                            raise Exception("Field opsional gagal diisi dan features.fail_on_optional=true")

                    # [F1.5/T21] data jam ini sudah ada di web -> tombol "Update"
                    if _mode_kirim(driver) == "update":
                        print("ℹ️ Data jam ini SUDAH ADA di web (mode Update)")
                        if slot[0]:
                            db.log_event(*slot, "mode_update", "data jam ini sudah ada di web")
                        if not CFG["features"].get("allow_update", True):
                            if slot[0]:
                                db.mark_skipped(*slot, "data sudah ada di web (mode Update) dan features.allow_update=false")
                            print("⏩ Dilewati karena features.allow_update=false")
                            row_processed = True
                            continue

                    # 🔒 SUBMISSION CHAIN
                    _jeda(1)
                    if not submit_with_retry(driver, "Preview", lambda: Preview(driver), max_attempts=3):
                        raise Exception("Gagal klik Preview setelah 3 percobaan")

                    _jeda(1)
                    print("🔄 [1/3] Mencoba Preview_OK...")
                    preview_ok_berhasil = False
                    ww_error_terdeteksi = False

                    for attempt in range(1, 4):
                        if attempt > 1:
                            print(f"🔄 [{attempt}/3] Mencoba Preview_OK...")

                        if Preview_OK(driver):
                            preview_ok_berhasil = True
                            print(f"✅ Preview_OK berhasil pada attempt {attempt}")
                            break

                        ww_val = str(row.get('ww', '')).zfill(2)
                        if ww_val == "10" and cek_ww_field_error(driver):
                            print(f"🔍 Terdeteksi error ww=10 (Mist) setelah attempt {attempt}")
                            print("⚡ Langsung ke fallback tanpa menunggu retry berikutnya")
                            ww_error_terdeteksi = True
                            break

                        if attempt < 3:
                            wait_time = 1 + (attempt - 1) * 0.5
                            print(f"⏳ Preview_OK gagal ({attempt}/3), menunggu {wait_time}s sebelum retry...")
                            time.sleep(wait_time)
                        else:
                            print("❌ Preview_OK gagal setelah 3 percobaan")
                            save_debug_snapshot(driver, "preview_ok_gagal_3x")

                    if not preview_ok_berhasil:
                        print("⚠️ Preview OK gagal, memeriksa apakah perlu fallback ww Mist→Haze...")
                        fallback_berhasil = fallback_ww_mist_ke_haze(driver, row)
                        if not fallback_berhasil:
                            raise Exception("Gagal klik Preview OK setelah percobaan dan fallback ww")
                        if slot[0]:
                            db.log_event(*slot, "ww_diubah", PERUBAHAN_OTOMATIS.get("ww", "ww 10->05"))   # [F3.6]
    
                    # [F1.4/F1.7] simpan sandi hasil Preview; dry-run berhenti di sini
                    sandi = baca_sandi(driver)
                    if sandi and slot[0]:
                        db.set_kode_synop(*slot, sandi)
                        print("🧾 Sandi:\n" + sandi)

                    # [F3.4] verifikasi sandi: bandingkan dengan data Excel (+ kewajaran data AWS)
                    if CFG["features"].get("verify_sandi", True):
                        hasil_cek = None
                        if not sandi:
                            print("⚠️ Sandi tidak terbaca dari halaman; verifikasi dilewati")
                        else:
                            try:
                                hasil_cek = verifikasi_sandi(
                                    sandi, row, plan=rr.plan,
                                    abaikan=("ww",) if "ww" in PERUBAHAN_OTOMATIS else (),
                                    cfg=CFG["features"])
                                print(format_hasil_sandi(hasil_cek))
                                if slot[0]:
                                    db.log_event(*slot, "verifikasi_sandi", hasil_cek.ringkas())
                                if not hasil_cek.ok:
                                    PERUBAHAN_OTOMATIS["verifikasi_sandi"] = hasil_cek.ringkas()
                            except Exception as e_cek:   # verifikator tidak boleh menggagalkan pengiriman
                                print(f"⚠️ Verifikasi sandi error (dilewati): {type(e_cek).__name__}: {e_cek}")
                        if (hasil_cek is not None and hasil_cek.errors and not DRY_RUN
                                and CFG["features"].get("sandi_block_on_mismatch", False)):
                            raise Exception("Verifikasi sandi gagal; pengiriman dibatalkan: " + hasil_cek.ringkas())
                    if DRY_RUN:
                        print("🧪 DRY-RUN: sampai Preview selesai; TIDAK mengirim.")
                        if slot[0]:
                            db.mark_skipped(*slot, "dry-run (tidak dikirim)")
                        row_processed = True
                        continue

                    if not gerbang_persetujuan(slot, sandi, tampil=not args.no_gui):   # [F3.5]
                        print("🛑 Dibatalkan pengamat sebelum SEND; jam ini tidak dikirim")
                        if slot[0]:
                            db.mark_skipped(*slot, "dibatalkan pengamat sebelum SEND (F3.5)")
                            db.log_event(*slot, "dibatalkan_pengamat", "jendela gerbang persetujuan")
                        notifier.kirim(f"🛑 Jam {slot[1]} UTC DIBATALKAN pengamat sebelum SEND (tidak dikirim).", "gagal")
                        row_processed = True
                        continue

                    _jeda(1)
                    if not submit_with_retry(driver, "Send_And_Submit", lambda: SEND_SEND_SUBMIT(driver), max_attempts=2):
                        raise Exception("Gagal klik Send & Submit setelah 2 percobaan")

                    print("ℹ️ Menggunakan alur Send & Submit")
                    if not submit_with_retry(driver, "Send_INASWITCH_Submit", lambda: SEND_INASWITCH_SUBMIT(driver), max_attempts=2):
                        print("⚠️ Tombol Send to INASwitching & Submit tidak ditemukan, fallback ke Send to INASwitching")
                        if not submit_with_retry(driver, "SEND_INASWITCH", lambda: SEND_INASWITCH(driver), max_attempts=3):
                            raise Exception("Gagal klik SEND INASWITCH setelah 3 percobaan")

                    print("⏳ Menunggu popup GTS muncul (buffer)...")
                    _jeda(3)   # SEND_GTS sendiri menunggu modal sampai 10 dtk
                    print("📨 Menunggu popup SEND final...")
                    if not submit_with_retry(driver, "SEND_GTS_final", lambda: SEND_GTS(driver), max_attempts=3):
                        raise Exception("Gagal klik SEND GTS final setelah 3 percobaan")
                    titik_tak_kembali = True   # [rev 30] SEND final sudah diklik: mulai sini galat TIDAK boleh memicu kirim ulang

                    _jeda(1)
                    if not submit_with_retry(driver, "SEND_GTS_OK", lambda: SEND_GTS_OK(driver), max_attempts=3):
                        raise Exception("Gagal klik SEND GTS OK setelah 3 percobaan")

                    # [F3.11] popup susulan (Koreksi QC dsb.) bisa muncul SETELAH OK; data baru terkirim
                    # setelah popup itu dikonfirmasi -> jangan mencatat 'sent' sebelum layar tenang
                    try:
                        pasca_ok, pasca_pesan = selesaikan_pasca_kirim(driver)
                    except Exception as e_pasca:   # [rev 30] galat membaca layar SESUDAH kirim: status tak diketahui, bukan "gagal"
                        pasca_ok, pasca_pesan = None, f"{type(e_pasca).__name__}: {str(e_pasca).splitlines()[0] if str(e_pasca) else ''}"
                    if "koreksi_qc" in PERUBAHAN_OTOMATIS and slot[0]:
                        db.log_event(*slot, "koreksi_qc", PERUBAHAN_OTOMATIS["koreksi_qc"])
                    if pasca_ok is None:
                        if BERHASIL_TERLIHAT:
                            print(f"⚠️ Galat saat memeriksa layar pasca-kirim ({pasca_pesan}), tetapi web menyatakan BERHASIL -> dicatat terkirim")
                            PERUBAHAN_OTOMATIS["pasca_kirim"] = "pemeriksaan layar pasca-kirim error: " + pasca_pesan[:120]
                            pasca_ok = True
                        else:
                            raise Exception("Setelah SEND: pemeriksaan layar error (" + pasca_pesan + "); data kemungkinan SUDAH terkirim")
                    elif not pasca_ok:
                        titik_tak_kembali = False   # kegagalan yang DIKETAHUI (popup galat/QC tak terkonfirmasi): data belum terkirim
                        raise Exception("Setelah SEND: " + pasca_pesan + " (data BELUM terkirim)")

                    print("✅✅✅ PENGIRIMAN BERHASIL ✅✅✅")
                    if slot[0]:
                        db.mark_sent(*slot, kode_synop=sandi or None,
                                     diubah_otomatis=dict(PERUBAHAN_OTOMATIS) or None,
                                     hujan_override=dict(HUJAN_OVERRIDE_LOG) or None)
                    notifier.sukses(slot, sandi, dict(PERUBAHAN_OTOMATIS) or None)   # [F3.7]
                    row_processed = True  # tandai sukses, keluar dari loop recovery
                    _tandai_sesi_ok()

                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Error saat memproses baris {index+1}: {error_msg}")
                    gagal_terakhir = [error_msg, None]
                    sesi_mati = SESSION_RECOVERY_NEEDED not in error_msg and sesi_habis(driver) is True   # [rev 28] ter-logout di tengah baris
                    if sesi_mati:
                        print("🔓 Terdeteksi ter-logout dari BMKG Satu di tengah pengisian -> diperlakukan sebagai masalah sesi")
                    sesi_terkait = SESSION_RECOVERY_NEEDED in error_msg or sesi_mati
                    lewat_batas = (datetime.now() - t_mulai_baris).total_seconds() / 60.0 > max_menit_baris

                    # ── pilih tindakan ────────────────────────────────────────
                    if titik_tak_kembali:
                        aksi = "cek_manual"            # SEND final sudah diklik: jangan kirim ulang
                    elif lewat_batas:
                        aksi = "menyerah"
                        print(f"⏱️ Baris ini sudah memakan > {max_menit_baris:.0f} menit; tidak diulang lagi")
                    elif sesi_terkait:
                        aksi = "recovery" if row_recovery_count < MAX_ROW_RECOVERY else "menyerah"
                    else:
                        aksi = "ulang" if percobaan_umum + 1 < max_percobaan else "menyerah"

                    if slot[0]:   # snapshot + jejak audit (status tetap 'berjalan' selama masih akan diulang)
                        try:
                            png = save_debug_snapshot(driver, f"gagal-percobaan{percobaan_umum + 1 + row_recovery_count}")
                        except Exception:
                            png = None
                        gagal_terakhir[1] = png
                        if aksi in ("recovery", "ulang"):
                            db.log_event(*slot, "percobaan_gagal", f"percobaan {percobaan_umum + 1 + row_recovery_count}: {error_msg[:250]}")

                    if aksi == "cek_manual":
                        tak_pasti = True
                        print("⚠️ Galat terjadi SETELAH tombol kirim akhir diklik: data KEMUNGKINAN SUDAH TERKIRIM — tidak dikirim ulang otomatis")
                        baris_menyerah = True
                    elif aksi == "menyerah":
                        print(f"❌ Menyerah untuk baris {index+1} (percobaan {percobaan_umum + 1 + row_recovery_count})")
                        baris_menyerah = True
                    elif aksi == "recovery":
                        row_recovery_count += 1
                        print(f"\n⚠️ DETEKSI MASALAH SESI/WEB — memulai recovery ({row_recovery_count}/{MAX_ROW_RECOVERY})...")
                        new_driver, recovery_ok = recover_session(driver, tanggal_utc=slot[0])
                        notifier.recovery(slot, recovery_ok)   # [F3.7]
                        if recovery_ok:
                            driver = new_driver
                            observer_selected = False
                            tanggal_aktif = None
                            print(f"✅ Recovery berhasil, mengulang baris {index+1}...")
                            time.sleep(2)
                        else:
                            print(f"❌ Recovery gagal total, melewati baris {index+1}")
                            baris_menyerah = True
                    else:   # "ulang": galat biasa sebelum kirim -> coba lagi dari awal dengan keadaan halaman yang bersih
                        percobaan_umum += 1
                        tingkat = "muat ulang halaman" if percobaan_umum == 1 else "buka browser baru"
                        print(f"\n🔁 PERCOBAAN ULANG {percobaan_umum + 1}/{max_percobaan} untuk jam {slot[1]} UTC ({tingkat})...")
                        try:
                            notifier.kirim(f"⚠️ Jam {slot[1]} UTC ({slot[0]}) gagal diisi: {error_msg[:160]}\n"
                                           f"🔁 Mencoba ulang {percobaan_umum + 1}/{max_percobaan} ({tingkat}).", "recovery")
                        except Exception:
                            pass
                        siap = False
                        if percobaan_umum == 1:
                            try:
                                try:
                                    driver.switch_to.alert.accept()   # alert JS yang menggantung menghalangi navigasi
                                except Exception:
                                    pass
                                segarkan_sesi(driver)
                                siap = True
                            except Exception as e_soft:
                                print(f"⚠️ Muat ulang halaman gagal ({type(e_soft).__name__}); membuka browser baru...")
                        if not siap:
                            new_driver, recovery_ok = recover_session(driver, tanggal_utc=slot[0])
                            notifier.recovery(slot, recovery_ok)
                            if recovery_ok:
                                driver = new_driver
                                siap = True
                        if siap:
                            observer_selected = False   # halaman baru: observer & tanggal dipilih ulang
                            tanggal_aktif = None
                            time.sleep(2)
                        else:
                            print("❌ Tidak bisa menyiapkan halaman baru; baris dilewati")
                            baris_menyerah = True

            set_slot_aktif(None)
            if not row_processed and gagal_terakhir and slot[0]:   # [F3.7] gagal akhir (setelah semua percobaan)
                pesan_akhir = gagal_terakhir[0]
                if tak_pasti:
                    pesan_akhir = f"{TANDA_CEK_MANUAL} {pesan_akhir}"
                db.mark_failed(*slot, pesan_akhir, screenshot_path=gagal_terakhir[1])
                if tak_pasti:
                    notifier.perlu_cek_manual(slot, gagal_terakhir[0], screenshot=gagal_terakhir[1])
                else:
                    notifier.gagal(slot, gagal_terakhir[0], percobaan=(db.get(*slot) or {}).get("percobaan"),
                                   screenshot=gagal_terakhir[1])

            time.sleep(2)

        print("\n✅ Semua data dalam file telah diproses")
        try:   # [F1.4] ringkasan log hari ini (UTC)
            print("📒 Ringkasan log:", db.summary(datetime.now(timezone.utc).strftime("%Y-%m-%d")))
        except Exception:
            pass
        notifier.rekap_jika_waktunya(db)   # [F3.7]
        print("🔄 Memeriksa data baru dalam 10 detik...")
        time.sleep(10)


def _tambah_argumen_restart():
    """Pastikan main() yang dijalankan ulang TIDAK menampilkan launcher lagi: observer & mode dry-run dibawa."""
    if nama_observer and "--observer" not in sys.argv:
        sys.argv += ["--observer", nama_observer]
    if "--no-gui" not in sys.argv:
        sys.argv.append("--no-gui")
    if DRY_RUN and "--dry-run" not in sys.argv:
        sys.argv.append("--dry-run")


def jalankan_dengan_pengawas():
    """[rev 30] Bila main() berhenti karena galat tak terduga (mis. Chrome crash saat Anda tidur), jalankan ulang otomatis
    (runtime.auto_restart_maks kali per jam). Tiap kegagalan diberitahukan lewat Telegram. KeyboardInterrupt tidak diulang."""
    rt = CFG["runtime"]
    maks = int(rt.get("auto_restart_maks", 5))
    jeda = float(rt.get("auto_restart_jeda_detik", 30))
    waktu_galat = []
    while True:
        try:
            main()
            return
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            if maks <= 0:
                raise
            sekarang = time.time()
            waktu_galat = [t for t in waktu_galat if sekarang - t < 3600] + [sekarang]
            ringkas = f"{type(e).__name__}: {str(e).splitlines()[0][:160] if str(e) else ''}"
            print(f"\n🚨 Bot berhenti karena galat: {ringkas}\n{traceback.format_exc()}")
            if len(waktu_galat) > maks:
                print(f"❌ Sudah {maks}x restart dalam 1 jam; pengawas menyerah")
                raise
            try:
                Notifier.from_config(CFG).kirim(
                    f"🚨 Bot SYNOP berhenti karena galat: {ringkas}\n"
                    f"🔄 Restart otomatis dalam {jeda:.0f} dtk ({len(waktu_galat)}/{maks} per jam).", "gagal")
            except Exception:
                pass
            try:
                if driver is not None:
                    driver.quit()
            except Exception:
                pass
            set_slot_aktif(None)
            _tambah_argumen_restart()
            time.sleep(jeda)


if __name__ == "__main__":
    try:
        jalankan_dengan_pengawas()
    except KeyboardInterrupt:
        try:   # [rev 23] Ctrl+C saat slot berjalan: jangan biarkan status 'berjalan' menggantung di dashboard
            _db_stop = SendLog(resolve_path(CFG, "db"))
            _db_stop.pulihkan_terhenti("dihentikan manual (Ctrl+C) saat slot ini berjalan")
        except Exception:
            pass
        raise
    except Exception as _e_fatal:   # [F3.7] skrip berhenti karena error tak tertangani -> beri tahu
        try:
            Notifier.from_config(CFG).fatal(f"{type(_e_fatal).__name__}: {_e_fatal}")
        except Exception:
            pass
        raise
