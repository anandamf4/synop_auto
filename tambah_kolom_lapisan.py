# -*- coding: utf-8 -*-
"""
tambah_kolom_lapisan.py  -  tambahkan kolom BARU (opsional) ke INPUT_PARAMETER.xlsx

Kolom yang ditambahkan bila belum ada (di sisi kanan, tanpa menyentuh data lama):
    awan rendah lapisan 3 : awan_rendah_3_jenis, awan_rendah_3_jumlah, cloud_low_base_3, cloud_arah_3
    awan tinggi lapisan 2 : awan_tinggi_2_jenis, awan_tinggi_2_jumlah, cloud_high_base_2, cloud_arah_tinggi_2
    vertical visibility   : vertical_visibility            (meter; wajib bila tutupan total = 9)
    override hujan        : hujan_override_aktif, hujan_override_mm
(Kolom awan menengah lapisan 2 sudah ada di Excel Anda.)

Kolom dropdown diberi daftar pilihan (dari core/options.json) lewat sheet "Daftar_Opsi", sehingga
nilai dipilih dari daftar, bukan diketik. Daftar bersifat saran: ketikan manual tetap diterima.

Pemakaian:
    python tambah_kolom_lapisan.py                    # Excel dari config.yaml -> menulis <nama>_baru.xlsx
    python tambah_kolom_lapisan.py D:\\path\\INPUT_PARAMETER.xlsx
    python tambah_kolom_lapisan.py --inplace          # timpa file asli (cadangan <nama>_cadangan.xlsx dibuat dulu)

CATATAN: file disimpan ulang dengan openpyxl. Rumus dan format sel biasa dipertahankan; objek khusus
(grafik, gambar, makro) tidak. Periksa hasilnya sebelum dipakai.
"""
import argparse
import json
import shutil
import sys
from copy import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_path  # noqa: E402

# kolom baru, urutan penambahan: (nama kolom, kunci opsi di options.json atau None)
KOLOM_BARU = [
    ("awan_rendah_3_jenis", "AWAN RENDAH|k3|b2|Jenis"),
    ("awan_rendah_3_jumlah", "AWAN RENDAH|k3|b3|Jumlah"),
    ("cloud_low_base_3", None),
    ("cloud_arah_3", "AWAN RENDAH|k3|b6|Arah Gerak"),
    ("awan_tinggi_2_jenis", "AWAN TINGGI|k2|b2|Jenis"),
    ("awan_tinggi_2_jumlah", "AWAN TINGGI|k2|b3|Jumlah"),
    ("cloud_high_base_2", None),
    ("cloud_arah_tinggi_2", "AWAN TINGGI|k2|b5|Arah"),
    ("vertical_visibility", None),
    ("hujan_override_aktif", "__YA_TIDAK__"),
    ("hujan_override_mm", None),
]


def main():
    ap = argparse.ArgumentParser(description="Tambah kolom baru ke INPUT_PARAMETER.xlsx")
    ap.add_argument("excel", nargs="?", help="path Excel (default: dari config.yaml)")
    ap.add_argument("--inplace", action="store_true", help="timpa file asli (cadangan dibuat dulu)")
    args = ap.parse_args()

    try:
        import openpyxl
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("openpyxl belum terpasang. Jalankan: pip install -r requirements.txt")
        return 2

    cfg = load_config()
    src = Path(args.excel) if args.excel else resolve_path(cfg, "excel")
    if not src.exists():
        print(f"File tidak ditemukan: {src}")
        return 2
    with open(resolve_path(cfg, "options"), encoding="utf-8") as f:
        options = json.load(f)["fields"]

    wb = openpyxl.load_workbook(src)
    ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.worksheets[0]
    headers = {}
    for c in ws[1]:
        if c.value is not None and str(c.value).strip():
            headers[str(c.value).strip()] = c.column
    last_col = max(headers.values()) if headers else 0
    baris_data = max(ws.max_row, 100)
    gaya = ws.cell(row=1, column=last_col) if last_col else None

    if "Daftar_Opsi" in wb.sheetnames:
        ds = wb["Daftar_Opsi"]
    else:
        ds = wb.create_sheet("Daftar_Opsi")
    ds_headers = {str(c.value): c.column for c in ds[1] if c.value}

    ditambah = []
    for nama, kunci in KOLOM_BARU:
        if nama in headers:
            continue
        last_col += 1
        cell = ws.cell(row=1, column=last_col, value=nama)
        if gaya is not None:
            cell._style = copy(gaya._style)
        headers[nama] = last_col
        ditambah.append(nama)
        if kunci is None:
            continue
        if kunci == "__YA_TIDAK__":
            nilai = ["ya", "tidak"]
        else:
            opts = (options.get(kunci) or {}).get("options") or []
            nilai = [o["value"] for o in opts]
        if not nilai:
            continue
        kol = ds_headers.get(nama)
        if kol is None:
            kol = (max(ds_headers.values()) + 1) if ds_headers else 1
            ds.cell(row=1, column=kol, value=nama)
            ds_headers[nama] = kol
        for i, v in enumerate(nilai, start=2):
            ds.cell(row=i, column=kol, value=v)
        huruf = get_column_letter(kol)
        dv = DataValidation(type="list", formula1=f"=Daftar_Opsi!${huruf}$2:${huruf}${len(nilai) + 1}",
                            allow_blank=True)
        dv.showErrorMessage = False      # saran saja; ketikan manual tetap diterima
        ws.add_data_validation(dv)
        dv.add(f"{get_column_letter(last_col)}2:{get_column_letter(last_col)}{baris_data}")

    if not ditambah:
        print("Semua kolom baru sudah ada di Excel. Tidak ada yang diubah.")
        return 0

    if args.inplace:
        cad = src.with_name(src.stem + "_cadangan" + src.suffix)
        shutil.copy2(src, cad)
        print(f"Cadangan: {cad}")
        out = src
    else:
        out = src.with_name(src.stem + "_baru" + src.suffix)
    wb.save(out)
    print(f"Kolom ditambahkan ({len(ditambah)}): {', '.join(ditambah)}")
    print(f"Disimpan: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
