# -*- coding: utf-8 -*-
"""
synop_app.py - [rev 36 / F4.3] TITIK MASUK tunggal aplikasi (dipakai sebagai entry PyInstaller -> SynopOtomatis.exe).

  python synop_app.py                       -> panel kontrol (jendela aplikasi)
  python synop_app.py --jalankan bot ...    -> bot pengirim (V7SATU.py)         [dipakai panel sebagai subproses]
  python synop_app.py --jalankan web ...    -> web form & dashboard (app.py)
  python synop_app.py --jalankan pantau ... -> pantau web (tools/pantau_web.py)
  python synop_app.py --jalankan telegram --test|--cari-chat-id -> bantu Telegram (core/notify.py)
Mode skrip dan mode .exe memakai jalur yang sama, sehingga yang diuji di sini = yang dijalankan di .exe.
"""
import multiprocessing
import runpy
import sys


def _paksa_utf8():
    # Di .exe PyInstaller variabel PYTHONIOENCODING diabaikan, jadi stdout/stderr yang diarahkan ke logs/*.log memakai cp1252
    # dan print("🌐 ...") crash dengan UnicodeEncodeError. reconfigure() berlaku di mode skrip maupun .exe.
    for s in (sys.stdout, sys.stderr):
        if s is not None and hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


def main():
    _paksa_utf8()
    multiprocessing.freeze_support()
    from core import paths
    paths.siapkan()            # .exe pertama kali: salin config.yaml & .env.example bawaan, buat data/ snapshots/ logs/
    if len(sys.argv) >= 3 and sys.argv[1] == "--jalankan":
        from core.proses import MODUL
        nama = sys.argv[2]
        if nama not in MODUL:
            sys.exit(f"komponen tidak dikenal: {nama} (pilihan: {', '.join(MODUL)})")
        sys.argv = [MODUL[nama].split(".")[-1] + ".py"] + sys.argv[3:]
        runpy.run_module(MODUL[nama], run_name="__main__", alter_sys=True)
        return 0
    import panel
    return panel.main()


if __name__ == "__main__":
    sys.exit(main())
