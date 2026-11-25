# -*- coding: utf-8 -*-
"""
Rev 30 - pelajaran dari kirim nyata 2026-11-22 (jam 18/22/23 UTC): galat stale pasca-kirim, klik dropdown yang kadang gagal,
kalender yang tidak terpilih; plus nama snapshot, pengawas auto-restart, dan penanda cek-manual.
Tanpa browser/jaringan asli:   python tests/test_rev30_bot.py
"""
import importlib.util
import os
import re
import sys
import tempfile
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
    spec = importlib.util.spec_from_file_location("V7_rev30", ROOT / "V7SATU.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    jam = {"t": 0.0}
    M.time = types.SimpleNamespace(sleep=lambda s: jam.__setitem__("t", jam["t"] + float(s)), time=lambda: jam["t"],
                                   perf_counter=_t.perf_counter)
    M.WebDriverWait = lambda drv, t: types.SimpleNamespace(until=lambda fn: _tunggu(M, drv, t, fn, jam))
    return M


def _tunggu(M, drv, t, fn, jam):
    akhir = jam["t"] + t
    while True:
        try:
            r = fn(drv)
        except Exception:
            r = False
        if r:
            return r
        if jam["t"] >= akhir:
            raise M.TimeoutException("timeout")
        jam["t"] += 0.5


# ======================================================================================================== kalender
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException

M = muat()


class Btn:
    def __init__(self, drv, nama, attrs=None):
        self.drv, self.nama, self.attrs = drv, nama, attrs or {}
    def get_attribute(self, a):
        if self.nama == "tgl" and a == "aria-expanded":
            return "true" if self.drv.buka else "false"
        if self.nama == "tgl" and a == "value":
            return ""
        return self.attrs.get(a)
    def click(self):
        self.drv.klik(self.nama)
    def is_displayed(self): return True
    def send_keys(self, *a): pass


class DrvKal:
    """Kalender bootstrap-vue palsu. bulan_tampil=(tahun,bulan). cell_muncul_setelah = jumlah pemeriksaan sebelum sel tampak."""
    def __init__(self, bulan=(2026, 11), kalender_bisa_buka=True, cell_muncul_setelah=0, klik_sel_gagal=False,
                 disabled=(), next_disabled=True, klik_diam=0, vue_bisa=True):
        self.buka, self.bulan = False, bulan
        self.bisa, self.lag, self.klik_gagal, self.disabled = kalender_bisa_buka, cell_muncul_setelah, klik_sel_gagal, set(disabled)
        self.next_disabled = next_disabled
        self.js_klik, self.dipilih, self.ditutup_esc = [], None, 0
        self.klik_diam, self.vue_bisa = klik_diam, vue_bisa   # klik_diam = berapa klik sel yang 'diam' (tak memilih; kasus 24 Nov)
        self.tgl = Btn(self, "tgl")
    def klik(self, nama, js=False):
        self.js_klik.append((nama, js))
        if nama == "tgl":
            if self.bisa:
                self.buka = not self.buka
        elif nama == "prev":
            y, m = self.bulan; self.bulan = (y, m - 1) if m > 1 else (y - 1, 12)
        elif nama == "next":
            y, m = self.bulan; self.bulan = (y, m + 1) if m < 12 else (y + 1, 1)
        elif nama.startswith("sel:"):
            if self.klik_diam > 0:
                self.klik_diam -= 1; return
            self.dipilih = nama[4:]; self.buka = False
    def find_element(self, by, v):
        if v == "input-datepicker":
            return self.tgl
        if by == "tag name":
            return Btn(self, "body")
        m = re.search(r"@data-date='([\d-]+)'", v)
        if m and self.buka:
            tgl = m.group(1)
            if (int(tgl[:4]), int(tgl[5:7])) == self.bulan:
                if self.lag > 0:
                    self.lag -= 1
                    raise NoSuchElementException("belum dirender")
                return CellEl(self, tgl, "true" if tgl in self.disabled else None)
        raise NoSuchElementException(v)
    def find_elements(self, by, v):
        if "@title='Previous month'" in v:
            return [Btn(self, "prev", {"title": "Previous month"})]
        if "@title='Next month'" in v:
            return [Btn(self, "next", {"title": "Next month", "aria-disabled": "true" if self.next_disabled else None})]
        return []
    def execute_script(self, js, *a):
        if "querySelectorAll" in js and "data-date" in js:
            return f"{self.bulan[0]}-{self.bulan[1]:02d}-15" if self.buka else None
        if "input-datepicker__value_" in js:   # [rev 35] pembacaan tanggal terpilih: [data-selected, label]
            ymd = self.dipilih or ""
            return [ymd, (f"{ymd[8:]}/{ymd[5:7]}/{ymd[:4]}" if ymd else "")]
        if "localYMD" in js:   # [rev 35] cadangan terakhir (Vue)
            if self.vue_bisa:
                self.dipilih, self.buka = a[0], False
            return self.vue_bisa
        if ".click()" in js:
            el = a[0]
            if isinstance(el, CellEl):
                self.klik("sel:" + el.tgl, js=True)
            else:
                self.klik(el.nama, js=True)
        return None


class CellEl:
    def __init__(self, drv, tgl, dis):
        self.drv, self.tgl, self.dis = drv, tgl, dis
    def get_attribute(self, a): return self.dis if a == "aria-disabled" else None
    def click(self):
        if self.drv.klik_gagal:
            raise ElementClickInterceptedException("diblokir elemen lain")
        self.drv.klik("sel:" + self.tgl)
    def is_displayed(self): return True


print("== memilih_tanggal: kalender terbuka & tanggal dipilih ==")
d = DrvKal()
check("tanggal di bulan berjalan dipilih", M.memilih_tanggal(d, "2026-11-22") is True and d.dipilih == "2026-11-22", d.js_klik)
check("kalender DIBUKA sekali saja (klik kedua akan menutupnya)", [k for k in d.js_klik if k[0] == "tgl"] == [("tgl", True)], d.js_klik)

d = DrvKal(bulan=(2026, 12))
check("slot akhir bulan lalu (30 Nov) saat kalender di Desember -> pindah bulan lalu terpilih",
      M.memilih_tanggal(d, "2026-11-30") is True and d.dipilih == "2026-11-30" and [k[0] for k in d.js_klik].count("prev") == 1, d.js_klik)
d = DrvKal(bulan=(2026, 11))
check("slot 3 bulan lalu -> 3x 'Previous month'", M.memilih_tanggal(d, "2026-08-15") is True and [k[0] for k in d.js_klik].count("prev") == 3)

d = DrvKal(klik_sel_gagal=True)
check("klik biasa pada sel diblokir -> cadangan klik JavaScript", M.memilih_tanggal(d, "2026-11-22") is True and d.dipilih == "2026-11-22")

d = DrvKal(cell_muncul_setelah=4)
check("sel baru dirender lambat -> tetap terpilih (tunggu keberadaan, bukan 'clickable')", M.memilih_tanggal(d, "2026-11-22") is True)

d = DrvKal(kalender_bisa_buka=False)
check("kalender tak pernah terbuka -> False setelah 3 percobaan (bukan lanjut diam-diam)",
      M.memilih_tanggal(d, "2026-11-22") is False and d.dipilih is None)

d = DrvKal(disabled=["2026-11-22"])
check("tanggal dinonaktifkan kalender -> False, tidak diklik paksa", M.memilih_tanggal(d, "2026-11-22") is False and d.dipilih is None)


print("== [rev 35] kalender: klik 'diam' (kasus 24 Nov 11:00 UTC) tidak lagi dianggap berhasil ==")
d = DrvKal(klik_diam=1)
check("klik biasa diam -> cara 'js' memilih; hasil terverifikasi", M.memilih_tanggal(d, "2026-11-22") is True and d.dipilih == "2026-11-22", d.js_klik)
d = DrvKal(klik_diam=3)
check("semua klik diam -> cadangan 'vue' memilih & terverifikasi", M.memilih_tanggal(d, "2026-11-22") is True and d.dipilih == "2026-11-22", d.js_klik)
d = DrvKal(klik_diam=99, vue_bisa=False)
check("semua cara gagal -> False (BUKAN True palsu seperti sebelum rev 35)", M.memilih_tanggal(d, "2026-11-22") is False and d.dipilih is None)
check("tanggal_di_web: belum dipilih -> '' ; sudah -> YYYY-MM-DD",
      M.tanggal_di_web(DrvKal()) == "" and M.tanggal_di_web(type("D", (DrvKal,), {})(klik_diam=0)) == "")
d = DrvKal(); d.dipilih = "2026-11-24"
check("tanggal_di_web membaca tanggal terpilih", M.tanggal_di_web(d) == "2026-11-24")
check("parser label: dd/mm/yyyy, 'Selasa, 24 November 2026', ISO, asing -> None",
      [M._tgl_dari_teks(x) for x in ("24/11/2026", "Selasa, 24 November 2026", "2026-11-24", "xyz")] == ["2026-11-24"] * 3 + [None])

print("== [rev 35 / F3.9] health check selector ==")
from core import health
hilang = health.periksa(lambda js, ids, lab: ["input-jam", "label:tanggal"])
check("elemen hilang dilaporkan apa adanya", hilang == ["input-jam", "label:tanggal"], hilang)
seen = {}
health.periksa(lambda js, ids, lab: seen.update(ids=ids) or [], form=True)
check("mode form memeriksa kerangka + field berid wajib (ww, vv, CL...)", "input-jam" in seen["ids"] and "present_weather_ww" in seen["ids"] and "visibility_vv" in seen["ids"], seen)
check("mode form tidak memeriksa field bersyarat (mis. cloud_vertical_vis)", "cloud_vertical_vis" not in seen["ids"])
check("galat membaca halaman -> dilaporkan, tidak melempar", health.periksa(lambda *a: 1 / 0)[0].startswith("(tidak terbaca"))
M2 = muat()
pesan = []
class N:
    def kirim(self, t, jenis): pesan.append((t, jenis))
class DH:
    current_url = "https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik"
    def find_elements(self, *a): return []
    def execute_script(self, js, ids=None, lab=None): return ["select-observer"]
M2.CFG["health"] = {"aktif": True, "cek_detik": 0}
M2.cek_selector_form(DH(), N(), ("2026-11-24", "11:00")); M2.cek_selector_form(DH(), N(), ("2026-11-24", "11:00"))
check("selector hilang -> 1 pesan Telegram (jenis 'selector'), tidak diulang-ulang", len(pesan) == 1 and pesan[0][1] == "selector", pesan)

# ======================================================================================================== snapshot
print("== nama snapshot: slot + jam di depan ==")
M = muat()
M.CFG["runtime"]["timezone_offset_hours"] = 7
M.set_slot_aktif(("2026-11-22", "22:00"))
n = M._nama_snapshot("gagal-percobaan1")
check("format <TANGGAL>_<JAM>UTC__<ket>__<waktu>WIB", re.fullmatch(r"20261122_2200UTC__gagal-percobaan1__\d{8}-\d{6}WIB", n), n)
M.set_slot_aktif(None)
check("tanpa slot aktif -> 'tanpa-slot'", M._nama_snapshot("login_gagal").startswith("tanpa-slot__login_gagal__"))
M.set_slot_aktif(("2026-11-22", "06:00"))
check("karakter aneh pada tag dibersihkan", "/" not in M._nama_snapshot("a b/c:d") and "a-b-c-d" in M._nama_snapshot("a b/c:d"))
M.CFG["runtime"]["timezone_offset_hours"] = 8
check("zona selain +7 diberi label LOKAL (bukan salah menulis WIB)", M._nama_snapshot("x").endswith("LOKAL"))
M.CFG["runtime"]["timezone_offset_hours"] = 7
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    M.SNAPSHOT_DIR = tmp
    M.set_slot_aktif(("2026-11-22", "22:00"))

    class DS:
        page_source = "<html></html>"
        def save_screenshot(self, p): open(p, "wb").write(b"png")

    png = M.save_debug_snapshot(DS(), "gagal-percobaan2")
    files = sorted(os.listdir(tmp))
    check("png & html tersimpan dengan awalan slot yang sama", len(files) == 2 and all(f.startswith("20261122_2200UTC__gagal-percobaan2__") for f in files), files)
    check("jalur png dikembalikan (untuk log & Telegram)", png and png.endswith(".png") and os.path.exists(png))

# ======================================================================================================== pasca kirim
print("== selesaikan_pasca_kirim: tahan StaleElementReference ==")
M = muat()
M.CFG["features"]["qc_popup_tenang"] = 1
M.CFG["features"]["qc_popup_tunggu"] = 3
M.tangani_popup_koreksi_qc = lambda drv, tunggu=0: {"muncul": False, "diklik": False, "teks": ""}


class ElStale:
    def find_elements(self, *a): raise M.StaleElementReferenceException("stale element reference")


urut = [(ElStale(), "Input Data Input data sinoptik berhasil", False)]
M._popup_swal_lain = lambda drv: urut.pop(0) if urut else None
ok, pesan = M.selesaikan_pasca_kirim(object())
check("popup 'berhasil' lalu elemen stale (kasus jam 18 UTC) -> BERHASIL, tidak melempar", ok is True and pesan == "", (ok, pesan))
check("keberhasilan yang dinyatakan web tercatat (BERHASIL_TERLIHAT)", M.BERHASIL_TERLIHAT is True)

M.BERHASIL_TERLIHAT = False
M._popup_swal_lain = lambda drv: (_ for _ in ()).throw(M.StaleElementReferenceException("stale"))
ok, pesan = M.selesaikan_pasca_kirim(object())
check("stale TERUS-MENERUS tanpa bukti -> False + pesan jelas (bukan melempar)", ok is False and "stale" in pesan, (ok, pesan))

M.BERHASIL_TERLIHAT = False
urut2 = [(ElStale(), "Berhasil: data tersimpan", False)]
M._popup_swal_lain = lambda drv: urut2.pop(0) if urut2 else (_ for _ in ()).throw(M.StaleElementReferenceException("stale"))
ok, pesan = M.selesaikan_pasca_kirim(object())
check("stale terus setelah 'berhasil' terlihat -> hasil = berhasil", ok is True or (ok is not False and M.BERHASIL_TERLIHAT), (ok, pesan))

M._popup_swal_lain = lambda drv: (types.SimpleNamespace(find_elements=lambda *a: []), "Gagal menyimpan data", True)
ok, pesan = M.selesaikan_pasca_kirim(object())
check("popup galat sungguhan tetap dilaporkan GAGAL", ok is False and "popup galat" in pesan, (ok, pesan))

# ======================================================================================================== pengawas
print("== pengawas auto-restart ==")
M = muat()
M.CFG["runtime"].update({"auto_restart_maks": 3, "auto_restart_jeda_detik": 5})
pesan = []


class N:
    @classmethod
    def from_config(cls, *a, **k): return cls()
    def kirim(self, t, j="info", **k): pesan.append(t)


M.Notifier = N
panggil = []


def main_galat_sekali():
    panggil.append(list(sys.argv))
    if len(panggil) == 1:
        raise RuntimeError("Chrome crash")


argv0 = list(sys.argv)
sys.argv = ["V7SATU.py"]
M.nama_observer, M.DRY_RUN = "Ananda Maulana", False
M.main = main_galat_sekali
M.jalankan_dengan_pengawas()
check("main() galat 1x -> dijalankan ulang otomatis lalu selesai normal", len(panggil) == 2, len(panggil))
check("restart membawa observer & --no-gui (tanpa launcher saat tidak ada yang menjaga)",
      "--observer" in panggil[1] and "Ananda Maulana" in panggil[1] and "--no-gui" in panggil[1], panggil[1])
check("Telegram diberi tahu penyebab & restart", len(pesan) == 1 and "Chrome crash" in pesan[0] and "Restart otomatis" in pesan[0], pesan)

sys.argv = ["V7SATU.py", "--observer", "X", "--no-gui"]
panggil.clear(); pesan.clear()
M.main = lambda: (panggil.append(1), (_ for _ in ()).throw(RuntimeError("selalu")))[1]
try:
    M.jalankan_dengan_pengawas(); ok = False
except RuntimeError:
    ok = True
check("galat terus-menerus: menyerah setelah > auto_restart_maks per jam (tidak looping selamanya)", ok and len(panggil) == 4, len(panggil))

panggil.clear()
M.main = lambda: (panggil.append(1), (_ for _ in ()).throw(KeyboardInterrupt()))[1]
try:
    M.jalankan_dengan_pengawas(); ok = False
except KeyboardInterrupt:
    ok = True
check("Ctrl+C tidak pernah di-restart", ok and len(panggil) == 1, len(panggil))

M.CFG["runtime"]["auto_restart_maks"] = 0
panggil.clear()
M.main = lambda: (panggil.append(1), (_ for _ in ()).throw(RuntimeError("x")))[1]
try:
    M.jalankan_dengan_pengawas(); ok = False
except RuntimeError:
    ok = True
check("auto_restart_maks=0 -> pengawas mati (perilaku lama)", ok and len(panggil) == 1)
sys.argv = argv0

# ======================================================================================================== db & notifier
print("== should_send: gagal-setelah-kirim tidak dikirim ulang ==")
from core.db import SendLog, TANDA_CEK_MANUAL
from core.notify import Notifier

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    log = SendLog(Path(tmp) / "x.db")
    log.register("2026-11-22", "18:00"); log.start_attempt("2026-11-22", "18:00", "T")
    log.mark_failed("2026-11-22", "18:00", f"{TANDA_CEK_MANUAL} stale element")
    k = log.should_send("2026-11-22", "18:00")
    check("[CEK-MANUAL] -> send=False (cegah kirim ganda), alasan menyebut cek manual", k["send"] is False and "cek manual" in k["reason"], k)
    log.register("2026-11-22", "19:00"); log.start_attempt("2026-11-22", "19:00", "T")
    log.mark_failed("2026-11-22", "19:00", "Gagal isi data")
    k = log.should_send("2026-11-22", "19:00")
    check("gagal biasa -> tetap boleh dicoba ulang", k["send"] is True and k["needs_web_check"] is True, k)
    check("atur ulang manual dari dashboard tetap bisa membuka kembali slot cek-manual", log.atur_ulang("2026-11-22", "18:00") is not None
          and log.should_send("2026-11-22", "18:00")["send"] is True)
    log.close()

print("== notifier: perlu_cek_manual ==")
n = Notifier.from_config({"notify": {"enabled": False}}, dry_run=False)
kirim, alarm = [], []
n.kirim = lambda teks, jenis="info", foto=None: kirim.append((teks, jenis, foto)) or True
n.alarm = lambda: alarm.append(1)
n.perlu_cek_manual(("2026-11-22", "18:00"), "stale element reference", screenshot="a.png")
t = kirim[0][0]
check("pesan memuat slot, 'KEMUNGKINAN SUDAH TERKIRIM', 'TIDAK mengirim ulang', dan langkah tindak lanjut",
      "2026-11-22 18:00" in t and "KEMUNGKINAN SUDAH TERKIRIM" in t and "TIDAK mengirim ulang" in t and "terkirim manual" in t, t)
check("dikirim sebagai jenis 'gagal' dengan screenshot & alarm suara", kirim[0][1] == "gagal" and kirim[0][2] == "a.png" and alarm == [1])
kirim.clear()
n.gagal(("2026-11-22", "22:00"), "Arah Awan Rendah gagal")
check("pesan gagal akhir menyatakan percobaan ulang otomatis sudah habis", "percobaan ulang otomatis habis" in kirim[0][0], kirim[0][0])

print("== konfigurasi bawaan rev 30 ==")
from core.config import load_config
C = load_config()["runtime"]
check("retry_past_minutes=90, max_row_attempts=3, max_row_menit=25, auto_restart tersedia",
      C["retry_past_minutes"] == 90 and C["max_row_attempts"] == 3 and C["max_row_menit"] == 25 and C["auto_restart_maks"] == 5, C)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
