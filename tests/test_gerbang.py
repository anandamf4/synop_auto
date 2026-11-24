# -*- coding: utf-8 -*-
"""F3.5: gerbang persetujuan sebelum SEND. Tanpa browser/layar (Tk dipalsukan).   python tests/test_gerbang.py"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))
spec = importlib.util.spec_from_file_location("V7SATU_g", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
passed = failed = 0


def check(n, c, info=""):
    global passed, failed
    print(("  OK   " if c else "  GAGAL"), n, "" if c else f"-> {info}")
    passed += bool(c)
    failed += (not c)


def tk_palsu(aksi):
    """aksi: 'batal' | 'kirim' | 'diam' (hitung-mundur habis) | 'tutup' -> modul tkinter palsu."""
    m = types.ModuleType("tkinter")
    cmds = {}

    class W:
        def __init__(self, *a, **k):
            if "command" in k:
                cmds[k["text"]] = k["command"]
        def pack(self, **k): pass
    class StringVar:
        def set(self, v): pass
    class Tk(W):
        def title(self, t): pass
        def attributes(self, *a): pass
        def protocol(self, n, f): cmds["tutup"] = f
        def after(self, ms, f, *a): pass          # tidak menjalankan tick: hitung-mundur 'diam'
        def destroy(self): pass
        def mainloop(self):
            {"batal": lambda: cmds["Batalkan"](), "kirim": lambda: cmds["Kirim sekarang"](),
             "tutup": lambda: cmds["tutup"](), "diam": lambda: None}[aksi]()
    m.Tk, m.Label, m.Button, m.StringVar = Tk, W, W, StringVar
    return m


S = ("2026-11-24", "07:00")
M.CFG.setdefault("gerbang", {"aktif": True, "detik": 20})
M.CFG["gerbang"].update(aktif=True, detik=20)
for aksi, harap in (("batal", False), ("kirim", True), ("tutup", True), ("diam", True)):
    sys.modules["tkinter"] = tk_palsu(aksi)
    check(f"jendela: {aksi} -> kirim={harap}", M.gerbang_persetujuan(S, "AAXX 24071", True) is harap)
sys.modules["tkinter"] = tk_palsu("batal")
check("--no-gui (tampil=False): tidak ada jendela, tetap kirim", M.gerbang_persetujuan(S, "x", False) is True)
M.CFG["gerbang"]["aktif"] = False
check("gerbang.aktif=false: tetap kirim walau 'batal' tersedia", M.gerbang_persetujuan(S, "x", True) is True)
M.CFG["gerbang"].update(aktif=True, detik=0)
check("detik=0: dimatikan -> kirim", M.gerbang_persetujuan(S, "x", True) is True)
M.CFG["gerbang"]["detik"] = 20
del sys.modules["tkinter"]
sys.modules["tkinter"] = None   # tkinter tidak ada / tanpa layar -> ImportError
check("tanpa tkinter/layar: tetap kirim (gerbang tak boleh menggagalkan kirim)", M.gerbang_persetujuan(S, "x", True) is True)
print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
