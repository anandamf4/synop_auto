# -*- coding: utf-8 -*-
"""Terapkan rev 37. Jalankan dari folder proyek:  python terapkan_rev37.py
Memperbaiki: (1) bot sumber DB gagal 'awan_rendah_2_jenis'; (2) tombol --process-past di Pantau Web.
Aman dijalankan ulang (yang sudah terpasang dilewati). Tahan CRLF."""
from pathlib import Path

EDITS = [
 [
  "core/obsdb.py",
  "        df = pd.DataFrame(rows)\n        urut = [c for c in URUTAN_KOLOM if c in df.columns] + [c for c in df.columns if c not in URUTAN_KOLOM]\n        df = df[urut]\n        df[\"waktu_eksekusi\"] = pd.to_datetime(df[\"waktu_eksekusi\"])",
  "        df = pd.DataFrame(rows)\n        # DB hanya menyimpan kolom yang terisi; bot mengakses row['awan_rendah_2_jenis'] dst. -> kolom yang tak ada HARUS ada (NaN),\n        # persis seperti Excel. Tanpa ini: KeyError 'awan_rendah_2_jenis' -> \"Gagal isi data\" di setiap percobaan (rev 37).\n        urut = URUTAN_KOLOM + [c for c in df.columns if c not in URUTAN_KOLOM]\n        df = df.reindex(columns=urut)\n        df[\"waktu_eksekusi\"] = pd.to_datetime(df[\"waktu_eksekusi\"])"
 ],
 [
  "panel.py",
  "\nREV = \"rev 36\"\nPORT_PANEL = 8765",
  "\nREV = \"rev 37\"\nPORT_PANEL = 8765"
 ],
 [
  "panel.py",
  "            args = [\"--mode\", mode, \"--jam\", jam, \"--no-gui\"] + ([\"--observer\", obs] if obs else []) + ([\"--izinkan-kirim\"] if mode == \"kirim\" else [])\n            cmd = perintah(\"pantau\", args)",
  "            args = [\"--mode\", mode, \"--jam\", jam, \"--no-gui\"] + ([\"--observer\", obs] if obs else []) + ([\"--izinkan-kirim\"] if mode == \"kirim\" else [])\n            if mode != \"jelajah\":\n                # [rev 37] argumen setelah '--' diteruskan ke bot: --jam membatasi jam yang diproses, --process-past = proses jam yang sudah lewat\n                args += [\"--\", \"--jam\", jam] + ([\"--process-past\"] if opsi.get(\"lampau\") else [])\n            cmd = perintah(\"pantau\", args)"
 ],
 [
  "panel/index.html",
  " b.innerHTML=`<div class=\"g2\"><div class=\"cd\"><h2>Jalankan pemantauan</h2><div class=\"col\" style=\"gap:10px\">\n <div><span class=\"lbl\">Mode</span><select id=\"pm\" onchange=\"$('pz').style.display=this.value=='kirim'?'flex':'none'\"><option value=\"dryrun\">Dry-run (tanpa kirim)</option><option value=\"jelajah\">Jelajah (hanya buka & potret form)</option><option value=\"kirim\">Kirim nyata</option></select></div>\n <label class=\"ck\" id=\"pz\" style=\"display:none;color:var(--er)\"><input type=\"checkbox\" id=\"pi\"> Saya izinkan pengiriman SUNGGUHAN</label>",
  " b.innerHTML=`<div class=\"g2\"><div class=\"cd\"><h2>Jalankan pemantauan</h2><div class=\"col\" style=\"gap:10px\">\n <div><span class=\"lbl\">Mode</span><select id=\"pm\" onchange=\"$('pz').style.display=this.value=='kirim'?'flex':'none';$('pl2').style.display=this.value=='jelajah'?'none':'flex'\"><option value=\"dryrun\">Dry-run (tanpa kirim)</option><option value=\"jelajah\">Jelajah (hanya buka & potret form)</option><option value=\"kirim\">Kirim nyata</option></select></div>\n <label class=\"ck\" id=\"pz\" style=\"display:none;color:var(--er)\"><input type=\"checkbox\" id=\"pi\"> Saya izinkan pengiriman SUNGGUHAN</label>"
 ],
 [
  "panel/index.html",
  " <div><span class=\"lbl\">Jam (UTC)</span><input type=\"text\" id=\"pj\" value=\"00:00\"></div><div><span class=\"lbl\">Observer</span>${observerSel('obsp')}</div>\n <div style=\"display:flex;gap:8px\"><button class=\"bt\" onclick=\"aksi('pantau','mulai',{mode:$('pm').value,jam:$('pj').value,observer:$('obsp').value,izin:$('pi').checked})\">Mulai pemantauan</button><button class=\"bt dg\" onclick=\"aksi('pantau','henti')\">Hentikan</button></div>\n <div id=\"ps\"></div></div></div><div class=\"cd\"><h2>Hasil terakhir</h2><div id=\"ph\" class=\"mu\">Memuat…</div></div></div><div class=\"cd\"><h2>Log pemantauan</h2><pre class=\"log\" id=\"pl\" style=\"max-height:30vh\"></pre></div>`}",
  " <div><span class=\"lbl\">Jam (UTC)</span><input type=\"text\" id=\"pj\" value=\"00:00\"></div><div><span class=\"lbl\">Observer</span>${observerSel('obsp')}</div>\n <label class=\"ck\" id=\"pl2\"><input type=\"checkbox\" id=\"plp\"> Proses juga jam yang sudah lewat (--process-past)</label>\n <div style=\"display:flex;gap:8px\"><button class=\"bt\" onclick=\"aksi('pantau','mulai',{mode:$('pm').value,jam:$('pj').value,observer:$('obsp').value,izin:$('pi').checked,lampau:$('plp').checked})\">Mulai pemantauan</button><button class=\"bt dg\" onclick=\"aksi('pantau','henti')\">Hentikan</button></div>\n <div id=\"ps\"></div></div></div><div class=\"cd\"><h2>Hasil terakhir</h2><div id=\"ph\" class=\"mu\">Memuat…</div></div></div><div class=\"cd\"><h2>Log pemantauan</h2><pre class=\"log\" id=\"pl\" style=\"max-height:30vh\"></pre></div>`}"
 ],
 [
  "tests/test_panel.py",
  "post(\"/api/proses\", {\"nama\": \"pantau\", \"aksi\": \"henti\"})\ncheck(\"komponen tak dikenal ditolak\", post(\"/api/proses\", {\"nama\": \"rm\", \"aksi\": \"mulai\"}).status_code == 400)",
  "post(\"/api/proses\", {\"nama\": \"pantau\", \"aksi\": \"henti\"})\nr = post(\"/api/proses\", {\"nama\": \"pantau\", \"aksi\": \"mulai\", \"opsi\": {\"mode\": \"dryrun\", \"observer\": \"B\", \"jam\": \"00:00\", \"lampau\": True}})\n_a = dipanggil[\"args\"]\ncheck(\"[rev 37] pantau + lampau: '-- --jam 00:00 --process-past' diteruskan ke bot\", r.status_code == 200 and _a[_a.index(\"--\") + 1:] == [\"--jam\", \"00:00\", \"--process-past\"], _a)\npost(\"/api/proses\", {\"nama\": \"pantau\", \"aksi\": \"henti\"})\nr = post(\"/api/proses\", {\"nama\": \"pantau\", \"aksi\": \"mulai\", \"opsi\": {\"mode\": \"dryrun\", \"observer\": \"B\", \"jam\": \"00:00\"}})\ncheck(\"[rev 37] pantau tanpa centang lampau: --process-past TIDAK ikut\", \"--process-past\" not in dipanggil[\"args\"], dipanggil[\"args\"])\npost(\"/api/proses\", {\"nama\": \"pantau\", \"aksi\": \"henti\"})\ncheck(\"komponen tak dikenal ditolak\", post(\"/api/proses\", {\"nama\": \"rm\", \"aksi\": \"mulai\"}).status_code == 400)"
 ]
]
NEWFILES = {"tests/test_db_kolom.py": "# -*- coding: utf-8 -*-\n\"\"\"Regresi rev 37:  python tests/test_db_kolom.py\nBot sumber DB gagal 'awan_rendah_2_jenis' (KeyError) karena DataFrame DB hanya memuat kolom yang tersimpan.\nUji ini memakai jalur ASLI: ObsStore.upsert -> to_dataframe -> V7SATU.isi_data (tanpa browser).\"\"\"\nimport importlib.util, re, sys, tempfile, types\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parent.parent\nsys.path.insert(0, str(ROOT))\nsys.modules.setdefault(\"pyautogui\", types.ModuleType(\"pyautogui\"))\nimport pandas as pd  # noqa: E402\nfrom core.obsdb import ObsStore, URUTAN_KOLOM  # noqa: E402\nfrom core.validator import Validator  # noqa: E402\n\nspec = importlib.util.spec_from_file_location(\"V7SATU_db\", ROOT / \"V7SATU.py\")\nM = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)\npassed = failed = 0\n\n\ndef check(name, cond, info=\"\"):\n    global passed, failed\n    print((\"  OK   \" if cond else \"  GAGAL\"), name, \"\" if cond else f\"-> {info}\")\n    passed += bool(cond); failed += (not cond)\n\n\n# data persis seperti kasus nyata: lapisan 1 saja, lapisan 2 TIDAK diisi (tak tersimpan di DB)\nDATA = {\"visibility\": 10, \"ww\": \"02 - state of sky unchanged\", \"w1\": \"2 - Cloudy +\", \"w2\": \"2 - Cloudy +\",\n        \"cloud_cover_oktas_m\": \"6 oktas\", \"cloud_low_type_cl\": \"5 - stratocumulus yang tidak terjadi dari bentangan cumulus\",\n        \"cloud_low_cover_oktas\": \"2 oktas\", \"awan_rendah_jenis\": \"6 - stratocumulus (Sc)\", \"awan_rendah_jumlah\": \"2 oktas\",\n        \"cloud_low_base_1\": 420, \"cloud_arah_awan_rendah\": \"0 - Stationary or No Clouds\"}\n\nprint(\"== DataFrame DB memuat semua kolom yang diakses bot ==\")\nwith tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:\n    st = ObsStore(str(Path(d) / \"t.db\"))\n    st.upsert(\"2026-11-25\", \"00:00\", DATA, \"uji\")\n    df = st.to_dataframe(\"2026-11-25\", \"2026-11-25\")\n    row = df.iloc[0]\n    check(\"kolom lapisan 2 ada & bernilai NaN (bukan KeyError)\", \"awan_rendah_2_jenis\" in df.columns and pd.isna(row[\"awan_rendah_2_jenis\"]))\n    kunci = set(re.findall(r\"row\\[\\s*['\\\"]([A-Za-z0-9_]+)['\\\"]\\s*\\]\", (ROOT / \"V7SATU.py\").read_text(encoding=\"utf-8\")))\n    hilang = sorted(kunci - set(df.columns))\n    check(\"SEMUA kolom row['...'] di V7SATU.py ada di DataFrame DB\", not hilang, hilang)\n    check(\"DB kosong tetap bisa dibuat DataFrame-nya\", st.to_dataframe(\"2030-01-01\", \"2030-01-02\").empty)\n\n    print(\"== isi_data dengan baris dari DB (tanpa lapisan 2) ==\")\n    calls = []\n    M.pilih_dropdown_ant_select = lambda drv, i, v, **k: (calls.append((\"select\", i, v)) or True)\n    M.isi_input_text = lambda drv, i, v, timeout=12: (calls.append((\"input\", i, v)) or True)\n    for n in (\"isi_jenis_dan_jumlah_awan_Rendah\", \"pilih_arah_Awan_Rendah\", \"pilih_arah_sebenarnya\", \"klik_switch_jika_type\",\n              \"isi_jenis_dan_jumlah_awan_rendah_2\", \"pilih_arah_2\", \"pilih_arah_sebenarnya_2\", \"isi_jenis_dan_jumlah_awan_menengah\",\n              \"pilih_arah_Awan_Menengah\", \"isi_jenis_dan_jumlah_awan_Tinggi\", \"pilih_arah_Awan_Tinggi\"):\n        setattr(M, n, lambda *a, **k: True)\n    M.isi_hujan_override = lambda drv, mm: True\n    M._switch_aktif = lambda drv, i: False\n    M._atur_switch = lambda drv, i, a: True\n    V = Validator.from_files(ROOT / \"core/options.json\", ROOT / \"core/rules.json\")\n    meta = st.to_row(\"2026-11-25\", \"00:00\")\n    rr = V.validate_row(meta, 2)\n    ok = M.isi_data(object(), row, plan=rr.plan)\n    check(\"isi_data(baris DB) berhasil, tidak 'Gagal mengisi data'\", ok is True, (ok, rr.errors if hasattr(rr, \"errors\") else \"\"))\n\nprint(f\"\\nHasil: {passed} lulus, {failed} gagal\")\nsys.exit(1 if failed else 0)\n"}

CAT = """  [2026-11-26] Rev 37 - BUG bot sumber DB: 'Gagal mengisi data: awan_rendah_2_jenis' di semua percobaan (dry-run & kirim nyata). AKAR: ObsStore.to_dataframe hanya
               memuat kolom yang tersimpan di DB; V7SATU mengakses row['awan_rendah_2_jenis'] dst. -> KeyError (Excel tak kena karena kolomnya selalu ada).
               Perbaikan: to_dataframe di-reindex ke URUTAN_KOLOM (kolom hilang = NaN). Tes baru tests/test_db_kolom.py (jalur asli DB -> isi_data; menjaga semua
               row['...'] di V7SATU ada di DataFrame). Pantau Web: checkbox 'Proses juga jam yang sudah lewat' -> '-- --jam HH:MM --process-past' ke bot (sebelumnya
               --jam & --process-past tidak diteruskan). Panel REV=37. Catatan: tests/test_obsdb.py 4 GAGAL sudah ada sebelumnya (membandingkan dengan isi Excel lama).
               Berikutnya: build_exe.bat ulang, uji dry-run --process-past jam 00:00, lalu kirim nyata.
"""


def baca(p):
    b = p.read_bytes().decode("utf-8")
    return b.replace("\r\n", "\n"), ("\r\n" if "\r\n" in b else "\n")


def tulis(p, s, nl):
    p.write_bytes(s.replace("\n", nl).encode("utf-8"))


gagal = 0
for berkas in dict.fromkeys(e[0] for e in EDITS):
    p = Path(berkas)
    if not p.exists():
        print("TIDAK ADA ", berkas); gagal += 1; continue
    s, nl = baca(p)
    for b, lama, baru in (e for e in EDITS if e[0] == berkas):
        if baru in s:
            print("sudah      ", berkas)
        elif lama in s:
            s = s.replace(lama, baru, 1); print("DIPASANG   ", berkas)
        else:
            print("GAGAL      ", berkas, "- teks asli tidak ditemukan:", lama.split("\n")[1][:60] if "\n" in lama else lama[:60]); gagal += 1
    tulis(p, s, nl)
for berkas, isi in NEWFILES.items():
    Path(berkas).write_bytes(isi.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")); print("DITULIS    ", berkas)
H = Path("docs/SYNOP_UPGRADE_HANDOFF.txt")
if H.exists():
    s, nl = baca(H)
    if "Rev 37" in s:
        print("sudah       handoff")
    else:
        k = s.rfind("\n################################################################################\n#  AKHIR FILE")
        s = (s[:k].rstrip("\n") + "\n" + CAT + s[k:]) if k >= 0 else (s.rstrip("\n") + "\n" + CAT)
        tulis(H, s, nl); print("DIPASANG    handoff")
print("\nSELESAI" if not gagal else "\n%d bagian GAGAL - kirim keluaran ini ke saya" % gagal)
