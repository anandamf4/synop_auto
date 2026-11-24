# -*- coding: utf-8 -*-
"""rev 27: bagian bawah form jam 00 UTC (penguapan, iE, radiasi, lama penyinaran): validator, skema form, penyimpanan, isian bot."""
import importlib.util, os, sys, tempfile, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond); failed += (not cond)


from app import create_app
from core.config import load_config
from core.formschema import opsi_kolom, field_state

os.environ.pop("WEB_PIN", None)
T = "2026-11-14"
d = tempfile.mkdtemp()
app = create_app(load_config(), db_path=str(Path(d) / "p.db"))
V = app.validator


def op(col, k): return next(o for o in opsi_kolom(V, col) if o.split(" ")[0] == k)


CERAH = {"cloud_cover_oktas_m": op("cloud_cover_oktas_m", "0"), "visibility": 10, "ww": op("ww", "00"),
         "w1": op("w1", "0"), "w2": op("w2", "0"), "land_cond": op("land_cond", "0")}


def nilai(jam, **ekstra):
    row = app.obs.to_row(T, jam, dict(CERAH, **ekstra))
    return V.validate_row(row, 0)


def aturan(rr, level=None): return {(i.rule, i.level) for i in rr.issues if level is None or i.level == level}


print("== validator ==")
rr = nilai("00:00", penguapan_mm=5.9, penguapan_ie=0, radiasi_kosongkan=True, lama_penyinaran_jam=2.4)
check("jam 00: rencana lengkap, tanpa ERROR", not rr.errors and rr.plan["penguapan"] == {"mm": 5.9, "ie": 0, "radiasi": {"kosongkan": True}, "sinar_jam": 2.4}, (rr.plan["penguapan"], [str(i) for i in rr.errors]))
rr = nilai("00:00")
check("jam 00 tanpa isian: tidak ada rencana (nilai AWS dibiarkan)", rr.plan["penguapan"] is None)
rr = nilai("00:00", radiasi_matahari=120)
check("radiasi nilai baru -> rencana nilai", rr.plan["penguapan"] == {"radiasi": {"nilai": 120.0}}, rr.plan["penguapan"])
rr = nilai("03:00", penguapan_mm=5.9)
check("jam 03: WARNING R25 dan DIABAIKAN", ("R25", "WARNING") in aturan(rr) and rr.plan["penguapan"] is None and not rr.errors)
check("kosongkan + nilai radiasi sekaligus -> ERROR R26", ("R26", "ERROR") in aturan(nilai("00:00", radiasi_kosongkan=True, radiasi_matahari=100)))
check("iE bukan 0-4 (dropdown web) -> ERROR R25", ("R25", "ERROR") in aturan(nilai("00:00", penguapan_ie=12)) and ("R25", "ERROR") in aturan(nilai("00:00", penguapan_ie=5)) and ("R25", "ERROR") not in aturan(nilai("00:00", penguapan_ie=4)))
check("lama penyinaran 30 jam -> ERROR R27", ("R27", "ERROR") in aturan(nilai("00:00", lama_penyinaran_jam=30)))
check("lama penyinaran 14 jam -> WARNING R27", ("R27", "WARNING") in aturan(nilai("00:00", lama_penyinaran_jam=14)))
check("angka negatif ditolak (R-NUM)", ("R-NUM", "ERROR") in aturan(nilai("00:00", penguapan_mm=-1)))

print("== skema form ==")
S0 = field_state(V, dict(CERAH), 0); S3 = field_state(V, dict(CERAH), 3)
cols = ["penguapan_mm", "penguapan_ie", "radiasi_kosongkan", "radiasi_matahari", "lama_penyinaran_jam"]
check("jam 00: semua kolom penguapan aktif", all(S0[c]["aktif"] for c in cols))
check("jam 03: semua kolom penguapan nonaktif", not any(S3[c]["aktif"] for c in cols))
check("radiasi dikosongkan -> kolom nilai radiasi nonaktif", not field_state(V, dict(CERAH, radiasi_kosongkan=True), 0)["radiasi_matahari"]["aktif"])
sk = app.test_client().get("/api/skema").get_json()
check("skema memuat bagian penguapan dengan 6 kolom (5 kolom jam 00 + keadaan tanah; saklar untuk 'kosongkan')",
      any(b["id"] == "penguapan" and len(b["field"]) == 6 and any(f["kolom"] == "radiasi_kosongkan" and f["jenis"] == "saklar" for f in b["field"]) for b in sk["bagian"]))

print("== simpan / baca / salin ==")
c = app.test_client()
data = dict(CERAH, penguapan_mm=5.9, penguapan_ie=0, radiasi_kosongkan=True, lama_penyinaran_jam=2.4)
r = c.post("/api/simpan", json={"tanggal": T, "jam": "00:00", "observer": "Tester", "data": data})
back = c.get(f"/api/slot/{T}/00:00").get_json()["data"]
check("tersimpan & terbaca utuh (termasuk saklar boolean)", r.status_code == 200 and back.get("penguapan_mm") == 5.9 and back.get("radiasi_kosongkan") is True and back.get("lama_penyinaran_jam") == 2.4, (r.get_json(), back))
c.post("/api/simpan", json={"tanggal": T, "jam": "01:00", "observer": "Tester", "data": CERAH})
sal = c.get(f"/api/salin?tanggal={T}&jam=01:00").get_json()
check("salin ke jam berikutnya TIDAK membawa isian penguapan", sal is not None and not any(k in sal["data"] for k in cols), sal)
r = c.post("/api/simpan", json={"tanggal": T, "jam": "03:00", "observer": "Tester", "data": dict(CERAH, penguapan_mm=3)})
check("jam 03 dengan isian penguapan: kolom dibuang oleh jaring pengaman (tidak tersimpan)", "penguapan_mm" not in (c.get(f"/api/slot/{T}/03:00").get_json().get("data") or {}))

print("== isian bot (driver palsu) ==")
sys.modules["pyautogui"] = None
spec = importlib.util.spec_from_file_location("V7_p", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
M.time = types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time)


class El:
    def __init__(self, value="", enabled=True, tolak=False, kelas="", teks="", id_=""):
        self.value, self.enabled, self.tolak, self.kelas, self.teks, self.id_ = value, enabled, tolak, kelas, teks, id_
        self.hapus = False
    def is_enabled(self): return self.enabled
    def click(self): pass
    def get_attribute(self, a): return {"value": self.value, "class": self.kelas, "id": self.id_}.get(a, "")
    def send_keys(self, *k):
        for x in k:
            if x == M.Keys.BACKSPACE: self.value = "" if not self.tolak else self.value
            elif x in (M.Keys.CONTROL, M.Keys.TAB): pass
            elif x == "a": pass
            elif not self.tolak: self.value += x


class Drv:
    def __init__(self, els): self.els = els; self.ant = []
    def execute_script(self, js, *a):
        if "startsWith" in js: return self.els.get(a[0])
        if "innerText" in js: return a[0].teks
        return None
    def find_element(self, by, v): raise Exception("tidak ada")


def fresh(**k):
    M.CFG["features"]["penguapan_strict"] = k.pop("strict", True)
    M.CFG["web_ids"] = {}
    return Drv({M.LABEL_PENGUAPAN[x]: e for x, e in k.items()})


drv = fresh(mm=El("3,2"), radiasi=El("850"), sinar_jam=El("1"))
ok = M.isi_penguapan_00(drv, {"mm": 5.9, "radiasi": {"kosongkan": True}, "sinar_jam": 2.4})
check("isi mm, kosongkan radiasi, isi sinar -> True, nilai akhir benar",
      ok and drv.els["penguapan (mm)"].value == "5.9" and drv.els["radiasi matahari"].value == "" and drv.els["lama penyinaran matahari"].value == "2.4", [(k, e.value) for k, e in drv.els.items()])
check("nilai AWS asli tercatat di log", M.PENGUAPAN_LOG["mm"]["aws"] == "3,2" and M.PENGUAPAN_LOG["radiasi"]["aws"] == "850" and M.PENGUAPAN_LOG["mm"]["applied"])
drv = fresh(mm=El("3,2"))
check("kolom diminta tapi tidak ada di web (strict) -> False", M.isi_penguapan_00(drv, {"mm": 5.9, "sinar_jam": 2.4}) is False)
drv = fresh(strict=False, mm=El("3,2"))
check("strict=false -> lanjut kirim (True) walau ada yang gagal", M.isi_penguapan_00(drv, {"mm": 5.9, "sinar_jam": 2.4}) is True)
drv = fresh(mm=El("3,2", enabled=False))
check("kolom nonaktif -> False", M.isi_penguapan_00(drv, {"mm": 5.9}) is False and "NONAKTIF" in M.PENGUAPAN_LOG["mm"]["reason"])
drv = fresh(mm=El("3,2", tolak=True))
check("web menolak ketikan (nilai akhir beda) -> False", M.isi_penguapan_00(drv, {"mm": 5.9}) is False)
drv = fresh(radiasi=El("850", tolak=True))
check("radiasi gagal dikosongkan -> False", M.isi_penguapan_00(drv, {"radiasi": {"kosongkan": True}}) is False)
drv = fresh(mm=El("3,2"))
M.CFG["web_ids"] = {"penguapan_mm": "evap_x"}
drv.find_element = lambda by, v: drv.els["penguapan (mm)"] if v == "evap_x" else (_ for _ in ()).throw(Exception("x"))
check("ID dari config.yaml dipakai bila diisi", M.isi_penguapan_00(drv, {"mm": 7}) is True and drv.els["penguapan (mm)"].value == "7")
M.CFG["web_ids"] = {}
dipilih = []
M.pilih_dropdown_ant_select = lambda dr, eid, teks, **k: (dipilih.append((eid, teks)), setattr(dr.els["pengenal data penguapan"], "teks", "0 - USA open pan"))[0] or True
drv = fresh(ie=El(kelas="ant-select ant-select-enabled", teks="2 - lain", id_="ie_div"))
check("iE: dropdown dipilih lewat kode & diverifikasi", M.isi_penguapan_00(drv, {"ie": 0}) is True and dipilih == [("ie_div", "0 -")], dipilih)

print("== pencari label di browser sungguhan (Chromium) ==")
try:
    from playwright.sync_api import sync_playwright
    html = """<div class=row><label class=c>Penguapan (mm) <i>?</i></label><div><input id=a1 value="5,9"></div></div>
    <div class=row><label>Pengenal Data Penguapan (iE) <i>?</i></label><div><div class="ant-select" id="ie1"><div class="ant-select-selection__rendered">0 - USA open</div><input class="ant-select-search__field"></div></div></div>
    <div class=row><label>Radiasi Matahari (Joule/cm2)</label><div><input id=a3></div></div>
    <div class=row><label for=zz>Lama Penyinaran Matahari (jam)</label><div><input id=zz value="2,4"></div></div>
    <div class=row><label>Catatan</label><div><input id=cat></div></div>"""
    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page(); pg.set_content(html)
        hasil = {k: pg.evaluate("(a)=>{const f=new Function('return (function(){'+a[1]+'}).apply(null,arguments)'); return null}", [k, ""]) for k in []}
        js = M._JS_CARI_LABEL
        cari = lambda t: pg.evaluate("([js,t])=>{const f=new Function('return (function(){'+js+'})')(); return (function(){const arguments_=[t]; return (new Function('arguments_', js.replace(/arguments\\[0\\]/g,'arguments_[0]')))(arguments_);})()?.id}", [js, t])
        check("label 'Penguapan (mm)' -> input a1 (bukan kolom iE)", cari("penguapan (mm)") == "a1", cari("penguapan (mm)"))
        check("label iE -> kontainer ant-select ie1", cari("pengenal data penguapan") == "ie1", cari("pengenal data penguapan"))
        check("label radiasi -> input a3", cari("radiasi matahari") == "a3")
        check("label ber-atribut for -> elemen sesuai id", cari("lama penyinaran matahari") == "zz")
        check("label tak ada -> null", cari("tidak ada") is None)
        br.close()
except Exception as e:
    print("  (dilewati: Chromium/playwright tidak tersedia:", str(e)[:80], ")")

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
