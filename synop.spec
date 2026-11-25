# -*- mode: python ; coding: utf-8 -*-
# [rev 36 / F4.3] PyInstaller: satu paket (folder dist/SynopOtomatis) berisi dua program:
#   SynopOtomatis.exe : panel kontrol (tanpa jendela konsol)
#   SynopWorker.exe   : pekerja berkonsol, dipanggil panel untuk bot / web / pantau (keluarannya diarahkan ke logs/*.log)
# Bangun:  build_exe.bat   (atau: pyinstaller synop.spec --noconfirm)
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("web", "web"), ("panel", "panel"), ("core/options.json", "core"), ("core/rules.json", "core"), ("core/rules_qc.json", "core"),
         ("config.yaml", "."), (".env.example", "."), ("docs", "docs")]
binaries = []
hidden = ["V7SATU", "app", "tools", "tools.pantau_web", "core.notify", "panel", "tkinter", "pyautogui"]
hidden += collect_submodules("core")
for paket in ("selenium", "webview", "segno"):          # selenium membawa selenium-manager (pengunduh chromedriver)
    try:
        d, b, h = collect_all(paket)
        datas += d
        binaries += b
        hidden += h
    except Exception:
        pass

a = Analysis(["synop_app.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden, hookspath=[], runtime_hooks=[],
             excludes=["matplotlib", "scipy", "IPython", "pytest", "notebook"], noarchive=False)
pyz = PYZ(a.pure)
panel = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SynopOtomatis", console=False, debug=False, strip=False, upx=False)
kerja = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SynopWorker", console=True, debug=False, strip=False, upx=False)
coll = COLLECT(panel, kerja, a.binaries, a.datas, strip=False, upx=False, name="SynopOtomatis")
