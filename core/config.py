# -*- coding: utf-8 -*-
"""
core/config.py  -  F1.1: konfigurasi + kredensial (tanpa password di kode)

Pemakaian:
    from core.config import load_config, get_credentials, resolve_path
    cfg = load_config()                       # membaca config.yaml (+ .env)
    sid, pw = get_credentials()               # dari .env / environment / prompt
    excel = resolve_path(cfg, "excel")        # path absolut
"""
import copy
import getpass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None
try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "station": {"name": "Stasiun Meteorologi Sultan Thaha"},
    "urls": {
        "login": "https://bmkgsatu.bmkg.go.id/login",
        "sinoptik": "https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik",
    },
    "paths": {
        "excel": "INPUT_PARAMETER.xlsx",
        "db": "data/synop.db",
        "snapshots": "snapshots",
        "options": "core/options.json",
        "rules": "core/rules.json",
        "rules_qc": "core/rules_qc.json",   # F1.10: aturan QC konsistensi
        # gambar tombol OK untuk popup awal (pyautogui); jika tidak ada, bot mencoba klik via Selenium
        "ok_image": r"D:\OTO_SYNOP\SYNOP\ok.PNG",
    },
    "runtime": {
        "timezone_offset_hours": 7,
        "max_row_recovery": 2,
        "window_open_minutes": 10,
        "late_info_minutes": 15,
        # >0: slot yang gagal/terhenti boleh dicoba ulang sampai sekian menit setelah waktu eksekusi
        "retry_past_minutes": 0,
    },
    "observers": {"allowed": []},
    "chrome": {
        "profile_dir": "",                    # F3.3: kosong = profil sementara; isi (mis. \"chrome_profile\") = sesi login disimpan
        "retry_buka": 3,                      # rev 28: berapa kali Chrome dicoba dibuka (profil dibebaskan di antara percobaan)
        "fallback_profil_sementara": True,    # rev 28: bila profil tetap terus gagal, pakai profil sementara (login dari awal)
    },
    "session": {                              # rev 28: BMKG Satu bisa logout sendiri tiap beberapa jam
        "aktif": True,
        "cek_sebelum_detik": 180,             # periksa sesi (login ulang bila perlu) sekian detik sebelum tiap eksekusi
        "cek_ulang_menit": 10,                # lewati pemeriksaan bila sesi terbukti hidup < sekian menit lalu
    },
    "features": {
        "extra_layers": True,          # F3.10: isi lapisan tambahan (rendah-3, menengah-2, tinggi-2)
        "send_despite_detail_fail": False,  # True: tetap kirim walau Jenis/Jumlah/Arah wajib gagal diisi
        "verify_sandi": True,               # F3.4: bandingkan sandi hasil Preview dengan data Excel
        "sandi_block_on_mismatch": False,   # True: batalkan KIRIM bila verifikasi sandi menemukan ERROR
        "qff_qfe_check": True,              # periksa selisih QFF-QFE setelah Fill AWS Digi
        "qff_qfe_expected_diff": 3.2,       # hPa; stasiun 27 m
        "qff_qfe_tolerance": 1.0,           # hPa
        "dry_run": False,
        "allow_update": True,          # jam yang sudah ada di web boleh ditimpa lewat tombol Update
        "rain_override_strict": False,  # True: batalkan baris jika override hujan gagal diterapkan
        "qc_enabled": True,             # F1.10: jalankan aturan QC konsistensi (core/qc.py)
        "qc_strict": False,             # True: temuan QC "pasti" (PPT) menjadi ERROR dan memblok baris
        "data_source": "excel",         # F2.7: "excel" (INPUT_PARAMETER.xlsx) atau "db" (diisi lewat form web app.py)
        "qc_popup_auto_submit": True,   # F3.11: popup web "Koreksi QC" -> klik Submit otomatis (data tetap terkirim)
        "qc_popup_tunggu": 12,          # F3.11: batas (detik) mengawasi popup susulan setelah OK terakhir
        "qc_popup_tenang": 4,           # F3.11: layar dianggap tenang bila tak ada popup selama N detik
    },
    "web": {"host": "0.0.0.0", "port": 8080, "menit_sebelum": 2},   # F2: form & dashboard (app.py)
    "notify": {                         # F3.7 Telegram (token & chat_id di .env, BUKAN di sini)
        "enabled": True,
        "kirim_gagal": True,            # gagal kirim / baris dilewati karena validasi / bot berhenti
        "kirim_recovery": True,         # pemulihan sesi browser
        "kirim_diubah": True,           # terkirim tetapi ada perubahan otomatis (mis. ww 10->05)
        "kirim_sukses": False,          # pesan tiap jam terkirim (24x/hari); bawaan mati
        "kirim_rekap": True,            # ringkasan harian
        "kirim_screenshot": True,
        "kirim_saat_dry_run": False,
        "alarm_suara": True,            # bunyi lokal (Windows) saat gagal total
        "rekap_jam_utc": "23:50",
        "nama_stasiun": "Sultan Thaha (96195)",
    },
}


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path=None):
    """Baca .env lalu config.yaml; kunci yang tidak ada memakai DEFAULTS."""
    env_file = ROOT / ".env"
    if load_dotenv is not None and env_file.exists():
        load_dotenv(env_file)
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    user_cfg = {}
    if cfg_path.exists():
        if yaml is None:
            raise RuntimeError("PyYAML belum terpasang. Jalankan: pip install -r requirements.txt")
        with open(cfg_path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    return _merge(DEFAULTS, user_cfg)


def resolve_path(cfg, key):
    """Path dari cfg['paths'][key]; relatif -> terhadap folder proyek."""
    p = Path(os.path.expandvars(os.path.expanduser(str(cfg["paths"][key]))))
    return p if p.is_absolute() else (ROOT / p)


def get_credentials(interactive=True):
    """
    Urutan: environment / .env  ->  prompt terminal (jika interactive).
    Nama variabel: BMKG_STATION_ID dan BMKG_PASSWORD.
    """
    sid = os.environ.get("BMKG_STATION_ID", "").strip()
    pw = os.environ.get("BMKG_PASSWORD", "")
    placeholder = {"", "isi_station_id", "isi_password"}
    if sid in placeholder or pw in placeholder:
        if not interactive:
            raise RuntimeError(
                "Kredensial belum diisi. Salin .env.example menjadi .env lalu isi "
                "BMKG_STATION_ID dan BMKG_PASSWORD."
            )
        if sid in placeholder:
            sid = input("Station ID : ").strip()
        if pw in placeholder:
            pw = getpass.getpass("Password   : ")
    return sid, pw
