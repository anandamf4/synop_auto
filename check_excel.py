# -*- coding: utf-8 -*-
"""
check_excel.py  -  periksa INPUT_PARAMETER.xlsx SEBELUM bot dijalankan (F1.3)

Contoh:
    python check_excel.py                         # pakai path Excel dari config.yaml
    python check_excel.py D:\\SYNOP\\INPUT_PARAMETER.xlsx
    python check_excel.py --no-info               # sembunyikan catatan INFO
    python check_excel.py --out hasil_validasi.txt
    python check_excel.py --register              # daftarkan slot ke log status (F1.4)

Kode keluar: 0 = tidak ada ERROR, 1 = ada ERROR, 2 = Excel tidak bisa dibaca.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_path  # noqa: E402
from core.validator import Validator, load_excel, format_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Validasi INPUT_PARAMETER.xlsx berdasar aturan web")
    ap.add_argument("excel", nargs="?", help="path Excel (default: dari config.yaml)")
    ap.add_argument("--no-info", action="store_true", help="sembunyikan catatan INFO")
    ap.add_argument("--out", help="simpan laporan ke file teks")
    ap.add_argument("--register", action="store_true",
                    help="daftarkan slot (pending) ke log status SQLite; slot ber-ERROR ditandai skipped")
    args = ap.parse_args()

    cfg = load_config()
    path = Path(args.excel) if args.excel else resolve_path(cfg, "excel")
    try:
        df = load_excel(path)
    except Exception as e:
        print(f"Gagal membaca Excel {path}: {e}")
        return 2

    v = Validator.from_config(cfg, ROOT)
    file_issues, results = v.validate_dataframe(df)
    report = format_report(file_issues, results, show_info=not args.no_info)
    header = f"VALIDASI {path}\n{'=' * 70}\n"
    print(header + report)
    if args.out:
        Path(args.out).write_text(header + report, encoding="utf-8")
        print(f"\nLaporan disimpan: {args.out}")

    if args.register:
        from core.db import SendLog
        log = SendLog(resolve_path(cfg, "db"))
        n_new = n_skip = 0
        for r in results:
            if not r.slot[0]:
                continue
            existing = log.get(*r.slot)
            log.register(r.slot[0], r.slot[1], waktu_eksekusi=r.waktu_eksekusi, plan=r.plan)
            if existing is None:
                n_new += 1
            if r.errors and (existing is None or existing["status"] in ("pending", "skipped")):
                log.mark_skipped(r.slot[0], r.slot[1], "validasi ERROR: " + "; ".join(i.message for i in r.errors[:2]))
                n_skip += 1
            elif existing is not None and existing["status"] in ("pending", "skipped"):
                log.update_plan(r.slot[0], r.slot[1], r.plan, r.waktu_eksekusi)
        print(f"\nLog status: {n_new} slot baru terdaftar, {n_skip} ditandai skipped (ERROR). DB: {log.path}")

    has_error = any(r.errors for r in results) or any(i.level == "ERROR" for i in file_issues)
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
