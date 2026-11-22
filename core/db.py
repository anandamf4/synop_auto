# -*- coding: utf-8 -*-
"""
core/db.py  -  F1.4: log status pengiriman (SQLite) + idempotensi

Satu baris per slot observasi = (tanggal_utc, jam). Status:
    pending  : terdaftar, belum dikerjakan
    running  : sedang dikerjakan (jika tertinggal setelah crash -> perlu cek web)
    sent     : sudah terkirim (TIDAK akan dikirim ulang)
    failed   : gagal setelah percobaan
    skipped  : sengaja dilewati (mis. waktu lewat, validasi ERROR)

should_send() menjawab "boleh kirim?" sekaligus memberi tanda needs_web_check:
jika slot pernah 'running'/'failed', data MUNGKIN sudah ada di web, dan tombol
di web berubah menjadi "Update" (temuan T21) -> bot harus mengenali kedua label.

Pemakaian:
    from core.db import SendLog
    log = SendLog("data/synop.db")
    log.register("2026-11-14", "07:00", waktu_eksekusi="2026-11-14 14:58", plan={...})
    d = log.should_send("2026-11-14", "07:00")      # {'send':True,'reason':...,'needs_web_check':False}
    log.start_attempt("2026-11-14", "07:00", observer="Nama")
    log.mark_sent("2026-11-14", "07:00", kode_synop="AAXX ...", diubah_otomatis=None)
"""
import json
import os
import sqlite3
import threading
from datetime import datetime

STATUSES = ("pending", "running", "sent", "failed", "skipped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS send_log (
    tanggal_utc      TEXT NOT NULL,
    jam              TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    waktu_eksekusi   TEXT,
    waktu_mulai      TEXT,
    waktu_selesai    TEXT,
    percobaan        INTEGER NOT NULL DEFAULT 0,
    observer         TEXT,
    kode_synop       TEXT,
    pesan            TEXT,
    screenshot_path  TEXT,
    diubah_otomatis  TEXT,
    hujan_override   TEXT,
    plan_json        TEXT,
    updated_at       TEXT,
    PRIMARY KEY (tanggal_utc, jam)
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    tanggal_utc TEXT,
    jam         TEXT,
    event       TEXT NOT NULL,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_slot ON events (tanggal_utc, jam);
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _js(x):
    return None if x is None else json.dumps(x, ensure_ascii=False)


class SendLog:
    def __init__(self, path):
        path = str(path)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.path = path
        # Flask melayani tiap permintaan di thread berbeda; objek koneksi SQLite tidak boleh
        # dipakai lintas thread. Solusi: satu koneksi PER THREAD (dibuat saat pertama dipakai).
        self._local = threading.local()
        self._semua = []
        self._kunci = threading.Lock()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @property
    def conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
            c.row_factory = sqlite3.Row
            self._local.c = c
            with self._kunci:
                self._semua.append(c)
        return c

    def close(self):
        with self._kunci:
            for c in self._semua:
                try:
                    c.close()
                except Exception:
                    pass
            self._semua.clear()
        self._local = threading.local()

    # ------------------------------------------------------------------ #
    def get(self, tanggal_utc, jam):
        r = self.conn.execute(
            "SELECT * FROM send_log WHERE tanggal_utc=? AND jam=?", (tanggal_utc, jam)).fetchone()
        return dict(r) if r else None

    def register(self, tanggal_utc, jam, waktu_eksekusi=None, plan=None):
        """Daftarkan slot (pending). Jika sudah ada, status TIDAK diubah."""
        self.conn.execute(
            "INSERT OR IGNORE INTO send_log (tanggal_utc, jam, status, waktu_eksekusi, plan_json, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (tanggal_utc, jam, "pending", str(waktu_eksekusi) if waktu_eksekusi else None, _js(plan), _now()))
        self.conn.commit()
        return self.get(tanggal_utc, jam)

    def update_plan(self, tanggal_utc, jam, plan, waktu_eksekusi=None):
        self.conn.execute(
            "UPDATE send_log SET plan_json=?, waktu_eksekusi=COALESCE(?, waktu_eksekusi), updated_at=? "
            "WHERE tanggal_utc=? AND jam=? AND status!='sent'",
            (_js(plan), str(waktu_eksekusi) if waktu_eksekusi else None, _now(), tanggal_utc, jam))
        self.conn.commit()

    # ------------------------------------------------------------------ #
    def should_send(self, tanggal_utc, jam):
        r = self.get(tanggal_utc, jam)
        if r is None:
            return {"send": True, "reason": "slot baru", "needs_web_check": False}
        st = r["status"]
        if st == "sent":
            return {"send": False, "reason": f"sudah terkirim ({r['waktu_selesai']})", "needs_web_check": False}
        if st == "skipped":
            return {"send": True, "reason": f"sebelumnya dilewati: {r['pesan']}", "needs_web_check": False}
        if st == "running":
            return {"send": True,
                    "reason": "sebelumnya berhenti saat berjalan (kemungkinan crash); data mungkin sudah ada di web",
                    "needs_web_check": True}
        if st == "failed":
            return {"send": True, "reason": f"percobaan sebelumnya gagal: {r['pesan']}",
                    "needs_web_check": True}
        return {"send": True, "reason": "pending", "needs_web_check": False}

    def start_attempt(self, tanggal_utc, jam, observer=None):
        self.register(tanggal_utc, jam)
        self.conn.execute(
            "UPDATE send_log SET status='running', waktu_mulai=?, waktu_selesai=NULL, percobaan=percobaan+1, "
            "observer=COALESCE(?, observer), pesan=NULL, updated_at=? WHERE tanggal_utc=? AND jam=?",
            (_now(), observer, _now(), tanggal_utc, jam))
        self.conn.commit()
        self.log_event(tanggal_utc, jam, "mulai", observer or "")

    def mark_sent(self, tanggal_utc, jam, kode_synop=None, diubah_otomatis=None, hujan_override=None):
        self.conn.execute(
            "UPDATE send_log SET status='sent', waktu_selesai=?, kode_synop=COALESCE(?, kode_synop), "
            "diubah_otomatis=?, hujan_override=?, pesan=NULL, updated_at=? WHERE tanggal_utc=? AND jam=?",
            (_now(), kode_synop, _js(diubah_otomatis), _js(hujan_override), _now(), tanggal_utc, jam))
        self.conn.commit()
        self.log_event(tanggal_utc, jam, "terkirim", kode_synop or "")

    def mark_failed(self, tanggal_utc, jam, pesan, screenshot_path=None):
        self.conn.execute(
            "UPDATE send_log SET status='failed', waktu_selesai=?, pesan=?, "
            "screenshot_path=COALESCE(?, screenshot_path), updated_at=? WHERE tanggal_utc=? AND jam=?",
            (_now(), str(pesan)[:500], screenshot_path, _now(), tanggal_utc, jam))
        self.conn.commit()
        self.log_event(tanggal_utc, jam, "gagal", str(pesan)[:300])

    def mark_skipped(self, tanggal_utc, jam, alasan):
        self.register(tanggal_utc, jam)
        self.conn.execute(
            "UPDATE send_log SET status='skipped', pesan=?, updated_at=? WHERE tanggal_utc=? AND jam=? AND status!='sent'",
            (str(alasan)[:500], _now(), tanggal_utc, jam))
        self.conn.commit()
        self.log_event(tanggal_utc, jam, "dilewati", str(alasan)[:300])

    def atur_ulang(self, tanggal_utc, jam, catatan="status diatur ulang manual"):
        """Kembalikan slot yang TERTAHAN ('running'/'failed'/'skipped') ke 'pending' agar bot boleh mencobanya lagi.
        Slot 'sent' tidak pernah diubah. Mengembalikan status lama, atau None bila tidak ada/tidak boleh."""
        r = self.get(tanggal_utc, jam)
        if r is None or r["status"] in ("sent", "pending"):
            return None
        lama = r["status"]
        self.conn.execute(
            "UPDATE send_log SET status='pending', waktu_selesai=NULL, pesan=NULL, updated_at=? "
            "WHERE tanggal_utc=? AND jam=? AND status NOT IN ('sent','pending')", (_now(), tanggal_utc, jam))
        self.conn.commit()
        self.log_event(tanggal_utc, jam, "diatur_ulang", f"{catatan} (dari {lama})")
        return lama

    def tandai_terkirim_manual(self, tanggal_utc, jam, catatan="dikonfirmasi manual: data sudah ada di web BMKG Satu"):
        """Untuk slot yang ternyata SUDAH terkirim di web (mis. bot berhenti tepat setelah SEND)."""
        r = self.get(tanggal_utc, jam)
        if r is None or r["status"] == "sent":
            return False
        self.conn.execute(
            "UPDATE send_log SET status='sent', waktu_selesai=?, pesan=?, updated_at=? WHERE tanggal_utc=? AND jam=?",
            (_now(), catatan, _now(), tanggal_utc, jam))
        self.conn.commit()
        self.log_event(tanggal_utc, jam, "terkirim_manual", catatan)
        return True

    def pulihkan_terhenti(self, alasan="proses bot berhenti saat slot ini berjalan (Ctrl+C/crash/PC mati)"):
        """Dipanggil saat bot START: tidak mungkin ada slot yang benar-benar 'running' sebelum bot jalan,
        jadi semua 'running' adalah sisa proses yang terhenti -> jadikan 'failed' (jujur, bukan 'berjalan' selamanya).
        should_send() tetap memberi needs_web_check=True sehingga bot memakai mode Update bila data sudah ada di web."""
        rows = self.conn.execute("SELECT tanggal_utc, jam FROM send_log WHERE status='running'").fetchall()
        for r in rows:
            self.mark_failed(r["tanggal_utc"], r["jam"], alasan)
        return [(r["tanggal_utc"], r["jam"]) for r in rows]

    def set_kode_synop(self, tanggal_utc, jam, kode_synop):
        self.conn.execute("UPDATE send_log SET kode_synop=?, updated_at=? WHERE tanggal_utc=? AND jam=?",
                          (kode_synop, _now(), tanggal_utc, jam))
        self.conn.commit()

    # ------------------------------------------------------------------ #
    def log_event(self, tanggal_utc, jam, event, detail=""):
        self.conn.execute(
            "INSERT INTO events (ts, tanggal_utc, jam, event, detail) VALUES (?,?,?,?,?)",
            (_now(), tanggal_utc, jam, event, detail))
        self.conn.commit()

    def history(self, tanggal_utc=None, limit=50):
        q = "SELECT * FROM send_log"
        args = []
        if tanggal_utc:
            q += " WHERE tanggal_utc=?"
            args.append(tanggal_utc)
        q += " ORDER BY tanggal_utc DESC, jam DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def summary(self, tanggal_utc):
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM send_log WHERE tanggal_utc=? GROUP BY status", (tanggal_utc,)).fetchall()
        out = {s: 0 for s in STATUSES}
        for r in rows:
            out[r["status"]] = r["n"]
        return out

    def events(self, tanggal_utc=None, jam=None, limit=100):
        q, args = "SELECT * FROM events WHERE 1=1", []
        if tanggal_utc:
            q += " AND tanggal_utc=?"
            args.append(tanggal_utc)
        if jam:
            q += " AND jam=?"
            args.append(jam)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]
