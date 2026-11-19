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
    "features": {
        "medium_layer2_supported": False,
        "dry_run": False,
        "allow_update": True,          # jam yang sudah ada di web boleh ditimpa lewat tombol Update
        "rain_override_strict": False,  # True: batalkan baris jika override hujan gagal diterapkan
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
