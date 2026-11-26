# -*- coding: utf-8 -*-
"""
core/obsdb.py  -  F2.1: penyimpanan data observasi (pengganti pengetikan di Excel)

Satu baris = satu slot (tanggal UTC + jam UTC). Isinya disimpan UTUH sebagai JSON berisi kolom
yang sama dengan Excel (nama kolom = nama kolom Excel; nilai dropdown = teks opsi web), jadi:
  * validator.py yang sama dipakai untuk Excel dan form;
  * satu baris Excel dapat disimpan dan dibaca kembali tanpa kehilangan apa pun (DoD F2.1).
waktu_eksekusi dan jam_input TIDAK disimpan; dihitung dari tanggal+jam (zona waktu & menit
sebelum jam observasi dari konfigurasi), sehingga tidak bisa salah ketik/tidak cocok.

Tabel `observasi` berada di berkas SQLite yang sama dengan send_log (data/synop.db).
"""
import datetime as dt
import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS observasi (
    tanggal_utc  TEXT NOT NULL,
    jam          TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    diubah_oleh  TEXT,
    dibuat       TEXT,
    updated_at   TEXT,
    PRIMARY KEY (tanggal_utc, jam)
);
-- [rev 30] jadwal pengiriman: default global + pengecualian per jam. Disimpan di DB agar bot langsung memakainya (tanpa restart).
CREATE TABLE IF NOT EXISTS pengaturan (
    kunci   TEXT PRIMARY KEY,
    nilai   TEXT
);
CREATE TABLE IF NOT EXISTS jadwal (
    tanggal_utc  TEXT NOT NULL,
    jam          TEXT NOT NULL,
    menit        INTEGER NOT NULL,       -- bot mulai mengisi N menit SEBELUM jam observasi (negatif = sesudah)
    diubah_oleh  TEXT,
    updated_at   TEXT,
    PRIMARY KEY (tanggal_utc, jam)
);
"""
# urutan kolom seperti Excel INPUT_PARAMETER (kolom tak dikenal ditaruh di belakang)
URUTAN_KOLOM = [
    "waktu_eksekusi", "jam_input", "visibility", "ww", "w1", "w2", "cloud_cover_oktas_m",
    "cloud_low_type_cl", "cloud_low_cover_oktas", "awan_rendah_jenis", "awan_rendah_jumlah", "cloud_low_base_1",
    "cloud_low_peak_1", "cloud_arah_awan_rendah", "cloud_elevation_1_angle_ec", "cloud_arah_sebenarnya_1",
    "awan_rendah_2_jenis", "awan_rendah_2_jumlah", "cloud_low_base_2", "cloud_low_peak_2", "cloud_arah_2",
    "cloud_elevation_2_angle_ec", "cloud_arah_sebenarnya_2", "awan_rendah_3_jenis", "awan_rendah_3_jumlah",
    "cloud_low_base_3", "cloud_arah_3", "cloud_med_type_cm", "cloud_med_cover_oktas", "awan_menengah_jenis_1",
    "awan_menengah_jumlah_1", "cloud_med_base_1", "cloud_arah_menengah_1", "awan_menengah_jenis_2",
    "awan_menengah_jumlah_2", "cloud_med_base_2", "cloud_arah_menengah_2", "cloud_high_type_ch",
    "cloud_high_cover_oktas", "awan_tinggi_jenis", "awan_tinggi_jumlah", "cloud_high_base_1", "cloud_arah_tinggi",
    "awan_tinggi_2_jenis", "awan_tinggi_2_jumlah", "cloud_high_base_2", "cloud_arah_tinggi_2", "land_cond",
    "vertical_visibility", "hujan_override_aktif", "hujan_override_mm",
    "penguapan_mm", "penguapan_ie", "radiasi_kosongkan", "radiasi_matahari", "lama_penyinaran_jam",
]
TIDAK_DISIMPAN = ("waktu_eksekusi", "jam_input")


def _now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _kosong(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return str(v).strip() in ("", "nan", "NaN", "NaT", "None", "-")


def _bersih(v):
    """Nilai yang aman disimpan sebagai JSON (angka tetap angka, bool tetap bool)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return int(f) if f.is_integer() else f
    if hasattr(v, "item"):            # numpy scalar
        return _bersih(v.item())
    return str(v).strip()


def normalisasi(data):
    """Buang kolom kosong & kolom turunan; kembalikan dict siap simpan."""
    out = {}
    for k, v in (data or {}).items():
        k = str(k).strip()
        if k in TIDAK_DISIMPAN or k.startswith("Unnamed") or _kosong(v):
            continue
        out[k] = _bersih(v)
    return out


class ObsStore:
    def __init__(self, path, tz_hours=7, menit_sebelum=2):
        self.path = str(path)
        self.tz = tz_hours
        self.menit = menit_sebelum
        self.kanonik = None          # fungsi opsional dict->dict (dipasang app.py: nilai dropdown -> teks opsi web)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        """Koneksi sekali pakai: commit bila sukses, rollback bila error, SELALU ditutup
        (sqlite3 'with' biasa tidak menutup; di Windows berkas .db jadi terkunci)."""
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    # ---------------------------------------------------------------- CRUD
    def get(self, tanggal_utc, jam):
        with self._conn() as c:
            r = c.execute("SELECT * FROM observasi WHERE tanggal_utc=? AND jam=?", (tanggal_utc, jam)).fetchone()
        return json.loads(r["data_json"]) if r else None

    def info(self, tanggal_utc, jam):
        with self._conn() as c:
            r = c.execute("SELECT diubah_oleh, dibuat, updated_at FROM observasi WHERE tanggal_utc=? AND jam=?",
                          (tanggal_utc, jam)).fetchone()
        return dict(r) if r else None

    def upsert(self, tanggal_utc, jam, data, oleh=None):
        d = normalisasi(self.kanonik(data) if self.kanonik else data)
        js = json.dumps(d, ensure_ascii=False, sort_keys=True)
        with self._conn() as c:
            c.execute(
                "INSERT INTO observasi (tanggal_utc, jam, data_json, diubah_oleh, dibuat, updated_at) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(tanggal_utc, jam) DO UPDATE SET data_json=excluded.data_json, "
                "diubah_oleh=excluded.diubah_oleh, updated_at=excluded.updated_at",
                (tanggal_utc, jam, js, oleh, _now(), _now()))
        return d

    def delete(self, tanggal_utc, jam):
        with self._conn() as c:
            c.execute("DELETE FROM observasi WHERE tanggal_utc=? AND jam=?", (tanggal_utc, jam))

    def list_day(self, tanggal_utc):
        with self._conn() as c:
            rs = c.execute("SELECT * FROM observasi WHERE tanggal_utc=? ORDER BY jam", (tanggal_utc,)).fetchall()
        return {r["jam"]: {"data": json.loads(r["data_json"]), "oleh": r["diubah_oleh"],
                           "updated_at": r["updated_at"]} for r in rs}

    @staticmethod
    def slot_sebelumnya(tanggal_utc, jam):
        t = dt.datetime.strptime(f"{tanggal_utc} {jam}", "%Y-%m-%d %H:%M") - dt.timedelta(hours=1)
        return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")

    def sebelumnya(self, tanggal_utc, jam):
        """Data jam sebelumnya (melewati pergantian hari UTC) untuk tombol 'salin'."""
        return self.get(*self.slot_sebelumnya(tanggal_utc, jam))

    @staticmethod
    def slot_berikutnya(tanggal_utc, jam):
        t = dt.datetime.strptime(f"{tanggal_utc} {jam}", "%Y-%m-%d %H:%M") + dt.timedelta(hours=1)
        return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")

    # ------------------------------------------------- jadwal pengiriman (rev 30)
    MENIT_SESUDAH_MAKS = 25     # < 30 agar pembulatan jam di validator/bot (+30 menit) tetap menemukan slot yang benar

    def peta_jadwal(self, c=None):
        """(menit_default, {(tanggal, jam): menit}) dibaca sekali agar to_dataframe tidak membuka koneksi per baris."""
        def baca(cn):
            r = cn.execute("SELECT nilai FROM pengaturan WHERE kunci='menit_sebelum'").fetchone()
            try:
                default = int(r["nilai"]) if r else self.menit
            except (TypeError, ValueError):
                default = self.menit
            ov = {(x["tanggal_utc"], x["jam"]): int(x["menit"]) for x in cn.execute("SELECT * FROM jadwal").fetchall()}
            return default, ov
        if c is not None:
            return baca(c)
        with self._conn() as cn:
            return baca(cn)

    def menit_default(self):
        return self.peta_jadwal()[0]

    def set_menit_default(self, menit):
        with self._conn() as c:
            c.execute("INSERT INTO pengaturan (kunci, nilai) VALUES ('menit_sebelum', ?) "
                      "ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai", (str(int(menit)),))

    def set_jadwal(self, tanggal_utc, jam, menit, oleh=None):
        with self._conn() as c:
            c.execute("INSERT INTO jadwal (tanggal_utc, jam, menit, diubah_oleh, updated_at) VALUES (?,?,?,?,?) "
                      "ON CONFLICT(tanggal_utc, jam) DO UPDATE SET menit=excluded.menit, diubah_oleh=excluded.diubah_oleh, "
                      "updated_at=excluded.updated_at", (tanggal_utc, jam, int(menit), oleh, _now()))

    def hapus_jadwal(self, tanggal_utc, jam):
        with self._conn() as c:
            c.execute("DELETE FROM jadwal WHERE tanggal_utc=? AND jam=?", (tanggal_utc, jam))

    def jadwal_hari(self, tanggal_utc):
        """{jam: menit} pengecualian pada tanggal itu."""
        with self._conn() as c:
            rs = c.execute("SELECT jam, menit FROM jadwal WHERE tanggal_utc=?", (tanggal_utc,)).fetchall()
        return {r["jam"]: int(r["menit"]) for r in rs}

    # ------------------------------------------------- jembatan ke bot/validator
    def waktu_eksekusi(self, tanggal_utc, jam, peta=None):
        """Waktu setempat (naive) saat bot mulai mengisi: jam observasi (UTC) + zona - menit.
        [rev 30] menit = pengecualian jam itu bila ada, jika tidak default dari dashboard (tabel pengaturan), jika tidak
        nilai config web.menit_sebelum."""
        default, ov = peta if peta is not None else self.peta_jadwal()
        menit = ov.get((tanggal_utc, jam), default)
        t = dt.datetime.strptime(f"{tanggal_utc} {jam}", "%Y-%m-%d %H:%M")
        return t + dt.timedelta(hours=self.tz) - dt.timedelta(minutes=menit)

    def to_row(self, tanggal_utc, jam, data=None, peta=None):
        """Baris bergaya Excel (dict) untuk Validator.validate_row / DataFrame bot."""
        d = self.get(tanggal_utc, jam) if data is None else normalisasi(data)
        if d is None:
            return None
        row = {"waktu_eksekusi": self.waktu_eksekusi(tanggal_utc, jam, peta), "jam_input": jam}
        row.update(d)
        return row

    def to_dataframe(self, dari=None, sampai=None):
        """DataFrame seperti load_excel() untuk slot dalam rentang tanggal UTC [dari, sampai]."""
        import pandas as pd
        q, args = "SELECT * FROM observasi", []
        if dari or sampai:
            q += " WHERE 1=1"
            if dari:
                q += " AND tanggal_utc>=?"
                args.append(dari)
            if sampai:
                q += " AND tanggal_utc<=?"
                args.append(sampai)
        q += " ORDER BY tanggal_utc, jam"
        with self._conn() as c:
            rs = c.execute(q, args).fetchall()
            peta = self.peta_jadwal(c)
        rows = [self.to_row(r["tanggal_utc"], r["jam"], json.loads(r["data_json"]), peta) for r in rs]
        if not rows:
            return pd.DataFrame(columns=URUTAN_KOLOM)
        df = pd.DataFrame(rows)
        # DB hanya menyimpan kolom yang terisi; bot mengakses row['awan_rendah_2_jenis'] dst. -> kolom yang tak ada HARUS ada (NaN),
        # persis seperti Excel. Tanpa ini: KeyError 'awan_rendah_2_jenis' -> "Gagal isi data" di setiap percobaan (rev 37).
        urut = URUTAN_KOLOM + [c for c in df.columns if c not in URUTAN_KOLOM]
        df = df.reindex(columns=urut)
        df["waktu_eksekusi"] = pd.to_datetime(df["waktu_eksekusi"])
        return df.reset_index(drop=True)

    def import_dataframe(self, df, tz_hours=None, oleh="import Excel"):
        """
        Masukkan baris Excel ke DB. Tanggal/jam UTC diturunkan dari waktu_eksekusi (+ pembulatan 30 menit,
        sama seperti validator). Return (jumlah_masuk, [(no_baris, alasan)] yang dilewati).
        """
        import pandas as pd
        tz = self.tz if tz_hours is None else tz_hours
        masuk, lewat = 0, []
        for i, (_, r) in enumerate(df.iterrows()):
            try:
                w = pd.to_datetime(r["waktu_eksekusi"]).to_pydatetime()
            except Exception:
                lewat.append((i + 2, "waktu_eksekusi tidak valid"))
                continue
            utc = w - dt.timedelta(hours=tz)
            n = (utc + dt.timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
            self.upsert(n.strftime("%Y-%m-%d"), f"{n.hour:02d}:00", {k: r[k] for k in df.columns}, oleh)
            masuk += 1
        return masuk, lewat
