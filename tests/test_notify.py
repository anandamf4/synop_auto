# -*- coding: utf-8 -*-
"""
Uji F3.7 (notifikasi Telegram) tanpa internet: server Telegram PALSU di localhost.
Jalankan:  python tests/test_notify.py
Yang diuji: pesan terkirim ke chat yang benar, upload screenshot, error tidak melempar,
token tidak bocor di log, tombol jenis pesan, dry-run diam, rekap harian sekali per hari.
"""
import json
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.db import SendLog  # noqa: E402
from core.notify import Notifier  # noqa: E402

TOKEN = "123456:SECRET-TOKEN-XYZ"
CHAT = "-1001234567890"
REQS = []
MODE = {"status": 200, "ok": True}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        REQS.append({"path": self.path, "ctype": self.headers.get("Content-Type", ""), "body": body})
        out = json.dumps({"ok": MODE["ok"], "description": "Bad Request: chat not found"} if not MODE["ok"]
                         else {"ok": True, "result": {}}).encode()
        self.send_response(MODE["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}"

LOGS = []
passed = failed = 0


def check(nama, kondisi, info=""):
    global passed, failed
    print(("  OK   " if kondisi else "  GAGAL"), nama, "" if kondisi else f"-> {info}")
    passed += bool(kondisi)
    failed += (not kondisi)


def N(**opsi):
    o = {"percobaan": 1, "alarm_suara": False}
    o.update(opsi)
    return Notifier(TOKEN, CHAT, o, api_base=BASE, log=LOGS.append)


def reset(status=200, ok=True):
    REQS.clear()
    LOGS.clear()
    MODE.update(status=status, ok=ok)


def teks(r):
    from urllib.parse import parse_qs
    return parse_qs(r["body"].decode())["text"][0]


print("== pengiriman dasar ==")
reset()
n = N()
check("aktif bila token & chat_id terisi", n.aktif)
check("uji() terkirim ke endpoint sendMessage token benar",
      n.uji() and REQS[-1]["path"] == f"/bot{TOKEN}/sendMessage")
from urllib.parse import parse_qs  # noqa: E402
check("pesan masuk ke chat_id grup", parse_qs(REQS[-1]["body"].decode())["chat_id"][0] == CHAT)

reset()
n = N()
check("gagal(): pesan berisi slot & penyebab", n.gagal(("2026-11-20", "07:00"), "Gagal klik Preview", 3)
      and "2026-11-20 07:00" in teks(REQS[0]) and "Gagal klik Preview" in teks(REQS[0]))

reset()
png = Path(tempfile.mkdtemp()) / "gagal.png"
png.write_bytes(b"\x89PNG-fake-bytes")
n = N()
n.gagal(("2026-11-20", "07:00"), "x", screenshot=str(png))
check("screenshot dikirim lewat sendPhoto (multipart)",
      len(REQS) == 2 and REQS[1]["path"].endswith("/sendPhoto") and "multipart/form-data" in REQS[1]["ctype"]
      and b"PNG-fake-bytes" in REQS[1]["body"])
reset()
N(kirim_screenshot=False).gagal(("2026-11-20", "07:00"), "x", screenshot=str(png))
check("kirim_screenshot=false: hanya teks", len(REQS) == 1)

print("\n== ketahanan: notifikasi tidak boleh menggagalkan bot ==")
reset(status=400, ok=False)
n = N()
try:
    hasil = n.gagal(("2026-11-20", "07:00"), "x")
    check("Telegram menolak (400): tidak melempar, return False", hasil is False)
except Exception:
    check("Telegram menolak (400): tidak melempar, return False", False)
check("token TIDAK muncul di log", not any(TOKEN in l for l in LOGS) and any("chat not found" in l for l in LOGS))
n2 = Notifier(TOKEN, CHAT, {"percobaan": 1, "timeout_detik": 1, "alarm_suara": False},
              api_base="http://127.0.0.1:9", log=LOGS.append)
try:
    check("server tak terjangkau: tidak melempar", n2.fatal("boom") is False)
except Exception:
    check("server tak terjangkau: tidak melempar", False)
check("token tidak bocor saat koneksi gagal", not any(TOKEN in l for l in LOGS))

print("\n== pengaturan jenis pesan ==")
reset()
check("tanpa token: nonaktif & tidak mengirim", not Notifier("", "", log=LOGS.append).gagal(("a", "b"), "x")
      and not REQS)
check("placeholder .env.example dianggap nonaktif", not Notifier("isi_token_bot", "isi_chat_id").aktif)
n = N(enabled=False)
n.gagal(("a", "b"), "x")
check("enabled=false: diam", not REQS)
n = N()
n.sukses(("2026-11-20", "07:00"), "AAXX 20074 96195 ...")
check("sukses bawaan MATI (tidak ramai)", not REQS)
n = N(kirim_sukses=True)
n.sukses(("2026-11-20", "07:00"), "AAXX 20074 96195 ...")
check("kirim_sukses=true: terkirim + kode SYNOP", len(REQS) == 1 and "AAXX 20074" in teks(REQS[0]))
reset()
n = N()
n.sukses(("2026-11-20", "07:00"), "AAXX ...", {"ww": "10 -> 05 (fallback Mist->Haze)"})
check("perubahan otomatis: diberitahukan (1 pesan, memuat perubahan)",
      len(REQS) == 1 and "PERUBAHAN OTOMATIS" in teks(REQS[0]) and "fallback" in teks(REQS[0]))
reset()
N(kirim_gagal=False).gagal(("a", "b"), "x")
check("kirim_gagal=false: diam", not REQS)
reset()
N().sukses(("2026-11-20", "07:00"), "AAXX ...", {"koreksi_qc": "Submit dikonfirmasi: temp_drybulb_c Step Check"})
check("Koreksi QC dikonfirmasi: pesan khusus memuat isi peringatan",
      len(REQS) == 1 and "Koreksi QC" in teks(REQS[0]) and "Step Check" in teks(REQS[0])
      and "PERUBAHAN OTOMATIS" not in teks(REQS[0]), teks(REQS[0]) if REQS else "tidak terkirim")
reset()
N(kirim_recovery=True).recovery(("2026-11-20", "07:00"), True)
check("recovery berhasil dilaporkan", len(REQS) == 1 and "dipulihkan" in teks(REQS[0]))
reset()
N().recovery(("2026-11-20", "07:00"), False)
check("recovery GAGAL dilaporkan sebagai darurat", len(REQS) == 1 and "GAGAL" in teks(REQS[0]))
reset()
N().dilewati_validasi(("2026-11-20", "07:00"), "validasi ERROR: tinggi dasar")
check("baris dilewati karena validasi dilaporkan", len(REQS) == 1 and "TIDAK DIKIRIM" in teks(REQS[0]))
reset()
n = Notifier(TOKEN, CHAT, {"percobaan": 1, "alarm_suara": False}, api_base=BASE, dry_run=True, log=LOGS.append)
n.gagal(("a", "b"), "x")
check("dry-run: tidak mengirim notifikasi", not REQS)
reset()
n = Notifier(TOKEN, CHAT, {"percobaan": 1, "alarm_suara": False, "kirim_saat_dry_run": True}, api_base=BASE,
             dry_run=True, log=LOGS.append)
n.gagal(("a", "b"), "x")
check("dry-run + kirim_saat_dry_run=true: terkirim", len(REQS) == 1)
reset()
long = "x" * 10000
N().kirim(long, "gagal")
check("pesan sangat panjang dipotong di bawah batas Telegram", len(teks(REQS[0])) <= 4096)

print("\n== rekap harian ==")
tmp = Path(tempfile.mkdtemp()) / "t.db"
db = SendLog(tmp)
hari = "2026-11-20"
for jam in ("00:00", "01:00", "02:00", "03:00"):
    db.register(hari, jam)
db.start_attempt(hari, "00:00")
db.mark_sent(hari, "00:00", kode_synop="AAXX")
db.start_attempt(hari, "01:00")
db.mark_sent(hari, "01:00", kode_synop="AAXX", diubah_otomatis={"ww": "10->05"})
db.start_attempt(hari, "02:00")
db.mark_failed(hari, "02:00", "Gagal klik Preview")
db.mark_skipped(hari, "03:00", "waktu eksekusi sudah lewat")
t = Notifier.susun_rekap(hari, db.history(hari), "Sultan Thaha")
check("rekap: hitungan benar", "Terkirim 2 dari 4" in t and "gagal 1" in t and "dilewati 1" in t)
check("rekap: daftar jam bermasalah + perubahan otomatis",
      "02:00 failed" in t and "03:00 skipped" in t and "Perubahan otomatis: 01:00" in t)
reset()
n = N()
sebelum = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)
sesudah = datetime(2026, 11, 20, 23, 55, tzinfo=timezone.utc)
check("rekap belum waktunya (22:00 UTC < 23:50): tidak dikirim", n.rekap_jika_waktunya(db, sebelum) is False and not REQS)
n._rekap_cek_terakhir = 0
check("rekap setelah 23:50 UTC: terkirim", n.rekap_jika_waktunya(db, sesudah) is True and len(REQS) == 1)
n._rekap_cek_terakhir = 0
check("rekap tidak terkirim dua kali di hari yang sama", n.rekap_jika_waktunya(db, sesudah) is False and len(REQS) == 1)
n3 = N()
check("rekap tidak terkirim ulang meski bot dimulai ulang (penanda di DB)",
      n3.rekap_jika_waktunya(db, sesudah) is False and len(REQS) == 1)
# rekap yang gagal terkirim tidak boleh diberi penanda -> dicoba lagi pada panggilan berikutnya
hari2 = "2026-11-21"
db.register(hari2, "00:00")
t2 = datetime(2026, 11, 21, 23, 55, tzinfo=timezone.utc)
reset()
mati = Notifier(TOKEN, CHAT, {"percobaan": 1, "timeout_detik": 1, "alarm_suara": False},
                api_base="http://127.0.0.1:9", log=LOGS.append)
check("rekap gagal kirim: return False", mati.rekap_jika_waktunya(db, t2, paksa=True) is False)
check("rekap gagal kirim: TIDAK diberi penanda 'rekap_terkirim'",
      not any(e["event"] == "rekap_terkirim" for e in db.events(hari2, "--")))
hidup = N()
check("rekap dicoba lagi saat Telegram pulih: terkirim", hidup.rekap_jika_waktunya(db, t2, paksa=True) is True
      and len(REQS) == 1)
db.close()

print(f"\nTotal: {passed} lulus, {failed} gagal")
srv.shutdown()
sys.exit(1 if failed else 0)
