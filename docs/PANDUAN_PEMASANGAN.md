# SYNOP Otomatis — Panduan Pemasangan & Penyesuaian

Aplikasi desktop lokal untuk mengisi dan mengirim data SYNOP ke BMKG Satu secara otomatis. Satu jendela mengendalikan:
**web form & dashboard**, **bot pengirim**, **pantau web**, dan **akses remote** (opsional), ditambah cek sistem, log, dan pengaturan.

> **Keselamatan data:** mulailah SELALU dengan **Dry-run** (mengisi sampai Preview, tidak mengirim). Kirim nyata hanya setelah hasil dry-run Anda periksa.

---

## 1. Yang dibutuhkan

| Kebutuhan | Keterangan |
|---|---|
| Windows 10/11 64-bit | PC stasiun yang menyala saat jam kirim |
| Google Chrome | Terpasang normal (bot memakai Chrome; chromedriver diunduh otomatis saat pertama jalan, **perlu internet**) |
| WebView2 Runtime | Sudah ada di Windows 11 dan Windows 10 yang terbarui. Bila jendela putih/kosong, pasang dari *Microsoft Edge WebView2* (gratis). Tanpa ini panel otomatis dibuka di browser. |
| Folder yang bisa ditulis | Mis. `C:\SYNOP\`. **Jangan** di `Program Files` (aplikasi menulis `.env`, `data\`, `logs\`) |
| Akun BMKG Satu stasiun | ID stasiun & password |
| (Opsional) Telegram | Token bot + chat id grup |
| (Opsional) cloudflared | Hanya untuk akses dari HP di luar jaringan stasiun |

Python **hanya** dibutuhkan untuk *membangun* `.exe` (langkah 2A) atau menjalankan dari kode (2B). PC stasiun yang memakai `.exe` jadi tidak perlu Python.

---

## 2. Dapatkan aplikasinya

### A. Bangun `.exe` (sekali, di PC mana pun yang punya Python 3.11/3.12)
1. Pasang Python 3.12 dari python.org — centang **Add python.exe to PATH**.
2. Buka folder proyek, klik dua kali **`build_exe.bat`** (5–10 menit; perlu internet).
3. Hasil: folder **`dist\SynopOtomatis\`** berisi `SynopOtomatis.exe` (panel) dan `SynopWorker.exe` (pekerja bot/web, jangan dihapus).
4. Salin **seluruh folder** itu ke PC stasiun, mis. `C:\SYNOP\SynopOtomatis\`.

### B. Atau jalankan dari kode (tanpa `.exe`)
```
pip install -r requirements.txt
python synop_app.py
```

---

## 3. Pertama kali dijalankan

1. Klik dua kali **`SynopOtomatis.exe`**.
   - Windows SmartScreen mungkin memperingatkan *"Windows protected your PC"* karena aplikasi tidak bertanda tangan digital: klik **More info → Run anyway**.
   - Firewall menanyakan izin: pilih **Private networks** (diperlukan agar form bisa dibuka dari PC lain di jaringan stasiun).
   - Antivirus kadang salah menandai aplikasi hasil PyInstaller; masukkan folder `SynopOtomatis` ke daftar pengecualian bila terjadi.
2. Aplikasi membuat `config.yaml`, `.env.example`, `data\`, `snapshots\`, `logs\` di samping `.exe`.
3. Buka menu **Pengaturan → Kredensial & rahasia**, isi dan **Simpan** satu per satu:
   - **ID stasiun BMKG Satu** dan **Password BMKG Satu** (wajib untuk bot)
   - **PIN halaman web** (wajib bila akan memakai akses remote; sebaiknya panjang dan acak)
   - **Token bot Telegram** dan **Chat ID Telegram** (opsional; chat id dapat dicari dengan menjalankan `SynopWorker.exe --jalankan telegram --cari-chat-id`)
4. Kembali ke **Beranda → Cek sistem**, klik **Cek ulang**. Baris yang masih kuning/abu: baca keterangannya (Chrome, kredensial, PIN, cloudflared, Telegram).
5. Klik **Kirim pesan uji** di baris Telegram — pesan harus masuk ke grup.

## 4. Pemakaian harian

1. **Beranda → Web form & dashboard → Mulai**, lalu **Buka**. Observer mengisi data tiap jam di form (juga bisa dari HP di jaringan stasiun).
2. **Bot Pengirim**: pilih **Observer**, lalu
   - **Dry-run** dulu (uji tanpa kirim), lihat log dan hasilnya;
   - setelah yakin, **Mulai (kirim nyata)**. Bot menunggu jam, mulai mengisi 2 menit sebelumnya, lalu — bila gerbang persetujuan aktif — menampilkan jendela hitung-mundur dengan tombol **Batalkan** / **Kirim sekarang**.
3. **Menutup panel TIDAK menghentikan bot.** Buka lagi `SynopOtomatis.exe` → status bot tampil kembali. Untuk menghentikan: tombol **Hentikan**.
4. **Sesi BMKG Satu habis?** Tidak perlu tindakan: bot mendeteksi popup/halaman login, klik OK, lalu mengisi ulang ID & password stasiun sendiri.
5. **Pantau Web**: mode *Dry-run* / *Jelajah* / *Kirim nyata* (terkunci sampai kotak izin dicentang). Hasil terakhir (waktu isi form, langkah paling lambat, sandi) tampil di kartu; **Buka laporan** / **Kemas .zip** untuk dikirim ke pengembang.
6. **Log**: keluaran bot/web/remote/pantau. Di Beranda, baris **Struktur web (selector)** memberi tahu bila tampilan BMKG Satu berubah.

## 5. Akses dari HP (opsional)
1. Pasang cloudflared sekali: buka *Command Prompt* → `winget install --id Cloudflare.cloudflared -e` (atau taruh `cloudflared.exe` di folder yang sama dengan `SynopOtomatis.exe`).
2. Pastikan **WEB_PIN** terisi (Pengaturan). Tanpa PIN, tombol Aktifkan ditolak.
3. **Akses Remote → Aktifkan akses remote** → tunggu link `https://....trycloudflare.com` → **Salin link** atau **QR layar penuh** → buka di HP, masukkan PIN.
4. Link berganti tiap diaktifkan. Pengaman utama = PIN. Panel ini sendiri **tidak** ikut terbuka lewat tunnel.

---

## 6. Penyesuaian saat pemasangan

| Situasi | Yang diubah |
|---|---|
| **Port 8080 bentrok** | Pengaturan → *Port web form* (Simpan, lalu Hentikan–Mulai web) |
| **Form hanya boleh dibuka dari PC itu sendiri** | `config.yaml` → `web: host: "127.0.0.1"` (bawaan `0.0.0.0` = bisa dibuka dari PC lain di jaringan stasiun) |
| **Stasiun di WITA/WIT** | `config.yaml` → `runtime: timezone_offset_hours: 8` (WITA) atau `9` (WIT); bawaan 7 (WIB) |
| **Nama/stasiun lain** | `config.yaml` → `station: name:` (persis seperti pilihan di web BMKG Satu) dan `notify: nama_stasiun:` |
| **Daftar observer dibatasi** | `config.yaml` → `observers: allowed: [nama1, nama2]`; daftar lengkap ada di `core\options.json` (di dalam `_internal\core\` pada `.exe`) |
| **Chrome terpasang di lokasi tak standar / berbeda** | Pasang Chrome normal; bot memakai Chrome bawaan sistem. Profil login tersimpan di `chrome_profile\` (jangan dibagikan) |
| **Internet lewat proxy kantor** | Atur proxy sistem Windows; bila chromedriver tak bisa diunduh, pasang chromedriver yang cocok dengan versi Chrome lalu taruh di PATH |
| **Teks popup "sesi habis" tidak dikenali** | Lihat `snapshots\*popup_sesi_habis*.html`/log; tambahkan kata kuncinya di `config.yaml` → `session: kata_popup: [sesi, berakhir, ...]` |
| **Notifikasi terlalu ramai/sepi** | Pengaturan → bagian *Telegram* |
| **Mengubah pengaturan lanjut** | Edit `config.yaml` (komentar di dalamnya menjelaskan tiap kunci). Pengaturan dari panel disimpan di `config.panel.yaml` dan **menimpa** `config.yaml`; hapus berkas itu untuk kembali ke `config.yaml` |

Semua perubahan berlaku **saat komponen dijalankan ulang** (Hentikan lalu Mulai).

## 7. Memperbarui aplikasi
Ganti isi folder dengan versi baru **tetapi pertahankan**: `.env`, `config.yaml`, `config.panel.yaml`, `data\` (database & riwayat), `chrome_profile\`, `logs\`, `pantau_out\`.

## 8. Jika ada masalah

| Gejala | Penyebab & tindakan |
|---|---|
| Jendela putih / tidak muncul | WebView2 belum ada → pasang WebView2 Runtime; panel akan otomatis memakai browser bila jendela gagal. Buka `http://127.0.0.1:8765` |
| "Panel sudah terbuka" (tidak muncul lagi) | Panel hanya satu; jendela lama terbuka di taskbar/browser. Alamat: `http://127.0.0.1:8765` |
| Bot langsung "Mati" setelah Mulai | Menu **Log → Bot pengirim**. Penyebab umum: kredensial kosong, Chrome belum terpasang, profil Chrome terkunci (tutup Chrome yang memakai `chrome_profile`) |
| `Kredensial BMKG Satu belum diisi` | Pengaturan → Kredensial & rahasia |
| Web form tidak bisa dibuka dari PC lain | Izinkan di Windows Firewall (Private network) dan cek `web: host` bukan `127.0.0.1` |
| Tombol Aktifkan remote ditolak | WEB_PIN kosong atau cloudflared belum terpasang (pesan jelasnya tampil) |
| Baris *Struktur web* berwarna kuning | Web BMKG Satu tampaknya berubah (elemen yang hilang disebut). Jalankan **Pantau Web → Jelajah**, kirim `.zip` ke pengembang |
| Kirim nyata gagal tengah jalan | Slot ditandai di dashboard (Gagal / perlu dicek manual); tidak dikirim ganda otomatis. Lihat Log dan snapshot di `snapshots\` |

## 9. Isi folder
```
SynopOtomatis\
  SynopOtomatis.exe   panel (jangan dipindah dari SynopWorker.exe)
  SynopWorker.exe     pekerja bot/web/pantau
  .env                rahasia (ID, password, PIN, token)  <- jangan dibagikan
  config.yaml         pengaturan dasar            config.panel.yaml  pengaturan dari panel
  data\               database form, riwayat kirim, status_bot.json
  logs\               log bot/web/remote/pantau   snapshots\  potret saat gagal
  chrome_profile\     profil Chrome bot (sesi login)   pantau_out\  laporan pantau
  _internal\          berkas program (jangan diubah)
```

## 10. Belum tercakup
Autostart saat Windows menyala dan pemulihan setelah PC mati (F4.4) belum ada. Sementara: taruh pintasan `SynopOtomatis.exe` di folder `shell:startup`, lalu buka panel dan tekan **Mulai** pada bot setelah PC menyala.
