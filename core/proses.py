# -*- coding: utf-8 -*-
"""
core/proses.py - [rev 36 / F4.3] pengelola proses untuk panel desktop.

Prinsip (REV 33): tiap komponen (web, bot, remote, pantau) = PROSES TERPISAH; satu mati tidak menjatuhkan yang lain, dan menutup panel
TIDAK menghentikan bot. Pelacakan lewat berkas PID (logs/<nama>.pid) sehingga panel yang dibuka ulang mengenali proses yang masih hidup.
Keluaran proses ditulis ke logs/<nama>.log (UTF-8).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psutil

from core.paths import FROZEN, ROOT

# nama -> modul yang dijalankan lewat synop_app.py --jalankan <nama>  (juga jalan di dalam .exe)
MODUL = {"bot": "V7SATU", "web": "app", "pantau": "tools.pantau_web", "telegram": "core.notify"}
_CREATE_NO_WINDOW = 0x08000000
_BARIS_HITUNG = re.compile(r"Akan dieksekusi dalam:\s*(\d+):(\d+)")


def perintah(nama, args=()):
    """Perintah subproses untuk komponen Python. Mode skrip: python synop_app.py ...; mode .exe: SynopOtomatis.exe ..."""
    if FROZEN:   # panel = exe tanpa jendela konsol; pekerja = exe berkonsol (stdout/stderr aman diarahkan ke logs/*.log)
        pekerja = Path(sys.executable).with_name("SynopWorker" + (".exe" if os.name == "nt" else ""))
        dasar = [str(pekerja if pekerja.exists() else sys.executable)]
    else:
        dasar = [sys.executable, str(ROOT / "synop_app.py")]
    return dasar + ["--jalankan", nama, *map(str, args)]


def cari_cloudflared():
    """Lokasi cloudflared.exe atau None."""
    import shutil
    ketemu = shutil.which("cloudflared")
    if ketemu:
        return ketemu
    kandidat = [ROOT / "cloudflared.exe"]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if os.environ.get(env):
            kandidat += [Path(os.environ[env]) / "cloudflared" / "cloudflared.exe", Path(os.environ[env]) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe"]
    return next((str(k) for k in kandidat if k.exists()), None)


class Pengelola:
    def __init__(self, root=None):
        self.root = Path(root or ROOT)
        self.dir = self.root / "logs"
        self.dir.mkdir(exist_ok=True)
        self._popen = {}

    # ------------------------------------------------------------- berkas
    def _pid_file(self, nama):
        return self.dir / f"{nama}.pid"

    def log_path(self, nama):
        return self.dir / f"{nama}.log"

    def _baca_pid(self, nama):
        try:
            return json.loads(self._pid_file(nama).read_text(encoding="utf-8"))
        except Exception:
            return None

    def _proses(self, nama):
        """psutil.Process bila komponen masih hidup (pid cocok dengan waktu-buat yang dicatat), selain itu None."""
        info = self._baca_pid(nama)
        if not info:
            return None
        try:
            p = psutil.Process(info["pid"])
            if abs(p.create_time() - info["buat"]) > 2 or p.status() == psutil.STATUS_ZOMBIE:
                return None
            return p
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
            return None

    # ------------------------------------------------------------- kendali
    def jalan(self, nama):
        return self._proses(nama) is not None

    def mulai(self, nama, cmd, env_tambahan=None):
        """Mulai komponen bila belum jalan. -> (ok, pesan)."""
        if self.jalan(nama):
            return False, f"{nama} sudah berjalan"
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", **(env_tambahan or {}))
        lp = self.log_path(nama)
        try:
            if lp.exists() and lp.stat().st_size > 5_000_000:      # log dipangkas sebelum penuh
                lp.replace(lp.with_suffix(".log.lama"))
            log = open(lp, "ab")
            log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} mulai {nama}: {' '.join(map(str, cmd[-6:]))} =====\n".encode("utf-8"))
            log.flush()
            kw = {"creationflags": _CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            pr = subprocess.Popen(list(map(str, cmd)), cwd=str(self.root), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  env=env, **kw)
        except Exception as e:
            return False, f"gagal memulai {nama}: {type(e).__name__}: {e}"
        self._popen[nama] = pr
        try:
            buat = psutil.Process(pr.pid).create_time()
        except Exception:
            buat = time.time()
        self._pid_file(nama).write_text(json.dumps({"pid": pr.pid, "buat": buat, "mulai": time.time()}), encoding="utf-8")
        return True, f"{nama} dimulai (PID {pr.pid})"

    def henti(self, nama, tunggu=6):
        """Hentikan komponen beserta anak-anaknya (Chrome/chromedriver milik bot ikut tertutup)."""
        p = self._proses(nama)
        if p is None:
            self._pid_file(nama).unlink(missing_ok=True)
            return True, f"{nama} tidak berjalan"
        try:
            semua = p.children(recursive=True) + [p]
            for x in semua:
                try:
                    x.terminate()
                except psutil.Error:
                    pass
            _, hidup = psutil.wait_procs(semua, timeout=tunggu)
            for x in hidup:
                try:
                    x.kill()
                except psutil.Error:
                    pass
        except psutil.Error as e:
            return False, f"gagal menghentikan {nama}: {e}"
        self._popen.pop(nama, None)
        self._pid_file(nama).unlink(missing_ok=True)
        return True, f"{nama} dihentikan"

    # ------------------------------------------------------------- info
    def sejak(self, nama):
        info = self._baca_pid(nama)
        return info.get("mulai") if info and self.jalan(nama) else None

    def ekor(self, nama, n=200):
        """n baris terakhir log; hitung-mundur bot ('\\r') disaring agar log tetap terbaca."""
        lp = self.log_path(nama)
        if not lp.exists():
            return []
        with open(lp, "rb") as f:
            f.seek(max(0, lp.stat().st_size - 200_000))
            teks = f.read().decode("utf-8", "replace")
        baris = []
        for b in teks.splitlines():
            bagian = [x for x in b.split("\r") if x.strip() and "Akan dieksekusi dalam" not in x]
            if bagian:
                baris.append(bagian[-1].rstrip())
        return baris[-n:]

    def hitung_mundur(self, nama="bot"):
        """(menit, detik) dari hitung-mundur terakhir bot, atau None."""
        lp = self.log_path(nama)
        if not lp.exists():
            return None
        with open(lp, "rb") as f:
            f.seek(max(0, lp.stat().st_size - 8000))
            m = _BARIS_HITUNG.findall(f.read().decode("utf-8", "replace"))
        return (int(m[-1][0]), int(m[-1][1])) if m else None
