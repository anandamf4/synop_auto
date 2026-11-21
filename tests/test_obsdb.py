# -*- coding: utf-8 -*-
"""Uji F2.1/F2.6: penyimpanan observasi. Excel nyata -> DB -> DataFrame harus identik.   python tests/test_obsdb.py"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402
from core.obsdb import ObsStore, normalisasi  # noqa: E402
from core.validator import Validator, load_excel  # noqa: E402

V = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json")
passed = failed = 0


def check(n, c, info=""):
    global passed, failed
    print(("  OK   " if c else "  GAGAL"), n, "" if c else f"-> {info}")
    passed += bool(c)
    failed += (not c)


with tempfile.TemporaryDirectory() as d:
    st = ObsStore(Path(d) / "o.db")
    print("== dasar ==")
    check("normalisasi: kosong/NaN/Unnamed/kolom turunan dibuang, angka bulat jadi int",
          normalisasi({"a": "x", "b": "", "c": float("nan"), "Unnamed: 3": 1, "jam_input": "07:00", "n": 450.0, "f": 2.5, "t": True})
          == {"a": "x", "n": 450, "f": 2.5, "t": True})
    st.upsert("2026-11-14", "07:00", {"visibility": 10, "ww": "02 - x"}, "Ana")
    check("simpan lalu baca", st.get("2026-11-14", "07:00") == {"visibility": 10, "ww": "02 - x"})
    st.upsert("2026-11-14", "07:00", {"visibility": 8}, "Budi")
    check("simpan lagi menimpa (1 baris per slot) dan mencatat siapa", st.get("2026-11-14", "07:00") == {"visibility": 8}
          and st.info("2026-11-14", "07:00")["diubah_oleh"] == "Budi")
    check("list_day", list(st.list_day("2026-11-14")) == ["07:00"])
    st.delete("2026-11-14", "07:00")
    check("hapus", st.get("2026-11-14", "07:00") is None)
    check("jam sebelumnya melewati pergantian hari UTC", ObsStore.slot_sebelumnya("2026-11-15", "00:00") == ("2026-11-14", "23:00"))
    check("waktu_eksekusi = jam UTC + 7 jam - 2 menit (13:58 WIB untuk 07:00 UTC)",
          st.waktu_eksekusi("2026-11-14", "07:00") == dt.datetime(2026, 11, 14, 13, 58))
    check("waktu_eksekusi lintas hari (23:00 UTC = 05:58 WIB hari berikutnya)",
          st.waktu_eksekusi("2026-11-14", "23:00") == dt.datetime(2026, 11, 15, 5, 58))

    print("\n== Excel nyata -> DB -> DataFrame (zero-loss) ==")
    xl = ROOT / "legacy" / "INPUT_PARAMETER_baru.xlsx"
    if xl.exists():
        df = load_excel(xl)
        st2 = ObsStore(Path(d) / "x.db")
        masuk, lewat = st2.import_dataframe(df)
        check("24 baris Excel masuk semua", masuk == len(df) == 24 and not lewat, (masuk, lewat))
        out = st2.to_dataframe()
        check("jumlah baris sama", len(out) == len(df), (len(out), len(df)))
        selisih = [(b - pd.to_datetime(a)).total_seconds() / 60 for a, b in zip(df["waktu_eksekusi"], out["waktu_eksekusi"])]
        check("waktu_eksekusi hasil hitung selisih 0-2 menit dari Excel asli (Excel memakai 0-2 menit sebelum jam; DB tetap 2 menit sebelum)",
              all(-2 <= x <= 0 for x in selisih), selisih)
        check("slot (tanggal+jam UTC) tiap baris identik dengan Excel asli",
              [r.slot for r in V.validate_dataframe(df)[1]] == [r.slot for r in V.validate_dataframe(out)[1]])
        beda = []
        for (_, a), (_, b) in zip(df.iterrows(), out.iterrows()):
            na = normalisasi({k: a[k] for k in df.columns})
            nb = normalisasi({k: b[k] for k in out.columns})
            if na != nb:
                beda.append({k: (na.get(k), nb.get(k)) for k in set(na) | set(nb) if na.get(k) != nb.get(k)})
        check("isi setiap sel identik (tanpa kehilangan kolom/nilai)", not beda, beda[:2])
        fi, hasil = V.validate_dataframe(out)
        fi0, hasil0 = V.validate_dataframe(df)
        check("validasi DataFrame dari DB = validasi Excel asli (0 ERROR, jumlah temuan sama)",
              sum(len(r.errors) for r in hasil) == 0 and
              sorted(str(i) for r in hasil for i in r.issues if i.level != "INFO") ==
              sorted(str(i) for r in hasil0 for i in r.issues if i.level != "INFO"))
        check("rentang tanggal: hanya 14 Nov", len(st2.to_dataframe("2026-11-14", "2026-11-14")) == 24
              and len(st2.to_dataframe("2026-11-15", "2026-11-16")) == 0)
    else:
        print("  (lewati) legacy/INPUT_PARAMETER_baru.xlsx tidak ada")

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
