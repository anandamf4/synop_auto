# -*- coding: utf-8 -*-
"""
core/formschema.py  -  F2.3: skema form + status field kondisional (SATU sumber kebenaran)

  build_schema(validator)          -> bagian & field untuk dirender browser (label, jenis, opsi)
  field_state(validator, data, jam)-> {kolom: {aktif, wajib, pilihan, alasan}} dihitung di SERVER
                                      dari rules.json + aturan validator; browser hanya mengikuti.

Browser tidak menyalin aturan R1-R24; setiap perubahan input dikirim ke /api/validasi dan server
menjawab status field + temuan validator. Dengan begitu form dan bot tidak mungkin berbeda aturan.
"""
try:
    from core.validator import (COLUMN_FIELD, LAYERS, EXTRA_SPECS, NUMERIC_COLS, is_blank, val)
except ImportError:  # pragma: no cover
    from validator import (COLUMN_FIELD, LAYERS, EXTRA_SPECS, NUMERIC_COLS, is_blank, val)

# (kolom, label) untuk kolom yang bukan dropdown atau tak punya label di options.json
LABEL_ANGKA = {
    "visibility": ("Penglihatan mendatar", "km"), "vertical_visibility": ("Penglihatan tegak", "m"),
    "cloud_low_base_1": ("Tinggi dasar", "m"), "cloud_low_peak_1": ("Tinggi puncak", "m"),
    "cloud_low_base_2": ("Tinggi dasar (lapisan 2)", "m"), "cloud_low_peak_2": ("Tinggi puncak (lapisan 2)", "m"),
    "cloud_low_base_3": ("Tinggi dasar (lapisan 3)", "m"), "cloud_med_base_1": ("Tinggi dasar", "m"),
    "cloud_med_base_2": ("Tinggi dasar (lapisan 2)", "m"), "cloud_high_base_1": ("Tinggi dasar", "m"),
    "cloud_high_base_2": ("Tinggi dasar (lapisan 2)", "m"), "hujan_override_mm": ("Curah hujan", "mm"),
}
LABEL_LAIN = {
    "ww": "Cuaca saat pengamatan (ww)", "w1": "Cuaca lalu (W1)", "w2": "Cuaca lalu (W2)",
    "cloud_cover_oktas_m": "Tutupan awan total (N)", "land_cond": "Keadaan tanah (E)",
    "cloud_low_type_cl": "CL", "cloud_low_cover_oktas": "NCL (okta)", "cloud_med_type_cm": "CM",
    "cloud_med_cover_oktas": "NCM (okta)", "cloud_high_type_ch": "CH", "cloud_high_cover_oktas": "NCH (okta)",
    "hujan_override_aktif": "Ganti curah hujan dari AWS",
}
SUFFIKS = {"jenis": "Jenis", "jumlah": "Jumlah", "arah": "Arah gerak"}

BAGIAN = [
    {"id": "umum", "judul": "Umum", "kolom": ["visibility", "ww", "w1", "w2", "land_cond", "cloud_cover_oktas_m",
                                               "vertical_visibility"]},
    {"id": "rendah", "judul": "Awan rendah", "kolom": [
        "cloud_low_type_cl", "cloud_low_cover_oktas", "awan_rendah_jenis", "awan_rendah_jumlah", "cloud_low_base_1",
        "cloud_low_peak_1", "cloud_arah_awan_rendah", "cloud_elevation_1_angle_ec", "cloud_arah_sebenarnya_1",
        "awan_rendah_2_jenis", "awan_rendah_2_jumlah", "cloud_low_base_2", "cloud_low_peak_2", "cloud_arah_2",
        "cloud_elevation_2_angle_ec", "cloud_arah_sebenarnya_2",
        "awan_rendah_3_jenis", "awan_rendah_3_jumlah", "cloud_low_base_3", "cloud_arah_3"]},
    {"id": "menengah", "judul": "Awan menengah", "kolom": [
        "cloud_med_type_cm", "cloud_med_cover_oktas", "awan_menengah_jenis_1", "awan_menengah_jumlah_1",
        "cloud_med_base_1", "cloud_arah_menengah_1", "awan_menengah_jenis_2", "awan_menengah_jumlah_2",
        "cloud_med_base_2", "cloud_arah_menengah_2"]},
    {"id": "tinggi", "judul": "Awan tinggi", "kolom": [
        "cloud_high_type_ch", "cloud_high_cover_oktas", "awan_tinggi_jenis", "awan_tinggi_jumlah", "cloud_high_base_1",
        "cloud_arah_tinggi", "awan_tinggi_2_jenis", "awan_tinggi_2_jumlah", "cloud_high_base_2",
        "cloud_arah_tinggi_2"]},
    {"id": "hujan", "judul": "Curah hujan", "kolom": ["hujan_override_aktif", "hujan_override_mm"]},
]
SEMUA_KOLOM = [c for b in BAGIAN for c in b["kolom"]]
# kolom ke-n pada lapisan: (judul kecil)
SUB = {
    "cloud_low_type_cl": "", "awan_rendah_2_jenis": "Lapisan 2 (opsional)", "awan_rendah_3_jenis": "Lapisan 3 (opsional)",
    "awan_menengah_jenis_2": "Lapisan 2 (opsional)", "awan_tinggi_2_jenis": "Lapisan 2 (opsional)",
}


def _label(v, col):
    if col in LABEL_ANGKA:
        return LABEL_ANGKA[col][0]
    if col in LABEL_LAIN:
        return LABEL_LAIN[col]
    f = v.fields.get(COLUMN_FIELD.get(col, ""), {}) if hasattr(v, "fields") else {}
    return f.get("label") or col


def opsi_kolom(v, col):
    """Daftar teks opsi (persis seperti di web) untuk kolom dropdown, atau None."""
    key = COLUMN_FIELD.get(col)
    if not key:
        return None
    return [o["value"] for o in (v.options_for(key) or [])]


def build_schema(v):
    bagian = []
    for b in BAGIAN:
        fl = []
        for col in b["kolom"]:
            if col in COLUMN_FIELD:
                fl.append({"kolom": col, "label": _label(v, col), "jenis": "pilih", "opsi": opsi_kolom(v, col) or [],
                           "sub": SUB.get(col)})
            elif col == "hujan_override_aktif":
                fl.append({"kolom": col, "label": _label(v, col), "jenis": "saklar", "sub": None})
            else:
                fl.append({"kolom": col, "label": _label(v, col), "jenis": "angka",
                           "satuan": LABEL_ANGKA.get(col, ("", ""))[1], "sub": SUB.get(col)})
        bagian.append({"id": b["id"], "judul": b["judul"], "field": fl})
    return {"bagian": bagian}


# --------------------------------------------------------------------------- #
def _kode(v, data, col):
    x = val(data, col)
    if x is None:
        return None
    m = v.resolve(col, x)
    return m.code if m.ok else None


def _pilihan_dari_kode(v, col, kode_ok):
    return [o["value"] for o in (v.options_for(COLUMN_FIELD[col]) or []) if (o["code"] or "") in kode_ok]


def field_state(v, data, jam_utc=None):
    """Status tiap kolom form untuk data saat ini (dict kolom -> dict)."""
    S = {c: {"aktif": True, "wajib": False, "pilihan": None, "alasan": ""} for c in SEMUA_KOLOM}

    def mati(cols, alasan):
        for c in cols:
            if c in S:
                S[c].update(aktif=False, wajib=False, pilihan=None, alasan=alasan)

    for c in ("visibility", "ww", "w1", "w2", "land_cond", "cloud_cover_oktas_m"):
        S[c]["wajib"] = True
    awan = [c for b in BAGIAN if b["id"] in ("rendah", "menengah", "tinggi") for c in b["kolom"]]

    total = _kode(v, data, "cloud_cover_oktas_m")
    if total is None:
        mati(awan, "isi tutupan total dulu")
        mati(["vertical_visibility"], "hanya bila tutupan total = 9")
    elif total in ("0", "/"):
        mati(awan, f"tutupan total {total}: awan diisi otomatis oleh web")
        mati(["vertical_visibility"], "hanya bila tutupan total = 9")
    elif total == "9":
        mati(awan, "tutupan total 9: awan diisi otomatis oleh web")
        S["vertical_visibility"].update(wajib=True, alasan="wajib saat tutupan total 9 (visibilitas harus < 1 km)")
    else:
        mati(["vertical_visibility"], "hanya bila tutupan total = 9")
        for lk, L in LAYERS.items():
            tc = _kode(v, data, L["type"])
            S[L["type"]]["wajib"] = True
            detail = [L["cover"], L["jenis"], L["jumlah"], L["base"], L["arah"]] + L["extra"]
            if L["l2"]:
                detail += [L["l2"]["jenis"], L["l2"]["jumlah"], L["l2"]["base"], L["l2"]["arah"]] + L["l2"]["extra"]
            for X in EXTRA_SPECS:
                if X["layer"] == lk:
                    detail += X["cols"]
            detail = list(dict.fromkeys(detail))
            if tc is None:
                mati(detail, f"pilih {L['table']} dulu")
                continue
            if tc in ("0", "/"):
                mati(detail, f"{L['table']}={tc}: detail diisi otomatis oleh web")
                continue
            spec = v.rules[L["table"]].get(tc, {})
            allowed = spec.get("jenis_allowed", [])
            for c in (L["cover"], L["jenis"], L["jumlah"], L["base"], L["arah"]):
                S[c]["wajib"] = True
            S[L["jenis"]]["pilihan"] = _pilihan_dari_kode(v, L["jenis"], allowed)
            jc = _kode(v, data, L["jenis"])
            if lk == "low":
                aktif = jc in ("8", "9") and tc != "1"
                for c in L["extra"]:
                    if aktif:
                        S[c]["wajib"] = True
                    else:
                        mati([c], "hanya untuk Cu/Cb (jenis 8/9) dan CL bukan 1")
            # lapisan tambahan: semua-atau-tidak-sama-sekali (R14); jenis memakai daftar yang sama
            grup = []
            if L["l2"] and lk == "low":
                grup.append([L["l2"]["jenis"], L["l2"]["jumlah"], L["l2"]["base"], L["l2"]["arah"]])
                S[L["l2"]["jenis"]]["pilihan"] = _pilihan_dari_kode(v, L["l2"]["jenis"], allowed)
                j2 = _kode(v, data, L["l2"]["jenis"])
                for c in L["l2"]["extra"]:
                    if not (j2 in ("8", "9") and tc != "1"):
                        mati([c], "hanya untuk Cu/Cb (jenis 8/9) dan CL bukan 1")
            for X in EXTRA_SPECS:
                if X["layer"] == lk:
                    grup.append(X["cols"])
                    S[X["jenis"]]["pilihan"] = _pilihan_dari_kode(v, X["jenis"], allowed)
            for g in grup:
                if any(val(data, c) is not None for g_ in [g] for c in g_):
                    for c in g:
                        S[c]["wajib"] = True
                        if not S[c]["alasan"]:
                            S[c]["alasan"] = "lapisan tambahan dipakai: semua kolomnya wajib"

    # curah hujan: kolom web hanya terbuka pada jam UTC kelipatan 3
    if jam_utc is not None and jam_utc % 3 != 0:
        mati(["hujan_override_aktif", "hujan_override_mm"], f"hanya jam 00,03,06,...UTC (jam ini {jam_utc:02d}:00)")
    else:
        akt = str(data.get("hujan_override_aktif", "")).strip().lower() in ("1", "true", "ya", "yes", "y", "v")
        if not akt:
            mati(["hujan_override_mm"], "aktifkan 'ganti curah hujan' dulu")
        else:
            S["hujan_override_mm"]["wajib"] = True
    return S
