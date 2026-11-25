# -*- coding: utf-8 -*-
"""
Rev 36 / F4.3 - panel kontrol desktop: pengelola proses, API panel (keamanan lokal, validasi, pengaturan, rahasia, remote),
dispatch synop_app (jalur yang sama dipakai di .exe), dan sintaks JavaScript antarmuka.
Tanpa browser/jaringan:   python tests/test_panel.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

passed = failed = 0


def check(name, cond, info=""):
    global passed, failed
    print(("  OK   " if cond else "  GAGAL"), name, "" if cond else f"-> {info}")
    passed += bool(cond)
    failed += (not cond)


TMP = Path(tempfile.mkdtemp(prefix="synop_panel_"))
(TMP / "data").mkdir()
import core.config as C        # noqa: E402
import core.status as S        # noqa: E402
import panel as P              # noqa: E402
import core.proses as PR       # noqa: E402
for m in (C, P, PR):
    m.ROOT = TMP               # semua berkas tulis diarahkan ke folder uji
S.BERKAS = TMP / "data" / "status_bot.json"
PY = sys.executable

print("== Pengelola proses ==")
G = PR.Pengelola(TMP)
ok, _ = G.mulai("web", [PY, "-c", "import time;print('halo dari anak',flush=True);time.sleep(60)"])
time.sleep(1.0)
check("proses dimulai & dikenali hidup", ok and G.jalan("web") and G.sejak("web"))
check("mulai kedua ditolak (tidak ganda)", G.mulai("web", [PY, "-c", "pass"])[0] is False)
check("keluaran masuk logs/web.log", any("halo dari anak" in x for x in G.ekor("web")), G.ekor("web"))
G2 = PR.Pengelola(TMP)
check("panel yang dibuka ulang mengenali proses yang masih hidup (berkas PID)", G2.jalan("web"))
ok, _ = G2.henti("web")
check("henti -> mati & berkas PID hilang", ok and not G.jalan("web") and not (TMP / "logs" / "web.pid").exists())
check("henti saat sudah mati -> aman", G.henti("web")[0] is True)
(TMP / "logs" / "bot.log").write_bytes("baris A\n\u23f3 Akan dieksekusi dalam: 12:34\rAkan dieksekusi dalam: 12:33\nbaris B\n".encode("utf-8"))
check("log disaring dari hitung-mundur", G.ekor("bot") == ["baris A", "baris B"], G.ekor("bot"))
check("hitung_mundur terbaca", G.hitung_mundur("bot") == (12, 33), G.hitung_mundur("bot"))
check("perintah mode skrip memakai synop_app.py --jalankan", PR.perintah("bot", ["--dry-run"])[-3:] == ["--jalankan", "bot", "--dry-run"])

print("== API panel ==")
dipanggil = {}
P.perintah = lambda nama, args=(): (dipanggil.update(nama=nama, args=list(map(str, args))) or [PY, "-c", "import time;time.sleep(30)"])
pn = P.Panel(TMP)
app = P.buat_app(pn)
c = app.test_client()
H = {"X-Panel": "1", "Host": "127.0.0.1:8765"}
check("GET / menyajikan antarmuka", b"SYNOP Otomatis" in c.get("/", headers={"Host": "127.0.0.1:8765"}).data)
check("host asing ditolak (DNS-rebinding)", c.get("/api/ping", headers={"Host": "evil.example.com"}).status_code == 403)
check("POST tanpa header X-Panel ditolak (CSRF)", c.post("/api/proses", json={"nama": "web", "aksi": "henti"}, headers={"Host": "127.0.0.1:8765"}).status_code == 403)
r = c.get("/api/ringkas", headers=H).get_json()
check("ringkas memuat proses, jadwal, observer, rev", set(r["proses"]) == {"web", "bot", "remote", "pantau"} and r["rev"] == P.REV and "observers" in r, list(r))
cek = c.get("/api/cek", headers=H).get_json()["baris"]
nama = [x["nama"] for x in cek]
check("cek sistem memuat Telegram, Sesi, Struktur web (selector), cloudflared", all(n in nama for n in ("Telegram", "Sesi BMKG Satu", "Struktur web (selector)", "cloudflared", "WEB_PIN")), nama)
S.tulis("selector", tahap="form", hilang=["input-jam"])
sel = [x for x in c.get("/api/cek", headers=H).get_json()["baris"] if x["nama"].startswith("Struktur")][0]
check("selector hilang dari bot -> baris 'Periksa' di panel", sel["status"] == "wt" and "input-jam" in sel["detail"], sel)

def post(u, b):
    return c.post(u, json=b, headers=H)

r = post("/api/proses", {"nama": "bot", "aksi": "mulai", "opsi": {"dry_run": True}})
check("bot tanpa observer ditolak", r.status_code == 400 and "observer" in r.get_json()["pesan"].lower())
r = post("/api/proses", {"nama": "bot", "aksi": "mulai", "opsi": {"dry_run": True, "observer": "Budi"}})
check("bot tanpa kredensial ditolak", r.status_code == 400 and "Kredensial" in r.get_json()["pesan"], r.get_json())
(TMP / ".env").write_text('BMKG_STATION_ID="id1"\nBMKG_PASSWORD="pw rahasia #1"\n', encoding="utf-8")
r = post("/api/proses", {"nama": "bot", "aksi": "mulai", "opsi": {"observer": "Budi"}})
check("kirim nyata tanpa konfirmasi ditolak", r.status_code == 400 and "konfirmasi" in r.get_json()["pesan"].lower(), r.get_json())
r = post("/api/proses", {"nama": "bot", "aksi": "mulai", "opsi": {"dry_run": True, "observer": "Budi", "jam": "07:00,08:00", "lampau": True}})
check("dry-run dimulai dengan argumen benar", r.status_code == 200 and dipanggil["args"] == ["--observer", "Budi", "--no-gui", "--dry-run", "--process-past", "--jam", "07:00,08:00"], (r.get_json(), dipanggil))
check("status bot: jalan", c.get("/api/ringkas", headers=H).get_json()["proses"]["bot"]["jalan"] is True)
post("/api/proses", {"nama": "bot", "aksi": "henti"})
check("hentikan bot", not pn.proc.jalan("bot"))
r = post("/api/proses", {"nama": "bot", "aksi": "mulai", "opsi": {"dry_run": True, "observer": "B", "jam": "7;rm -rf"}})
check("format jam salah ditolak sebelum proses dibuat", r.status_code == 400 and not pn.proc.jalan("bot"), r.get_json())
r = post("/api/proses", {"nama": "pantau", "aksi": "mulai", "opsi": {"mode": "kirim", "observer": "B"}})
check("pantau 'kirim' terkunci tanpa izin", r.status_code == 400 and "izin" in r.get_json()["pesan"].lower())
r = post("/api/proses", {"nama": "pantau", "aksi": "mulai", "opsi": {"mode": "dryrun", "observer": "B", "jam": "00:00"}})
check("pantau dry-run dimulai", r.status_code == 200 and "--mode" in dipanggil["args"] and "--izinkan-kirim" not in dipanggil["args"], dipanggil)
post("/api/proses", {"nama": "pantau", "aksi": "henti"})
check("komponen tak dikenal ditolak", post("/api/proses", {"nama": "rm", "aksi": "mulai"}).status_code == 400)

print("== Akses remote ==")
r = post("/api/proses", {"nama": "remote", "aksi": "mulai"})
check("remote ditolak bila WEB_PIN kosong", r.status_code == 400 and "WEB_PIN" in r.get_json()["pesan"], r.get_json())
(TMP / "logs" / "remote.log").write_text("INF +----+\nINF https://abc-def-ghi.trycloudflare.com\n", encoding="utf-8")
pn.proc.mulai("remote", [PY, "-c", "import time;time.sleep(30)"])
(TMP / "logs" / "remote.log").write_text("INF https://abc-def-ghi.trycloudflare.com\n", encoding="utf-8")
check("URL tunnel dibaca dari log", c.get("/api/remote", headers=H).get_json()["url"] == "https://abc-def-ghi.trycloudflare.com")
pn.proc.henti("remote")
check("tanpa proses remote -> URL kosong", c.get("/api/remote", headers=H).get_json()["url"] is None)

print("== Pengaturan & rahasia ==")
r = post("/api/pengaturan", {"perubahan": {"speed.fast_input": True, "health.cek_detik": 120, "notify.rekap_jam_utc": "22:30"}})
cfg = C.load_config(muat_env=False)
check("pengaturan tersimpan di config.panel.yaml & menimpa config", r.status_code == 200 and cfg["speed"]["fast_input"] is True and cfg["health"]["cek_detik"] == 120
      and cfg["notify"]["rekap_jam_utc"] == "22:30" and (TMP / "config.panel.yaml").exists(), r.get_json())
check("pengaturan lain tetap bawaan (merge)", cfg["session"]["aktif"] is True)
check("kunci di luar daftar putih ditolak", post("/api/pengaturan", {"perubahan": {"paths.db": "x"}}).status_code == 400)
check("tipe/batas salah ditolak", post("/api/pengaturan", {"perubahan": {"health.cek_detik": 5}}).status_code == 400
      and post("/api/pengaturan", {"perubahan": {"speed.fast_input": "ya"}}).status_code == 400
      and post("/api/pengaturan", {"perubahan": {"notify.rekap_jam_utc": "25:99"}}).status_code == 400)
r = post("/api/rahasia", {"kunci": "WEB_PIN", "nilai": "pin 'aneh' #9"})
from dotenv import dotenv_values  # noqa: E402
check("rahasia tersimpan di .env (karakter khusus aman) & kunci lain utuh",
      r.status_code == 200 and dotenv_values(TMP / ".env")["WEB_PIN"] == "pin 'aneh' #9" and dotenv_values(TMP / ".env")["BMKG_PASSWORD"] == "pw rahasia #1")
resp = c.get("/api/pengaturan", headers=H).data.decode("utf-8")
check("password/PIN/token TIDAK pernah dikembalikan API", "pw rahasia" not in resp and "aneh" not in resp)
check("kunci rahasia tak dikenal ditolak", post("/api/rahasia", {"kunci": "PATH", "nilai": "x"}).status_code == 400
      and post("/api/rahasia", {"kunci": "WEB_PIN", "nilai": "a\nb"}).status_code == 400)
check("load_config(muat_env=False) tidak mengotori environment panel", "WEB_PIN" not in os.environ)

print("== Pantau (hasil terakhir) ==")
run = TMP / "pantau_out" / "20261125_100000_dryrun"
run.mkdir(parents=True)
(run / "laporan.json").write_text(json.dumps({"mode": "dryrun", "kejadian": [{"nama": "isi_data", "arg": "", "durasi": 45.5}, {"nama": "pilih_ant_select", "arg": "CL", "durasi": 3.2}]}), encoding="utf-8")
(run / "laporan.txt").write_text("LAPORAN", encoding="utf-8")
(run / "log_konsol.txt").write_text("Verifikasi sandi: sesuai data\n", encoding="utf-8")
h = c.get("/api/pantau/hasil", headers=H).get_json()["hasil"]
check("hasil pantau terakhir terbaca (isi_data, sandi, langkah lambat)", h["isi_data"] == 45.5 and "sesuai" in h["sandi"] and h["lambat"][0]["nama"].startswith("isi_data"), h)
check("laporan dapat dibuka", c.get("/api/pantau/laporan", headers=H).data == b"LAPORAN")

print("== synop_app (jalur sama dengan .exe) ==")
env = dict(os.environ, PYTHONIOENCODING="utf-8")
r = subprocess.run([PY, str(ROOT / "synop_app.py"), "--jalankan", "telegram"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, cwd=str(TMP))
check("--jalankan telegram menjalankan core/notify.py (CLI-nya menjawab)", "TELEGRAM_BOT_TOKEN" in r.stdout + r.stderr or "--cari-chat-id" in r.stdout, (r.stdout + r.stderr)[-200:])
r = subprocess.run([PY, str(ROOT / "synop_app.py"), "--jalankan", "xyz"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
check("komponen tak dikenal -> galat jelas", r.returncode != 0 and "tidak dikenal" in r.stderr)

print("== Pemasangan pertama (.exe) ==")
import core.paths as CP  # noqa: E402
sumber, tujuan = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
(sumber / "config.yaml").write_text("station: {name: X}\n", encoding="utf-8")
(sumber / ".env.example").write_text("WEB_PIN=\n", encoding="utf-8")
(tujuan / "config.yaml").write_text("punya_pengguna: true\n", encoding="utf-8")
asli = (CP.BUNDLE, CP.ROOT)
CP.BUNDLE, CP.ROOT = sumber, tujuan
CP.siapkan()
CP.BUNDLE, CP.ROOT = asli
check("siapkan(): berkas bawaan disalin bila belum ada, TIDAK menimpa milik pengguna, folder kerja dibuat",
      (tujuan / ".env.example").exists() and (tujuan / "config.yaml").read_text(encoding="utf-8") == "punya_pengguna: true\n"
      and all((tujuan / d).is_dir() for d in ("data", "snapshots", "logs")))

print("== Antarmuka ==")
html = (ROOT / "panel" / "index.html").read_text(encoding="utf-8")
js = html[html.index("<script>") + 8:html.index("</script>")]
check("menu sketsa lengkap (Beranda, Bot Pengirim, Pantau Web, Akses Remote, Log, Pengaturan)", all(t in js for t in ("Beranda", "Bot Pengirim", "Pantau Web", "Akses Remote", "'Log'", "Pengaturan")))
check("mode malam & token warna ada", "body.dk" in html and "--ok:" in html)
import shutil  # noqa: E402
if shutil.which("node"):
    (TMP / "p.js").write_text(js, encoding="utf-8")
    check("sintaks JavaScript valid", subprocess.run(["node", "--check", str(TMP / "p.js")], capture_output=True).returncode == 0)

for nama_ in ("web", "bot", "remote", "pantau"):
    pn.proc.henti(nama_)
print(f"\nHasil: {passed} lulus, {failed} gagal")
sys.exit(1 if failed else 0)
