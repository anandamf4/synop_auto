# -*- coding: utf-8 -*-
"""
core/synop_check.py  -  F3.4: verifikasi sandi SYNOP hasil "Preview & Generate Sandi"

Membandingkan sandi yang dibuat web dengan sandi yang SEHARUSNYA berdasarkan data Excel/plan:
  - Dari Excel : N, VV, h, ww/W1/W2, Nh/CL/CM/CH, grup awan 8NsChshs (aturan penggabungan WMO 306),
                 grup puncak 80Chh, grup 57CDaEc, grup arah 56DLDMDH.
  - Dari AWS   : suhu, Td, QFE, QFF, angin TIDAK ada di Excel -> hanya diperiksa kewajarannya
                 (Td <= T, rentang, selisih QFF-QFE ~ 3 hPa pada 27 m).
Semua temuan bertingkat: ERROR (tidak boleh dikirim bila block_on_mismatch), WARNING, INFO.
Dasar aturan: handoff 2.11 (PPT pusat 16 Nov 2026) + sandi nyata 14 Nov 2026 08:00 UTC (lihat tests/test_sandi.py).

Pemakaian CLI (offline, memeriksa ulang semua sandi tersimpan di DB):
    python core/synop_check.py --db data/synop.db --excel INPUT_PARAMETER.xlsx
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"
CB = "9"


@dataclass
class Temuan:
    level: str
    kode: str
    pesan: str


@dataclass
class HasilCek:
    temuan: list = field(default_factory=list)
    parsed: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)

    @property
    def errors(self):
        return [t for t in self.temuan if t.level == ERROR]

    @property
    def warnings(self):
        return [t for t in self.temuan if t.level == WARNING]

    @property
    def ok(self):
        return not self.errors and not self.warnings

    def ringkas(self):
        if not self.temuan:
            return "sandi sesuai data"
        return "; ".join(f"{t.level} {t.kode}: {t.pesan}" for t in self.temuan if t.level != INFO) or "sandi sesuai data"


# ---------------------------------------------------------------------------
# utilitas data Excel
# ---------------------------------------------------------------------------
def _kosong(v):
    if v is None:
        return True
    try:
        if v != v:   # NaN
            return True
    except Exception:
        pass
    return str(v).strip().lower() in ("", "nan", "none", "-")


def kode_dropdown(v):
    """'21 -' -> '21'; '/ -' -> '/'; '8 - cumulus (Cu)' -> '8'; '8 okta' -> '8'; kosong -> None."""
    if _kosong(v):
        return None
    m = re.match(r"\s*(\d+|/)", str(v))
    return m.group(1) if m else None


def angka(v):
    try:
        if _kosong(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def kode_vv(km):
    """Jarak pandang (km) -> kode VV (tabel 4377)."""
    if km is None:
        return None
    if km < 0.1:
        return "00"
    if km <= 5.0:
        return f"{int(round(km * 10)):02d}"
    if km < 6:
        return "50"            # 51-55 tidak dipakai
    if km <= 30:
        return f"{int(km) + 50:02d}"
    if km <= 70:
        return f"{81 + int((km - 35) // 5):02d}" if km >= 35 else "80"
    return "89"


def kode_hshs(meter):
    """Tinggi (m) -> hshs (tabel 1677): 00-50 = x30 m; 56-80 = (h/300)+50; 81-89 = 9000 + 1500 x (k-80)."""
    if meter is None:
        return None
    m = float(meter)
    if m <= 1500:
        return f"{int(m // 30):02d}"
    if m <= 9000:
        return f"{int(m // 300) + 50:02d}"
    return f"{min(89, int((m - 9000) // 1500) + 80):02d}"


def kode_h(meter):
    """Tinggi dasar awan terendah (m) -> kode h (tabel 1600)."""
    if meter is None:
        return "9"
    for batas, k in ((50, "0"), (100, "1"), (200, "2"), (300, "3"), (600, "4"), (1000, "5"),
                     (1500, "6"), (2000, "7"), (2500, "8")):
        if meter < batas:
            return k
    return "9"


# ---------------------------------------------------------------------------
# penguraian sandi
# ---------------------------------------------------------------------------
def parse_sandi(teks):
    """Uraikan sandi AAXX. Mengembalikan dict; kunci 'valid' False bila bentuk tidak dikenali."""
    p = {"valid": False, "raw": teks}
    if not teks:
        return p
    toks = re.sub(r"=", " ", str(teks)).split()
    if "AAXX" not in toks:
        return p
    i = toks.index("AAXX")
    t = toks[i:]
    if len(t) < 5:
        return p
    sec3 = []
    if "333" in t:
        j = t.index("333")
        sec3 = t[j + 1:]
        t = t[:j]
    p.update(valid=True, tanggal_jam=t[1], stasiun=t[2])
    g = t[3]
    if len(g) == 5:
        p.update(iR=g[0], iX=g[1], h=g[2], VV=g[3:5])
    g = t[4]
    if len(g) == 5:
        p.update(N=g[0], dd=g[1:3], ff=g[3:5])
    grup = {}
    for x in t[5:]:
        if len(x) == 5 and x[0] in "12345678" and x[0] not in grup:
            grup[x[0]] = x
    if "1" in grup:
        p["T"] = (-1 if grup["1"][1] == "1" else 1) * int(grup["1"][2:5]) / 10 if grup["1"][2:5].isdigit() else None
    if "2" in grup:
        p["Td"] = (-1 if grup["2"][1] == "1" else 1) * int(grup["2"][2:5]) / 10 if grup["2"][2:5].isdigit() else None
    if "3" in grup and grup["3"][1:].isdigit():
        v = int(grup["3"][1:]) / 10
        p["QFE"] = v + 1000 if v < 500 else v
    if "4" in grup and grup["4"][1:].isdigit() and grup["4"][1] in "01":
        v = int(grup["4"][1:]) / 10
        p["QFF"] = v + 1000 if v < 500 else v
    if "7" in grup:
        p.update(ww=grup["7"][1:3], W1=grup["7"][3], W2=grup["7"][4])
    if "8" in grup:
        p.update(Nh=grup["8"][1], CL=grup["8"][2], CM=grup["8"][3], CH=grup["8"][4])
    # --- seksi 3
    layers, tops, arah, genus = [], [], None, None
    for x in sec3:
        if len(x) != 5:
            continue
        if x.startswith("56") and arah is None:
            arah = x[2:5]
        elif x.startswith("57") and genus is None:
            genus = x[2:5]
        elif x[0] == "8":
            if x[1] == "0":
                tops.append(x)
            else:
                layers.append(x)
    p.update(layers=layers, tops=tops, arah=arah, genus=genus, sec3=sec3)
    return p


# ---------------------------------------------------------------------------
# sandi yang diharapkan dari Excel
# ---------------------------------------------------------------------------
# (kolom jenis, kolom jumlah, kolom tinggi dasar, tingkat) tiap lapisan awan
LAPISAN = [
    ("awan_rendah_jenis", "awan_rendah_jumlah", "cloud_low_base_1", "low"),
    ("awan_rendah_2_jenis", "awan_rendah_2_jumlah", "cloud_low_base_2", "low"),
    ("awan_rendah_3_jenis", "awan_rendah_3_jumlah", "cloud_low_base_3", "low"),
    ("awan_menengah_jenis_1", "awan_menengah_jumlah_1", "cloud_med_base_1", "med"),
    ("awan_menengah_jenis_2", "awan_menengah_jumlah_2", "cloud_med_base_2", "med"),
    ("awan_tinggi_jenis", "awan_tinggi_jumlah", "cloud_high_base_1", "high"),
    ("awan_tinggi_2_jenis", "awan_tinggi_2_jumlah", "cloud_high_base_2", "high"),
]


def _g(row, k):
    try:
        return row.get(k) if hasattr(row, "get") else row[k]
    except Exception:
        return None


def hitung_harapan(row):
    """Sandi bagian-bagian yang dapat diturunkan dari Excel. Nilai None = tidak dapat/tidak perlu dicek."""
    e = {"layers": [], "tops": [], "ok_awan": False}
    e["N"] = kode_dropdown(_g(row, "cloud_cover_oktas_m"))
    e["VV"] = kode_vv(angka(_g(row, "visibility")))
    ww = kode_dropdown(_g(row, "ww"))
    e["ww"] = ww.zfill(2) if ww and ww != "/" else ww
    e["W1"] = kode_dropdown(_g(row, "w1"))
    e["W2"] = kode_dropdown(_g(row, "w2"))
    CL = kode_dropdown(_g(row, "cloud_low_type_cl"))
    CM = kode_dropdown(_g(row, "cloud_med_type_cm"))
    CH = kode_dropdown(_g(row, "cloud_high_type_ch"))
    e.update(CL=CL, CM=CM, CH=CH)
    if e["N"] in (None, "9", "/"):
        # web mengisi CL/CM/CH otomatis & menonaktifkan detail awan: nilai awan di Excel bukan yang dikirim
        e.update(CL=None, CM=None, CH=None)
        return e
    if e["N"] == "0":
        e.update(Nh="0", CL="0", CM="0", CH="0", ok_awan=True)
        return e
    aktif = {"low": CL not in (None, "0", "/"), "med": CM not in (None, "0", "/"), "high": CH not in (None, "0", "/")}
    lap = []
    for kj, ku, kb, tingkat in LAPISAN:
        if not aktif[tingkat]:
            continue
        jenis, jml, base = kode_dropdown(_g(row, kj)), kode_dropdown(_g(row, ku)), angka(_g(row, kb))
        if jenis in (None, "/") or jml in (None, "/") or base is None:
            continue
        lap.append({"jenis": jenis, "jumlah": int(jml), "base": base, "tingkat": tingkat, "hh": kode_hshs(base)})
    e["layers"] = lap
    # Nh: banyak awan lapisan terendah yang tampak (CL jika ada, kalau tidak CM)
    if aktif["low"]:
        e["Nh"] = kode_dropdown(_g(row, "cloud_low_cover_oktas"))
    elif aktif["med"]:
        e["Nh"] = kode_dropdown(_g(row, "cloud_med_cover_oktas"))
    else:
        e["Nh"] = "0" if not aktif["high"] else None
    e["h"] = kode_h(min((x["base"] for x in lap), default=None)) if lap else None
    # --- penggabungan lapisan setinggi sama (WMO 306)
    grup = {}
    for x in lap:
        kunci = (x["hh"], "cb") if x["jenis"] == CB else (x["hh"], "lain")
        grup.setdefault(kunci, []).append(x)
    cb_token, lain = [], []
    for (hh, jenis_grup), anggota in grup.items():
        total = min(8, sum(a["jumlah"] for a in anggota))
        if jenis_grup == "cb":
            cb_token.append(f"8{total}{CB}{hh}")
        else:   # jenis dengan jumlah terbanyak; sama -> kode tertinggi
            per = {}
            for a in anggota:
                per[a["jenis"]] = per.get(a["jenis"], 0) + a["jumlah"]
            c = max(per, key=lambda k: (per[k], int(k)))
            lain.append({"hh": int(hh), "ns": total, "token": f"8{total}{c}{hh}"})
    # --- pemilihan grup yang DILAPORKAN (WMO 306; cocok dengan 21 sandi nyata 14 Nov 2026):
    #     grup-1 = lapisan terendah (jumlah berapa pun), grup-2 = lapisan berikutnya yang > 2 okta,
    #     grup-3 = lapisan berikutnya yang > 4 okta; Cb dilaporkan tersendiri (di luar 3 grup).
    lain.sort(key=lambda g: g["hh"])
    terpilih = []
    for g in lain:
        if len(terpilih) < 3 and g["ns"] > (0, 2, 4)[len(terpilih)]:
            terpilih.append(g)
    e["groups"] = [g["token"] for g in terpilih] + cb_token          # WAJIB ada di sandi
    e["groups_opsional"] = [g["token"] for g in lain if g not in terpilih]   # boleh ada, tidak wajib
    e["n_grup_non_cb"] = len(lain)
    # --- puncak Cu/Cb lapisan 1 (terbukti dari sandi nyata: 80860 = puncak 3000 m)
    j1 = kode_dropdown(_g(row, "awan_rendah_jenis"))
    pk = angka(_g(row, "cloud_low_peak_1"))
    if aktif["low"] and j1 in ("8", "9") and CL != "1" and pk is not None:
        e["tops"].append(f"80{j1}{kode_hshs(pk)}")
        ec = kode_dropdown(_g(row, "cloud_elevation_1_angle_ec"))
        da = kode_dropdown(_g(row, "cloud_arah_sebenarnya_1"))
        if ec is not None and da is not None:
            e["genus"] = f"{j1}{da}{ec}"
    # --- arah gerak awan 56DLDMDH
    e["DL"] = kode_dropdown(_g(row, "cloud_arah_awan_rendah")) if aktif["low"] else None
    e["DM"] = kode_dropdown(_g(row, "cloud_arah_menengah_1")) if aktif["med"] else None
    e["DH"] = kode_dropdown(_g(row, "cloud_arah_tinggi")) if aktif["high"] else None
    e["ok_awan"] = True
    return e


# ---------------------------------------------------------------------------
# pembanding
# ---------------------------------------------------------------------------
def verifikasi(sandi, row, plan=None, abaikan=(), cfg=None):
    """
    sandi    : teks dari textarea-sandi
    row      : baris Excel (pandas Series / dict)
    abaikan  : kunci yang sengaja diubah otomatis (mis. ('ww',) setelah fallback Mist->Haze)
    cfg      : dict features (qff_qfe_expected_diff, qff_qfe_tolerance, ...)
    """
    cfg = cfg or {}
    h = HasilCek()
    p = parse_sandi(sandi)
    h.parsed = p
    if not p["valid"]:
        h.temuan.append(Temuan(ERROR, "S0", "sandi kosong / bentuk AAXX tidak dikenali"))
        return h
    e = hitung_harapan(row)
    h.expected = e
    add = lambda lv, k, m: h.temuan.append(Temuan(lv, k, m))

    def banding(kunci, nama, expected, actual, level=ERROR):
        if kunci in abaikan:
            add(INFO, "S-AUTO", f"{nama} sengaja diubah otomatis; tidak dibandingkan")
            return
        if expected is None or actual is None:
            return
        if str(expected) != str(actual):
            add(level, f"S-{kunci}", f"{nama}: Excel={expected} tetapi sandi={actual}")

    banding("N", "Tutupan total N", e.get("N"), p.get("N"))
    banding("VV", "Jarak pandang VV", e.get("VV"), p.get("VV"))
    banding("ww", "Cuaca saat ini ww", e.get("ww"), p.get("ww"))
    banding("W1", "Cuaca lampau W1", e.get("W1"), p.get("W1"))
    banding("W2", "Cuaca lampau W2", e.get("W2"), p.get("W2"))
    banding("CL", "Awan rendah CL", e.get("CL"), p.get("CL"))
    banding("CM", "Awan menengah CM", e.get("CM"), p.get("CM"))
    banding("CH", "Awan tinggi CH", e.get("CH"), p.get("CH"))
    if e.get("ok_awan"):
        banding("Nh", "Nh (jumlah awan terendah)", e.get("Nh"), p.get("Nh"))
        banding("h", "h (tinggi dasar awan terendah)", e.get("h"), p.get("h"), level=WARNING)
        # --- grup awan 8NsChshs
        exp_g = e.get("groups", [])
        opsi = e.get("groups_opsional", [])
        act = p.get("layers", [])
        for g in exp_g:
            if g not in act:
                add(WARNING, "S-GRUP", f"grup awan {g} (hasil penggabungan + seleksi WMO 306) tidak ada di sandi; "
                                       f"sandi memuat: {' '.join(act) or '-'}")
        for g in act:
            if g in exp_g or not e.get("layers"):
                continue
            if g in opsi:
                add(INFO, "S-GRUP", f"grup {g} dilaporkan web walau tidak wajib menurut seleksi jumlah (>2/>4 okta)")
            else:
                add(WARNING, "S-GRUP", f"grup awan {g} ada di sandi tetapi tidak diharapkan dari Excel "
                                       f"(harapan: {' '.join(exp_g) or '-'})")
        for tp in e.get("tops", []):
            if tp not in p.get("tops", []):
                add(WARNING, "S-PUNCAK", f"grup puncak {tp} tidak ada di sandi (ada: {' '.join(p.get('tops', [])) or '-'})")
        if e.get("genus") and p.get("genus") is not None and e["genus"] != p["genus"]:
            add(WARNING, "S-57", f"grup 57: Excel={e['genus']} (jenis, arah sebenarnya, elevasi) tetapi sandi={p['genus']}")
        if p.get("arah"):
            for idx, kunci, nama in ((0, "DL", "arah gerak awan rendah"), (1, "DM", "arah gerak awan menengah"),
                                     (2, "DH", "arah gerak awan tinggi")):
                if e.get(kunci) is not None and p["arah"][idx] != e[kunci]:
                    add(WARNING, "S-56", f"{nama}: Excel={e[kunci]} tetapi sandi={p['arah'][idx]}")
    # --- kewajaran data AWS (tidak ada di Excel)
    T, Td, qfe, qff = p.get("T"), p.get("Td"), p.get("QFE"), p.get("QFF")
    if T is not None and not (-10 <= T <= 45):
        add(WARNING, "S-T", f"suhu {T} °C di luar rentang wajar (-10..45)")
    if T is not None and Td is not None and Td > T + 0.05:
        add(WARNING, "S-TD", f"titik embun {Td} °C lebih tinggi dari suhu {T} °C")
    if qfe is not None and not (980 <= qfe <= 1040):
        add(WARNING, "S-QFE", f"QFE {qfe} hPa di luar rentang wajar (980..1040)")
    if qfe is not None and qff is not None and cfg.get("qff_qfe_check", True):
        sel, harap, tol = qff - qfe, float(cfg.get("qff_qfe_expected_diff", 3.2)), float(cfg.get("qff_qfe_tolerance", 1.0))
        if abs(sel - harap) > tol:
            add(WARNING, "S-QFF", f"QFF-QFE = {sel:.1f} hPa; seharusnya sekitar {harap:.1f} hPa (stasiun 27 m). "
                                  f"Cek hasil Fill AWS Digi (QFF=QFE?)")
    dd = p.get("dd")
    if dd and dd.isdigit() and not (int(dd) <= 36 or dd == "99"):
        add(WARNING, "S-DD", f"arah angin dd={dd} tidak valid (00-36 atau 99)")
    return h


def format_hasil(h, judul=""):
    baris = [f"{'🧾 ' + judul if judul else '🧾 Verifikasi sandi'}: " + ("✅ sesuai data" if h.ok else "⚠️ ada temuan")]
    for t in h.temuan:
        ikon = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}[t.level]
        baris.append(f"   {ikon} {t.kode}: {t.pesan}")
    return "\n".join(baris)


# ---------------------------------------------------------------------------
# CLI: periksa ulang semua sandi tersimpan di DB terhadap Excel
# ---------------------------------------------------------------------------
def _main(argv=None):
    import argparse
    import sqlite3
    import warnings
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(description="Periksa ulang sandi di DB terhadap Excel")
    ap.add_argument("--db", default="data/synop.db")
    ap.add_argument("--excel", default="INPUT_PARAMETER.xlsx")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.validator import load_excel
    df = load_excel(a.excel)
    c = sqlite3.connect(a.db)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT tanggal_utc, jam, kode_synop FROM send_log "
                     "WHERE kode_synop IS NOT NULL AND kode_synop != '' ORDER BY tanggal_utc, jam").fetchall()
    if not rows:
        print("Tidak ada sandi tersimpan di DB.")
        return 0
    tot_bad = 0
    for r in rows:
        jam = r["jam"]
        cocok = df[df["jam_input"].astype(str).str[:5] == jam[:5]]
        if cocok.empty:
            print(f"{r['tanggal_utc']} {jam}: baris Excel tidak ditemukan")
            continue
        hasil = verifikasi(r["kode_synop"], cocok.iloc[0])
        print(format_hasil(hasil, f"{r['tanggal_utc']} {jam} UTC"))
        tot_bad += 0 if hasil.ok else 1
    print(f"\n{len(rows)} sandi diperiksa, {tot_bad} bermasalah")
    return 1 if tot_bad else 0


if __name__ == "__main__":
    sys.exit(_main())
