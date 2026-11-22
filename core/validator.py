# -*- coding: utf-8 -*-
"""
core/validator.py  -  F1.3: validator baris Excel berbasis aturan web

Memeriksa tiap baris INPUT_PARAMETER.xlsx SEBELUM bot berjalan, memakai:
  - core/options.json : teks opsi dropdown persis seperti di web
  - core/rules.json   : aturan hasil pengukuran F0.5 (Jenis per kode CL/CM/CH,
                        tutupan total 0/9/"/", aturan puncak, hujan, dst.)

Hasil per baris = RowResult:
    issues : daftar Issue (ERROR / WARNING / INFO) dengan kode aturan (R20, R13 ...)
    plan   : keputusan yang dipakai bot (F1.9) agar bot & validator TIDAK berbeda:
             skip_clouds, vertical_visibility, low/med/high aktif, peak aktif,
             override hujan, dst.
    slot   : (tanggal_utc, jam) -> kunci log status (F1.4)

ERROR   = baris tidak boleh dikirim sebelum diperbaiki
WARNING = data tetap bisa dikirim, tetapi ada yang diabaikan / janggal
INFO    = catatan

Pemakaian:
    from core.validator import Validator, load_excel
    v = Validator.from_files("core/options.json", "core/rules.json")
    df = load_excel("INPUT_PARAMETER.xlsx")
    results = v.validate_dataframe(df)
"""
import datetime as dt
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

try:                                  # [F1.10] aturan QC konsistensi (core/qc.py)
    from core.qc import QC
except ImportError:                   # dijalankan sebagai skrip dari dalam folder core/
    from qc import QC

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"

# --------------------------------------------------------------------------- #
#  Peta kolom Excel -> key field di options.json                               #
# --------------------------------------------------------------------------- #
COLUMN_FIELD = {
    "ww": "present_weather_ww", "w1": "past_weather_w1", "w2": "past_weather_w2",
    "cloud_cover_oktas_m": "cloud_cover_oktas_m",
    "cloud_low_type_cl": "cloud_low_type_cl", "cloud_low_cover_oktas": "cloud_low_cover_oktas",
    "awan_rendah_jenis": "AWAN RENDAH|k1|b2|Jenis", "awan_rendah_jumlah": "AWAN RENDAH|k1|b3|Jumlah",
    "cloud_arah_awan_rendah": "AWAN RENDAH|k1|b6|Arah Gerak",
    "cloud_elevation_1_angle_ec": "cloud_elevation_1_angle_ec",
    "cloud_arah_sebenarnya_1": "AWAN RENDAH|k1|b8|Arah Sebenarnya",
    "awan_rendah_2_jenis": "AWAN RENDAH|k2|b2|Jenis", "awan_rendah_2_jumlah": "AWAN RENDAH|k2|b3|Jumlah",
    "cloud_arah_2": "AWAN RENDAH|k2|b6|Arah Gerak",
    "cloud_elevation_2_angle_ec": "cloud_elevation_2_angle_ec",
    "cloud_arah_sebenarnya_2": "AWAN RENDAH|k2|b8|Arah Sebenarnya",
    "cloud_med_type_cm": "cloud_med_type_cm", "cloud_med_cover_oktas": "cloud_med_cover_oktas",
    "awan_menengah_jenis_1": "AWAN MENENGAH|k1|b2|Jenis", "awan_menengah_jumlah_1": "AWAN MENENGAH|k1|b3|Jumlah",
    "cloud_arah_menengah_1": "AWAN MENENGAH|k1|b5|Arah",
    "awan_menengah_jenis_2": "AWAN MENENGAH|k2|b2|Jenis", "awan_menengah_jumlah_2": "AWAN MENENGAH|k2|b3|Jumlah",
    "cloud_arah_menengah_2": "AWAN MENENGAH|k2|b5|Arah",
    "cloud_high_type_ch": "cloud_high_type_ch", "cloud_high_cover_oktas": "cloud_high_cover_oktas",
    "awan_tinggi_jenis": "AWAN TINGGI|k1|b2|Jenis", "awan_tinggi_jumlah": "AWAN TINGGI|k1|b3|Jumlah",
    "cloud_arah_tinggi": "AWAN TINGGI|k1|b5|Arah",
    "land_cond": "land_cond",
    # [F3.10] lapisan tambahan
    "awan_rendah_3_jenis": "AWAN RENDAH|k3|b2|Jenis", "awan_rendah_3_jumlah": "AWAN RENDAH|k3|b3|Jumlah",
    "cloud_arah_3": "AWAN RENDAH|k3|b6|Arah Gerak",
    "awan_tinggi_2_jenis": "AWAN TINGGI|k2|b2|Jenis", "awan_tinggi_2_jumlah": "AWAN TINGGI|k2|b3|Jumlah",
    "cloud_arah_tinggi_2": "AWAN TINGGI|k2|b5|Arah",
}
NUMERIC_COLS = [
    "visibility", "cloud_low_base_1", "cloud_low_peak_1", "cloud_low_base_2", "cloud_low_peak_2",
    "cloud_med_base_1", "cloud_med_base_2", "cloud_high_base_1",
    "cloud_low_base_3", "cloud_high_base_2",
    "vertical_visibility", "hujan_override_mm",
    "penguapan_mm", "radiasi_matahari", "lama_penyinaran_jam", "penguapan_ie",
]
# [rev 27] bagian bawah form jam 00 UTC (penguapan, radiasi, lama penyinaran, pengenal data penguapan)
PENGUAPAN_COLS = ["penguapan_mm", "penguapan_ie", "radiasi_kosongkan", "radiasi_matahari", "lama_penyinaran_jam"]
REQUIRED_COLUMNS = ["waktu_eksekusi", "jam_input", "visibility", "ww", "w1", "w2",
                    "cloud_cover_oktas_m", "land_cond"]
OPTIONAL_NEW_COLUMNS = ["vertical_visibility", "hujan_override_aktif", "hujan_override_mm"] + PENGUAPAN_COLS

# kolom detail per lapisan (untuk cek "harus kosong" saat lapisan nonaktif)
LAYERS = {
    "low": {
        "name": "awan rendah", "table": "CL", "type": "cloud_low_type_cl",
        "cover": "cloud_low_cover_oktas", "jenis": "awan_rendah_jenis", "jumlah": "awan_rendah_jumlah",
        "base": "cloud_low_base_1", "arah": "cloud_arah_awan_rendah",
        "extra": ["cloud_low_peak_1", "cloud_elevation_1_angle_ec", "cloud_arah_sebenarnya_1"],
        "l2": {"jenis": "awan_rendah_2_jenis", "jumlah": "awan_rendah_2_jumlah", "base": "cloud_low_base_2",
               "arah": "cloud_arah_2",
               "extra": ["cloud_low_peak_2", "cloud_elevation_2_angle_ec", "cloud_arah_sebenarnya_2"]},
    },
    "med": {
        "name": "awan menengah", "table": "CM", "type": "cloud_med_type_cm",
        "cover": "cloud_med_cover_oktas", "jenis": "awan_menengah_jenis_1", "jumlah": "awan_menengah_jumlah_1",
        "base": "cloud_med_base_1", "arah": "cloud_arah_menengah_1", "extra": [],
        "l2": {"jenis": "awan_menengah_jenis_2", "jumlah": "awan_menengah_jumlah_2", "base": "cloud_med_base_2",
               "arah": "cloud_arah_menengah_2", "extra": []},
    },
    "high": {
        "name": "awan tinggi", "table": "CH", "type": "cloud_high_type_ch",
        "cover": "cloud_high_cover_oktas", "jenis": "awan_tinggi_jenis", "jumlah": "awan_tinggi_jumlah",
        "base": "cloud_high_base_1", "arah": "cloud_arah_tinggi", "extra": [], "l2": None,
    },
}
# [F3.10] lapisan tambahan yang diisi lewat posisi + switch (BUKAN jalur lama rendah-2/id 775)
#   toggle_ordinal = urutan switch di kartu; fallback = id yang terlihat di web (hanya cadangan)
EXTRA_SPECS = [
    {"layer": "med", "n": 2, "section": "AWAN MENENGAH", "col": 2, "toggle_ordinal": 1, "fallback_toggle_id": "777",
     "arah_row": 5, "jenis": "awan_menengah_jenis_2", "jumlah": "awan_menengah_jumlah_2",
     "base_id": "cloud_med_base_2", "arah": "cloud_arah_menengah_2", "prev_base": ["cloud_med_base_1"]},
    {"layer": "low", "n": 3, "section": "AWAN RENDAH", "col": 3, "toggle_ordinal": 2, "fallback_toggle_id": "776",
     "arah_row": 6, "jenis": "awan_rendah_3_jenis", "jumlah": "awan_rendah_3_jumlah",
     "base_id": "cloud_low_base_3", "arah": "cloud_arah_3", "prev_base": ["cloud_low_base_1", "cloud_low_base_2"]},
    {"layer": "high", "n": 2, "section": "AWAN TINGGI", "col": 2, "toggle_ordinal": 1, "fallback_toggle_id": "778",
     "arah_row": 5, "jenis": "awan_tinggi_2_jenis", "jumlah": "awan_tinggi_2_jumlah",
     "base_id": "cloud_high_base_2", "arah": "cloud_arah_tinggi_2", "prev_base": ["cloud_high_base_1"]},
]
for _x in EXTRA_SPECS:
    _x["cols"] = [_x["jenis"], _x["jumlah"], _x["base_id"], _x["arah"]]
ALL_CLOUD_COLS = []
for _l in LAYERS.values():
    ALL_CLOUD_COLS += [_l["type"], _l["cover"], _l["jenis"], _l["jumlah"], _l["base"], _l["arah"]] + _l["extra"]
    if _l["l2"]:
        ALL_CLOUD_COLS += [_l["l2"]["jenis"], _l["l2"]["jumlah"], _l["l2"]["base"], _l["l2"]["arah"]] + _l["l2"]["extra"]
for _x in EXTRA_SPECS:
    for _c in _x["cols"]:
        if _c not in ALL_CLOUD_COLS:
            ALL_CLOUD_COLS.append(_c)


# --------------------------------------------------------------------------- #
#  Struktur hasil                                                              #
# --------------------------------------------------------------------------- #
@dataclass
class Issue:
    level: str
    rule: str
    column: str
    message: str

    def __str__(self):
        col = f"[{self.column}] " if self.column else ""
        return f"{self.level:<7} {self.rule:<8} {col}{self.message}"


@dataclass
class RowResult:
    row_no: int                      # nomor baris di Excel (judul = baris 1)
    slot: tuple = (None, None)       # (tanggal_utc 'YYYY-MM-DD', jam 'HH:00')
    waktu_eksekusi: object = None
    issues: list = field(default_factory=list)
    plan: dict = field(default_factory=dict)

    @property
    def errors(self):
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self):
        return [i for i in self.issues if i.level == WARNING]

    @property
    def ok(self):
        return not self.errors


@dataclass
class Match:
    ok: bool
    text: str = ""
    code: str = ""
    reason: str = ""
    candidates: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Utilitas nilai                                                              #
# --------------------------------------------------------------------------- #
def norm(s):
    return " ".join(str(s).split())


def is_blank(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    try:
        import pandas as pd
        if v is pd.NaT or (not isinstance(v, (str, bytes)) and pd.isna(v)):
            return True
    except Exception:
        pass
    s = norm(v)
    return s == "" or s.lower() in ("nan", "nat", "none") or s == "-"


def val(row, col):
    v = row.get(col) if hasattr(row, "get") else None
    return None if is_blank(v) else v


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm(v).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_jam(v):
    """jam_input bisa datetime.time, 'HH:MM[:SS]', pecahan hari (float) atau integer jam."""
    if is_blank(v):
        return None
    if isinstance(v, dt.datetime):
        return v.hour
    if isinstance(v, dt.time):
        return v.hour
    if isinstance(v, (int, float)):
        f = float(v)
        if 0 <= f < 1:
            return int(round(f * 24)) % 24
        if f == int(f) and 0 <= f <= 23:
            return int(f)
        return None
    s = norm(v)
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", s)
    if m and 0 <= int(m.group(1)) <= 23:
        return int(m.group(1))
    if re.match(r"^\d{1,2}$", s) and 0 <= int(s) <= 23:
        return int(s)
    return None


def truthy(v):
    if is_blank(v):
        return False
    s = norm(v).lower()
    return s in ("1", "ya", "y", "yes", "true", "aktif", "on", "x", "v")


def parse_waktu(v):
    if is_blank(v):
        return None
    if isinstance(v, dt.datetime):
        return v
    try:
        import pandas as pd
        ts = pd.to_datetime(v, errors="coerce")
        return None if pd.isna(ts) else ts.to_pydatetime()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Validator                                                                   #
# --------------------------------------------------------------------------- #
class Validator:
    def __init__(self, options, rules, tz_hours=7, window_open_min=10, late_min=15,
                 extra_layers_supported=True, medium_layer2_supported=None,
                 rules_qc=None, qc_enabled=True, qc_strict=False):
        self.fields = options["fields"]
        self.jam_list = options.get("jam", [])
        self.rules = rules
        self.tz = tz_hours
        self.window_open_min = window_open_min
        self.late_min = late_min
        # [F3.10] medium_layer2_supported = nama lama (diabaikan); saklar sekarang: features.extra_layers
        self.extra_layers_supported = extra_layers_supported
        # [F1.10] QC konsistensi: qc_strict=False -> semua temuan QC hanya WARNING/INFO
        self.qc = QC(rules_qc, enabled=qc_enabled, strict=qc_strict)

    @classmethod
    def from_files(cls, options_path, rules_path, rules_qc_path=None, **kw):
        with open(options_path, encoding="utf-8") as f:
            options = json.load(f)
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)
        # rules_qc.json dicari di folder yang sama dengan rules.json bila path tidak diberikan
        qp = Path(rules_qc_path) if rules_qc_path else Path(rules_path).with_name("rules_qc.json")
        if "rules_qc" not in kw and qp.exists():
            with open(qp, encoding="utf-8") as f:
                kw["rules_qc"] = json.load(f)
        return cls(options, rules, **kw)

    @classmethod
    def from_config(cls, cfg, root):
        rt, ft = cfg["runtime"], cfg["features"]
        return cls.from_files(
            Path(root) / cfg["paths"]["options"], Path(root) / cfg["paths"]["rules"],
            tz_hours=rt["timezone_offset_hours"], window_open_min=rt["window_open_minutes"],
            late_min=rt["late_info_minutes"],
            extra_layers_supported=ft.get("extra_layers", True),
            rules_qc_path=Path(root) / cfg["paths"].get("rules_qc", "core/rules_qc.json"),
            qc_enabled=ft.get("qc_enabled", True), qc_strict=ft.get("qc_strict", False),
        )

    # ------------------------------------------------------------------ #
    #  Pencocokan nilai Excel -> opsi web                                #
    # ------------------------------------------------------------------ #
    def options_for(self, key):
        f = self.fields.get(key)
        if f is None:
            return None
        if f.get("options") is None and f.get("assume_same_as"):
            return self.options_for(f["assume_same_as"])
        return f.get("options")

    def resolve(self, col, value):
        """Cocokkan teks Excel ke SATU opsi web (exact -> substring -> kode)."""
        key = COLUMN_FIELD[col]
        opts = self.options_for(key)
        if not opts:
            return Match(False, reason="daftar opsi untuk kolom ini belum tersedia")
        v = norm(value)
        exact = [o for o in opts if norm(o["value"]) == v]
        if len(exact) == 1:
            return Match(True, exact[0]["value"], exact[0]["code"] or "")
        sub = [o for o in opts if v and v in norm(o["value"])]
        if len(sub) == 1:
            return Match(True, sub[0]["value"], sub[0]["code"] or "")
        m = re.match(r"^(\S+?)\s*-", v) or re.match(r"^(\d|/)", v)
        lead = m.group(1) if m else None
        pool = sub if sub else opts
        by_code = [o for o in pool if lead is not None and (o["code"] or "") == lead]
        if len(by_code) == 1:
            return Match(True, by_code[0]["value"], by_code[0]["code"] or "")
        if len(sub) > 1:
            return Match(False, reason="ambigu", candidates=[norm(o["value"])[:50] for o in sub[:4]])
        return Match(False, reason="tidak ada di daftar opsi web")

    def jenis_names(self, col, codes):
        opts = self.options_for(COLUMN_FIELD[col]) or []
        names = []
        for c in codes:
            n = next((norm(o["value"]) for o in opts if (o["code"] or "") == c), c)
            names.append(n)
        return ", ".join(names)

    # ------------------------------------------------------------------ #
    #  Validasi satu baris                                               #
    # ------------------------------------------------------------------ #
    def validate_row(self, row, row_no):
        res = RowResult(row_no=row_no)
        add = lambda lvl, rule, col, msg: res.issues.append(Issue(lvl, rule, col, msg))
        plan = res.plan = {"skip_clouds": False, "vertical_visibility": None, "total": None,
                           "layers": {}, "rain_override": None, "penguapan": None, "ww_code": None, "notes": [],
                           "extra": [], "extra_off": []}

        # ---- waktu & slot ------------------------------------------------
        waktu = parse_waktu(row.get("waktu_eksekusi"))
        res.waktu_eksekusi = waktu
        jam_h = parse_jam(row.get("jam_input"))
        if waktu is None:
            add(ERROR, "R-WKT", "waktu_eksekusi", "kosong atau bukan tanggal/waktu yang valid")
        if jam_h is None:
            add(ERROR, "R-JAM", "jam_input", f"tidak valid: {row.get('jam_input')!r} (format HH:MM)")
        if waktu is not None:
            w_utc = waktu - dt.timedelta(hours=self.tz)
            nearest = (w_utc + dt.timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
            res.slot = (nearest.strftime("%Y-%m-%d"), f"{nearest.hour:02d}:00")
            if jam_h is not None and jam_h != nearest.hour:
                add(ERROR, "R-JAM", "jam_input",
                    f"jam {jam_h:02d}:00 tidak cocok dengan waktu_eksekusi {waktu:%Y-%m-%d %H:%M} WIB "
                    f"(setara {nearest.hour:02d}:00 UTC)")
            diff_min = (w_utc - nearest).total_seconds() / 60.0
            if diff_min < -self.window_open_min:
                add(ERROR, "R-WKT", "waktu_eksekusi",
                    f"{abs(diff_min):.0f} menit sebelum jam observasi; web baru membuka {self.window_open_min} menit sebelumnya")
            elif diff_min > self.late_min:
                add(INFO, "R-WKT", "waktu_eksekusi", f"{diff_min:.0f} menit setelah jam observasi (terlambat)")
        jam_for_rules = jam_h if jam_h is not None else (int(res.slot[1][:2]) if res.slot[1] else None)

        # ---- baris hampir kosong (N5) ---------------------------------
        core = [c for c in ("visibility", "ww", "w1", "w2", "cloud_cover_oktas_m") if val(row, c) is None]
        if len(core) >= 4:
            add(ERROR, "R9", "", "baris hampir kosong / tidak lengkap (ww, w1, w2, visibilitas, tutupan total kosong)")
            return res

        # ---- kolom wajib -------------------------------------------------
        for c in REQUIRED_COLUMNS[2:]:
            if val(row, c) is None:
                add(ERROR, "R9", c, "wajib diisi")

        # ---- cocokkan semua dropdown ------------------------------------
        matched = {}
        for col in COLUMN_FIELD:
            v = val(row, col)
            if v is None:
                continue
            m = self.resolve(col, v)
            matched[col] = m
            if not m.ok:
                lvl = ERROR
                detail = m.reason + (f"; kandidat: {m.candidates}" if m.candidates else "")
                if m.reason.startswith("daftar opsi"):
                    lvl = INFO
                add(lvl, "R-OPT", col, f"nilai {norm(v)!r}: {detail}")

        def code(col):
            m = matched.get(col)
            return m.code if (m and m.ok) else None

        # ---- angka ---------------------------------------------------------
        nums = {}
        for c in NUMERIC_COLS:
            v = val(row, c)
            if v is None:
                continue
            f = to_float(v)
            if f is None:
                add(ERROR, "R-NUM", c, f"bukan angka: {norm(v)!r}")
            elif f < 0:
                add(ERROR, "R-NUM", c, f"tidak boleh negatif: {f}")
            else:
                nums[c] = f
        vis = nums.get("visibility")
        if vis is not None and vis > 50:
            add(WARNING, "R-NUM", "visibility", f"{vis:g} km tidak lazim (satuan km); periksa")

        # ---- cuaca ---------------------------------------------------------
        ww = code("ww")
        plan["ww_code"] = ww
        if ww == "10":
            plan["notes"].append("ww=10 (Mist): jika web menolak (RH<95%) bot otomatis mengganti ke 05 (Haze) dan mencatatnya (K2)")
            add(INFO, "K2", "ww", "ww=10 (Mist) dapat otomatis diganti 05 (Haze) bila web menolak; akan dicatat di log")
        if ww is not None and vis is not None:
            if ww.isdigit() and 40 <= int(ww) <= 49 and vis >= 1:
                add(WARNING, "R-WX", "ww", f"ww={ww} (kabut) biasanya visibilitas < 1 km, di Excel {vis:g} km")
            if ww == "10" and vis < 1:
                add(WARNING, "R-WX", "ww", f"ww=10 (Mist) biasanya visibilitas >= 1 km, di Excel {vis:g} km")

        # ---- tutupan total & logika awan ----------------------------------
        total = code("cloud_cover_oktas_m")
        plan["total"] = total
        if total in ("0", "9", "/"):
            plan["skip_clouds"] = True
            filled = [c for c in ALL_CLOUD_COLS if val(row, c) is not None]
            rule_txt = {"0": "tutupan 0: web mengisi CL=CM=CH=0 otomatis",
                        "9": "tutupan 9: web mengisi CL=CM=CH='/' otomatis",
                        "/": "tutupan '/': web mengisi CL=CM=CH='/' otomatis"}[total]
            if filled:
                add(WARNING, "R20", "cloud_cover_oktas_m",
                    f"{rule_txt}; {len(filled)} kolom awan terisi akan DIABAIKAN: {filled[:6]}{'...' if len(filled) > 6 else ''}")
            if total == "9":
                vv = nums.get("vertical_visibility")
                if "vertical_visibility" in nums:
                    plan["vertical_visibility"] = vv
                elif val(row, "vertical_visibility") is None:
                    add(ERROR, "R21", "vertical_visibility",
                        "tutupan total 9: vertical visibility (m) WAJIB diisi manual")
                if vis is not None and vis >= 1:
                    add(ERROR, "R21", "visibility",
                        f"tutupan total 9 mensyaratkan visibilitas < 1 km (ketentuan stasiun, K8); "
                        f"di Excel {vis:g} km. Perbaiki visibilitas atau tutupan total")
        else:
            if val(row, "vertical_visibility") is not None:
                add(WARNING, "R21", "vertical_visibility", "hanya dipakai bila tutupan total = 9; diabaikan")
            if total is not None:
                self._check_layers(row, res, matched, nums, total)

        # ---- hujan override -------------------------------------------------
        if val(row, "hujan_override_aktif") is not None or val(row, "hujan_override_mm") is not None:
            self._check_rain(row, res, nums, jam_for_rules)

        # ---- [rev 27] penguapan / radiasi / lama penyinaran (jam 00 UTC) -----
        if any(val(row, c) is not None for c in PENGUAPAN_COLS):
            self._check_penguapan(row, res, nums, jam_for_rules)

        # ---- land_cond: sudah divalidasi lewat pencocokan ------------------

        # ---- [F1.10] aturan QC konsistensi (core/qc.py) ----------------------
        add_q = lambda lvl, rule, col, msg: res.issues.append(Issue(lvl, rule, col, msg))
        plan["qc_hits"] = self.qc.run(row, matched, nums, total, plan, add_q)
        return res

    # ------------------------------------------------------------------ #
    def _check_layers(self, row, res, matched, nums, total):
        add = lambda lvl, rule, col, msg: res.issues.append(Issue(lvl, rule, col, msg))
        plan = res.plan
        codes = {}
        for lk, L in LAYERS.items():
            m = matched.get(L["type"])
            if val(row, L["type"]) is None:
                add(ERROR, "R9", L["type"], f"wajib diisi (tutupan total {total} okta, bukan 0/9/'/')")
                codes[lk] = None
                continue
            codes[lk] = m.code if (m and m.ok) else None
        # total 1-8 tetapi semua lapisan 0 atau "/"
        if total.isdigit() and all(c in ("0", "/") for c in codes.values() if c is not None) \
                and all(c is not None for c in codes.values()):
            add(WARNING, "R-CLD", "cloud_cover_oktas_m",
                f"tutupan total {total} okta tetapi CL/CM/CH semua 0 atau '/'")

        for lk, L in LAYERS.items():
            c = codes[lk]
            lp = plan["layers"][lk] = {"type": c, "active": False, "peak_active": False,
                                       "layer2": False, "jenis": None}
            if c is None:
                continue
            spec = self.rules[L["table"]].get(c)
            if spec is None:
                add(ERROR, "R-OPT", L["type"], f"kode {c!r} tidak dikenal di aturan {L['table']}")
                continue
            detail_cols = [L["cover"], L["jenis"], L["jumlah"], L["base"], L["arah"]] + L["extra"]
            if L["l2"]:
                detail_cols += [L["l2"]["jenis"], L["l2"]["jumlah"], L["l2"]["base"], L["l2"]["arah"]] + L["l2"]["extra"]
            for X in EXTRA_SPECS:
                if X["layer"] == lk:
                    detail_cols += X["cols"]
            detail_cols = list(dict.fromkeys(detail_cols))
            if c in ("0", "/"):
                filled = [d for d in detail_cols if val(row, d) is not None]
                if filled:
                    add(WARNING, "R20b", L["type"],
                        f"{L['table']}={c}: detail {L['name']} nonaktif di web (diisi otomatis) -> diabaikan: {filled[:5]}")
                continue

            lp["active"] = True
            # ---- lapisan 1 wajib ----
            for d in (L["cover"], L["jenis"], L["jumlah"], L["arah"]):
                if val(row, d) is None:
                    add(ERROR, "R3", d, f"wajib diisi ({L['table']}={c})")
            if val(row, L["base"]) is None:
                add(WARNING, "R4", L["base"], f"tinggi dasar {L['name']} kosong (dilewati bot)")
            jc = code_of(matched, L["jenis"])
            lp["jenis"] = jc
            allowed = spec["jenis_allowed"]
            if jc is not None and jc not in allowed:
                add(ERROR, "R13", L["jenis"],
                    f"{L['table']}={c}: Jenis {jc} TIDAK diizinkan web. Boleh: {self.jenis_names(L['jenis'], allowed)}")
            # ---- puncak awan rendah (R23) ----
            if lk == "low":
                peak_active = jc in ("8", "9") and c != "1"
                lp["peak_active"] = peak_active
                pcols = L["extra"]
                if peak_active:
                    miss = [p for p in pcols if val(row, p) is None]
                    if miss:
                        add(WARNING, "R23", miss[0],
                            f"CL={c}, Jenis {jc}: tinggi puncak/elevasi/arah sebenarnya aktif di web, kosong: {miss}")
                    pk, bs = nums.get("cloud_low_peak_1"), nums.get("cloud_low_base_1")
                    if pk is not None and bs is not None and pk < bs:
                        add(WARNING, "R-NUM", "cloud_low_peak_1", f"tinggi puncak {pk:g} < tinggi dasar {bs:g}")
                else:
                    filled = [p for p in pcols if val(row, p) is not None]
                    if filled and jc is not None:
                        why = "CL=1" if c == "1" else f"Jenis {jc} bukan 8/9"
                        # angka puncak / elevasi yang terbuang = WARNING; hanya
                        # 'arah sebenarnya' (biasanya nilai default tersalin) = INFO
                        real = [p for p in filled if p != "cloud_arah_sebenarnya_1"]
                        add(WARNING if real else INFO, "R23", filled[0],
                            f"{why}: kolom ini NONAKTIF di web -> diabaikan: {filled}")
            # ---- lapisan 2 ----
            L2 = L["l2"] if lk == "low" else None   # [F3.10] menengah-2 & tinggi-2 lewat _check_extras
            if L2:
                l2_cols = [L2["jenis"], L2["jumlah"], L2["base"], L2["arah"]]
                if any(val(row, d) is not None for d in l2_cols + L2["extra"]):
                    lp["layer2"] = True
                    for d in l2_cols:
                        if val(row, d) is None:
                            add(ERROR, "R14", d,
                                f"lapisan ke-2 {L['name']} dipakai: kolom ini WAJIB (web menandai merah jika kosong)")
                    j2 = code_of(matched, L2["jenis"])
                    if j2 is not None and j2 not in allowed:
                        add(ERROR, "R24", L2["jenis"],
                            f"{L['table']}={c}: Jenis lapisan 2 ({j2}) TIDAK diizinkan. Boleh: {self.jenis_names(L['jenis'], allowed)}")
                    if lk == "low":
                        p2 = j2 in ("8", "9") and c != "1"
                        lp["peak2_active"] = p2
                        if not p2 and any(val(row, e) is not None for e in L2["extra"]):
                            add(INFO, "R24", L2["extra"][0],
                                "puncak/elevasi/arah sebenarnya lapisan 2 terisi tetapi Jenis bukan 8/9 (aturan lapisan 2 belum terverifikasi penuh)")

        self._check_extras(row, res, matched, nums, codes)

        # ---- konsistensi tutupan total vs lapisan (peringatan) ------------
        ncs = {}
        for lk, L in LAYERS.items():
            m = matched.get(L["cover"])
            if m and m.ok and m.code.isdigit():
                ncs[lk] = int(m.code)
        if total.isdigit() and ncs:
            t = int(total)
            if t < max(ncs.values()):
                add(WARNING, "R-NC1", "cloud_cover_oktas_m",
                    f"tutupan total {t} lebih kecil dari tutupan lapisan terbesar ({max(ncs.values())} okta)")
            if len(ncs) == 3 and t > sum(ncs.values()):
                add(WARNING, "R-NC2", "cloud_cover_oktas_m",
                    f"tutupan total {t} lebih besar dari jumlah tutupan semua lapisan ({sum(ncs.values())} okta)")

    # ------------------------------------------------------------------ #
    def _check_extras(self, row, res, matched, nums, codes):
        """[F3.10] Lapisan tambahan: menengah-2, rendah-3, tinggi-2 -> plan['extra'] / plan['extra_off']."""
        add = lambda lvl, rule, col, msg: res.issues.append(Issue(lvl, rule, col, msg))
        plan = res.plan
        for X in EXTRA_SPECS:
            lk = X["layer"]
            L = LAYERS[lk]
            c = codes.get(lk)
            if c in (None, "0", "/"):
                continue                      # lapisan 1 nonaktif / belum valid: lapisan tambahan tidak relevan
            filled = [d for d in X["cols"] if val(row, d) is not None]
            nama = f"{L['name']} ke-{X['n']}"
            if not filled:
                # kolom ADA di Excel tetapi kosong -> matikan switch bila masih aktif (sisa data lama)
                if all(d in row for d in X["cols"]) and self.extra_layers_supported:
                    plan["extra_off"].append({"layer": lk, "n": X["n"], "section": X["section"],
                                              "toggle_ordinal": X["toggle_ordinal"],
                                              "fallback_toggle_id": X["fallback_toggle_id"]})
                continue
            if not self.extra_layers_supported:
                add(WARNING, "F3.10", X["jenis"], f"{nama} dilewati (features.extra_layers = false)")
                continue
            for d in X["cols"]:
                if val(row, d) is None:
                    add(ERROR, "R14", d, f"lapisan ke-{X['n']} {L['name']} dipakai: kolom ini WAJIB "
                                         f"(web menandai merah jika kosong)")
            allowed = self.rules[L["table"]][c]["jenis_allowed"]
            jc = code_of(matched, X["jenis"])
            if jc is not None and jc not in allowed:
                add(ERROR, "R24", X["jenis"],
                    f"{L['table']}={c}: Jenis lapisan {X['n']} ({jc}) TIDAK diizinkan. "
                    f"Boleh: {self.jenis_names(L['jenis'], allowed)}")
            # QC121: lapisan berikutnya tidak boleh lebih rendah dari sebelumnya
            b = nums.get(X["base_id"])
            prev = [nums[p] for p in X["prev_base"] if p in nums]
            if b is not None and prev and b < max(prev):
                add(WARNING, "R-ORD", X["base_id"],
                    f"tinggi dasar {nama} ({b:g} m) lebih rendah dari lapisan sebelumnya ({max(prev):g} m)")
            if res.errors and any(i.column in X["cols"] and i.level == ERROR for i in res.issues):
                continue
            def full(col):
                m = matched.get(col)
                return m.text if (m and m.ok) else None
            plan["extra"].append({
                "layer": lk, "n": X["n"], "section": X["section"], "col": X["col"],
                "toggle_ordinal": X["toggle_ordinal"], "fallback_toggle_id": X["fallback_toggle_id"],
                "arah_row": X["arah_row"], "base_id": X["base_id"],
                "jenis": full(X["jenis"]), "jumlah": full(X["jumlah"]), "arah": full(X["arah"]),
                "base": b,
            })

    # ------------------------------------------------------------------ #
    def _check_rain(self, row, res, nums, jam):
        add = lambda lvl, rule, col, msg: res.issues.append(Issue(lvl, rule, col, msg))
        aktif = truthy(row.get("hujan_override_aktif"))
        mm = nums.get("hujan_override_mm")
        if val(row, "hujan_override_mm") is not None and mm is None:
            return  # sudah ditandai R-NUM
        if not aktif:
            if mm is not None:
                add(INFO, "R22", "hujan_override_mm", "angka hujan terisi tetapi override tidak aktif -> diabaikan")
            return
        if mm is None:
            add(ERROR, "R22", "hujan_override_mm", "override hujan aktif tetapi angka (mm) kosong")
            return
        if jam is not None and jam % 3 != 0:
            add(WARNING, "R22", "hujan_override_aktif",
                f"kolom hujan di web hanya terbuka tiap 3 jam UTC (00,03,06,..); jam {jam:02d}:00 -> override DIABAIKAN")
            return
        res.plan["rain_override"] = {"mm": mm}

    def _check_penguapan(self, row, res, nums, jam):
        """[rev 27] Kolom bawah form web yang terbuka pada jam 00 UTC. Kosong = biarkan nilai AWS Digi apa adanya.
        radiasi: 'kosongkan' (hapus nilai AWS yang tak relevan) ATAU 'nilai' baru, tidak keduanya."""
        add = lambda lvl, rule, col, msg: res.issues.append(Issue(lvl, rule, col, msg))
        mm, rad, sinar = nums.get("penguapan_mm"), nums.get("radiasi_matahari"), nums.get("lama_penyinaran_jam")
        ie_raw, ie = val(row, "penguapan_ie"), nums.get("penguapan_ie")
        kosongkan = truthy(row.get("radiasi_kosongkan"))
        for c in ("penguapan_mm", "radiasi_matahari", "lama_penyinaran_jam", "penguapan_ie"):
            if val(row, c) is not None and nums.get(c) is None:
                return          # sudah ditandai R-NUM (bukan angka / negatif)
        if ie is not None and (ie != int(ie) or not 0 <= ie <= 9):
            add(ERROR, "R25", "penguapan_ie", f"pengenal data penguapan (iE) harus bilangan bulat 0-9 (kode di web), bukan {ie_raw!r}")
            return
        if kosongkan and rad is not None:
            add(ERROR, "R26", "radiasi_matahari", "pilih salah satu: kosongkan radiasi ATAU isi nilai radiasi, bukan keduanya")
            return
        if sinar is not None and sinar > 24:
            add(ERROR, "R27", "lama_penyinaran_jam", f"lama penyinaran {sinar:g} jam tidak mungkin (maks 24 jam)")
            return
        if sinar is not None and sinar > 13:
            add(WARNING, "R27", "lama_penyinaran_jam", f"lama penyinaran {sinar:g} jam > 13 jam: tidak lazim untuk Jambi; pastikan benar")
        if mm is not None and mm > 30:
            add(WARNING, "R27", "penguapan_mm", f"penguapan {mm:g} mm per hari tidak lazim (umumnya 0-15 mm); pastikan benar")
        if jam is not None and jam != 0:
            add(WARNING, "R25", "penguapan_mm",
                f"bagian penguapan/matahari di web hanya terbuka pada jam 00 UTC; jam {jam:02d}:00 -> semua isian bagian ini DIABAIKAN")
            return
        rencana = {}
        if mm is not None:
            rencana["mm"] = mm
        if ie is not None:
            rencana["ie"] = int(ie)
        if kosongkan:
            rencana["radiasi"] = {"kosongkan": True}
        elif rad is not None:
            rencana["radiasi"] = {"nilai": rad}
        if sinar is not None:
            rencana["sinar_jam"] = sinar
        res.plan["penguapan"] = rencana or None

    # ------------------------------------------------------------------ #
    #  Seluruh DataFrame                                                 #
    # ------------------------------------------------------------------ #
    def validate_dataframe(self, df):
        results = []
        file_issues = []
        for c in REQUIRED_COLUMNS:
            if c not in df.columns:
                file_issues.append(Issue(ERROR, "R-FILE", c, "kolom wajib tidak ada di Excel"))
        for c in OPTIONAL_NEW_COLUMNS:
            if c not in df.columns:
                file_issues.append(Issue(INFO, "R-FILE", c, "kolom baru (opsional) belum ada di Excel"))
        _extra_cols = {c for X in EXTRA_SPECS for c in X["cols"]}
        missing_cloud = [c for c in ALL_CLOUD_COLS if c not in df.columns and c not in _extra_cols]
        if missing_cloud:
            file_issues.append(Issue(WARNING, "R-FILE", "", f"kolom awan tidak ada (dianggap kosong): {missing_cloud[:6]}"))

        seen = {}
        for pos, (_, r) in enumerate(df.iterrows()):
            row = {k: r[k] for k in df.columns}
            rr = self.validate_row(row, row_no=pos + 2)
            if rr.slot[0]:
                if rr.slot in seen:
                    rr.issues.append(Issue(ERROR, "R-DUP", "jam_input",
                                           f"jam {rr.slot[1]} UTC tanggal {rr.slot[0]} duplikat dengan baris {seen[rr.slot]}"))
                else:
                    seen[rr.slot] = rr.row_no
            results.append(rr)
        return file_issues, results


def code_of(matched, col):
    m = matched.get(col)
    return m.code if (m and m.ok) else None


# --------------------------------------------------------------------------- #
#  Excel & laporan                                                             #
# --------------------------------------------------------------------------- #
def load_excel(path, sheet=0):
    import pandas as pd
    df = pd.read_excel(path, sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[df["waktu_eksekusi"].notna()] if "waktu_eksekusi" in df.columns else df
    return df.reset_index(drop=True)


def format_report(file_issues, results, show_info=True):
    L = []
    for i in file_issues:
        if i.level != INFO or show_info:
            L.append(f"FILE    {i}")
    n_err = n_warn = n_ok = 0
    for r in results:
        lvl_rank = {ERROR: 0, WARNING: 1, INFO: 2}
        issues = sorted(r.issues, key=lambda i: lvl_rank[i.level])
        if not show_info:
            issues = [i for i in issues if i.level != INFO]
        status = "ERROR  " if r.errors else ("WARNING" if r.warnings else "OK     ")
        n_err += bool(r.errors)
        n_warn += bool(r.warnings and not r.errors)
        n_ok += (not r.errors and not r.warnings)
        wk = f"{r.waktu_eksekusi:%Y-%m-%d %H:%M}" if r.waktu_eksekusi else "?"
        L.append(f"[{status}] baris {r.row_no:>2} | slot {r.slot[0]} {r.slot[1]} UTC | eksekusi {wk} WIB")
        for i in issues:
            L.append(f"          {i}")
    L.append("")
    L.append(f"RINGKASAN: {len(results)} baris | OK {n_ok} | WARNING {n_warn} | ERROR {n_err}")
    return "\n".join(L)
