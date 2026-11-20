# -*- coding: utf-8 -*-
"""Uji F3.4 (verifikasi sandi) tanpa browser:  python tests/test_sandi.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.synop_check import (kode_vv, kode_hshs, kode_h, parse_sandi, hitung_harapan, verifikasi,  # noqa: E402
                              ERROR, WARNING)

passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


# sandi NYATA 14 Nov 2026 08:00 UTC (dari synop.db) dan baris Excel-nya
SANDI = "SNID52 WIJJ 140800\nAAXX 14084\n96195 41450 83305 10270 20257 30074 40105 72162 8421/\n  333 56009 57801 85615 88460 80860="
ROW = {"visibility": 5.0, "ww": "21 -", "w1": "6 -", "w2": "2 -", "cloud_cover_oktas_m": "8 okta",
       "cloud_low_type_cl": "2 -", "cloud_low_cover_oktas": "4 okta", "awan_rendah_jenis": "8 - cumulus (Cu)",
       "awan_rendah_jumlah": "2 okta", "cloud_low_base_1": 450.0, "cloud_low_peak_1": 3000.0,
       "cloud_arah_awan_rendah": "0 - Stationary or No Clouds", "cloud_elevation_1_angle_ec": "1 -",
       "cloud_arah_sebenarnya_1": "0 - Stationary or No Clouds", "awan_rendah_2_jenis": "6 - stratocumulus (Sc)",
       "awan_rendah_2_jumlah": "3 okta", "cloud_low_base_2": 450.0, "cloud_med_type_cm": "1 -",
       "cloud_med_cover_oktas": "8 okta", "awan_menengah_jenis_1": "4 - altostratus (As)",
       "awan_menengah_jumlah_1": "8 okta", "cloud_med_base_1": 3000.0,
       "cloud_arah_menengah_1": "0 - Stationary or No Clouds", "cloud_high_type_ch": "/ -", "land_cond": "2 -"}

print("== tabel kode ==")
check("VV 5.0 km -> 50 (sandi nyata)", kode_vv(5.0) == "50")
check("VV 0.05 -> 00; 0.5 -> 05; 6 -> 56; 10 -> 60; 30 -> 80; 35 -> 81; 80 -> 89",
      [kode_vv(x) for x in (0.05, 0.5, 6, 10, 30, 35, 80)] == ["00", "05", "56", "60", "80", "81", "89"],
      [kode_vv(x) for x in (0.05, 0.5, 6, 10, 30, 35, 80)])
check("hshs 450 -> 15; 3000 -> 60; 9000 -> 80; 1800 -> 56; 10500 -> 81",
      [kode_hshs(x) for x in (450, 3000, 9000, 1800, 10500)] == ["15", "60", "80", "56", "81"])
check("h: 450 m -> 4 (sandi nyata); 30 -> 0; 2600 -> 9; None -> 9",
      [kode_h(x) for x in (450, 30, 2600, None)] == ["4", "0", "9", "9"])

print("== parse sandi nyata ==")
p = parse_sandi(SANDI)
check("parse: N, VV, ww, CL/CM/CH, QFE/QFF, grup awan",
      p["N"] == "8" and p["VV"] == "50" and p["ww"] == "21" and (p["CL"], p["CM"], p["CH"]) == ("2", "1", "/")
      and p["QFE"] == 1007.4 and p["QFF"] == 1010.5 and p["layers"] == ["85615", "88460"] and p["tops"] == ["80860"], p)
check("parse: sandi kosong / tanpa AAXX tidak valid", not parse_sandi("")["valid"] and not parse_sandi("abc")["valid"])

print("== verifikasi: sandi nyata vs Excel ==")
h = verifikasi(SANDI, ROW)
check("sandi nyata 08:00 UTC sesuai Excel (tanpa temuan)", h.ok, h.ringkas())

print("== contoh PPT pusat (penggabungan WMO 306) ==")
r = dict(ROW, cloud_cover_oktas_m="8 okta", cloud_med_type_cm="0 -", awan_rendah_jenis="9 - cumulonimbus (Cb)",
         awan_rendah_jumlah="2 okta", awan_rendah_2_jenis="8 - cumulus (Cu)", awan_rendah_2_jumlah="3 okta",
         awan_rendah_3_jenis="6 - stratocumulus (Sc)", awan_rendah_3_jumlah="1 okta or less, but not zero",
         cloud_low_base_3=450.0, cloud_low_type_cl="3 -")
e = hitung_harapan(r)
check("Cb 2 + Cu 3 + Sc 1 @450 -> grup Cb '82915' & grup 'Cu 4' '84815'", set(e["groups"]) == {"82915", "84815"}, e["groups"])
r = dict(ROW, cloud_low_type_cl="0 -", cloud_med_type_cm="7 -", cloud_med_cover_oktas="4 okta",
         awan_menengah_jenis_1="3 - altocumulus (Ac)", awan_menengah_jumlah_1="2 okta",
         awan_menengah_jenis_2="4 - altostratus (As)", awan_menengah_jumlah_2="2 okta", cloud_med_base_2=3000.0)
e = hitung_harapan(r)
check("Ac 2 + As 2 @3000 -> satu grup 'As 4' = 84460 (jumlah sama -> kode tertinggi)", e["groups"] == ["84460"], e["groups"])
check("lapisan rendah nonaktif (CL=0): lapisan rendah diabaikan, Nh dari CM", e["Nh"] == "4", e)

print("== seleksi grup WMO 306 (dikalibrasi dari 21 sandi nyata 14 Nov 2026) ==")
# lapisan nyata jam 04:00: Sc3@450, Ac4@3000, Ci2@9000 -> sandi memuat 83615 84360 (tanpa grup tinggi)
r = dict(ROW, cloud_cover_oktas_m="8 okta", cloud_low_type_cl="2 -", awan_rendah_jenis="6 - stratocumulus (Sc)",
         awan_rendah_jumlah="3 okta", awan_rendah_2_jenis=float("nan"), awan_rendah_2_jumlah=float("nan"),
         cloud_low_base_2=float("nan"), cloud_low_peak_1=float("nan"), cloud_med_type_cm="3 -",
         awan_menengah_jenis_1="3 - altocumulus (Ac)", awan_menengah_jumlah_1="4 okta",
         cloud_high_type_ch="1 -", cloud_high_cover_oktas="2 okta", awan_tinggi_jenis="0 - cirrus (Ci)",
         awan_tinggi_jumlah="2 okta", cloud_high_base_1=9000.0, cloud_arah_tinggi="0 - Stationary or No Clouds")
e = hitung_harapan(r)
check("Sc3@450 + Ac4@3000 + Ci2@9000: grup wajib = 83615, 84360; grup tinggi 82080 hanya opsional",
      e["groups"] == ["83615", "84360"] and e["groups_opsional"] == ["82080"], (e["groups"], e["groups_opsional"]))
S04 = "AAXX 14044\n96195 41450 83305 10270 20257 30074 40105 72162 84231 333 56000 83615 84360="
r04 = dict(r)
h = verifikasi(S04, r04)
check("sandi tanpa grup tinggi untuk Ci 2 okta TIDAK dianggap salah", "S-GRUP" not in [t.kode for t in h.temuan], h.ringkas())
h = verifikasi(S04.replace("84360", "84360 82080"), r04)
check("web melaporkan grup tinggi opsional -> hanya INFO", h.ok and any(t.level == "INFO" and t.kode == "S-GRUP" for t in h.temuan), h.ringkas())
h = verifikasi(S04.replace(" 84360", ""), r04)
check("grup wajib ke-2 (Ac 4 okta) hilang -> WARNING S-GRUP", "S-GRUP" in [t.kode for t in h.warnings], h.ringkas())
r5 = dict(r, awan_tinggi_jumlah="5 okta", cloud_high_cover_oktas="5 okta")
check("tinggi 5 okta (>4) menjadi grup ke-3 yang WAJIB: 85080", hitung_harapan(r5)["groups"][-1] == "85080", hitung_harapan(r5)["groups"])
r3 = dict(r, awan_tinggi_jumlah="3 okta")
check("tinggi 3 okta sebagai grup ke-3 (butuh >4) -> tidak wajib", "83080" not in hitung_harapan(r3)["groups"])

print("== verifikasi: kesalahan terdeteksi ==")
def kode_temuan(h, lv=None):
    return [t.kode for t in h.temuan if lv is None or t.level == lv]

h = verifikasi(SANDI.replace("41450", "41410"), ROW)
check("VV sandi 10 (1.0 km) padahal Excel 5 km -> ERROR S-VV", "S-VV" in kode_temuan(h, ERROR), h.ringkas())
h = verifikasi(SANDI.replace("72162", "71162"), ROW)
check("ww sandi 11 padahal Excel 21 -> ERROR S-ww", "S-ww" in kode_temuan(h, ERROR))
h = verifikasi(SANDI.replace("72162", "71162"), ROW, abaikan=("ww",))
check("ww diubah otomatis (fallback Mist->Haze): tidak dianggap salah", "S-ww" not in kode_temuan(h) and h.ok, h.ringkas())
h = verifikasi(SANDI.replace("85615", "82815"), ROW)
check("lapisan-2 tidak ikut tergabung (82815, kasus lama pengguna) -> WARNING S-GRUP", "S-GRUP" in kode_temuan(h, WARNING), h.ringkas())
h = verifikasi(SANDI.replace(" 80860", ""), ROW)
check("grup puncak hilang -> WARNING S-PUNCAK", "S-PUNCAK" in kode_temuan(h, WARNING))
h = verifikasi(SANDI.replace("83305", "73305"), ROW)
check("N sandi 7 padahal Excel 8 -> ERROR S-N", "S-N" in kode_temuan(h, ERROR))
h = verifikasi(SANDI.replace("8421/", "8426/"), ROW)
check("CM sandi 6 padahal Excel 1 -> ERROR S-CM", "S-CM" in kode_temuan(h, ERROR))
h = verifikasi(SANDI.replace("57801", "57811"), ROW)
check("elevasi/arah sebenarnya beda (grup 57) -> WARNING S-57", "S-57" in kode_temuan(h, WARNING))
h = verifikasi(SANDI.replace("56009", "56509"), ROW)
check("arah gerak awan rendah beda (grup 56) -> WARNING S-56", "S-56" in kode_temuan(h, WARNING))
h = verifikasi("", ROW)
check("sandi kosong -> ERROR S0", "S0" in kode_temuan(h, ERROR))

print("== kewajaran data AWS ==")
h = verifikasi(SANDI.replace("40105", "40075"), ROW)
check("QFF=QFE (selisih ~0) -> WARNING S-QFF (usulan roadmap no.4)", "S-QFF" in kode_temuan(h, WARNING), h.ringkas())
h = verifikasi(SANDI.replace("20257", "20307"), ROW)
check("Td 30.7 > T 27.0 -> WARNING S-TD", "S-TD" in kode_temuan(h, WARNING))
h = verifikasi(SANDI.replace("10270", "10600"), ROW)
check("suhu 60 °C -> WARNING S-T", "S-T" in kode_temuan(h, WARNING))
h = verifikasi(SANDI.replace("40105", "40075"), ROW, cfg={"qff_qfe_check": False})
check("qff_qfe_check=false -> tidak diperiksa", "S-QFF" not in kode_temuan(h))

print("== tutupan 0 / 9 ==")
r0 = dict(ROW, cloud_cover_oktas_m="0")
s0 = SANDI.replace("83305", "03305").replace("8421/", "80000").replace(" 56009 57801 85615 88460 80860", "")
h = verifikasi(s0, r0)
check("N=0: Nh/CL/CM/CH = 0, tanpa grup awan -> sesuai", h.ok, h.ringkas())
r9 = dict(ROW, cloud_cover_oktas_m="9 -")
h = verifikasi(SANDI.replace("83305", "93305"), r9)
check("N=9: detail awan tidak dibandingkan (hanya N/VV/ww...)", "S-GRUP" not in kode_temuan(h), h.ringkas())

print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
