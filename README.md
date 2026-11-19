# synop_auto

SYNOP AUTO  -  Fase 1 selesai di kode (V7SATU)                      revisi 2026-11-15
================================================================================
ISI PAKET (semua file lengkap, siap pakai)

  V7SATU.py              BOT UTAMA (turunan V6SATU.py; semua fungsi V6 tetap ada)
  config.yaml            pengaturan (path, URL, fitur)
  .env.example           contoh kredensial -> salin jadi .env
  core/config.py         pembaca config + kredensial
  core/options.json      teks opsi dropdown persis seperti di web
  core/rules.json        aturan hasil pengukuran web
  core/validator.py      validator baris Excel
  core/db.py             log status pengiriman (SQLite)
  check_excel.py         periksa Excel tanpa menjalankan bot
  tests/                 test_validator.py (30) + test_bot_flow.py (24) + test_bot_fill.py (22) + test_popup.py (7)
  collect_web_info.py / collect_rules_matrix.py   skrip kolektor aturan web
  legacy/V6SATU.py       script lama (simpan sebagai cadangan; JANGAN dihapus)

PERSIAPAN (sekali)
  1. pip install -r requirements.txt
  2. Salin .env.example -> .env ; isi BMKG_STATION_ID dan BMKG_PASSWORD
  3. config.yaml: isi paths.excel (path INPUT_PARAMETER.xlsx) dan paths.ok_image (gambar
     tombol OK popup awal; bila tidak ada, bot mencoba klik popup lewat Selenium)
  4. Folder snapshot: config.yaml memakai nama "snapshots" (samakan dengan folder Anda)
  5. legacy/V6SATU.py juga membaca kredensial dari .env; jangan unggah file .env.

URUTAN UJI YANG DISARANKAN (jangan langsung kirim sungguhan)
  A. python tests/test_validator.py ; python tests/test_bot_flow.py ;
     python tests/test_bot_fill.py ; python tests/test_popup.py
  B. python V7SATU.py --check-only          -> validasi Excel saja, tanpa browser
  C. python V7SATU.py --dry-run --process-past --jam 08:00
                                            -> login, isi form SATU slot sampai Preview, simpan
                                               sandi, TIDAK mengirim. Periksa sandi di layar & log.
     (--process-past: baris yang waktunya sudah lewat tetap diproses sekarang. Tanpa flag ini
      baris lewat waktu DILEWATI -> itu sebabnya Excel tanggal lama tampak "skipped" semua.)
  D. python V7SATU.py                       -> kirim sungguhan (mulai dari SATU slot saja;
                                               untuk susul kirim jam lewat: --process-past --jam HH:00)

CARA JALAN
  python V7SATU.py                           launcher: pilih observer (dropdown) + opsi dry-run
  python V7SATU.py --observer "Nama" --no-gui   tanpa dialog (untuk Task Scheduler)
  python V7SATU.py --dry-run | --check-only
  python V7SATU.py --process-past            baris lewat waktu tetap diproses sekarang
  python V7SATU.py --jam 07:00[,08:00]       hanya jam UTC tertentu (baris lain diabaikan)

YANG BERUBAH DIBANDING V6SATU
  - Kredensial dari .env; path dari config.yaml; observer lewat dropdown (tidak diketik)
  - Excel divalidasi saat start & sebelum tiap baris; baris ber-ERROR dilewati + dicatat
  - Log status per slot (tanggal UTC, jam): jam yang sudah 'sent' tidak dikirim ulang
  - Tanggal web dipilih PER SLOT (UTC) -> tidak basi saat melewati pergantian hari
  - Tombol "Send & Update" dikenali bila data jam itu sudah ada di web
  - Klik popup OK: Selenium dulu, gambar (pyautogui) cadangan; ImageNotFoundException dari
    pyautogui versi baru (Python 3.13) kini ditangani, tidak lagi membuat bot crash
  - Total tutupan 0 / 9 / "/" melewati awan; total 9 mengisi vertical visibility
  - Puncak awan rendah tidak diisi bila CL=1; CL/CM/CH berkode 0 atau "/" dilewati
  - Override hujan: kolom hujan_override_aktif (ya/tidak) + hujan_override_mm

KOLOM EXCEL BARU (opsional, tambahkan di kanan)
  vertical_visibility    meter; WAJIB bila tutupan total = 9 (dan visibilitas harus < 1 km)
  hujan_override_aktif   ya / tidak
  hujan_override_mm      angka mm; hanya berlaku pada jam UTC kelipatan 3

OPSI config.yaml BARU
  runtime.retry_past_minutes   0 = slot lewat waktu dilewati; >0 = slot gagal/terhenti dicoba ulang
  features.allow_update        true = jam yang sudah ada di web boleh ditimpa (Send & Update)
  features.rain_override_strict true = batalkan baris bila override hujan gagal diterapkan

BATASAN YANG DIKETAHUI
  - Awan menengah ke-2 (Ac+As) BELUM didukung bot (validator memberi WARNING) -> tahap F3.10
  - Tombol lapisan 2 awan rendah masih memakai id tetap (775) dan hanya untuk CL 2/3/9 -> F3.10
  - Fitur V7 baru diuji dengan browser tiruan; uji di web asli (langkah B-D) belum dilakukan
================================================================================
