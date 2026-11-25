# -*- coding: utf-8 -*-
"""
tools/pantau_web.py  -  SKRIP PEMANTAU perilaku web BMKG Satu (rev 27)

Tujuan: merekam perilaku web SUNGGUHAN saat bot berjalan, lalu menghasilkan laporan yang bisa diunggah untuk
mengambil keputusan (mengganti jeda sleep, profil Chrome, ID kolom jam 00 UTC, dll). Hasilnya ada di folder
pantau_out/<waktu>_<mode>/ dan zip-nya (pantau_<waktu>_<mode>.zip). Isi laporan:
  laporan.txt   ringkasan terbaca manusia: waktu tiap langkah, jeda sleep vs kerja nyata, tunggu yang habis waktu,
                kolom form (label, id, nilai dari AWS, aktif/nonaktif) pada tiap titik
  laporan.json  data lengkap (semua kejadian + semua kolom form)
  dom_*.json / dom_*.png / dom_*.html   potret halaman tiap titik (setelah Fill AWS, sebelum/sesudah isi data, Preview)
  log_konsol.txt  seluruh keluaran konsol bot

MODE
  jelajah  (AMAN, hanya membaca)  login -> pilih stasiun -> tanggal -> jam -> Fill AWS Digi -> potret kolom. TIDAK mengisi
           data, TIDAK mengirim. Cocok untuk melihat bagian bawah jam 00 UTC (penguapan, radiasi, dst).
             python tools/pantau_web.py --mode jelajah --tanggal 2026-11-21 --jam 00:00,03:00,07:00
  dryrun   menjalankan bot ASLI sampai Preview (tidak mengirim) sambil memantau.
             python tools/pantau_web.py --mode dryrun --observer "Nama" --no-gui -- --jam 00:00 --process-past
  kirim    seperti dryrun tetapi MENGIRIM sungguhan (kasus nyata). Wajib tambah --izinkan-kirim.
             python tools/pantau_web.py --mode kirim --izinkan-kirim --observer "Nama" --no-gui -- --jam 00:00 --process-past
Argumen setelah tanda `--` diteruskan apa adanya ke bot (V7SATU.py).
Sebelum mengunggah zip, periksa isinya: tidak memuat kata sandi, tetapi memuat nama stasiun/observer dan data observasi.
"""
import argparse
import atexit
import datetime as dt
import functools
import importlib
import json
import sys
import time as _real_time
import traceback
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.paths import ROOT  # noqa: E402  [rev 36] mode .exe: pantau_out/ di samping program

# --------------------------------------------------------------------------- #
#  JS: potret semua kolom form (label, id, nilai, aktif/nonaktif, bagian)       #
# --------------------------------------------------------------------------- #
JS_DUMP = r"""
const norm = x => (x || '').replace(/\s+/g, ' ').trim();
const tampak = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
const penanda = [...document.querySelectorAll('.badge, legend, .card-title, h1, h2, h3, h4, h5, h6')]
  .filter(e => norm(e.textContent).length > 1 && norm(e.textContent).length < 60);
const bagian = el => { let b = ''; for (const p of penanda) { if (p.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) b = norm(p.textContent); else break; } return b; };
const label = el => {
  if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return norm(l.textContent); }
  let box = el.parentElement;
  for (let i = 0; i < 4 && box; i++, box = box.parentElement) {
    const l = [...box.querySelectorAll('label')].find(x => (x.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
    if (l) return norm(l.textContent);
  }
  return norm(el.getAttribute('aria-label') || el.placeholder || '');
};
const out = [];
for (const el of document.querySelectorAll('input, textarea, select, .ant-select')) {
  if (el.classList.contains('ant-select-search__field')) continue;
  if (el.type === 'password') continue;
  const ant = el.classList.contains('ant-select');
  out.push({tag: el.tagName.toLowerCase(), type: el.type || '', id: el.id || '', name: el.name || '',
    label: label(el), bagian: bagian(el), visible: tampak(el),
    value: ant ? norm((el.querySelector('.ant-select-selection-selected-value, .ant-select-selection__rendered') || {}).innerText)
               : (el.type === 'checkbox' || el.type === 'radio' ? String(el.checked) : (el.value || '')),
    disabled: ant ? el.classList.contains('ant-select-disabled') : !!el.disabled, readonly: !!el.readOnly,
    placeholder: el.placeholder || '', cls: (el.className || '').toString().slice(0, 80)});
  if (out.length >= 500) break;
}
const tombol = [...document.querySelectorAll('button, a.btn')].map(b => ({teks: norm(b.textContent).slice(0, 60), disabled: !!b.disabled || b.classList.contains('disabled'), visible: tampak(b)}))
  .filter(b => b.teks).slice(0, 80);
return {url: location.href, judul: document.title, kolom: out, tombol: tombol,
        bagian: penanda.map(p => norm(p.textContent)).slice(0, 60)};
"""

NAMA_DIBUNGKUS = [
    "login", "_buka_sinoptik", "klik_tombol_oke_popup", "memilih_stasiun", "memilih_observer", "memilih_tanggal",
    "isi_per_jam", "Fill_AWS_Digi", "isi_data", "isi_penguapan_00", "isi_hujan_override", "isi_lapisan_tambahan",
    "Preview", "Preview_OK", "SEND_SEND_SUBMIT", "SEND_INASWITCH_SUBMIT", "SEND_GTS", "SEND_GTS_OK",
    "selesaikan_pasca_kirim", "tangani_popup_koreksi_qc", "recover_session", "baca_sandi",
    "pilih_dropdown_ant_select", "isi_input_text", "wait_for_presence", "wait_for_clickable", "click_button_by_text",
    "pilih_ant_select", "isi_input", "pilih_opsi_ant_select", "_pilih_cepat", "pilih_ant_select_berlapis", "_isi_bagian_bawah",
]
SNAPSHOT_SESUDAH = {"Fill_AWS_Digi": "setelah_fill_aws", "isi_data": "setelah_isi_data", "Preview": "setelah_preview",
                    "selesaikan_pasca_kirim": "setelah_kirim"}
SNAPSHOT_SEBELUM = {"isi_data": "sebelum_isi_data"}


class Perekam:
    def __init__(self, folder, snapshot_maks=12, screenshot=True):
        self.folder, self.snapshot_maks, self.screenshot = Path(folder), snapshot_maks, screenshot
        self.folder.mkdir(parents=True, exist_ok=True)
        self.t0 = _real_time.time()
        self.kejadian, self.tumpukan, self.snapshots = [], [], []
        self.jeda_di_luar = 0.0
        self.info = {}

    def t(self):
        return round(_real_time.time() - self.t0, 3)

    # ---- jeda (time.sleep) dihitung per langkah ----------------------------
    def tidur(self, s):
        for fr in self.tumpukan:
            fr["tidur"] += s
        if not self.tumpukan:
            self.jeda_di_luar += s
        _real_time.sleep(s)

    def bungkus(self, nama, fn):
        rek = self

        @functools.wraps(fn)
        def w(*a, **k):
            fr = {"nama": nama, "mulai": rek.t(), "tidur": 0.0, "depth": len(rek.tumpukan),
                  "arg": rek._ringkas_arg(nama, a, k)}
            drv = a[0] if a and hasattr(a[0], "execute_script") else k.get("driver") or k.get("drv")
            if nama in SNAPSHOT_SEBELUM and drv is not None:
                rek.potret(drv, SNAPSHOT_SEBELUM[nama])
            rek.tumpukan.append(fr)
            hasil, galat = None, None
            try:
                hasil = fn(*a, **k)
                return hasil
            except BaseException as e:      # termasuk KeyboardInterrupt: dicatat lalu dilempar ulang
                galat = f"{type(e).__name__}: {str(e)[:200]}"
                raise
            finally:
                rek.tumpukan.pop()
                fr["durasi"] = round(rek.t() - fr["mulai"], 3)
                fr["tidur"] = round(fr["tidur"], 3)
                fr["hasil"] = (None if hasil is None else (hasil if isinstance(hasil, (bool, int, float, str)) else "obj"))
                fr["galat"] = galat
                fr["ok"] = (galat is None) and (hasil is not False) and not (nama.startswith("wait_for") and hasil is None)
                rek.kejadian.append(fr)
                if nama in SNAPSHOT_SESUDAH and drv is not None and galat is None:
                    rek.potret(drv, SNAPSHOT_SESUDAH[nama])
        return w

    @staticmethod
    def _ringkas_arg(nama, a, k):
        try:
            if nama in ("pilih_dropdown_ant_select", "isi_input_text", "pilih_ant_select", "isi_input"):
                return f"{a[1]}={str(a[2])[:30]}"
            if nama in ("pilih_opsi_ant_select", "_pilih_cepat"):     # (driver, combobox, target, nama_field)
                return f"{a[3]}={str(a[2])[:30]}"
            if nama.startswith("wait_for"):
                return str(a[1])[:90]
            if nama == "click_button_by_text":
                return str(a[1])[:40]
            if nama in ("memilih_tanggal",):
                return str(a[1] if len(a) > 1 else k.get("utc_date"))
        except Exception:
            pass
        return ""

    # ---- potret halaman -----------------------------------------------------
    def potret(self, driver, label):
        if len(self.snapshots) >= self.snapshot_maks:
            return None
        n = len(self.snapshots) + 1
        dasar = f"dom_{n:02d}_{label}"
        try:
            dump = driver.execute_script(JS_DUMP)
        except Exception as e:
            dump = {"galat": str(e)[:200]}
        dump["label"], dump["t"] = label, self.t()
        (self.folder / f"{dasar}.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        if self.screenshot:
            try:
                driver.save_screenshot(str(self.folder / f"{dasar}.png"))
            except Exception:
                pass
        try:
            if "login" not in (driver.current_url or ""):          # jangan simpan halaman login
                (self.folder / f"{dasar}.html").write_text(driver.page_source, encoding="utf-8")
        except Exception:
            pass
        self.snapshots.append(dump)
        return dump


def pasang(V, rek):
    """Pasang pembungkus waktu/potret pada fungsi-fungsi V7SATU (dipakai lewat nama global, jadi berlaku di seluruh bot)."""
    class _Waktu:
        def __getattr__(self, n): return getattr(_real_time, n)
        def sleep(self, s): rek.tidur(s)
    V.time = _Waktu()
    for n in NAMA_DIBUNGKUS:
        if hasattr(V, n):
            setattr(V, n, rek.bungkus(n, getattr(V, n)))


# --------------------------------------------------------------------------- #
#  Laporan                                                                      #
# --------------------------------------------------------------------------- #
def agregat(kejadian):
    A = {}
    for e in kejadian:
        a = A.setdefault(e["nama"], {"n": 0, "total": 0.0, "maks": 0.0, "tidur": 0.0, "gagal": 0})
        a["n"] += 1; a["total"] += e["durasi"]; a["maks"] = max(a["maks"], e["durasi"]); a["tidur"] += e["tidur"]
        a["gagal"] += (not e["ok"])
    return A


def kolom_penting(dump):
    for k in dump.get("kolom", []):
        yield k


def teks_laporan(rek, mode, argv):
    L = [f"LAPORAN PEMANTAU WEB  | mode={mode} | {dt.datetime.now():%Y-%m-%d %H:%M:%S} | total {rek.t():.1f} dtk",
         f"argumen: {' '.join(argv)}"]
    for k, v in rek.info.items():
        L.append(f"{k}: {v}")
    A = agregat(rek.kejadian)
    L += ["", "== WAKTU PER LANGKAH (diurutkan total terbesar) ==",
          f"{'langkah':34}{'x':>4}{'total dtk':>11}{'maks':>8}{'tidur(sleep)':>14}{'gagal':>7}"]
    for n, a in sorted(A.items(), key=lambda kv: -kv[1]["total"]):
        L.append(f"{n:34}{a['n']:>4}{a['total']:>11.1f}{a['maks']:>8.1f}{a['tidur']:>14.1f}{a['gagal']:>7}")
    tidur_dalam = sum(e["tidur"] for e in rek.kejadian if e["depth"] == 0)
    total_dalam = sum(e["durasi"] for e in rek.kejadian if e["depth"] == 0)
    L += ["", f"Langkah tingkat atas: {total_dalam:.1f} dtk, di antaranya {tidur_dalam:.1f} dtk ({(100*tidur_dalam/total_dalam if total_dalam else 0):.0f}%) "
              f"berupa time.sleep/_jeda -> kandidat diganti explicit wait.",
          f"Menunggu jadwal (sleep di luar langkah, mis. hitung mundur): {rek.jeda_di_luar:.1f} dtk"]
    lambat = sorted(rek.kejadian, key=lambda e: -e["durasi"])[:15]
    L += ["", "== 15 KEJADIAN TERLAMA =="]
    for e in lambat:
        L.append(f"  {e['durasi']:7.1f} dtk (tidur {e['tidur']:.1f}) {e['nama']} {e['arg']} {'' if e['ok'] else '<-- GAGAL ' + str(e['galat'] or e['hasil'])}")
    gagal = [e for e in rek.kejadian if not e["ok"]]
    L += ["", f"== KEGAGALAN / TUNGGU HABIS WAKTU ({len(gagal)}) =="]
    for e in gagal[:60]:
        L.append(f"  t={e['mulai']:.1f} {e['nama']} {e['arg']} -> {e['galat'] or e['hasil']} ({e['durasi']:.1f} dtk)")
    L += ["", "== URUTAN KEJADIAN (tingkat atas; indentasi = bersarang) =="]
    for e in sorted(rek.kejadian, key=lambda e: e["mulai"])[:400]:
        if e["nama"] in ("wait_for_presence", "wait_for_clickable", "pilih_dropdown_ant_select", "isi_input_text", "_pilih_cepat") and e["ok"] and e["durasi"] < 1.0:
            continue
        L.append(f"  {e['mulai']:7.1f}s {'  ' * e['depth']}{e['nama']} {e['arg']} [{e['durasi']:.1f} dtk{'; tidur %.1f' % e['tidur'] if e['tidur'] else ''}]{'' if e['ok'] else ' GAGAL'}")
    for d in rek.snapshots:
        L += ["", f"== KOLOM FORM @ {d['label']} (t={d['t']:.0f}s) | {d.get('url', '')} =="]
        ks = [k for k in kolom_penting(d) if k["visible"]]
        bag = None
        for k in ks:
            if k["bagian"] != bag:
                bag = k["bagian"]; L.append(f"  [{bag or '-'}]")
            st = "NONAKTIF" if k["disabled"] else ("baca-saja" if k["readonly"] else "aktif")
            L.append(f"    {k['label'][:46]:46} id={k['id'] or '-':26} nilai={k['value'][:30]!r:34} {st}")
        L.append(f"  tombol: " + ", ".join(f"{t['teks']}{'(nonaktif)' if t['disabled'] else ''}" for t in d.get("tombol", []) if t["visible"])[:400])
    return "\n".join(L)


def tulis_laporan(rek, mode, argv, tee):
    (rek.folder / "laporan.json").write_text(json.dumps({"mode": mode, "argv": argv, "info": rek.info, "kejadian": rek.kejadian,
                                                          "snapshots": rek.snapshots, "jeda_di_luar": rek.jeda_di_luar}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (rek.folder / "laporan.txt").write_text(teks_laporan(rek, mode, argv), encoding="utf-8")
    zp = rek.folder.parent / f"pantau_{rek.folder.name}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(rek.folder.iterdir()):
            z.write(f, f"{rek.folder.name}/{f.name}")
    return zp


class Tee:
    def __init__(self, asli, path):
        self.asli, self.f = asli, open(path, "w", encoding="utf-8")
    def write(self, s):
        self.asli.write(s)
        if "Akan dieksekusi dalam" not in s:
            self.f.write(s); self.f.flush()
    def flush(self): self.asli.flush()
    def __getattr__(self, n): return getattr(self.asli, n)


# --------------------------------------------------------------------------- #
#  Mode                                                                         #
# --------------------------------------------------------------------------- #
def mode_jelajah(V, rek, a):
    V._muat_kredensial()      # [rev 28] jalur jelajah tidak melewati main(); tanpa ini STATION_ID=None -> galat "'NoneType' object is not iterable"
    drv = V.buat_driver()     # [rev 28] pembukaan tangguh (memastikan Chrome benar-benar sampai ke BMKG Satu)
    rek.info["profil_chrome"] = str(V._profil_chrome_dir() or "(sementara)")
    try:
        rek.info["versi_chrome"] = drv.capabilities.get("browserVersion", "?")
        rek.info["versi_driver"] = drv.capabilities.get("chrome", {}).get("chromedriverVersion", "?")[:30]
    except Exception:
        pass
    try:
        V.login(drv)
        V.klik_tombol_oke_popup(drv=drv)
        V.memilih_stasiun(drv)
        V.ukur_latensi(drv)       # [rev 29] diagnosa latensi driver/DOM/fokus jendela -> masuk laporan
        tgl = a.tanggal or (dt.datetime.utcnow().strftime("%Y-%m-%d"))
        if V.memilih_tanggal(drv, tgl) is False:
            raise SystemExit(f"tanggal {tgl} tidak bisa dipilih di web")
        for jam in [j.strip() for j in a.jam.split(",") if j.strip()]:
            if not V.isi_per_jam(drv, {"jam_input": jam}):
                print(f"❌ jam {jam} tidak bisa dipilih"); continue
            V._jeda(2)
            V.Fill_AWS_Digi(drv)           # -> potret otomatis 'setelah_fill_aws'
            V._jeda(1)
            V.wait_for_presence(drv, (V.By.ID, "present_weather_ww"), timeout=15)
            rek.potret(drv, f"jam_{jam.replace(':', '')}_siap")
    finally:
        try:
            drv.quit()
        except Exception:
            pass


def mode_bot(V, rek, a, lanjut, kirim):
    argv = ["V7SATU.py"] + ([] if kirim else ["--dry-run"]) + (["--observer", a.observer] if a.observer else []) + (["--no-gui"] if a.no_gui else []) + lanjut
    sys.argv = argv
    rek.info["perintah_bot"] = " ".join(argv)
    rek.info["profil_chrome"] = str(V._profil_chrome_dir() or "(sementara)")
    V.main()


def main():
    ap = argparse.ArgumentParser(description="Pemantau perilaku web BMKG Satu", epilog="Argumen setelah '--' diteruskan ke bot.")
    ap.add_argument("--mode", choices=["jelajah", "dryrun", "kirim"], default="jelajah")
    ap.add_argument("--tanggal", help="(jelajah) tanggal UTC YYYY-MM-DD; default hari ini UTC")
    ap.add_argument("--jam", default="00:00", help="(jelajah) jam UTC, boleh beberapa: 00:00,03:00,07:00")
    ap.add_argument("--observer"); ap.add_argument("--no-gui", action="store_true")
    ap.add_argument("--izinkan-kirim", action="store_true", help="wajib untuk mode kirim (pengiriman SUNGGUHAN)")
    ap.add_argument("--snapshot-maks", type=int, default=12); ap.add_argument("--tanpa-screenshot", action="store_true")
    a, lanjut = ap.parse_known_args()
    lanjut = [x for x in lanjut if x != "--"]
    if a.mode == "kirim" and not a.izinkan_kirim:
        sys.exit("Mode 'kirim' mengirim data SUNGGUHAN. Tambahkan --izinkan-kirim bila memang itu yang Anda mau.")
    folder = ROOT / "pantau_out" / f"{dt.datetime.now():%Y%m%d_%H%M%S}_{a.mode}"
    rek = Perekam(folder, a.snapshot_maks, not a.tanpa_screenshot)
    sys.stdout = Tee(sys.stdout, folder / "log_konsol.txt")
    argv = sys.argv[1:]
    V = importlib.import_module("V7SATU")
    pasang(V, rek)
    zp = None
    try:
        if a.mode == "jelajah":
            mode_jelajah(V, rek, a)
        else:
            mode_bot(V, rek, a, lanjut, a.mode == "kirim")
    except KeyboardInterrupt:
        print("\n⏹️ Dihentikan pengguna; laporan tetap dibuat dari data yang sudah terekam")
    except Exception as e:     # [rev 28] galat fatal dicatat ke laporan agar ikut terunggah di zip
        traceback.print_exc()
        rek.info["GALAT_FATAL"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"\n❌ Berhenti karena galat: {rek.info['GALAT_FATAL']}")
    finally:
        if getattr(V, "LATENSI", None):
            rek.info["latensi_driver"] = dict(V.LATENSI)    # [rev 29]
        rek.info["anti_throttle"] = bool((V.CFG.get("chrome", {}) or {}).get("anti_throttle", True))
        zp = tulis_laporan(rek, a.mode, argv, sys.stdout)
        sys.stdout = sys.stdout.asli
        print(f"\n📊 Laporan: {folder / 'laporan.txt'}\n📦 Unggah file ini ke chat: {zp}")


if __name__ == "__main__":
    main()
