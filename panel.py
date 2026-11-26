# -*- coding: utf-8 -*-
"""
panel.py - [rev 36 / F4.3] PANEL KONTROL DESKTOP "SYNOP Otomatis" (lokal).

Satu jendela untuk mengendalikan semua komponen: web form & dashboard (app.py), bot pengirim (V7SATU.py), pantau web
(tools/pantau_web.py) dan akses remote (cloudflared), plus cek sistem, log, dan pengaturan. Tiap komponen = proses terpisah
(core/proses.py). Panel hanya melayani 127.0.0.1 dan tidak pernah ikut dibuka lewat tunnel (tunnel hanya menuju web form).

Jalankan:  python synop_app.py            (atau SynopOtomatis.exe)
Tampilan: jendela aplikasi (pywebview) bila terpasang; bila tidak, browser bawaan.
"""
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_file

from core import paths, status as status_bot
from core.config import load_config, resolve_path
from core.paths import BUNDLE, ROOT
from core.proses import MODUL, Pengelola, cari_cloudflared, perintah

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

REV = "rev 38"
PORT_PANEL = 8765
KUNCI_ENV = ("BMKG_STATION_ID", "BMKG_PASSWORD", "WEB_PIN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
RAHASIA = {"BMKG_STATION_ID": "ID stasiun BMKG Satu", "BMKG_PASSWORD": "Password BMKG Satu", "WEB_PIN": "PIN halaman web",
           "TELEGRAM_BOT_TOKEN": "Token bot Telegram", "TELEGRAM_CHAT_ID": "Chat ID Telegram"}
_RE_URL = re.compile(r"https://[a-z0-9\-]+\.trycloudflare\.com")
_RE_JAM = re.compile(r"^\d{2}:\d{2}(,\d{2}:\d{2})*$")

# Pengaturan yang boleh diubah dari panel (kunci config -> tampilan). Menambah baris di sini = menambah kontrol di layar Pengaturan.
PENGATURAN = [
    ("Telegram", "notify.kirim_sukses", "Kabari tiap jam yang terkirim (24x/hari)", "bool"),
    ("Telegram", "notify.kirim_rekap", "Rekap harian", "bool"),
    ("Telegram", "notify.rekap_jam_utc", "Jam rekap harian (UTC, HH:MM)", "jam"),
    ("Telegram", "notify.kirim_screenshot", "Sertakan screenshot saat gagal", "bool"),
    ("Telegram", "notify.kirim_saat_dry_run", "Tetap kabari saat dry-run", "bool"),
    ("Telegram", "notify.alarm_suara", "Bunyi alarm lokal saat gagal total", "bool"),
    ("Sesi & pemantauan web", "session.aktif", "Pulihkan sesi BMKG Satu otomatis (popup sesi habis -> OK -> login ulang)", "bool"),
    ("Sesi & pemantauan web", "session.pantau_pasif_detik", "Periksa sesi tiap (detik; hanya membaca halaman)", ("int", 15, 600)),
    ("Sesi & pemantauan web", "health.aktif", "Health check selector (lapor bila struktur web berubah)", "bool"),
    ("Sesi & pemantauan web", "health.cek_detik", "Health check kerangka tiap (detik)", ("int", 60, 3600)),
    ("Pengiriman", "gerbang.aktif", "Jendela batal sebelum SEND (gerbang persetujuan)", "bool"),
    ("Pengiriman", "gerbang.detik", "Lama jendela batal (detik)", ("int", 5, 120)),
    ("Pengiriman", "features.allow_update", "Boleh 'Send & Update' bila jam itu sudah ada di web", "bool"),
    ("Pengiriman", "features.verify_sandi", "Bandingkan sandi hasil Preview dengan data", "bool"),
    ("Pengiriman", "features.extra_layers", "Isi lapisan awan tambahan (rendah-3, menengah-2, tinggi-2)", "bool"),
    ("Pengiriman", "runtime.max_row_attempts", "Percobaan ulang per jam", ("int", 1, 6)),
    ("Pengiriman", "runtime.max_field_attempts", "Percobaan ulang per kolom", ("int", 1, 6)),
    ("Kecepatan", "speed.fast_select", "Jalur cepat dropdown", "bool"),
    ("Kecepatan", "speed.fast_input", "Jalur cepat kotak angka (aktifkan setelah dry-run terbukti)", "bool"),
    ("Web form", "web.port", "Port web form", ("int", 1024, 65535)),
]


def _ambil(d, kunci):
    for k in kunci.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _pasang(d, kunci, nilai):
    ks = kunci.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = nilai


def baca_env():
    """Isi .env sebagai dict (tanpa memasukkannya ke environment proses panel)."""
    try:
        from dotenv import dotenv_values
        return {k: (v or "") for k, v in dotenv_values(ROOT / ".env").items()}
    except Exception:
        return {}


def cari_chrome():
    import os
    import shutil
    for n in ("chrome", "google-chrome", "chromium"):
        if shutil.which(n):
            return shutil.which(n)
    kand = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if os.environ.get(env):
            kand.append(Path(os.environ[env]) / "Google" / "Chrome" / "Application" / "chrome.exe")
    return next((str(k) for k in kand if k.exists()), None)


def baris(ikon, nama, detail, st, aksi=None):
    """Satu baris Cek sistem. st: ok | wt (perlu perhatian) | of (tidak aktif / belum). Baris baru cukup ditambah di cek_sistem()."""
    return {"ikon": ikon, "nama": nama, "detail": detail, "status": st, "aksi": aksi}


def cek_sistem(cfg, env):
    out = []
    chrome = cari_chrome()
    prof = ROOT / ((cfg.get("chrome", {}) or {}).get("profile_dir") or "chrome_profile")
    out.append(baris("chrome", "Chrome & driver", ("Chrome terpasang" + (" · profil BMKG Satu siap" if prof.exists() else " · profil dibuat saat bot pertama jalan"))
                     if chrome else "Chrome belum ditemukan — pasang Google Chrome", "ok" if chrome else "wt"))
    kred = bool(env.get("BMKG_STATION_ID") and env.get("BMKG_PASSWORD"))
    out.append(baris("kunci", "Kredensial BMKG Satu", "Tersimpan di .env" if kred else "Belum diisi — menu Pengaturan > Kredensial", "ok" if kred else "wt"))
    pin = bool(env.get("WEB_PIN"))
    out.append(baris("pin", "WEB_PIN", "Terisi" if pin else "Kosong — wajib untuk akses remote", "ok" if pin else "wt"))
    cf = cari_cloudflared()
    out.append(baris("awan", "cloudflared", "Terpasang" if cf else "Belum terpasang (hanya perlu untuk akses remote)", "ok" if cf else "of"))
    tg_ok = bool(env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID")
                 and env.get("TELEGRAM_BOT_TOKEN") != "isi_token_bot")
    uji = status_bot.baca().get("telegram_uji")
    n = cfg.get("notify", {}) or {}
    aktif = [k.replace("kirim_", "") for k in ("kirim_sukses", "kirim_rekap", "kirim_screenshot") if n.get(k)]
    out.append(baris("kirim", "Telegram", ("Grup terhubung" + (f" · uji terakhir {uji['waktu'][11:16]} ({'berhasil' if uji.get('ok') else 'GAGAL'})" if uji else " · belum pernah diuji")
                                           + (" · pesan aktif: " + ", ".join(aktif) if aktif else "")) if tg_ok else "Belum diatur (token & chat id di Pengaturan)",
                     "ok" if tg_ok and (not uji or uji.get("ok")) else ("wt" if tg_ok else "of"), "uji_telegram" if tg_ok else None))
    ses = status_bot.baca().get("sesi")
    out.append(baris("sesi", "Sesi BMKG Satu", (ses.get("ket", "aktif") + f" · {ses['waktu'][11:16]}") if ses else "Belum ada data — muncul setelah bot berjalan",
                     "ok" if ses else "of"))
    sel = status_bot.baca().get("selector")
    if sel:
        hil = sel.get("hilang") or []
        out.append(baris("web", "Struktur web (selector)", ("Semua elemen utama ditemukan" if not hil else "TIDAK ditemukan: " + ", ".join(hil[:4]))
                         + f" · {sel['waktu'][11:16]} ({sel.get('tahap')})", "ok" if not hil else "wt"))
    else:
        out.append(baris("web", "Struktur web (selector)", "Belum ada data — muncul setelah bot berjalan", "of"))
    db = resolve_path(cfg, "db")
    out.append(baris("db", "Database", f"{db.name} · {db.stat().st_size // 1024} KB" if db.exists() else "Dibuat saat web form pertama dibuka", "ok" if db.exists() else "of"))
    return out


class Panel:
    def __init__(self, root=None):
        self.root = Path(root or ROOT)
        self.proc = Pengelola(self.root)

    # ------------------------------------------------------------- konfigurasi
    def cfg(self):
        return load_config(muat_env=False)

    def env_anak(self):
        """Proses anak membaca .env sendiri; buang salinan lama dari environment panel agar tak menutupi nilai terbaru."""
        import os
        return {k: v for k, v in os.environ.items() if k not in KUNCI_ENV}

    def observer_list(self, cfg):
        boleh = (cfg.get("observers", {}) or {}).get("allowed") or []
        try:
            obs = [o["name"] for o in json.load(open(BUNDLE / "core" / "options.json", encoding="utf-8")).get("observer", []) if o.get("active", True)]
        except Exception:
            obs = []
        return [o for o in obs if not boleh or o in boleh]

    # ------------------------------------------------------------- kendali proses
    def mulai(self, nama, opsi):
        cfg, env = self.cfg(), baca_env()
        opsi = opsi or {}
        if nama == "web":
            w = cfg.get("web", {}) or {}
            cmd = perintah("web", ["--host", w.get("host", "0.0.0.0"), "--port", int(w.get("port", 8080))])
        elif nama == "bot":
            obs = (opsi.get("observer") or "").strip()
            if not obs:
                return False, "Pilih nama observer dulu"
            if not (env.get("BMKG_STATION_ID") and env.get("BMKG_PASSWORD")):
                return False, "Kredensial BMKG Satu belum diisi (Pengaturan > Kredensial)"
            dry = bool(opsi.get("dry_run"))
            if not dry and not opsi.get("konfirmasi_kirim_nyata"):
                return False, "Pengiriman nyata butuh konfirmasi"
            args = ["--observer", obs, "--no-gui"] + (["--dry-run"] if dry else []) + (["--process-past"] if opsi.get("lampau") else [])
            jam = (opsi.get("jam") or "").strip()
            if jam:
                if not _RE_JAM.match(jam):
                    return False, "Format jam salah (contoh: 07:00 atau 07:00,08:00)"
                args += ["--jam", jam]
            cmd = perintah("bot", args)
        elif nama == "pantau":
            mode = opsi.get("mode", "dryrun")
            if mode not in ("jelajah", "dryrun", "kirim"):
                return False, "Mode tidak dikenal"
            if mode == "kirim" and not opsi.get("izin"):
                return False, "Mode 'Kirim nyata' terkunci sampai izin dicentang"
            jam = (opsi.get("jam") or "00:00").strip()
            if not _RE_JAM.match(jam):
                return False, "Format jam salah (contoh: 00:00)"
            obs = (opsi.get("observer") or "").strip()
            if mode != "jelajah" and not obs:
                return False, "Pilih nama observer dulu"
            args = ["--mode", mode, "--jam", jam, "--no-gui"] + (["--observer", obs] if obs else []) + (["--izinkan-kirim"] if mode == "kirim" else [])
            if mode != "jelajah":
                # [rev 37] argumen setelah '--' diteruskan ke bot: --jam membatasi jam yang diproses, --process-past = proses jam yang sudah lewat
                args += ["--", "--jam", jam] + (["--process-past"] if opsi.get("lampau") else [])
            cmd = perintah("pantau", args)
        elif nama == "remote":
            return self.mulai_remote(cfg, env)
        else:
            return False, "Komponen tidak dikenal"
        return self._mulai(nama, cmd)

    def _mulai(self, nama, cmd):
        # proses anak membaca .env sendiri: salinan lama di environment panel (bila ada) disingkirkan sementara agar tak menutupi nilai terbaru
        import os
        simpan = {k: os.environ.pop(k) for k in KUNCI_ENV if k in os.environ}
        try:
            return self.proc.mulai(nama, cmd)
        finally:
            os.environ.update(simpan)

    def mulai_remote(self, cfg, env):
        if not env.get("WEB_PIN"):
            return False, "WEB_PIN masih kosong. Isi dulu di Pengaturan — halaman akan terbuka ke internet."
        cf = cari_cloudflared()
        if not cf:
            return False, "cloudflared belum terpasang (lihat panduan: winget install --id Cloudflare.cloudflared -e)"
        if not self.proc.jalan("web"):
            ok, pesan = self.mulai("web", {})
            if not ok:
                return False, "Web form gagal dimulai: " + pesan
            time.sleep(2)
        port = int((cfg.get("web", {}) or {}).get("port", 8080))
        self.proc.log_path("remote").unlink(missing_ok=True)
        return self._mulai("remote", [cf, "tunnel", "--url", f"http://127.0.0.1:{port}"])

    def henti(self, nama):
        if nama not in ("web", "bot", "pantau", "remote"):
            return False, "Komponen tidak dikenal"
        return self.proc.henti(nama)

    # ------------------------------------------------------------- data tampilan
    def url_remote(self):
        if not self.proc.jalan("remote"):
            return None
        lp = self.proc.log_path("remote")
        try:
            m = _RE_URL.findall(lp.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None
        return m[-1] if m else None

    def status_proses(self, cfg):
        out = {}
        for nama in ("web", "bot", "remote", "pantau"):
            jalan = self.proc.jalan(nama)
            st, ket = ("of", "Mati") if not jalan else ("ok", "Jalan")
            detail = ""
            if jalan and nama == "bot":
                hm = self.proc.hitung_mundur("bot")
                lg = self.proc.ekor("bot", 1)
                if hm:
                    st, ket, detail = "wt", "Siaga", f"Eksekusi berikutnya dalam {hm[0]:02d}:{hm[1]:02d}"
                else:
                    detail = (lg[0][:140] if lg else "Memulai...")
            elif jalan and nama == "remote":
                u = self.url_remote()
                st, ket, detail = ("ok", "Jalan", u) if u else ("wt", "Menyambung", "Menunggu link dari Cloudflare...")
            elif jalan and nama == "pantau":
                lg = self.proc.ekor("pantau", 1)
                detail = lg[0][:140] if lg else "Memulai..."
            elif not jalan and nama == "bot":
                lg = self.proc.ekor("bot", 1)
                detail = "Belum berjalan" if not lg else "Terakhir: " + lg[-1][:120]
            elif jalan and nama == "web":
                detail = f"Port {int((cfg.get('web', {}) or {}).get('port', 8080))}"
            out[nama] = {"jalan": jalan, "st": st, "ket": ket, "detail": detail, "sejak": self.proc.sejak(nama)}
        return out

    def jadwal_dan_aktivitas(self, cfg):
        """Jadwal sekitar jam sekarang (UTC) + aktivitas terakhir dari send_log/obsdb. Gagal baca -> kosong (panel tetap hidup)."""
        sekarang = dt.datetime.now(dt.timezone.utc)
        tgl = sekarang.strftime("%Y-%m-%d")
        rows, akt = [], []
        try:
            from core.db import SendLog
            from core.obsdb import ObsStore
            path = resolve_path(cfg, "db")
            if not path.exists():
                return rows, akt
            log = SendLog(path)
            obs = ObsStore(path, tz_hours=int(cfg["runtime"].get("timezone_offset_hours", 7)))
            hist = {r["jam"]: r for r in log.history(tgl, limit=100)}
            ada = obs.list_day(tgl)
            for h in range(max(0, sekarang.hour - 3), min(24, sekarang.hour + 6)):
                jam = f"{h:02d}:00"
                s = (hist.get(jam) or {}).get("status")
                if s == "sent":
                    st, ket = "ok", "Terkirim"
                elif s == "failed":
                    st, ket = "er", "Gagal"
                elif s == "running":
                    st, ket = "wt", "Sedang diproses"
                elif s == "skipped":
                    st, ket = "of", "Dilewati"
                elif jam in ada:
                    st, ket = "wt", "Data siap · menunggu bot"
                else:
                    st, ket = "of", "Menunggu data" if h >= sekarang.hour else "Tanpa data"
                rows.append({"jam": jam, "st": st, "ket": ket, "sekarang": h == sekarang.hour})
            for e in log.events(limit=8):
                akt.append({"waktu": str(e.get("ts") or "")[11:16], "jam": e.get("jam"), "event": e.get("event"),
                            "detail": (e.get("detail") or "")[:110]})
            log.close()
        except Exception as ex:
            akt = [{"waktu": "", "jam": "", "event": "galat", "detail": f"Gagal membaca database: {type(ex).__name__}"}]
        return rows, akt

    def akses_terakhir(self, cfg):
        try:
            from core.db import SendLog
            log = SendLog(resolve_path(cfg, "db"))
            out = [{"waktu": str(e.get("ts") or "")[11:16], "detail": e.get("detail", "")}
                   for e in log.events(limit=60) if e.get("event") == "akses_web"][:6]
            log.close()
            return out
        except Exception:
            return []

    # ------------------------------------------------------------- pengaturan
    def baca_pengaturan(self, cfg):
        out = []
        for grup, kunci, label, tipe in PENGATURAN:
            out.append({"grup": grup, "kunci": kunci, "label": label, "tipe": tipe if isinstance(tipe, str) else tipe[0],
                        "batas": list(tipe[1:]) if not isinstance(tipe, str) else None, "nilai": _ambil(cfg, kunci)})
        return out

    def simpan_pengaturan(self, perubahan):
        peta = {k: (t, l) for _, k, l, t in PENGATURAN}
        if yaml is None:
            return False, "PyYAML belum terpasang"
        berkas = self.root / "config.panel.yaml"
        data = {}
        if berkas.exists():
            data = yaml.safe_load(berkas.read_text(encoding="utf-8")) or {}
        for kunci, nilai in (perubahan or {}).items():
            if kunci not in peta:
                return False, f"Pengaturan tidak dikenal: {kunci}"
            tipe, label = peta[kunci]
            if tipe == "bool":
                if not isinstance(nilai, bool):
                    return False, f"{label}: harus ya/tidak"
            elif tipe == "jam":
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(nilai)):
                    return False, f"{label}: format HH:MM"
            else:
                try:
                    nilai = int(nilai)
                except (TypeError, ValueError):
                    return False, f"{label}: harus bilangan bulat"
                if not tipe[1] <= nilai <= tipe[2]:
                    return False, f"{label}: harus {tipe[1]}–{tipe[2]}"
            _pasang(data, kunci, nilai)
        berkas.write_text("# Dibuat otomatis oleh panel (menu Pengaturan). Menimpa config.yaml; hapus berkas ini untuk kembali ke config.yaml.\n"
                          + yaml.safe_dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8")
        return True, "Tersimpan. Berlaku saat komponen dijalankan ulang."

    def simpan_rahasia(self, kunci, nilai):
        if kunci not in RAHASIA:
            return False, "Kunci tidak dikenal"
        nilai = str(nilai or "")
        if "\n" in nilai or "\r" in nilai or len(nilai) > 300:
            return False, "Nilai tidak valid"
        from dotenv import set_key
        env = self.root / ".env"
        env.touch(exist_ok=True)
        set_key(str(env), kunci, nilai, quote_mode="always")
        return True, f"{RAHASIA[kunci]} tersimpan. Berlaku saat komponen dijalankan ulang."

    def uji_telegram(self):
        r = subprocess.run(perintah("telegram", ["--test"]), cwd=str(self.root), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, env=self.env_anak(), creationflags=(0x08000000 if sys.platform == "win32" else 0))
        ok = r.returncode == 0
        status_bot.tulis("telegram_uji", ok=ok)
        return ok, ((r.stdout or "") + (r.stderr or "")).strip()[-300:] or ("Terkirim" if ok else "Gagal")

    # ------------------------------------------------------------- pantau
    def hasil_pantau(self):
        folder = self.root / "pantau_out"
        if not folder.exists():
            return None
        runs = sorted([d for d in folder.iterdir() if d.is_dir() and (d / "laporan.json").exists()], reverse=True)
        if not runs:
            return None
        d = runs[0]
        try:
            lap = json.loads((d / "laporan.json").read_text(encoding="utf-8"))
        except Exception:
            return None
        kej = lap.get("kejadian") or []
        isi = max((e["durasi"] for e in kej if e.get("nama") == "isi_data"), default=None)
        lambat = sorted(kej, key=lambda e: -e.get("durasi", 0))[:4]
        sandi = next((l for l in (d / "log_konsol.txt").read_text(encoding="utf-8", errors="replace").splitlines() if "Verifikasi sandi" in l), "") \
            if (d / "log_konsol.txt").exists() else ""
        return {"nama": d.name, "mode": lap.get("mode"), "isi_data": isi, "sandi": sandi.strip()[-60:],
                "lambat": [{"nama": f"{e['nama']} {e.get('arg', '')}".strip()[:48], "dtk": round(e["durasi"], 1)} for e in lambat],
                "zip": (folder / f"pantau_{d.name}.zip").exists()}


# =========================================================================== snapshot kegagalan
_RE_SNAP = re.compile(r"^(?:(\d{8})_(\d{4})UTC|tanpa-slot)__(.+?)__(\d{8})-(\d{6})([A-Za-z]*)$")
_RE_GAGAL = re.compile(r"gagal|failed|exception|error|galat|habis|no_modal", re.I)
_RE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def daftar_snapshot(cfg, batas=300):
    """Pasangan <nama>.png + <nama>.html di folder snapshots/ (dibuat V7SATU.save_debug_snapshot), terbaru dulu."""
    d = resolve_path(cfg, "snapshots")
    if not d.is_dir():
        return []
    kel = {}
    for f in d.iterdir():
        if f.is_file() and f.suffix.lower() in (".png", ".html"):
            kel.setdefault(f.stem, {})[f.suffix.lower()[1:]] = f
    out = []
    for stem, fs in kel.items():
        m = _RE_SNAP.match(stem)
        label = m.group(3) if m else stem
        it = {"id": stem, "label": label, "png": "png" in fs, "html": "html" in fs, "gagal": bool(_RE_GAGAL.search(label)),
              "mtime": max(f.stat().st_mtime for f in fs.values()), "slot": None, "waktu": None}
        if m:
            if m.group(1):
                g, j = m.group(1), m.group(2)
                it["slot"] = f"{g[:4]}-{g[4:6]}-{g[6:]} {j[:2]}:{j[2:]} UTC"
            w, t = m.group(4), m.group(5)
            it["waktu"] = f"{w[:4]}-{w[4:6]}-{w[6:]} {t[:2]}:{t[2:4]}:{t[4:]} {m.group(6)}".strip()
        out.append(it)
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out[:batas]


def hitung_snapshot_gagal(cfg, jam=24):
    batas = time.time() - jam * 3600
    return sum(1 for x in daftar_snapshot(cfg) if x["gagal"] and x["mtime"] >= batas)


# =========================================================================== Flask
def buat_app(panel=None):
    P = panel or Panel()
    app = Flask(__name__, static_folder=None)
    app.config["JSON_AS_ASCII"] = False

    @app.before_request
    def jaga():
        host = (request.host or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            abort(403)                                # DNS-rebinding: panel hanya untuk PC ini
        if request.method == "POST" and request.headers.get("X-Panel") != "1":
            abort(403)                                # CSRF: form/halaman lain tidak bisa menembak panel

    def jawab(hasil):
        ok, pesan = hasil
        return jsonify({"ok": bool(ok), "pesan": pesan}), (200 if ok else 400)

    @app.route("/")
    def index():
        return Response((BUNDLE / "panel" / "index.html").read_text(encoding="utf-8"), mimetype="text/html")

    @app.route("/api/ping")
    def ping():
        return jsonify({"app": "synop-panel", "rev": REV})

    @app.route("/api/ringkas")
    def ringkas():
        cfg, env = P.cfg(), baca_env()
        jadwal, akt = P.jadwal_dan_aktivitas(cfg)
        tg = bool(env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"))
        return jsonify({"rev": REV, "stasiun": (cfg.get("notify", {}) or {}).get("nama_stasiun") or cfg["station"]["name"],
                        "utc": dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S"), "proses": P.status_proses(cfg), "jadwal": jadwal, "aktivitas": akt,
                        "telegram": tg, "port_web": int((cfg.get("web", {}) or {}).get("port", 8080)),
                        "host_web": (cfg.get("web", {}) or {}).get("host", "0.0.0.0"), "pin": bool(env.get("WEB_PIN")),
                        "observers": P.observer_list(cfg), "gerbang": cfg.get("gerbang", {}),
                        "snap_gagal": hitung_snapshot_gagal(cfg)})

    @app.route("/api/cek")
    def cek():
        return jsonify({"baris": cek_sistem(P.cfg(), baca_env())})

    @app.route("/api/proses", methods=["POST"])
    def proses():
        b = request.get_json(force=True, silent=True) or {}
        nama, aksi = b.get("nama"), b.get("aksi")
        if aksi == "mulai":
            return jawab(P.mulai(nama, b.get("opsi")))
        if aksi == "henti":
            return jawab(P.henti(nama))
        return jawab((False, "Aksi tidak dikenal"))

    @app.route("/api/log")
    def log():
        nama = request.args.get("nama", "bot")
        if nama not in ("bot", "web", "remote", "pantau"):
            abort(404)
        return jsonify({"baris": P.proc.ekor(nama, min(int(request.args.get("n", 300)), 1000))})

    @app.route("/api/buka_web", methods=["POST"])
    def buka_web():
        webbrowser.open(f"http://127.0.0.1:{int((P.cfg().get('web', {}) or {}).get('port', 8080))}")
        return jsonify({"ok": True})

    @app.route("/api/remote")
    def remote():
        cfg = P.cfg()
        return jsonify({"url": P.url_remote(), "jalan": P.proc.jalan("remote"), "sejak": P.proc.sejak("remote"),
                        "pin": bool(baca_env().get("WEB_PIN")), "host_web": (cfg.get("web", {}) or {}).get("host", "0.0.0.0"),
                        "cloudflared": bool(cari_cloudflared()), "akses": P.akses_terakhir(cfg)})

    @app.route("/api/qr.svg")
    def qr():
        u = P.url_remote()
        if not u:
            abort(404)
        try:
            import io
            import segno
            buf = io.BytesIO()
            segno.make(u, error="m").save(buf, kind="svg", scale=8, border=2)
            return Response(buf.getvalue(), mimetype="image/svg+xml")
        except ImportError:
            abort(501)

    @app.route("/api/pengaturan", methods=["GET", "POST"])
    def pengaturan():
        if request.method == "POST":
            return jawab(P.simpan_pengaturan((request.get_json(force=True, silent=True) or {}).get("perubahan")))
        cfg, env = P.cfg(), baca_env()
        return jsonify({"daftar": P.baca_pengaturan(cfg), "rahasia": [{"kunci": k, "label": v, "terisi": bool(env.get(k)),
                                                                          "tampil": (env.get(k) if k in ("BMKG_STATION_ID", "TELEGRAM_CHAT_ID") else None)}
                                                                         for k, v in RAHASIA.items()]})

    @app.route("/api/rahasia", methods=["POST"])
    def rahasia():
        b = request.get_json(force=True, silent=True) or {}
        return jawab(P.simpan_rahasia(b.get("kunci"), b.get("nilai")))

    @app.route("/api/telegram/uji", methods=["POST"])
    def telegram_uji():
        try:
            return jawab(P.uji_telegram())
        except Exception as e:
            return jawab((False, f"{type(e).__name__}: {e}"))

    @app.route("/api/pantau/hasil")
    def pantau_hasil():
        return jsonify({"hasil": P.hasil_pantau()})

    @app.route("/api/pantau/<jenis>")
    def pantau_berkas(jenis):
        h = P.hasil_pantau()
        if not h:
            abort(404)
        d = P.root / "pantau_out"
        if jenis == "laporan":
            return send_file(d / h["nama"] / "laporan.txt", mimetype="text/plain")
        if jenis == "zip" and h["zip"]:
            return send_file(d / f"pantau_{h['nama']}.zip", as_attachment=True)
        abort(404)


    @app.route("/api/snapshot")
    def snapshot_daftar():
        return jsonify({"daftar": daftar_snapshot(P.cfg())})

    @app.route("/api/snapshot/<sid>/<jenis>")
    def snapshot_berkas(sid, jenis):
        # nama dari klien: hanya huruf/angka/_.- dan harus berada di folder snapshots (cegah path traversal)
        if not _RE_ID.match(sid) or jenis not in ("png", "html"):
            abort(404)
        d = resolve_path(P.cfg(), "snapshots").resolve()
        f = (d / f"{sid}.{jenis}").resolve()
        if f.parent != d or not f.is_file():
            abort(404)
        if jenis == "png":
            r = send_file(f, mimetype="image/png")
            r.headers["Cache-Control"] = "private, max-age=3600"
            return r
        # HTML hasil simpan dari halaman BMKG: ditampilkan tanpa skrip/jaringan (sandbox + CSP) agar aman dibuka di panel
        r = Response(f.read_bytes(), mimetype="text/html")
        r.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
        return r

    @app.route("/api/snapshot/folder", methods=["POST"])
    def snapshot_folder():
        d = resolve_path(P.cfg(), "snapshots")
        d.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(d))          # Windows: buka di Explorer
            else:
                webbrowser.open(d.as_uri())
        except OSError as e:
            return jsonify({"ok": False, "pesan": f"Tidak bisa membuka folder: {e}"}), 500
        return jsonify({"ok": True, "pesan": f"Folder dibuka: {d}"})

    app.panel = P
    return app


# =========================================================================== peluncur
def _port_dipakai(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    paths.siapkan()
    url = f"http://127.0.0.1:{PORT_PANEL}/"
    if _port_dipakai(PORT_PANEL):                     # panel sudah terbuka: cukup tampilkan jendelanya lagi
        webbrowser.open(url)
        return 0
    app = buat_app()
    try:
        import webview                                # pywebview: jendela aplikasi sungguhan (opsional)
    except Exception:                                 # tak terpasang / komponen jendela tak tersedia -> browser bawaan
        webview = None
    if webview is None:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        app.run(host="127.0.0.1", port=PORT_PANEL, threaded=True)
        return 0
    threading.Thread(target=lambda: app.run(host="127.0.0.1", port=PORT_PANEL, threaded=True), daemon=True).start()
    for _ in range(50):
        if _port_dipakai(PORT_PANEL):
            break
        time.sleep(0.1)
    try:
        webview.create_window("SYNOP Otomatis · BMKG Satu", url, width=1180, height=820, min_size=(980, 640))
        webview.start()
    except Exception as e:                            # mis. WebView2 belum ada: jangan mati, buka di browser
        print(f"Jendela aplikasi tidak bisa dibuka ({type(e).__name__}); memakai browser bawaan. Server panel tetap berjalan.")
        webbrowser.open(url)
        threading.Event().wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
