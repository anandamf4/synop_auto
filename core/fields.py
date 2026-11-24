# -*- coding: utf-8 -*-
"""
core/fields.py  -  F3.1: peta field form BMKGSoft v2 sebagai DATA (bukan fungsi).

Kunci FIELDS = nama kolom Excel = id elemen web bila ada, sehingga V7SATU.isi_data memanggil
    pilih_ant_select(driver, "cloud_low_type_cl", nilai)   /   isi_input(driver, "visibility_vv", nilai)
dan SATU fungsi generik yang membaca peta ini (cara mencari elemen, wajib/opsional -> jumlah percobaan ulang).

tipe  : "pilih" = dropdown Ant berid (ketik + ENTER)   | "isi" = kotak teks/angka
        "combo" = combobox Ant TANPA id; dicari lewat 'cari' (xpath tunggal, atau 'berlapis': posisi -> relatif-id -> xpath lama)
wajib : True = gagal membatalkan jam (3 percobaan ulang per langkah); False = opsional (percobaan ulang lebih sedikit)
aktif : kapan field aktif di web (dokumentasi aturan R-xx; gerbangnya tetap di isi_data/validator)

Tanpa impor selenium: modul ini aman diimpor tes, validator, dan web app.
"""


def _p(nama, wajib, aktif="selalu"):
    return {"tipe": "pilih", "nama": nama, "wajib": wajib, "aktif": aktif}


def _i(nama, wajib, aktif="selalu"):
    return {"tipe": "isi", "nama": nama, "wajib": wajib, "aktif": aktif}


def _xp_saudara_input(id_input):
    return f"//input[@id='{id_input}']/parent::div/following-sibling::div//div[@role='combobox']"


def _xp_saudara_baris(id_div):
    return (f"//div[@id='{id_div}']/ancestor::div[contains(@class,'row')]"
            "/following-sibling::div//div[@role='combobox']")


def _combo_xpath(nama, wajib, aktif, xpath):
    return {"tipe": "combo", "nama": nama, "wajib": wajib, "aktif": aktif, "cari": {"xpath": xpath}}


def _combo_berlapis(nama, wajib, aktif, bagian, baris, ref, k):
    xp = (f"//div[@id='{ref}']/ancestor::div[contains(@class,'row')]"
          f"/following-sibling::div[contains(@class,'row')]{'' if k == 1 else '[2]'}//div[@role='combobox']")
    return {"tipe": "combo", "nama": nama, "wajib": wajib, "aktif": aktif,
            "cari": {"bagian": bagian, "kol": 1, "baris": baris, "ref": ref, "k": k, "xpath_lama": xp}}


_RENDAH = "CL bukan 0 dan bukan '/'"
_PUNCAK = "jenis awan rendah 8/9 dan CL bukan 1 (R23)"
_LAP2 = "awan_rendah_2_jenis terisi (switch lapisan 2 aktif); puncak/elevasi/arah sebenarnya hanya bila CL bukan 1"
_MENENGAH = "CM bukan 0 dan bukan '/'"
_TINGGI = "CH bukan 0 dan bukan '/' dan awan tinggi terisi"

FIELDS = {
    # --- cuaca, visibilitas, tutupan, tanah (wajib) ---
    "present_weather_ww": _p("ww", True),
    "past_weather_w1": _p("w1", True),
    "past_weather_w2": _p("w2", True),
    "visibility_vv": _i("Visibilitas", True),
    "cloud_cover_oktas_m": _p("Tutupan total", True),
    "cloud_vertical_vis": _i("Penglihatan vertikal", True, "tutupan total 9"),
    "land_cond": _p("Keadaan tanah", True),
    # --- awan rendah ---
    "cloud_low_type_cl": _p("CL", True),
    "cloud_low_cover_oktas": _p("NCL", True, _RENDAH),
    "awan_rendah_jenis": _combo_berlapis("Jenis Awan Rendah", True, _RENDAH, "AWAN RENDAH", 2, "cloud_low_cover_oktas", 1),
    "awan_rendah_jumlah": _combo_berlapis("Jumlah Awan Rendah", True, _RENDAH, "AWAN RENDAH", 3, "cloud_low_cover_oktas", 2),
    "cloud_low_base_1": _i("Tinggi dasar awan rendah", False, _RENDAH),
    "cloud_low_peak_1": _i("Tinggi puncak awan rendah", False, _PUNCAK),
    "cloud_elevation_1_angle_ec": _p("Sudut elevasi 1", False, _PUNCAK),
    "cloud_arah_sebenarnya_1": _combo_xpath("Arah Sebenarnya", False, _PUNCAK, _xp_saudara_baris("cloud_elevation_1_angle_ec")),
    "cloud_arah_awan_rendah": _combo_xpath("Arah Awan Rendah", True, _RENDAH, _xp_saudara_input("cloud_low_peak_1")),
    # --- awan rendah lapisan 2 ---
    "awan_rendah_2_jenis": _combo_xpath("Jenis Awan Rendah 2", False, _LAP2, "//div[contains(@class,'row mt-5 pr-1')]//div[@role='combobox']"),
    "awan_rendah_2_jumlah": _combo_xpath("Jumlah Awan Rendah 2", False, _LAP2,
                                         "//div[contains(@class,'row mt-5 pr-1')]/following-sibling::div//div[@role='combobox']"),
    "cloud_low_base_2": _i("Tinggi dasar awan rendah 2", False, _LAP2),
    "cloud_low_peak_2": _i("Tinggi puncak awan rendah 2", False, _LAP2),
    "cloud_elevation_2_angle_ec": _p("Sudut elevasi 2", False, _LAP2),
    "cloud_arah_sebenarnya_2": _combo_xpath("Arah Sebenarnya 2", False, _LAP2, _xp_saudara_baris("cloud_elevation_2_angle_ec")),
    "cloud_arah_2": _combo_xpath("Arah Awan Rendah 2", False, _LAP2, _xp_saudara_input("cloud_low_peak_2")),
    # --- awan menengah ---
    "cloud_med_type_cm": _p("CM", True),
    "cloud_med_cover_oktas": _p("NCM", False, _MENENGAH),
    "awan_menengah_jenis_1": _combo_berlapis("Jenis Awan Menengah", False, _MENENGAH, "AWAN MENENGAH", 2, "cloud_med_cover_oktas", 1),
    "awan_menengah_jumlah_1": _combo_berlapis("Jumlah Awan Menengah", False, _MENENGAH, "AWAN MENENGAH", 3, "cloud_med_cover_oktas", 2),
    "cloud_med_base_1": _i("Tinggi dasar awan menengah", False, _MENENGAH),
    "cloud_arah_menengah_1": _combo_xpath("Arah Awan Menengah", False, _MENENGAH, _xp_saudara_input("cloud_med_base_1")),
    # --- awan tinggi ---
    "cloud_high_type_ch": _p("CH", True),
    "cloud_high_cover_oktas": _p("NCH", False, _TINGGI),
    "awan_tinggi_jenis": _combo_berlapis("Jenis Awan Tinggi", False, _TINGGI, "AWAN TINGGI", 2, "cloud_high_cover_oktas", 1),
    "awan_tinggi_jumlah": _combo_berlapis("Jumlah Awan Tinggi", False, _TINGGI, "AWAN TINGGI", 3, "cloud_high_cover_oktas", 2),
    "cloud_high_base_1": _i("Tinggi dasar awan tinggi", False, _TINGGI),
    "cloud_arah_tinggi": _combo_xpath("Arah Awan Tinggi", False, _TINGGI, _xp_saudara_input("cloud_high_base_1")),
}

# T21: dua set label tombol kirim. 'update' dipakai bila data jam ini SUDAH ADA di web (tombol: Send / Update / Send & Update);
# 'submit' bila belum ada. 'fallback' = kata-kata cadangan bila teks persis tak ditemukan (update sengaja tanpa cadangan).
TOMBOL_KIRIM = {
    "update": {"teks": "send & update", "fallback": None},
    "submit": {"teks": "send & submit", "fallback": ["send", "submit"]},
}
