# -*- coding: utf-8 -*-
"""
Uji lapisan tambahan V7SATU (F3.10) TANPA browser:  python tests/test_layers.py
Menguji alur isi_lapisan_tambahan, pencarian switch berdasar urutan, dan pilih_dropdown_posisi
dengan DOM tiruan. Perilaku di web asli dibuktikan lewat dry-run pengguna.
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))

spec = importlib.util.spec_from_file_location("V7SATU_layers", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


class El:
    def __init__(self, enabled=True, **attrs):
        self._en, self.attrs = enabled, attrs

    def is_enabled(self):
        return self._en

    def get_attribute(self, n):
        return self.attrs.get(n)

    @property
    def text(self):
        return self.attrs.get("title", "")


# ---------------------------------------------------------------------------
print("== isi_lapisan_tambahan: alur ==")
calls = []
state = {"dd_ok": True, "switch_ok": True, "input_ok": True, "switch_state": {}}


class DrvFlow:
    def find_element(self, by, value):
        return El(enabled=True)


M._id_toggle = lambda drv, sec, ordn, fb: f"T{ordn}"
M._atur_switch = lambda drv, tid, aktif: (calls.append(("switch", tid, aktif)) or state["switch_ok"])
M._switch_aktif = lambda drv, tid: state["switch_state"].get(tid, False)
M.pilih_dropdown_posisi = lambda drv, sec, col, row, text, timeout=4: (
    calls.append(("dd", sec, col, row, text)) or (state["dd_ok"] if row != 3 else state.get("jumlah_ok", True)))
M.isi_input_text = lambda drv, id_, nilai, timeout=12: (calls.append(("input", id_, nilai)) or state["input_ok"])

MED2 = {"layer": "med", "n": 2, "section": "AWAN MENENGAH", "col": 2, "toggle_ordinal": 1, "fallback_toggle_id": "777",
        "arah_row": 5, "base_id": "cloud_med_base_2", "jenis": "3 - altocumulus (Ac)", "jumlah": "2 - 2 oktas",
        "arah": "0 - Stationary or No Clouds", "base": 4500.0}
LOW3 = {"layer": "low", "n": 3, "section": "AWAN RENDAH", "col": 3, "toggle_ordinal": 2, "fallback_toggle_id": "776",
        "arah_row": 6, "base_id": "cloud_low_base_3", "jenis": "6 - stratocumulus (Sc)", "jumlah": "1 okta or less, but not zero",
        "arah": "0 - Stationary or No Clouds", "base": 500.0}

M.CFG["features"]["extra_layers"] = True
M.GAGAL_OPSIONAL.clear()
calls.clear()
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [MED2], "extra_off": []})
check("switch dinyalakan, 3 dropdown dipilih di posisi yang benar, dasar diisi",
      calls == [("switch", "T1", True),
                ("dd", "AWAN MENENGAH", 2, 2, "3 - altocumulus (Ac)"),
                ("dd", "AWAN MENENGAH", 2, 3, "2 - 2 oktas"),
                ("dd", "AWAN MENENGAH", 2, 5, "0 - Stationary or No Clouds"),
                ("input", "cloud_med_base_2", "4500")], calls)
check("tanpa kegagalan -> GAGAL_OPSIONAL kosong", M.GAGAL_OPSIONAL == [], M.GAGAL_OPSIONAL)

calls.clear()
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [LOW3], "extra_off": []})
check("rendah-3: kolom 3, baris Arah 6, switch urutan ke-2",
      ("switch", "T2", True) in calls and ("dd", "AWAN RENDAH", 3, 6, "0 - Stationary or No Clouds") in calls
      and ("input", "cloud_low_base_3", "500") in calls, calls)

M.GAGAL_OPSIONAL.clear()
state["jumlah_ok"] = False
calls.clear()
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [MED2], "extra_off": []})
check("satu dropdown gagal: dicatat, sisanya tetap diisi",
      any("Jumlah" in g for g in M.GAGAL_OPSIONAL) and ("input", "cloud_med_base_2", "4500") in calls, (M.GAGAL_OPSIONAL, calls))
state["jumlah_ok"] = True

M.GAGAL_OPSIONAL.clear()
state["switch_ok"] = False
calls.clear()
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [MED2], "extra_off": []})
check("switch gagal diaktifkan: dicatat dan tidak ada dropdown diisi",
      any("switch" in g for g in M.GAGAL_OPSIONAL) and not any(c[0] == "dd" for c in calls), (M.GAGAL_OPSIONAL, calls))
state["switch_ok"] = True

M.GAGAL_OPSIONAL.clear()
state["input_ok"] = False
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [MED2], "extra_off": []})
check("tinggi dasar gagal diisi: dicatat", any("tinggi dasar" in g for g in M.GAGAL_OPSIONAL), M.GAGAL_OPSIONAL)
state["input_ok"] = True

print("== extra_off: matikan lapisan sisa data lama ==")
OFF = {"layer": "med", "n": 2, "section": "AWAN MENENGAH", "toggle_ordinal": 1, "fallback_toggle_id": "777"}
state["switch_state"] = {"T1": True}
calls.clear()
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [], "extra_off": [OFF]})
check("switch aktif & Excel kosong -> dimatikan", calls == [("switch", "T1", False)], calls)
state["switch_state"] = {"T1": False}
calls.clear()
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [], "extra_off": [OFF]})
check("switch sudah mati -> tidak disentuh", calls == [], calls)

print("== saklar fitur & plan kosong ==")
M.CFG["features"]["extra_layers"] = False
calls.clear()
M.isi_lapisan_tambahan(DrvFlow(), {"extra": [MED2], "extra_off": [OFF]})
check("features.extra_layers=false: tidak melakukan apa pun", calls == [], calls)
M.CFG["features"]["extra_layers"] = True
M.isi_lapisan_tambahan(DrvFlow(), None)
M.isi_lapisan_tambahan(DrvFlow(), {})
check("plan None / kosong: aman", calls == [], calls)

# ---------------------------------------------------------------------------
print("== _id_toggle: urutan di seksi ==")
M2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M2)


class DrvIds:
    def __init__(self, ids, boom=False):
        self.ids, self.boom = ids, boom

    def execute_script(self, js, *a):
        if self.boom:
            raise RuntimeError("x")
        return self.ids


check("urutan ke-2 dari ['775','776'] -> '776'", M2._id_toggle(DrvIds(["775", "776"]), "AWAN RENDAH", 2, "999") == "776")
check("id berubah di web (['801','802']) tetap benar lewat urutan", M2._id_toggle(DrvIds(["801", "802"]), "AWAN RENDAH", 2, "776") == "802")
check("daftar kosong -> id terakhir terlihat", M2._id_toggle(DrvIds([]), "AWAN TINGGI", 1, "778") == "778")
check("error JS -> id terakhir terlihat", M2._id_toggle(DrvIds([], boom=True), "AWAN MENENGAH", 1, "777") == "777")

# ---------------------------------------------------------------------------
print("== pilih_dropdown_posisi dengan DOM tiruan ==")


class Li:
    def __init__(self, text):
        self.text = text


class Sel:
    def __init__(self):
        self.selected = None
        self.combo = El(**{"aria-controls": "menu-1"})

    def find_element(self, by, value):
        return self.combo

    def find_elements(self, by, value):
        return [El(title=self.selected)] if self.selected else []


class DrvDom:
    def __init__(self, sel, options, missing=False):
        self.sel, self.options, self.missing, self.open = sel, options, missing, False

    def execute_script(self, js, *a):
        if "querySelector('.ant-select')" in js:
            return None if self.missing else self.sel
        if "offsetParent" in js:
            return self.open
        if "querySelectorAll('li')" in js:
            return Li(a[1]) if a[1] in self.options else None
        return None


def fake_click(drv, el):
    if el is drv.sel.combo:
        drv.open = True
    elif isinstance(el, Li):
        drv.sel.selected = el.text
    return True


M2.attempt_click = fake_click
sel = Sel()
d = DrvDom(sel, ["3 - altocumulus (Ac)", "4 - altostratus (As)"])
check("memilih opsi yang ada -> True & nilai terpilih",
      M2.pilih_dropdown_posisi(d, "AWAN MENENGAH", 2, 2, "3 - altocumulus (Ac)", timeout=1) is True
      and sel.selected == "3 - altocumulus (Ac)", sel.selected)
sel = Sel()
d = DrvDom(sel, ["4 - altostratus (As)"])
check("opsi tidak ada / nonaktif -> False tanpa crash",
      M2.pilih_dropdown_posisi(d, "AWAN MENENGAH", 2, 2, "3 - altocumulus (Ac)", timeout=1) is False and sel.selected is None)
d = DrvDom(Sel(), [], missing=True)
check("posisi tidak ditemukan -> False tanpa crash",
      M2.pilih_dropdown_posisi(d, "AWAN MENENGAH", 9, 9, "x", timeout=1) is False)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
