# -*- coding: utf-8 -*-
"""
core/qc.py  -  F1.10: aturan QC konsistensi (dari PPT pusat 16 Nov 2026 + PDF Materi
Pengamatan AMG 2014; lihat SYNOP_UPGRADE_HANDOFF.txt bagian 2.11 dan 2.12-M).

Tujuan: baris Excel yang akan ditolak sistem pusat ("Tidak dapat dientri": alur Gross ->
Consistency, 126 aturan) terdeteksi SEBELUM bot mengisi form.

Modul ini hanya memeriksa apa yang bisa dihitung dari kolom Excel. Aturan yang butuh data
AWS (Td, QFF/QFE, Tx/Tn, RRR ...) ada di tahap berikutnya (synop_check, kelompok A1-A6).

Tingkat keparahan (core/rules_qc.json):
    level        = tingkat bawaan (WARNING: data tetap dikirim, ada peringatan)
    strict_level = tingkat bila features.qc_strict = true (ERROR: baris tidak dikirim)
Aturan turunan/usulan (QC-Uxx, QC-PK, QC121) TIDAK pernah menjadi ERROR.

Pemakaian (dipanggil oleh Validator.validate_row):
    qc = QC(spec_dict, enabled=True, strict=False)
    hits = qc.run(row, matched, nums, total, plan, add)
"""
ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"

# (lapisan, no, kolom jenis, kolom jumlah, kolom tinggi dasar, kolom tinggi puncak)
CLOUD_LAYERS = [
    ("low", 1, "awan_rendah_jenis", "awan_rendah_jumlah", "cloud_low_base_1", "cloud_low_peak_1"),
    ("low", 2, "awan_rendah_2_jenis", "awan_rendah_2_jumlah", "cloud_low_base_2", "cloud_low_peak_2"),
    ("low", 3, "awan_rendah_3_jenis", "awan_rendah_3_jumlah", "cloud_low_base_3", None),
    ("med", 1, "awan_menengah_jenis_1", "awan_menengah_jumlah_1", "cloud_med_base_1", None),
    ("med", 2, "awan_menengah_jenis_2", "awan_menengah_jumlah_2", "cloud_med_base_2", None),
    ("high", 1, "awan_tinggi_jenis", "awan_tinggi_jumlah", "cloud_high_base_1", None),
    ("high", 2, "awan_tinggi_2_jenis", "awan_tinggi_2_jumlah", "cloud_high_base_2", None),
]
TYPE_COL = {"low": "cloud_low_type_cl", "med": "cloud_med_type_cm", "high": "cloud_high_type_ch"}
COVER_COL = {"low": "cloud_low_cover_oktas", "med": "cloud_med_cover_oktas",
             "high": "cloud_high_cover_oktas"}
NAMA = {"low": "awan rendah", "med": "awan menengah", "high": "awan tinggi"}
JENIS_NAMA = {("low", "6"): "Sc", ("low", "7"): "St", ("low", "8"): "Cu", ("low", "9"): "Cb",
              ("med", "3"): "Ac", ("med", "4"): "As", ("med", "5"): "Ns",
              ("high", "0"): "Ci", ("high", "1"): "Cc", ("high", "2"): "Cs"}

# QC13 (PPT slide 9): N=9 (langit tertutup tak terlihat) tidak konsisten dengan ww berikut
# (ww=04 smoke dikecualikan). ww 41,43,45,47,49 (langit tak terlihat) wajar bila N=9.
QC13_WW = set(range(0, 4)) | set(range(5, 17)) | set(range(18, 30)) | {40, 42, 44, 46, 48}

# ww presipitasi di stasiun / sekitar saat pengamatan (untuk QC-U1, QC-U2)
def _ww_presipitasi(w):
    return 50 <= w <= 69 or 80 <= w <= 99

# QC-U3 [turunan WMO]: ww 20-29 & 91-94 menandakan kejadian dalam sejam lalu; W1/W2 yang
# mencakup periode itu seharusnya memuat fenomena tsb.
WW_KE_W = {20: {5}, 21: {6}, 22: {7}, 23: {6, 7}, 24: {5, 6}, 25: {8}, 26: {7, 8}, 27: {8},
           28: {4}, 29: {9}, 91: {9}, 92: {9}, 93: {9}, 94: {9}}

DEFAULT_PARAM = {
    "base_min_cc_cs_m": 4800,   # QC90-93: Cc/Cs
    "base_min_ac_as_m": 2100,   # QC90-93: Ac/As
    "base_max_ns_m": 6900,      # QC90-93: Ns
    "base_max_low_m": 1800,     # QC90-93: Sc/St/Cu/Cb
    "cu_top_max_m": 6900,       # QC-PK: Cu dengan puncak > ini hampir pasti Tcu/Cb
    "cb_top_min_m": 4500,       # QC-PK: Cb dengan puncak < ini hampir pasti Cu
}


def _i(c):
    return int(c) if (c is not None and str(c).isdigit()) else None


class QC:
    def __init__(self, spec=None, enabled=True, strict=False):
        spec = spec or {}
        self.rules = spec.get("rules", {})
        self.param = dict(DEFAULT_PARAM)
        self.param.update(spec.get("param", {}))
        self.enabled = enabled
        self.strict = strict

    # ------------------------------------------------------------------ #
    def level(self, rid, default=WARNING):
        """Tingkat efektif aturan rid; None = aturan dimatikan."""
        r = self.rules.get(rid, {})
        if r.get("aktif", True) is False:
            return None
        lvl = r.get("level", default)
        if self.strict:
            lvl = r.get("strict_level", lvl)
        return lvl

    # ------------------------------------------------------------------ #
    def run(self, row, matched, nums, total, plan, add):
        """
        row/matched/nums/total/plan = keluaran validate_row; add(level, rule, kolom, pesan).
        Mengembalikan daftar id aturan yang terpicu.
        """
        hits = []
        if not self.enabled:
            return hits

        def code(col):
            m = matched.get(col)
            return m.code if (m and m.ok) else None

        def fire(rid, col, msg, default=WARNING):
            lvl = self.level(rid, default)
            if lvl is None:
                return
            add(lvl, rid, col, msg)
            hits.append(rid)

        ww = _i(code("ww"))
        w1, w2 = _i(code("w1")), _i(code("w2"))
        n_tot = _i(total)

        # ---- QC10: W1 harus >= W2 ----------------------------------------------------
        if w1 is not None and w2 is not None and w1 < w2:
            fire("QC10", "w1", f"W1 ({w1}) lebih kecil dari W2 ({w2}); aturan W1 >= W2 "
                               "(W1 = W2 boleh). Tukar kedua nilai")

        # ---- QC13: ww vs tutupan total 9 ---------------------------------------------
        if total == "9" and ww is not None and ww in QC13_WW:
            fire("QC13", "ww", f"tutupan total 9 (langit tak terlihat) tetapi ww={ww:02d} tidak "
                               "konsisten (hanya ww 04, 41/43/45/47/49 dan ww presipitasi/guntur "
                               "yang wajar)")

        # ---- QC-U1 [usulan]: presipitasi tanpa awan ----------------------------------
        if total == "0" and ww is not None and _ww_presipitasi(ww):
            fire("QC-U1", "ww", f"ww={ww:02d} (presipitasi/badai guntur) tetapi tutupan total 0 "
                                "okta: periksa tutupan total atau ww")

        # ---- QC-U2 [usulan]: tanah kering saat hujan --------------------------------
        lc = code("land_cond")
        if lc == "0" and ww is not None and _ww_presipitasi(ww):
            fire("QC-U2", "land_cond", f"ww={ww:02d} (presipitasi saat pengamatan) tetapi keadaan "
                                       "tanah 0 (kering); periksa (INFO)", default=INFO)

        # ---- QC-U3 [turunan WMO]: ww 20-29/91-94 harus tercermin di W1/W2 ------------
        if ww in WW_KE_W and w1 is not None and w2 is not None:
            if not ({w1, w2} & WW_KE_W[ww]):
                ok_txt = "/".join(str(x) for x in sorted(WW_KE_W[ww]))
                fire("QC-U3", "w1", f"ww={ww:02d} (kejadian dalam sejam lalu) tetapi W1/W2 = "
                                    f"{w1}/{w2} tidak memuat fenomena itu (diharapkan {ok_txt}); "
                                    "periksa (INFO)", default=INFO)

        # ---- aturan awan (hanya bila detail awan memang diisi) ----------------------
        if plan.get("skip_clouds"):
            return hits
        ctype = {k: code(c) for k, c in TYPE_COL.items()}
        ncov = {k: _i(code(c)) for k, c in COVER_COL.items()}

        # QC35: N < 8 dengan CH = 7 (Cs menutup seluruh langit)
        if n_tot is not None and n_tot < 8 and ctype["high"] == "7":
            fire("QC35", "cloud_high_type_ch", f"tutupan total {n_tot} okta tetapi CH=7 "
                                               "(Cs menutup seluruh langit; butuh total 8)")

        # Nh = jumlah awan rendah; bila tak ada CL -> jumlah awan menengah; else 0
        nh, nh_src = 0, None
        if ctype["low"] not in (None, "0", "/") and ncov["low"] is not None:
            nh, nh_src = ncov["low"], "CL"
        elif ctype["med"] not in (None, "0", "/") and ncov["med"] is not None:
            nh, nh_src = ncov["med"], "CM"
        # QC44/47: Nh = 8 -> awan di atasnya tidak terlihat -> CM dan CH harus '/'
        if nh == 8:
            if nh_src == "CL" and ctype["med"] not in (None, "/"):
                fire("QC44", "cloud_med_type_cm", f"awan rendah 8 okta (Nh=8): CM seharusnya '/' "
                                                  f"(tidak terlihat), di Excel CM={ctype['med']}")
            if ctype["high"] not in (None, "/"):
                fire("QC47", "cloud_high_type_ch", f"Nh=8 ({'awan rendah' if nh_src == 'CL' else 'awan menengah'} "
                                                   f"8 okta): CH seharusnya '/', di Excel CH={ctype['high']}")

        # data per lapisan yang aktif
        layers = []
        for lk, n, jcol, ucol, bcol, pcol in CLOUD_LAYERS:
            if ctype[lk] in (None, "0", "/"):
                continue
            jenis, jml = code(jcol), code(ucol)
            base = nums.get(bcol)
            peak = nums.get(pcol) if pcol else None
            if jenis is None and jml is None and base is None:
                continue
            layers.append(dict(lk=lk, n=n, jenis=jenis, jml=_i(jml), base=base, peak=peak,
                               bcol=bcol, pcol=pcol, jcol=jcol, ucol=ucol))

        for L in layers:
            nama = f"{NAMA[L['lk']]} ke-{L['n']}"
            gname = JENIS_NAMA.get((L["lk"], L["jenis"]), L["jenis"])

            # QC107/108: jumlah lapisan tidak boleh melebihi tutupan total
            if L["jml"] is not None and L["jml"] <= 8 and n_tot is not None and n_tot <= 8 \
                    and L["jml"] > n_tot:
                fire("QC107", L["ucol"], f"jumlah {nama} ({L['jml']} okta) lebih besar dari tutupan "
                                         f"total ({n_tot} okta); lapisan 8 okta mensyaratkan total 8")

            # QC90-93: tinggi dasar vs jenis
            b, j, lk, P = L["base"], L["jenis"], L["lk"], self.param
            if b is not None and j is not None:
                bad = None
                if lk == "high" and j in ("1", "2") and b < P["base_min_cc_cs_m"]:
                    bad = f">= {P['base_min_cc_cs_m']:g} m"
                elif lk == "med" and j in ("3", "4") and b < P["base_min_ac_as_m"]:
                    bad = f">= {P['base_min_ac_as_m']:g} m"
                elif lk == "med" and j == "5" and b > P["base_max_ns_m"]:
                    bad = f"<= {P['base_max_ns_m']:g} m"
                elif lk == "low" and j in ("6", "7", "8", "9") and b > P["base_max_low_m"]:
                    bad = f"<= {P['base_max_low_m']:g} m"
                if bad:
                    fire("QC90", L["bcol"], f"tinggi dasar {gname} {b:g} m di luar kewajaran "
                                            f"(QC90-93: {gname} {bad})")

            # QC-PK [turunan PDF hal.36]: puncak konvektif wajar
            if L["peak"] is not None and lk == "low":
                if b is not None and L["peak"] < b:
                    fire("QC-PK", L["pcol"], f"tinggi puncak {L['peak']:g} m < tinggi dasar {b:g} m")
                elif j == "8" and L["peak"] > P["cu_top_max_m"]:
                    fire("QC-PK", L["pcol"], f"Cu dengan puncak {L['peak']:g} m terlalu tinggi "
                                             f"(> {P['cu_top_max_m']:g} m): kemungkinan Tcu/Cb")
                elif j == "9" and L["peak"] < P["cb_top_min_m"]:
                    fire("QC-PK", L["pcol"], f"Cb dengan puncak {L['peak']:g} m terlalu rendah "
                                             f"(< {P['cb_top_min_m']:g} m): kemungkinan Cu")

        # QC121: lapisan rendah ke-2 tidak boleh lebih rendah dari lapisan ke-1
        # (rendah-3, menengah-2, tinggi-2 diperiksa oleh R-ORD di validator)
        lows = {L["n"]: L for L in layers if L["lk"] == "low"}
        if 1 in lows and 2 in lows and lows[1]["base"] is not None and lows[2]["base"] is not None \
                and lows[2]["base"] < lows[1]["base"]:
            fire("QC121", "cloud_low_base_2", f"tinggi dasar awan rendah ke-2 ({lows[2]['base']:g} m) "
                                              f"lebih rendah dari ke-1 ({lows[1]['base']:g} m); grup 2 "
                                              "harus lebih tinggi dari grup 1")

        # QC102/103: Cs 8 okta <-> CH = 7
        h1 = next((L for L in layers if L["lk"] == "high" and L["n"] == 1), None)
        cs8 = bool(h1 and h1["jenis"] == "2" and h1["jml"] == 8)
        if ctype["high"] == "7" and h1 is not None and not cs8:
            fire("QC102", "awan_tinggi_jenis", "CH=7 mensyaratkan Cs (jenis 2) dengan jumlah 8 okta "
                                               "(QC102/103)")
        if cs8 and ctype["high"] not in (None, "7"):
            fire("QC102", "cloud_high_type_ch", f"Cs 8 okta mensyaratkan CH=7, di Excel CH="
                                                f"{ctype['high']} (QC102/103)")

        return hits
