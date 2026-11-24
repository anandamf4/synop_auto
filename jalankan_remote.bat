@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title SYNOP - Akses Remote (Cloudflare Tunnel)

rem ====== Pengaturan (ubah bila perlu) ======
set PORT=8080
set JUDUL_APP=SYNOP Web (app.py)

echo.
echo ============================================================
echo   SYNOP - jalankan web + tunnel agar bisa dibuka dari HP
echo   di jaringan mana pun (tetap berjalan di PC ini)
echo ============================================================
echo.

rem ---- 1. Python ----
set PY=python
where python >nul 2>nul || set PY=py
where %PY% >nul 2>nul
if errorlevel 1 (
  echo [GAGAL] Python tidak ditemukan di PATH.
  pause & exit /b 1
)

rem ---- 2. WEB_PIN wajib terisi (halaman akan terbuka ke internet) ----
findstr /R /C:"^WEB_PIN=..*" ".env" >nul 2>nul
if errorlevel 1 (
  echo [DIBATALKAN] WEB_PIN di file .env masih kosong / belum ada.
  echo Karena halaman akan bisa dibuka dari internet, isi dulu PIN di .env, contoh:
  echo     WEB_PIN=pin_panjang_dan_acak
  pause & exit /b 1
)

rem ---- 3. cloudflared ----
set CF=cloudflared
where cloudflared >nul 2>nul
if errorlevel 1 (
  if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" (
    set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
  ) else if exist "%ProgramFiles%\cloudflared\cloudflared.exe" (
    set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
  ) else (
    echo cloudflared belum terpasang. Memasang lewat winget...
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
    if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
    if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
    "%CF%" --version >nul 2>nul
    if errorlevel 1 (
      echo.
      echo [PERLU TINDAKAN] cloudflared sudah dipasang tetapi belum terbaca.
      echo Tutup jendela ini lalu jalankan jalankan_remote.bat sekali lagi.
      pause & exit /b 1
    )
  )
)

rem ---- 4. Jalankan app.py di jendela terpisah (hanya menerima koneksi dari PC ini; tunnel yang meneruskan) ----
echo Menjalankan app.py di port %PORT% ...
start "%JUDUL_APP%" cmd /k %PY% app.py --host 127.0.0.1 --port %PORT%
timeout /t 5 /nobreak >nul

rem ---- 5. Tunnel: link https://xxxx.trycloudflare.com akan tercetak di bawah ----
echo.
echo Cari baris berisi  https://....trycloudflare.com  di bawah, buka di HP,
echo lalu masukkan WEB_PIN. Link BERUBAH setiap kali skrip ini dijalankan ulang.
echo Tutup jendela ini (atau Ctrl+C) untuk memutus akses remote.
echo ------------------------------------------------------------
"%CF%" tunnel --url http://127.0.0.1:%PORT%

rem ---- 6. Bersih-bersih saat tunnel berhenti ----
echo.
echo Tunnel berhenti. Menutup app.py ...
taskkill /FI "WINDOWTITLE eq %JUDUL_APP%*" /T /F >nul 2>nul
pause
endlocal
