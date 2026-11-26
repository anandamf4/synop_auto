# -*- coding: utf-8 -*-
"""Regresi rev 37:  python tests/test_db_kolom.py
Bot sumber DB gagal 'awan_rendah_2_jenis' (KeyError) karena DataFrame DB hanya memuat kolom yang tersimpan.
Uji ini memakai jalur ASLI: ObsStore.upsert -> to_dataframe -> V7SATU.isi_data (tanpa browser)."""
import importlib.util, re, sys, tempfile, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("pyautogui", types.ModuleType("pyautogui"))
import pandas as pd  # noqa: E402
from core.obsdb import ObsStore, URUTAN_KOLOM  # noqa: E402
from core.validator import Validator  # noqa: E402

spec = importlib.util.spec_from_file_location("V7SATU_db", ROOT / "V7SATU.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond); failed += (not cond)


# data persis seperti kasus nyata: lapisan 1 saja, lapisan 2 TIDAK diisi (tak tersimpan di DB)
DATA = {"visibility": 10, "ww": "02 - state of sky unchanged", "w1": "2 - Cloudy +", "w2": "2 - Cloudy +",
        "cloud_cover_oktas_m": "6 oktas", "cloud_low_type_cl": "5 - stratocumulus yang tidak terjadi dari bentangan cumulus",
        "cloud_low_cover_oktas": "2 oktas", "awan_rendah_jenis": "6 - stratocumulus (Sc)", "awan_rendah_jumlah": "2 oktas",
        "cloud_low_base_1": 420, "cloud_arah_awan_rendah": "0 - Stationary or No Clouds"}

print("== DataFrame DB memuat semua kolom yang diakses bot ==")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
    st = ObsStore(str(Path(d) / "t.db"))
    st.upsert("2026-11-25", "00:00", DATA, "uji")
    df = st.to_dataframe("2026-11-25", "2026-11-25")
    row = df.iloc[0]
    check("kolom lapisan 2 ada & bernilai NaN (bukan KeyError)", "awan_rendah_2_jenis" in df.columns and pd.isna(row["awan_rendah_2_jenis"]))
    kunci = set(re.findall(r"row\[\s*['\"]([A-Za-z0-9_]+)['\"]\s*\]", (ROOT / "V7SATU.py").read_text(encoding="utf-8")))
    hilang = sorted(kunci - set(df.columns))
    check("SEMUA kolom row['...'] di V7SATU.py ada di DataFrame DB", not hilang, hilang)
    check("DB kosong tetap bisa dibuat DataFrame-nya", st.to_dataframe("2030-01-01", "2030-01-02").empty)

    print("== isi_data dengan baris dari DB (tanpa lapisan 2) ==")
    calls = []
    M.pilih_dropdown_ant_select = lambda drv, i, v, **k: (calls.append(("select", i, v)) or True)
    M.isi_input_text = lambda drv, i, v, timeout=12: (calls.append(("input", i, v)) or True)
    for n in ("isi_jenis_dan_jumlah_awan_Rendah", "pilih_arah_Awan_Rendah", "pilih_arah_sebenarnya", "klik_switch_jika_type",
              "isi_jenis_dan_jumlah_awan_rendah_2", "pilih_arah_2", "pilih_arah_sebenarnya_2", "isi_jenis_dan_jumlah_awan_menengah",
              "pilih_arah_Awan_Menengah", "isi_jenis_dan_jumlah_awan_Tinggi", "pilih_arah_Awan_Tinggi"):
        setattr(M, n, lambda *a, **k: True)
    M.isi_hujan_override = lambda drv, mm: True
    M._switch_aktif = lambda drv, i: False
    M._atur_switch = lambda drv, i, a: True
    V = Validator.from_files(ROOT / "core/options.json", ROOT / "core/rules.json")
    meta = st.to_row("2026-11-25", "00:00")
    rr = V.validate_row(meta, 2)
    ok = M.isi_data(object(), row, plan=rr.plan)
    check("isi_data(baris DB) berhasil, tidak 'Gagal mengisi data'", ok is True, (ok, rr.errors if hasattr(rr, "errors") else ""))

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
