# -*- coding: utf-8 -*-
"""
Uji F2.3: status field kondisional (core/formschema.py) selaras dengan validator.   python tests/test_form.py
Inti: baris yang diisi HANYA dari field aktif + opsi yang diizinkan tidak boleh menghasilkan ERROR
(DoD F2.3: tidak mungkin menyimpan kombinasi yang melanggar aturan), diuji pada 3000 baris acak.
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.formschema import SEMUA_KOLOM, build_schema, field_state, opsi_kolom  # noqa: E402
from core.obsdb import ObsStore  # noqa: E402
from core.validator import COLUMN_FIELD, Validator  # noqa: E402

V = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json")
ST = ObsStore(":memory:" if False else str(ROOT / "data" / "_test_form.db"))
passed = failed = 0


def check(n, c, info=""):
    global passed, failed
    print(("  OK   " if c else "  GAGAL"), n, "" if c else f"-> {info}")
    passed += bool(c)
    failed += (not c)


def kode(col, k):
    return next(o for o in opsi_kolom(V, col) if o.split(" ")[0] == k)


def S(d, jam=7):
    return field_state(V, d, jam)


print("== aturan field kondisional ==")
d = {}
s = S(d)
check("tutupan total kosong: semua awan nonaktif", all(not s[c]["aktif"] for c in ("cloud_low_type_cl", "awan_rendah_jenis")))
check("kolom wajib dasar ditandai", all(s[c]["wajib"] for c in ("visibility", "ww", "w1", "w2", "land_cond", "cloud_cover_oktas_m")))
for t in ("0", "/"):
    s = S({"cloud_cover_oktas_m": kode("cloud_cover_oktas_m", t)})
    check(f"total {t}: awan & vertical visibility nonaktif", not s["cloud_low_type_cl"]["aktif"] and not s["vertical_visibility"]["aktif"])
s = S({"cloud_cover_oktas_m": kode("cloud_cover_oktas_m", "9")})
check("total 9: vertical visibility aktif+wajib, awan nonaktif", s["vertical_visibility"]["wajib"] and not s["cloud_med_type_cm"]["aktif"])
base = {"cloud_cover_oktas_m": kode("cloud_cover_oktas_m", "5")}
s = S(base)
check("total 5: CL/CM/CH aktif & wajib, detail menunggu pilihan CL", s["cloud_low_type_cl"]["wajib"] and not s["awan_rendah_jenis"]["aktif"])
d = dict(base, cloud_low_type_cl=kode("cloud_low_type_cl", "1"))
s = S(d)
check("CL=1: jenis hanya Cu (8) [rules.json]", [x.split(" ")[0] for x in s["awan_rendah_jenis"]["pilihan"]] == ["8"], s["awan_rendah_jenis"])
d = dict(base, cloud_low_type_cl=kode("cloud_low_type_cl", "3"))
check("CL=3: jenis boleh 6,7,8,9", [x.split(" ")[0] for x in S(d)["awan_rendah_jenis"]["pilihan"]] == ["6", "7", "8", "9"])
check("CL=3 tanpa jenis: puncak nonaktif", not S(d)["cloud_low_peak_1"]["aktif"])
d["awan_rendah_jenis"] = V.options_for("AWAN RENDAH|k1|b2|Jenis") and next(o["value"] for o in V.options_for("AWAN RENDAH|k1|b2|Jenis") if o["code"] == "8")
s = S(d)
check("CL=3 + Cu: puncak/elevasi/arah sebenarnya aktif & wajib", all(s[c]["aktif"] and s[c]["wajib"] for c in
      ("cloud_low_peak_1", "cloud_elevation_1_angle_ec", "cloud_arah_sebenarnya_1")))
d2 = dict(base, cloud_low_type_cl=kode("cloud_low_type_cl", "1"), awan_rendah_jenis=d["awan_rendah_jenis"])
check("CL=1 + Cu: puncak NONAKTIF (aturan R23)", not S(d2)["cloud_low_peak_1"]["aktif"])
d3 = dict(base, cloud_low_type_cl=kode("cloud_low_type_cl", "0"))
check("CL=0: detail awan rendah nonaktif", not S(d3)["awan_rendah_jenis"]["aktif"] and not S(d3)["cloud_low_cover_oktas"]["aktif"])
d4 = dict(base, cloud_low_type_cl=kode("cloud_low_type_cl", "6"), awan_rendah_3_jenis=next(
    o["value"] for o in V.options_for("AWAN RENDAH|k3|b2|Jenis") if o["code"] == "7"))
s = S(d4)
check("lapisan 3 dipakai: kolom lapisan 3 jadi wajib semua (R14)", all(s[c]["wajib"] for c in
      ("awan_rendah_3_jumlah", "cloud_low_base_3", "cloud_arah_3")))
check("lapisan 3 memakai daftar jenis yang sama (CL=6 -> 7)", [x.split(" ")[0] for x in s["awan_rendah_3_jenis"]["pilihan"]] == ["7"])
s = S({}, jam=7)
check("jam 07 UTC: kolom hujan nonaktif (bukan kelipatan 3)", not s["hujan_override_aktif"]["aktif"])
s = S({}, jam=6)
check("jam 06 UTC: saklar hujan aktif, mm menunggu saklar", s["hujan_override_aktif"]["aktif"] and not s["hujan_override_mm"]["aktif"])
check("saklar hujan Ya: mm aktif & wajib", S({"hujan_override_aktif": True}, 6)["hujan_override_mm"]["wajib"])

print("\n== skema ==")
sk = build_schema(V)
kol = [f["kolom"] for b in sk["bagian"] for f in b["field"]]
check("semua kolom Excel ada di form, tanpa duplikat", len(kol) == len(set(kol)) and set(COLUMN_FIELD) <= set(kol), set(COLUMN_FIELD) - set(kol))
check("setiap dropdown punya daftar opsi", all(f["opsi"] for b in sk["bagian"] for f in b["field"] if f["jenis"] == "pilih"))

print("\n== sifat: isian dari field_state tidak pernah ditolak validator (3000 baris acak) ==")
rnd = random.Random(11)


def isi(jam):
    d = {"cloud_cover_oktas_m": rnd.choice(opsi_kolom(V, "cloud_cover_oktas_m"))}
    for _ in range(40):                                  # sampai stabil
        st = field_state(V, d, jam)
        berubah = False
        for c in SEMUA_KOLOM:
            s = st[c]
            if not s["aktif"]:
                berubah |= d.pop(c, None) is not None
                continue
            if c in d:
                if s["pilihan"] is not None and d[c] not in s["pilihan"]:
                    d.pop(c)
                    berubah = True
                continue
            if not (s["wajib"] or rnd.random() < 0.3):
                continue
            berubah = True
            if c in COLUMN_FIELD:
                pil = s["pilihan"] if s["pilihan"] is not None else opsi_kolom(V, c)
                d[c] = rnd.choice(pil)
            elif c == "hujan_override_aktif":
                d[c] = rnd.random() < 0.5
            else:
                d[c] = {"visibility": rnd.choice([0.5, 3, 8, 10]), "vertical_visibility": rnd.choice([30, 60, 90])}.get(
                    c, rnd.choice([300, 450, 900, 1500, 3000]))
        if not berubah:
            break
    if str(d["cloud_cover_oktas_m"]).startswith("9"):
        d["visibility"] = 0.5
    for c in ("ww", "w1", "w2", "land_cond"):
        d.setdefault(c, rnd.choice(opsi_kolom(V, c)))
    d.setdefault("visibility", 10)
    return d


galat, n_awan = {}, 0
for i in range(3000):
    jam = rnd.randrange(24)
    d = isi(jam)
    n_awan += "cloud_low_type_cl" in d
    r = V.validate_row(ST.to_row("2026-11-14", f"{jam:02d}:00", d), 2)
    for x in r.errors:
        galat[(x.rule, x.column)] = galat.get((x.rule, x.column), 0) + 1
check("3000 baris acak: 0 ERROR dari validator", not galat, galat)
check("sebagian besar baris acak benar-benar memakai awan (uji bermakna)", n_awan > 1500, n_awan)

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
