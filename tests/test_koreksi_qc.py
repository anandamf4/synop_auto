# -*- coding: utf-8 -*-
"""
Uji F3.11: popup web "Koreksi QC" setelah Send/OK, TANPA browser:  python tests/test_koreksi_qc.py

DOM tiruan memakai struktur SweetAlert2 (swal2-container/swal2-popup/swal2-title/swal2-confirm) dan
XPath dijalankan sungguhan oleh lxml terhadap HTML itu; jam virtual (sleep memajukan waktu) sehingga
skenario "popup muncul N detik setelah OK" bisa diuji cepat.

Memerlukan: pip install lxml
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))

from lxml import html as LH  # noqa: E402

spec = importlib.util.spec_from_file_location("V7SATU_qc", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

T = {"t": 0.0}
M.time = types.SimpleNamespace(sleep=lambda s: T.__setitem__("t", T["t"] + float(s)), time=lambda: T["t"])
SNAPS = []
M.save_debug_snapshot = lambda drv, tag="debug": SNAPS.append(tag)

PAGE = ('<html><body><div id="page"><button id="pagesubmit">Submit</button>'
        '<button id="sendsubmit">Send &amp; Submit</button></div></body></html>')

QC_TEKS = ("pressure_qff_mb_derived: Step Check - Selisih Batas Bawah 1005.1, Selisih Batas Atas 1011.1<br>"
           "pressure_qfe_mb_derived: Step Check - Selisih Batas Bawah 1002.1, Selisih Batas Atas 1008.1<br>"
           "temp_drybulb_c_tttttt: Step Check - Selisih Batas Bawah 30.6, Selisih Batas Atas 36.6")


def qc_html(id_="qc", tombol_submit=True, tombol_cek=True, teks=QC_TEKS, style=""):
    sub = '<button type="button" class="swal2-confirm swal2-styled">Submit</button>' if tombol_submit else ""
    cek = '<button type="button" class="swal2-cancel swal2-styled">Cek Data</button>' if tombol_cek else ""
    return (f'<div id="{id_}" style="{style}" class="swal2-container swal2-center swal2-backdrop-show">'
            '<div class="swal2-popup swal2-modal swal2-icon-warning swal2-show" role="dialog">'
            '<div class="swal2-icon swal2-warning"><div class="swal2-icon-content">!</div></div>'
            f'<h2 class="swal2-title">Koreksi QC</h2><div class="swal2-html-container">{teks}</div>'
            f'<div class="swal2-actions">{sub}{cek}</div></div></div>')


def ok_html(id_="okpop", judul="Success", isi="Data berhasil dikirim", error=False):
    ikon = "swal2-icon-error" if error else "swal2-icon-success"
    return (f'<div id="{id_}" class="swal2-container swal2-center swal2-backdrop-show">'
            f'<div class="swal2-popup swal2-modal {ikon} swal2-show" role="dialog">'
            f'<div class="swal2-icon"></div><h2 class="swal2-title">{judul}</h2>'
            f'<div class="swal2-html-container">{isi}</div>'
            '<div class="swal2-actions"><button type="button" class="swal2-confirm swal2-styled">OK</button>'
            '</div></div></div>')


class El:
    def __init__(self, node, drv):
        self.node, self.drv = node, drv

    def _hidden(self):
        n = self.node
        while n is not None:
            if "display:none" in (n.get("style") or "").replace(" ", "") or n.get("data-removed"):
                return True
            n = n.getparent()
        return False

    def is_displayed(self):
        return not self._hidden()

    def is_enabled(self):
        return self.node.get("disabled") is None

    @property
    def text(self):
        out = []
        for n in self.node.iter():
            if n.tag in ("div", "h2", "br", "button", "p"):
                out.append("\n")
            if n.text:
                out.append(n.text)
            if n.tail:
                out.append(n.tail)
        return "".join(out)

    def click(self):
        self.drv.on_click(self.node)

    def find_elements(self, by, xp):
        return [El(n, self.drv) for n in self.node.xpath(xp)]


class Drv:
    """events: daftar (waktu, fungsi(drv)) yang dijalankan saat waktu virtual tercapai."""

    def __init__(self, events=(), submit_menutup=True, setelah_submit=None):
        self.root = LH.fromstring(PAGE)
        self.events = sorted(events, key=lambda e: e[0])
        self.klik = []
        self.submit_menutup = submit_menutup
        self.setelah_submit = setelah_submit      # fungsi(drv) setelah Submit QC diklik
        self.n_qc = 0

    def sync(self):
        while self.events and self.events[0][0] <= T["t"]:
            self.events.pop(0)[1](self)

    def tambah(self, html):
        self.root.find("body").append(LH.fromstring(html))

    def hapus(self, id_):
        for n in self.root.xpath(f"//*[@id='{id_}']"):
            n.set("data-removed", "1")

    def find_elements(self, by, xp):
        self.sync()
        return [El(n, self) for n in self.root.xpath(xp)]

    def execute_script(self, *a, **k):
        return None

    def on_click(self, node):
        teks = (node.text_content() or "").strip()
        induk = node
        while induk is not None and induk.get("id") not in ("qc", "qc2", "okpop", "pagesubmit", "sendsubmit"):
            induk = induk.getparent()
        iid = induk.get("id") if induk is not None else None
        self.klik.append((iid, teks))
        if iid in ("qc", "qc2") and teks == "Submit":
            self.n_qc += 1
            if self.submit_menutup:
                self.hapus(iid)
            if self.setelah_submit:
                self.setelah_submit(self)
        elif iid == "okpop" and teks == "OK":
            self.hapus("okpop")


M.attempt_click = lambda drv, el: (el.click(), True)[1]

passed = failed = 0


def check(nama, kondisi, info=""):
    global passed, failed
    print(("  OK   " if kondisi else "  GAGAL"), nama, "" if kondisi else f"-> {info}")
    passed += bool(kondisi)
    failed += (not kondisi)


def baru(**kw):
    T["t"] = 0.0
    SNAPS.clear()
    M.PERUBAHAN_OTOMATIS.clear()
    M.CFG["features"]["qc_popup_auto_submit"] = kw.pop("auto", True)
    M.CFG["features"]["qc_popup_tunggu"] = 12
    M.CFG["features"]["qc_popup_tenang"] = 4
    return Drv(**kw)


def tambah_qc(at, id_="qc", **kw):
    return (at, lambda d: d.tambah(qc_html(id_, **kw)))


def klik_qc_submit(d):
    return [k for k in d.klik if k[0] in ("qc", "qc2") and k[1] == "Submit"]


print("== pasca-kirim: popup muncul SETELAH OK terakhir ==")
d = baru(events=[tambah_qc(2.0)])
ok, pesan = M.selesaikan_pasca_kirim(d)
check("popup muncul 2 dtk setelah OK -> Submit diklik, hasil berhasil", ok and pesan == "" and len(klik_qc_submit(d)) == 1,
      (ok, pesan, d.klik))
check("yang diklik tombol Submit DI DALAM popup, bukan Submit/Send&Submit halaman",
      not [k for k in d.klik if k[0] in ("pagesubmit", "sendsubmit")], d.klik)
check("tombol 'Cek Data' TIDAK pernah diklik", not [k for k in d.klik if k[1] == "Cek Data"], d.klik)
ket = M.PERUBAHAN_OTOMATIS.get("koreksi_qc", "")
check("isi popup tercatat (Step Check, nilai batas) tanpa judul/tombol", "Step Check" in ket and "1005.1" in ket
      and "Submit dikonfirmasi" in ket and "Cek Data" not in ket, ket)
check("screenshot+HTML bukti diambil", "koreksi_qc" in SNAPS, SNAPS)

d = baru(events=[tambah_qc(3.5)])
ok, pesan = M.selesaikan_pasca_kirim(d)
check("popup yang terlambat (3,5 dtk, sebelum layar dianggap tenang) tetap tertangkap", ok and len(klik_qc_submit(d)) == 1,
      (ok, d.klik))

d = baru()
ok, pesan = M.selesaikan_pasca_kirim(d)
check("tidak ada popup -> berhasil, tidak ada klik apa pun", ok and not d.klik and "koreksi_qc" not in M.PERUBAHAN_OTOMATIS,
      (ok, d.klik))
check("layar tenang dicapai sekitar 4 dtk (tidak menunggu lama)", 3.5 <= T["t"] <= 6.0, T["t"])

d = baru(events=[tambah_qc(1.0)], setelah_submit=lambda dr: dr.tambah(ok_html()))
ok, pesan = M.selesaikan_pasca_kirim(d)
check("Koreksi QC lalu popup sukses (OK): keduanya ditutup, berhasil",
      ok and len(klik_qc_submit(d)) == 1 and ("okpop", "OK") in d.klik, (ok, pesan, d.klik))

d = baru(events=[(1.0, lambda dr: dr.tambah(ok_html(judul="Gagal", isi="Gagal mengirim ke GTS", error=True)))])
ok, pesan = M.selesaikan_pasca_kirim(d)
check("popup GALAT setelah SEND -> dianggap gagal (bukan sukses)", (not ok) and "galat" in pesan, (ok, pesan))
check("popup galat difoto sebagai bukti", "popup_galat_setelah_kirim" in SNAPS, SNAPS)

print("\n== pasca-kirim: kegagalan harus terlihat, tidak diam-diam 'terkirim' ==")
d = baru(events=[tambah_qc(1.0, tombol_submit=False)])
ok, pesan = M.selesaikan_pasca_kirim(d)
check("popup tanpa tombol Submit -> gagal, 'Cek Data' tidak diklik", (not ok) and "Koreksi QC" in pesan
      and not [k for k in d.klik if k[1] == "Cek Data"], (ok, pesan, d.klik))
d = baru(events=[tambah_qc(1.0)], submit_menutup=False)
ok, pesan = M.selesaikan_pasca_kirim(d)
check("Submit diklik tetapi popup tidak menutup -> gagal", not ok, (ok, pesan))
d = baru(events=[tambah_qc(1.0)], auto=False)
ok, pesan = M.selesaikan_pasca_kirim(d)
check("qc_popup_auto_submit=false: tidak mengklik apa pun, gagal, tercatat butuh konfirmasi manual",
      (not ok) and not d.klik and "BUTUH KONFIRMASI MANUAL" in M.PERUBAHAN_OTOMATIS.get("koreksi_qc", ""), (ok, d.klik))

d = baru(events=[tambah_qc(1.0)], setelah_submit=lambda dr: dr.tambah(qc_html("qc2")) if dr.n_qc == 1 else None)
ok, pesan = M.selesaikan_pasca_kirim(d)
check("popup QC muncul lagi satu kali setelah Submit: ditangani dua kali", ok and d.n_qc == 2, (ok, d.n_qc, d.klik))

state = {"n": 0}


def selalu_muncul(dr):
    state["n"] += 1
    dr.tambah(qc_html("qc2"))


d = baru(events=[tambah_qc(1.0)], setelah_submit=selalu_muncul)
ok, pesan = M.selesaikan_pasca_kirim(d)
check("popup QC muncul terus-menerus -> berhenti setelah 3x dan GAGAL (tidak loop tanpa akhir)",
      (not ok) and "berulang" in pesan and d.n_qc <= 4, (ok, pesan, d.n_qc))

d = baru(events=[tambah_qc(0.0, style="display: none")])
ok, pesan = M.selesaikan_pasca_kirim(d)
check("popup tersembunyi (display:none) tidak dianggap muncul", ok and not d.klik, (ok, d.klik))

print("\n== sebelum/ketika klik SEND (wait_for_send_ok_button, wait_for_submit_progress, SEND_GTS_OK) ==")
d = baru(events=[tambah_qc(0.0)])
check("wait_for_send_ok_button: popup QC -> Submit diklik, True", M.wait_for_send_ok_button(d, timeout=12)
      and len(klik_qc_submit(d)) == 1, d.klik)
d = baru(events=[(0.0, lambda dr: dr.tambah(ok_html()))])
check("wait_for_send_ok_button: hanya tombol OK (alur normal) -> True, tanpa klik", M.wait_for_send_ok_button(d, timeout=12)
      and not d.klik, d.klik)
d = baru()
check("wait_for_send_ok_button: tidak ada apa pun -> False (timeout)", M.wait_for_send_ok_button(d, timeout=3) is False)
d = baru(events=[tambah_qc(0.0, tombol_submit=False)])
check("wait_for_send_ok_button: popup QC tak bisa dikonfirmasi -> False", M.wait_for_send_ok_button(d, timeout=3) is False)

d = baru(events=[tambah_qc(0.0)])
check("wait_for_submit_progress: popup QC muncul lebih awal dianggap progres + dikonfirmasi",
      M.wait_for_submit_progress(d, timeout=5) is True and len(klik_qc_submit(d)) == 1, d.klik)

d = baru(events=[tambah_qc(0.0), (0.0, lambda dr: dr.tambah(ok_html()))])
M.wait_for_clickable = lambda drv, loc, timeout=10: next(
    (e for e in drv.find_elements(None, "//div[@id='okpop']//button") if e.is_displayed()), None)
hasil = M.SEND_GTS_OK(d)
urutan = [k[0] for k in d.klik]
check("SEND_GTS_OK: popup QC di atas tombol OK ditangani DULU, baru OK diklik",
      hasil is True and urutan[:2] == ["qc", "okpop"], (hasil, d.klik))
d = baru(events=[tambah_qc(0.0, tombol_submit=False), (0.0, lambda dr: dr.tambah(ok_html()))])
check("SEND_GTS_OK: popup QC tak bisa dikonfirmasi -> False, OK tidak diklik menembus popup",
      M.SEND_GTS_OK(d) is False and ("okpop", "OK") not in d.klik, d.klik)

print("\n== varian DOM & teks ==")
varian = ('<div id="qc" class="ant-modal-content" role="dialog"><div class="ant-modal-title">Koreksi QC</div>'
          '<p>temp_wetbulb_c: Step Check</p><button>Submit</button><button>Cek Data</button></div>')
d = baru(events=[(0.0, lambda dr: dr.tambah(varian))])
ok, pesan = M.selesaikan_pasca_kirim(d)
check("cadangan: dialog non-SweetAlert berjudul 'Koreksi QC' juga ditangani", ok and len(klik_qc_submit(d)) == 1, (ok, d.klik))
check("ringkas teks: judul & tombol dibuang, spasi dirapikan",
      M._ringkas_teks_qc("Koreksi QC\n a   b \n c\nSubmit\nCek Data") == "a b c", M._ringkas_teks_qc("Koreksi QC\n a   b \n c\nSubmit\nCek Data"))

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
