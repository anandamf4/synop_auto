# -*- coding: utf-8 -*-
"""
app.py  -  F2: form pengamatan + dashboard (web lokal untuk jaringan stasiun)

Menjalankan:
    pip install flask
    python app.py                  # http://localhost:8080  (juga bisa dari PC lain: http://IP-PC:8080)
    python app.py --port 8081 --host 127.0.0.1

Alur: pengamat membuka dashboard -> pilih jam -> mengisi form. Setiap perubahan dikirim ke
/api/validasi; SERVER (validator.py + formschema.py yang sama dengan bot) menjawab field mana yang
aktif/wajib/pilihannya dan temuan ERROR/WARNING. Simpan ditolak bila masih ada ERROR, sehingga
data yang tersimpan tidak akan ditolak validator bot. Data disimpan di tabel `observasi`
(core/obsdb.py). Bot membaca data dari DB bila features.data_source = "db" (F2.7).

Keamanan: untuk jaringan lokal. Isi WEB_PIN di .env agar halaman meminta PIN (opsional).
"""
import argparse
import datetime as dt
import hmac
import io
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote

from flask import (Flask, Response, abort, jsonify, make_response, redirect, render_template, request,
                   send_file, url_for)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core.config import load_config, resolve_path  # noqa: E402
from core.db import SendLog  # noqa: E402
from core.formschema import build_schema, field_state, SEMUA_KOLOM  # noqa: E402
from core.obsdb import ObsStore, normalisasi, URUTAN_KOLOM  # noqa: E402
from core.validator import Validator, COLUMN_FIELD  # noqa: E402

ERR, WRN, INF = "ERROR", "WARNING", "INFO"


def create_app(cfg=None, db_path=None):
    cfg = cfg or load_config()
    app = Flask(__name__, template_folder=str(ROOT / "web"), static_folder=str(ROOT / "web" / "static"))
    app.config["JSON_AS_ASCII"] = False
    V = Validator.from_config(cfg, ROOT)
    path_db = db_path or resolve_path(cfg, "db")
    OBS = ObsStore(path_db, tz_hours=V.tz, menit_sebelum=int((cfg.get("web", {}) or {}).get("menit_sebelum", 2)))
    LOG = SendLog(path_db)
    SKEMA = build_schema(V)
    PIN = os.environ.get("WEB_PIN", "").strip()
    nama_stasiun = (cfg.get("notify", {}) or {}).get("nama_stasiun", "Stasiun")

    # ------------------------------------------------------------------ util
    def observer_cookie():
        """Nama observer yang diingat browser. Nilai cookie dikodekan-persen oleh JavaScript (spasi -> %20), jadi harus
        di-decode; tanpa itu nama berspasi tak pernah cocok dengan opsi dropdown sehingga selalu tampil '— pilih —'."""
        return unquote(request.cookies.get("observer", "") or "").strip()

    def nama_pengubah(body_observer, tanggal=None, jam=None):
        """[rev 28] Observer OPSIONAL. Urutan: isian formulir -> cookie browser -> pengubah sebelumnya pada jam itu -> kosong."""
        oleh = (body_observer or "").strip() or observer_cookie()
        if not oleh and tanggal and jam:
            oleh = ((OBS.info(tanggal, jam) or {}).get("diubah_oleh") or "").strip()
        return oleh

    def daftar_observer():
        boleh = (cfg.get("observers", {}) or {}).get("allowed") or []
        obs = [o["name"] for o in json.load(open(ROOT / "core" / "options.json", encoding="utf-8")).get("observer", [])
               if o.get("active", True)]
        return [o for o in obs if not boleh or o in boleh]

    def parse_slot(tanggal, jam):
        try:
            dt.datetime.strptime(f"{tanggal} {jam}", "%Y-%m-%d %H:%M")
        except ValueError:
            abort(400, "format tanggal/jam salah (YYYY-MM-DD, HH:00)")
        if not jam.endswith(":00"):
            abort(400, "jam harus HH:00")
        return tanggal, jam

    YA = {"1", "true", "ya", "yes", "y", "v"}
    TIDAK = {"0", "false", "tidak", "no", "n", ""}

    def kanonik(data):
        """Samakan nilai dengan teks opsi di form. Excel biasanya menyimpan kode saja (mis. 5, '00', 'ya'),
        sedangkan dropdown form berisi teks lengkap ('5 oktas', '00 - clear sky'); tanpa penyamaan,
        dropdown tampil KOSONG walau datanya ada. Nilai yang tak dikenali dibiarkan apa adanya."""
        out = {}
        for k, v in (data or {}).items():
            if k in COLUMN_FIELD and v is not None and str(v).strip() != "":
                try:
                    m = V.resolve(k, v)
                except Exception:
                    m = None
                out[k] = m.text if (m is not None and m.ok and m.text) else v
            elif k in ("hujan_override_aktif", "radiasi_kosongkan") and not isinstance(v, bool) and v is not None:
                t = str(v).strip().lower()
                out[k] = True if t in YA else (False if t in TIDAK else v)
            else:
                out[k] = v
        return out

    OBS.kanonik = kanonik

    def hasil_validasi(tanggal, jam, data):
        d = normalisasi(data)
        jam_h = int(jam[:2])
        row = OBS.to_row(tanggal, jam, d)
        rr = V.validate_row(row, 0)
        temuan = [{"level": i.level, "rule": i.rule, "kolom": i.column, "pesan": i.message}
                  for i in rr.issues if i.level in (ERR, WRN, INF)]
        # jaring pengaman: kolom yang field_state anggap nonaktif tidak boleh ikut tersimpan
        return d, rr, temuan, field_state(V, d, jam_h)

    def level_slot(tanggal, jam, data):
        if data is None:
            return "kosong"
        _, rr, temuan, _ = hasil_validasi(tanggal, jam, data)
        if any(t["level"] == ERR for t in temuan):
            return "merah"
        return "kuning" if any(t["level"] == WRN for t in temuan) else "hijau"

    # --------------------------------------------------------------- PIN login
    @app.before_request
    def cek_pin():
        if not PIN or request.endpoint in ("login", "static"):
            return None
        if request.cookies.get("pin_ok") == hmac.new(PIN.encode(), b"synop", "sha256").hexdigest():
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "PIN diperlukan"}), 401
        return redirect(url_for("login", next=request.path))

    def catat(tanggal, jam, event, detail):
        """[F4.2] Jejak audit perubahan data lewat web (siapa & apa); tidak boleh menggagalkan aksi utama."""
        try:
            LOG.log_event(tanggal, jam, event, str(detail)[:500])
        except Exception:
            pass

    def ringkas_diff(lama, baru, maks=6):
        lama, baru = lama or {}, baru or {}
        out = []
        for k in sorted(set(lama) | set(baru)):
            a_, b_ = lama.get(k), baru.get(k)
            if str(a_) != str(b_):
                out.append(f"{k}: {'-' if a_ is None else str(a_)[:18]} -> {'-' if b_ is None else str(b_)[:18]}")
        if not out:
            return "tanpa perubahan isi"
        return "; ".join(out[:maks]) + (f"; +{len(out) - maks} kolom lain" if len(out) > maks else "")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if hmac.compare_digest(request.form.get("pin", ""), PIN):
                r = make_response(redirect(request.args.get("next") or "/"))
                r.set_cookie("pin_ok", hmac.new(PIN.encode(), b"synop", "sha256").hexdigest(), max_age=86400 * 30,
                             httponly=True, samesite="Lax")
                return r
            return render_template("login.html", salah=True), 401
        return render_template("login.html", salah=False)

    # ------------------------------------------------------------- halaman
    @app.route("/")
    def dashboard():
        tgl = request.args.get("tanggal") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        return render_template("dashboard.html", tanggal=tgl, stasiun=nama_stasiun, observers=daftar_observer(),
                               observer=observer_cookie())

    @app.route("/form/<tanggal>/<jam>")
    def form(tanggal, jam):
        parse_slot(tanggal, jam)
        return render_template("form.html", tanggal=tanggal, jam=jam, stasiun=nama_stasiun,
                               observers=daftar_observer(), observer=observer_cookie(),
                               prev=OBS.slot_sebelumnya(tanggal, jam))

    # ----------------------------------------------------------------- API
    @app.route("/api/skema")
    def api_skema():
        return jsonify(SKEMA)

    @app.route("/api/slot/<tanggal>/<jam>")
    def api_slot(tanggal, jam):
        parse_slot(tanggal, jam)
        data = OBS.get(tanggal, jam)
        if data is not None:
            data = kanonik(data)              # data lama/impor Excel -> teks opsi form (dropdown terisi)
        d, rr, temuan, S = hasil_validasi(tanggal, jam, data or {})
        s = LOG.get(tanggal, jam)
        return jsonify({"ada": data is not None, "data": data or {}, "state": S, "temuan": temuan if data else [],
                        "info": OBS.info(tanggal, jam), "status_kirim": s["status"] if s else None})

    @app.route("/api/validasi", methods=["POST"])
    def api_validasi():
        b = request.get_json(force=True, silent=True) or {}
        tanggal, jam = parse_slot(b.get("tanggal", ""), b.get("jam", ""))
        d, rr, temuan, S = hasil_validasi(tanggal, jam, b.get("data") or {})
        return jsonify({"state": S, "temuan": temuan, "ok": not any(t["level"] == ERR for t in temuan)})

    @app.route("/api/simpan", methods=["POST"])
    def api_simpan():
        b = request.get_json(force=True, silent=True) or {}
        tanggal, jam = parse_slot(b.get("tanggal", ""), b.get("jam", ""))
        oleh = nama_pengubah(b.get("observer"), tanggal, jam)     # [rev 28] opsional; tidak lagi menolak simpan
        d, rr, temuan, S = hasil_validasi(tanggal, jam, b.get("data") or {})
        # kolom nonaktif menurut aturan tidak ikut disimpan (web mengabaikannya)
        d = {k: v for k, v in d.items() if k not in S or S[k]["aktif"]}
        d, rr, temuan, S = hasil_validasi(tanggal, jam, d)
        galat = [t for t in temuan if t["level"] == ERR]
        if galat:
            return jsonify({"ok": False, "pesan": f"{len(galat)} kesalahan harus diperbaiki dulu", "temuan": temuan}), 422
        s = LOG.get(tanggal, jam)
        if s and s["status"] == "sent" and not b.get("paksa"):
            return jsonify({"ok": False, "perlu_konfirmasi": True,
                            "pesan": "jam ini SUDAH terkirim ke BMKG Satu. Perubahan hanya tersimpan di sini dan "
                                     "tidak dikirim ulang otomatis. Tetap simpan?"}), 409
        sebelum = OBS.get(tanggal, jam)
        OBS.upsert(tanggal, jam, d, oleh or None)
        catat(tanggal, jam, "form_simpan", f"{oleh or 'tanpa nama'}: " + ("data baru" if sebelum is None else ringkas_diff(kanonik(sebelum), kanonik(d)))
              + (" [jam sudah terkirim; tidak dikirim ulang]" if s and s["status"] == "sent" else ""))
        return jsonify({"ok": True, "pesan": "tersimpan", "temuan": temuan})

    @app.route("/api/salin")
    def api_salin():
        tanggal, jam = parse_slot(request.args.get("tanggal", ""), request.args.get("jam", ""))
        data = OBS.sebelumnya(tanggal, jam)
        if data is None:
            return jsonify({"ada": False}), 404
        data = kanonik(data)
        for k in ("hujan_override_aktif", "hujan_override_mm", "penguapan_mm", "penguapan_ie", "radiasi_kosongkan",
                  "radiasi_matahari", "lama_penyinaran_jam"):     # override hujan & penguapan tidak ikut disalin
            data.pop(k, None)
        return jsonify({"ada": True, "data": data, "dari": OBS.slot_sebelumnya(tanggal, jam)})

    @app.route("/api/salin_rentang", methods=["POST"])
    def api_salin_rentang():
        """Salin data satu tanggal ke tanggal lain untuk rentang jam (UTC) atau seharian.
        pratinjau=true -> hanya menghitung, tidak menulis. Slot yang sudah TERKIRIM tidak pernah disentuh."""
        b = request.get_json(force=True, silent=True) or {}
        dari, ke = b.get("dari_tanggal", ""), b.get("ke_tanggal", "")
        parse_slot(dari, "00:00")
        parse_slot(ke, "00:00")
        if dari == ke:
            return jsonify({"ok": False, "pesan": "tanggal sumber dan tujuan tidak boleh sama"}), 400
        try:
            j1, j2 = (0, 23) if b.get("seharian") else (int(b.get("jam_dari")), int(b.get("jam_sampai")))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "pesan": "rentang jam tidak valid"}), 400
        if not (0 <= j1 <= j2 <= 23):
            return jsonify({"ok": False, "pesan": "rentang jam tidak valid (00-23, awal <= akhir)"}), 400
        mode = b.get("mode", "lewati")
        if mode not in ("lewati", "timpa"):
            return jsonify({"ok": False, "pesan": "mode harus 'lewati' atau 'timpa'"}), 400
        pratinjau = bool(b.get("pratinjau"))
        oleh = nama_pengubah(b.get("observer"))                   # [rev 28] opsional
        sekarang = dt.datetime.now(dt.timezone.utc)
        hasil = {"disalin": [], "lewati_terisi": [], "lewati_terkirim": [], "tanpa_sumber": [], "ditolak": []}
        for h in range(j1, j2 + 1):
            jam = f"{h:02d}:00"
            src = OBS.get(dari, jam)
            if src is None:
                hasil["tanpa_sumber"].append(jam)
                continue
            st = LOG.get(ke, jam)
            if st and st["status"] == "sent":
                hasil["lewati_terkirim"].append(jam)
                continue
            ada = OBS.get(ke, jam) is not None
            if ada and mode == "lewati":
                hasil["lewati_terisi"].append(jam)
                continue
            d = kanonik(src)
            for k in ("hujan_override_aktif", "hujan_override_mm", "penguapan_mm", "penguapan_ie", "radiasi_kosongkan",
                  "radiasi_matahari", "lama_penyinaran_jam"):     # override hujan & penguapan tidak ikut disalin
                d.pop(k, None)
            d, rr, temuan, S = hasil_validasi(ke, jam, d)
            d = {k: v for k, v in d.items() if k not in S or S[k]["aktif"]}
            d, rr, temuan, S = hasil_validasi(ke, jam, d)
            galat = [t["pesan"] for t in temuan if t["level"] == ERR]
            if galat:
                hasil["ditolak"].append({"jam": jam, "alasan": galat[:2]})
                continue
            if not pratinjau:
                OBS.upsert(ke, jam, d, oleh or None)
                catat(ke, jam, "form_salin", f"{oleh or 'tanpa nama'}: disalin dari {dari} {jam}" + (" (menimpa data lama)" if ada else ""))
            waktu = dt.datetime.strptime(f"{ke} {jam}", "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
            hasil["disalin"].append({"jam": jam, "menimpa": ada, "sudah_lewat": waktu <= sekarang})
        return jsonify({"ok": True, "pratinjau": pratinjau, **hasil})

    @app.route("/api/hapus", methods=["POST"])
    def api_hapus():
        b = request.get_json(force=True, silent=True) or {}
        tanggal, jam = parse_slot(b.get("tanggal", ""), b.get("jam", ""))
        s = LOG.get(tanggal, jam)
        if s and s["status"] == "sent":
            return jsonify({"ok": False, "pesan": "jam yang sudah terkirim tidak dapat dihapus"}), 409
        OBS.delete(tanggal, jam)
        catat(tanggal, jam, "form_hapus", f"{observer_cookie() or 'tanpa nama'}: data jam ini dihapus")
        return jsonify({"ok": True})

    @app.route("/api/atur_ulang", methods=["POST"])
    def api_atur_ulang():
        """Selesaikan slot yang tertahan ('berjalan' macet / gagal / dilewati). aksi: 'ulang' (bot boleh coba lagi)
        atau 'terkirim' (pengguna SUDAH memastikan datanya ada di web BMKG Satu). Slot terkirim tidak disentuh."""
        b = request.get_json(force=True, silent=True) or {}
        tanggal, jam = parse_slot(b.get("tanggal", ""), b.get("jam", ""))
        aksi = b.get("aksi", "ulang")
        s = LOG.get(tanggal, jam)
        if s is None:
            return jsonify({"ok": False, "pesan": "slot ini belum punya status pengiriman"}), 404
        if s["status"] == "sent":
            return jsonify({"ok": False, "pesan": "slot sudah terkirim; tidak ada yang perlu diatur ulang"}), 409
        if aksi == "terkirim":
            LOG.tandai_terkirim_manual(tanggal, jam)
            return jsonify({"ok": True, "pesan": "ditandai sudah terkirim"})
        if aksi != "ulang":
            return jsonify({"ok": False, "pesan": "aksi tidak dikenal"}), 400
        lama = LOG.atur_ulang(tanggal, jam)
        if lama is None:
            return jsonify({"ok": False, "pesan": "status sudah 'menunggu'"}), 409
        return jsonify({"ok": True, "pesan": f"status diatur ulang ke menunggu (sebelumnya: {lama})"})

    def macet(waktu_mulai, batas_menit=15):
        """'running' lebih dari batas_menit dianggap macet (satu slot normalnya selesai dalam hitungan menit)."""
        try:
            return (dt.datetime.now() - dt.datetime.fromisoformat(waktu_mulai)).total_seconds() > batas_menit * 60
        except (TypeError, ValueError):
            return True      # tanpa waktu mulai yang sah -> anggap macet agar tombol atur ulang muncul

    @app.route("/api/status")
    def api_status():
        tanggal = request.args.get("tanggal") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        ada = OBS.list_day(tanggal)
        riwayat = {r["jam"]: r for r in LOG.history(tanggal, limit=100)}
        sekarang = dt.datetime.now(dt.timezone.utc)
        baris = []
        for h in range(24):
            jam = f"{h:02d}:00"
            o, s = ada.get(jam), riwayat.get(jam)
            waktu = dt.datetime.strptime(f"{tanggal} {jam}", "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
            baris.append({"jam": jam, "level": level_slot(tanggal, jam, o["data"] if o else None),
                          "oleh": o["oleh"] if o else None, "diubah": o["updated_at"] if o else None,
                          "kirim": s["status"] if s else None, "pesan": (s.get("pesan") if s else None),
                          "sandi": (s.get("kode_synop") if s else None),
                          "diubah_otomatis": (s.get("diubah_otomatis") if s else None),
                          "mulai": (s.get("waktu_mulai") if s else None), "percobaan": (s.get("percobaan") if s else 0),
                          "macet": bool(s and s["status"] == "running" and macet(s.get("waktu_mulai"))),
                          "sudah_lewat": waktu <= sekarang, "sekarang": waktu <= sekarang < waktu + dt.timedelta(hours=1)})
        ringkas = {"terkirim": sum(1 for x in baris if x["kirim"] == "sent"),
                   "gagal": sum(1 for x in baris if x["kirim"] == "failed"),
                   "dilewati": sum(1 for x in baris if x["kirim"] == "skipped"),
                   "terisi": sum(1 for x in baris if x["level"] != "kosong"),
                   "perlu_perhatian": sum(1 for x in baris if x["level"] == "merah" or x["kirim"] in ("failed",)),
                   "berjalan": sum(1 for x in baris if x["kirim"] == "running")}
        return jsonify({"tanggal": tanggal, "baris": baris, "ringkas": ringkas,
                        "waktu_server_utc": sekarang.strftime("%Y-%m-%d %H:%M:%S")})

    # ------------------------------------------------------- Excel (F2.6)
    @app.route("/ekspor/<tanggal>.xlsx")
    def ekspor(tanggal):
        import pandas as pd
        parse_slot(tanggal, "00:00")
        df = OBS.to_dataframe(tanggal, tanggal)
        for c in URUTAN_KOLOM:
            if c not in df.columns:
                df[c] = None
        df = df[URUTAN_KOLOM]
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"INPUT_PARAMETER_{tanggal}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.route("/api/impor", methods=["POST"])
    def api_impor():
        import pandas as pd
        f = request.files.get("berkas")
        oleh = (request.form.get("observer") or "").strip() or "import Excel"
        if not f:
            return jsonify({"ok": False, "pesan": "berkas belum dipilih"}), 400
        try:
            df = pd.read_excel(f)
            df.columns = [str(c).strip() for c in df.columns]
            df = df[df["waktu_eksekusi"].notna()]
        except Exception as e:
            return jsonify({"ok": False, "pesan": f"gagal membaca Excel: {e}"}), 400
        fi, hasil = V.validate_dataframe(df)
        masuk, ditolak = 0, []
        for rr, (_, r) in zip(hasil, df.iterrows()):
            if rr.errors:
                ditolak.append({"baris": rr.row_no, "slot": list(rr.slot), "kesalahan": [str(i) for i in rr.errors][:3]})
                continue
            n, _ = OBS.import_dataframe(df.loc[[r.name]], tz_hours=V.tz, oleh=oleh)
            masuk += n
            if n:
                catat(rr.slot[0], rr.slot[1], "impor_excel", f"{oleh}: dari baris Excel {rr.row_no}")
        return jsonify({"ok": True, "masuk": masuk, "ditolak": ditolak})

    # ------------------------------------------------------ [F4.2] riwayat & audit
    def filter_riwayat():
        a = request.args
        def tgl(k):
            v = (a.get(k) or "").strip()
            if not v:
                return None
            parse_slot(v, "00:00")
            return v
        jam = (a.get("jam") or "").strip() or None
        if jam:
            parse_slot("2000-01-01", jam)
        return dict(dari=tgl("dari"), sampai=tgl("sampai"), jam=jam, event=(a.get("event") or "").strip() or None,
                    q=(a.get("q") or "").strip() or None)

    @app.route("/riwayat")
    def riwayat():
        hari = dt.datetime.now(dt.timezone.utc).date()
        return render_template("riwayat.html", stasiun=nama_stasiun, tanggal=hari.isoformat(),
                               dari=request.args.get("dari") or (hari - dt.timedelta(days=7)).isoformat(),
                               sampai=request.args.get("sampai") or hari.isoformat(),
                               jam=request.args.get("jam", ""), event=request.args.get("event", ""), q=request.args.get("q", ""))

    @app.route("/api/riwayat")
    def api_riwayat():
        f = filter_riwayat()
        try:
            limit = int(request.args.get("limit", 300))
        except ValueError:
            limit = 300
        baris, total = LOG.cari_events(limit=limit, **f)
        return jsonify({"total": total, "baris": baris, "jenis": LOG.daftar_event()})

    @app.route("/ekspor_riwayat.xlsx")
    def ekspor_riwayat():
        import pandas as pd
        baris, _ = LOG.cari_events(limit=50000, **filter_riwayat())
        df = pd.DataFrame(baris, columns=["id", "ts", "tanggal_utc", "jam", "event", "detail"]).rename(
            columns={"ts": "waktu_server", "tanggal_utc": "tanggal_slot_utc", "jam": "jam_slot_utc", "event": "kejadian"})
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="riwayat")
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="riwayat_synop.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    app.obs, app.log, app.validator = OBS, LOG, V
    return app


if __name__ == "__main__":
    cfg = load_config()
    w = cfg.get("web", {}) or {}
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=w.get("host", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(w.get("port", 8080)))
    a = ap.parse_args()
    app = create_app(cfg)
    print(f"🌐 Form & dashboard: http://localhost:{a.port}  (dari PC lain: http://<IP-PC-ini>:{a.port})")
    if not os.environ.get("WEB_PIN"):
        print("ℹ️ WEB_PIN belum diisi di .env: halaman terbuka untuk siapa pun di jaringan ini")
    app.run(host=a.host, port=a.port, threaded=True)
