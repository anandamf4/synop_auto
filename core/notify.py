# -*- coding: utf-8 -*-
"""
core/notify.py  -  F3.7: notifikasi Telegram (+ alarm suara lokal untuk gagal total)

Prinsip:
  * NOTIFIKASI TIDAK BOLEH MENGGAGALKAN PENGIRIMAN SYNOP: semua error jaringan/Telegram
    ditangkap dan hanya dicetak; method publik tidak pernah melempar exception.
  * Hanya pustaka standar (urllib); tidak menambah dependensi.
  * Token & chat_id dari .env (JANGAN masuk config.yaml / GitHub):
        TELEGRAM_BOT_TOKEN=123456:ABC...
        TELEGRAM_CHAT_ID=-1001234567890
  * Pengaturan jenis pesan di config.yaml bagian `notify:`.

Jenis pesan (K4 + permintaan pengguna 2026-11-20):
    gagal     : pengiriman gagal (+ screenshot), baris dilewati karena validasi ERROR
    recovery  : pemulihan sesi browser berhasil/gagal
    diubah    : terkirim tetapi ada perubahan otomatis (mis. ww 10 -> 05)
    sukses    : tiap jam terkirim (+ kode SYNOP)  [bawaan MATI agar grup tidak ramai]
    rekap     : ringkasan harian (sekali per hari UTC)
    fatal     : skrip berhenti karena error tak tertangani

CLI:
    python core/notify.py --cari-chat-id     # tampilkan chat_id grup yang dikenal bot
    python core/notify.py --test             # kirim pesan uji ke grup
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.telegram.org"
MAX_LEN = 3900            # batas Telegram 4096; sisakan ruang
DEFAULTS = {
    "enabled": True,
    "kirim_gagal": True,
    "kirim_recovery": True,
    "kirim_diubah": True,
    "kirim_sukses": False,
    "kirim_rekap": True,
    "kirim_screenshot": True,
    "kirim_saat_dry_run": False,
    "alarm_suara": True,
    "rekap_jam_utc": "23:50",     # rekap hari UTC berjalan dikirim sekali setelah jam ini
    "timeout_detik": 10,
    "percobaan": 2,
    "nama_stasiun": "Sultan Thaha (96195)",
}


def _potong(t, n=MAX_LEN):
    t = str(t)
    return t if len(t) <= n else t[: n - 20] + "\n...(dipotong)"


class Notifier:
    def __init__(self, token="", chat_id="", opsi=None, api_base=API_BASE, dry_run=False, log=print):
        self.opsi = dict(DEFAULTS)
        self.opsi.update(opsi or {})
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.api_base = api_base.rstrip("/")
        self.dry_run = dry_run
        self.log = log
        self._rekap_cek_terakhir = 0.0
        self.terkirim = 0
        self.gagal_kirim = 0

    # ------------------------------------------------------------------ fabrik
    @classmethod
    def from_config(cls, cfg, dry_run=False, **kw):
        opsi = (cfg or {}).get("notify", {}) or {}
        return cls(os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""),
                   opsi, dry_run=dry_run, **kw)

    @property
    def aktif(self):
        placeholder = {"", "isi_token_bot", "isi_chat_id"}
        return bool(self.opsi.get("enabled") and self.token not in placeholder
                    and self.chat_id not in placeholder)

    def _boleh(self, jenis):
        if not self.aktif:
            return False
        if self.dry_run and not self.opsi.get("kirim_saat_dry_run"):
            return False
        return bool(self.opsi.get(f"kirim_{jenis}", True))

    # --------------------------------------------------------------- transport
    def _post(self, metode, fields, file_field=None):
        """POST ke API Telegram. file_field = (nama_field, path). Return (ok, info)."""
        url = f"{self.api_base}/bot{self.token}/{metode}"
        if file_field:
            boundary = "----synop" + uuid.uuid4().hex
            parts = []
            for k, v in fields.items():
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
            nama, path = file_field
            with open(path, "rb") as f:
                data = f.read()
            parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{nama}\"; "
                          f"filename=\"{Path(path).name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode("utf-8"))
            parts.append(data)
            parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
            body = b"".join(parts)
            headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        else:
            body = urllib.parse.urlencode(fields).encode("utf-8")
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.opsi.get("timeout_detik", 10)) as r:
            js = json.loads(r.read().decode("utf-8", "replace") or "{}")
        return bool(js.get("ok")), js

    def _coba(self, metode, fields, file_field=None):
        """Kirim dengan percobaan ulang; TIDAK PERNAH melempar. Token tidak ikut dicetak."""
        n = max(1, int(self.opsi.get("percobaan", 2)))
        err = ""
        for i in range(1, n + 1):
            try:
                ok, js = self._post(metode, fields, file_field)
                if ok:
                    self.terkirim += 1
                    return True
                err = str(js.get("description", js))[:200]
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode("utf-8", "replace")).get("description", str(e.code))
                except Exception:
                    err = f"HTTP {e.code}"
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            err = err.replace(self.token, "***") if self.token else err
            if i < n:
                time.sleep(1.5)
        self.gagal_kirim += 1
        self.log(f"⚠️ Telegram gagal terkirim ({metode}): {err}")
        return False

    # ------------------------------------------------------------- API publik
    def kirim(self, teks, jenis="info", foto=None):
        """Kirim teks (+ foto bila ada). Return True/False; aman dipanggil kapan saja."""
        try:
            if jenis != "info" and not self._boleh(jenis):
                return False
            if jenis == "info" and not self.aktif:
                return False
            ok = self._coba("sendMessage", {"chat_id": self.chat_id, "text": _potong(teks),
                                             "disable_web_page_preview": "true"})
            if ok and foto and self.opsi.get("kirim_screenshot") and Path(str(foto)).is_file():
                self._coba("sendPhoto", {"chat_id": self.chat_id, "caption": "screenshot kegagalan"},
                           file_field=("photo", str(foto)))
            return ok
        except Exception as e:     # lapis terakhir
            self.log(f"⚠️ Notifikasi error (diabaikan): {type(e).__name__}: {e}")
            return False

    def alarm(self):
        """Bunyi lokal (Windows) untuk gagal total; diam-diam dilewati di OS lain."""
        if not self.opsi.get("alarm_suara") or self.dry_run:
            return
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1500, 400)
                time.sleep(0.15)
        except Exception:
            pass

    # ---------------------------------------------------------------- pesan
    def _stn(self):
        return self.opsi.get("nama_stasiun", "")

    def gagal(self, slot, pesan, percobaan=None, screenshot=None, alarm=True):
        t = [f"❌ SYNOP GAGAL (semua percobaan ulang otomatis habis) — {self._stn()}",
             f"Slot: {slot[0]} {slot[1]} UTC"]
        if percobaan:
            t.append(f"Percobaan: {percobaan}")
        t.append(f"Penyebab: {pesan}")
        t.append("Tindakan: kirim manual lewat BMKG Satu SEKARANG bila belum (data ada di form dashboard). "
                 "Bot masih akan mencoba lagi pada putaran berikutnya selama masih dalam jendela retry.")
        ok = self.kirim("\n".join(t), "gagal", foto=screenshot)
        if alarm:
            self.alarm()
        return ok

    def perlu_cek_manual(self, slot, pesan, screenshot=None):
        """[rev 30] Galat terjadi SETELAH tombol kirim akhir diklik: data kemungkinan sudah terkirim. Bot tidak mengirim ulang."""
        t = [f"⚠️ SYNOP PERLU DICEK MANUAL — {self._stn()}",
             f"Slot: {slot[0]} {slot[1]} UTC",
             "Bot sudah menekan tombol kirim akhir, tetapi konfirmasinya tidak lengkap: data KEMUNGKINAN SUDAH TERKIRIM.",
             "Bot TIDAK mengirim ulang (mencegah kiriman ganda).",
             f"Rincian: {str(pesan)[:220]}",
             "Tindakan: cek jam itu di BMKG Satu. Sudah ada -> tandai 'terkirim manual' di dashboard. "
             "Belum ada -> 'atur ulang' di dashboard lalu jalankan ulang jam itu."]
        ok = self.kirim("\n".join(t), "gagal", foto=screenshot)
        self.alarm()
        return ok

    def dilewati_validasi(self, slot, alasan):
        return self.kirim(f"⛔ SYNOP TIDAK DIKIRIM (validasi) — {self._stn()}\n"
                          f"Slot: {slot[0]} {slot[1]} UTC\n{alasan}\n"
                          "Perbaiki Excel lalu jalankan ulang jam itu (--process-past --jam HH:00).",
                          "gagal")

    def recovery(self, slot, berhasil, percobaan=None):
        if berhasil:
            return self.kirim(f"🔄 Sesi browser dipulihkan — slot {slot[0]} {slot[1]} UTC dilanjutkan.", "recovery")
        self.alarm()
        return self.kirim(f"🚨 Pemulihan sesi browser GAGAL — slot {slot[0]} {slot[1]} UTC dilewati. "
                          "Periksa komputer/bot sekarang.", "recovery")

    def sukses(self, slot, kode_synop=None, diubah=None):
        """Dua jalur: ringkas (jenis 'sukses') dan pemberitahuan perubahan otomatis (jenis 'diubah')."""
        hasil = False
        if diubah and "koreksi_qc" in diubah:
            t = (f"⚠️ Koreksi QC dikonfirmasi — {self._stn()}\n"
                 f"Slot: {slot[0]} {slot[1]} UTC\n{diubah['koreksi_qc']}")
            lainnya = {k: v for k, v in diubah.items() if k != "koreksi_qc"}
            if lainnya:
                t += "\nPerubahan otomatis: " + "; ".join(f"{k}: {v}" for k, v in lainnya.items())
            if kode_synop:
                t += f"\n\n{kode_synop}"
            hasil = self.kirim(t, "diubah")
        elif diubah:
            d = "; ".join(f"{k}: {v}" for k, v in diubah.items())
            t = (f"ℹ️ SYNOP terkirim DENGAN PERUBAHAN OTOMATIS — {self._stn()}\n"
                 f"Slot: {slot[0]} {slot[1]} UTC\n{d}")
            if kode_synop:
                t += f"\n\n{kode_synop}"
            hasil = self.kirim(t, "diubah")
        if not diubah or not self._boleh("diubah"):
            t = f"✅ SYNOP terkirim — {slot[0]} {slot[1]} UTC"
            if kode_synop:
                t += f"\n{kode_synop}"
            hasil = self.kirim(t, "sukses") or hasil
        return hasil

    def fatal(self, err):
        self.alarm()
        return self.kirim(f"🚨 SKRIP SYNOP BERHENTI — {self._stn()}\n{err}\nJalankan ulang bot.", "gagal")

    def uji(self):
        return self.kirim(f"🔔 Uji notifikasi SYNOP — {self._stn()}\nWaktu: "
                          f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", "info")

    # ---------------------------------------------------------------- rekap
    @staticmethod
    def susun_rekap(tanggal_utc, baris, nama=""):
        """baris = db.history(tanggal) (daftar dict). Mengembalikan teks rekap."""
        hitung = {}
        for r in baris:
            hitung[r["status"]] = hitung.get(r["status"], 0) + 1
        n = len(baris)
        ikon = "✅" if n and hitung.get("sent", 0) == n else "📋"
        t = [f"{ikon} REKAP SYNOP {tanggal_utc} (UTC) — {nama}",
             f"Terkirim {hitung.get('sent', 0)} dari {n} slot | gagal {hitung.get('failed', 0)} | "
             f"dilewati {hitung.get('skipped', 0)} | menunggu {hitung.get('pending', 0) + hitung.get('running', 0)}"]
        buruk = sorted((r for r in baris if r["status"] in ("failed", "skipped", "pending", "running")),
                       key=lambda r: r["jam"])
        if buruk:
            t.append("Perlu perhatian:")
            for r in buruk[:24]:
                t.append(f"• {r['jam']} {r['status']}: {(r.get('pesan') or '-')[:90]}")
        ubah = [r for r in baris if r.get("diubah_otomatis")]
        if ubah:
            t.append("Perubahan otomatis: " + ", ".join(r["jam"] for r in sorted(ubah, key=lambda r: r["jam"])))
        if not buruk:
            t.append("Semua slot tercatat terkirim." if n else "Tidak ada slot tercatat.")
        return "\n".join(t)

    def rekap_jika_waktunya(self, db, sekarang_utc=None, paksa=False):
        """
        Kirim rekap hari UTC berjalan SEKALI, setelah jam `rekap_jam_utc`. Aman dipanggil
        sering (dibatasi 1x/menit). Penanda 'rekap_terkirim' disimpan di tabel events,
        jadi tidak terkirim ulang meski bot dimulai ulang.
        """
        try:
            if not self._boleh("rekap"):
                return False
            now = sekarang_utc or datetime.now(timezone.utc)
            if not paksa:
                if time.time() - self._rekap_cek_terakhir < 60:
                    return False
                self._rekap_cek_terakhir = time.time()
                hh, mm = (int(x) for x in str(self.opsi["rekap_jam_utc"]).split(":"))
                if (now.hour, now.minute) < (hh, mm):
                    return False
            tgl = now.strftime("%Y-%m-%d")
            if any(e.get("event") == "rekap_terkirim" for e in db.events(tgl, "--", limit=20)):
                return False
            baris = db.history(tgl, limit=100)
            ok = self.kirim(self.susun_rekap(tgl, baris, self._stn()), "rekap")
            if ok:
                db.log_event(tgl, "--", "rekap_terkirim", f"{len(baris)} slot")
            return ok
        except Exception as e:
            self.log(f"⚠️ Rekap harian error (diabaikan): {type(e).__name__}: {e}")
            return False


# ======================================================================= CLI
def _cli():
    import argparse
    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    from core.config import load_config
    ap = argparse.ArgumentParser(description="Bantu setup Telegram")
    ap.add_argument("--cari-chat-id", action="store_true", help="tampilkan chat_id yang dikenal bot")
    ap.add_argument("--test", action="store_true", help="kirim pesan uji ke TELEGRAM_CHAT_ID")
    a = ap.parse_args()
    cfg = load_config()
    n = Notifier.from_config(cfg)
    if not n.token or n.token == "isi_token_bot":
        print("TELEGRAM_BOT_TOKEN belum diisi di .env")
        return 1
    if a.cari_chat_id:
        try:
            with urllib.request.urlopen(f"{n.api_base}/bot{n.token}/getUpdates", timeout=15) as r:
                js = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("Gagal menghubungi Telegram:", str(e).replace(n.token, "***"))
            return 1
        seen = {}
        for u in js.get("result", []):
            for k in ("message", "channel_post", "my_chat_member", "edited_message"):
                c = (u.get(k) or {}).get("chat")
                if c:
                    seen[c["id"]] = f"{c.get('type')} | {c.get('title') or c.get('username') or c.get('first_name')}"
        if not seen:
            print("Belum ada chat. Tambahkan bot ke grup, kirim satu pesan di grup (mis. /start@namabot), "
                  "lalu jalankan lagi.")
        for cid, ket in seen.items():
            print(f"chat_id = {cid}   ({ket})")
        return 0
    if a.test:
        if not n.chat_id or n.chat_id == "isi_chat_id":
            print("TELEGRAM_CHAT_ID belum diisi di .env")
            return 1
        ok = n.uji()
        print("Terkirim" if ok else "GAGAL (lihat pesan di atas)")
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
