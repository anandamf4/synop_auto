# -*- coding: utf-8 -*-
"""
core/paths.py - [rev 36 / F4.3] lokasi berkas untuk mode skrip DAN mode .exe (PyInstaller).

  BUNDLE : sumber daya BACA-SAJA yang ikut terkemas (web/, core/*.json, config.yaml bawaan). Mode skrip = folder proyek.
  ROOT   : folder TULIS milik pengguna (.env, config.yaml, data/, snapshots/, chrome_profile/, logs/). Mode .exe = folder tempat
           SynopOtomatis.exe berada; mode skrip = folder proyek (perilaku lama tidak berubah).
"""
import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ROOT = Path(sys.executable).resolve().parent if FROZEN else BUNDLE

_SALIN_AWAL = ("config.yaml", ".env.example")


def siapkan():
    """Pertama kali dijalankan dari .exe: salin config.yaml & .env.example bawaan ke folder pengguna, buat folder kerja."""
    for nama in _SALIN_AWAL:
        tujuan, sumber = ROOT / nama, BUNDLE / nama
        if not tujuan.exists() and sumber.exists() and sumber != tujuan:
            shutil.copy2(sumber, tujuan)
    for d in ("data", "snapshots", "logs"):
        (ROOT / d).mkdir(exist_ok=True)
