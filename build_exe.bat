@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title SYNOP Otomatis - Bangun aplikasi (.exe)

echo ============================================================
echo   Membangun SYNOP Otomatis menjadi aplikasi Windows (.exe)
echo   Hasil: folder dist\SynopOtomatis  (salin seluruh folder itu)
echo ============================================================

rem ---- 1. Python 3.11 / 3.12 (hanya diperlukan untuk MEMBANGUN, bukan untuk menjalankan hasilnya) ----
set PY=python
where python >nul 2>nul || set PY=py
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo [GAGAL] Python tidak ditemukan. Pasang Python 3.12 dari python.org ^(centang "Add python.exe to PATH"^).
  pause & exit /b 1
)

rem ---- 2. Lingkungan khusus pembangunan ----
if not exist ".venv-build\Scripts\activate.bat" (
  echo Membuat lingkungan .venv-build ...
  %PY% -m venv .venv-build
  if errorlevel 1 ( echo [GAGAL] membuat lingkungan Python & pause & exit /b 1 )
)
call ".venv-build\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 ( echo [GAGAL] pemasangan pustaka. Periksa koneksi internet. & pause & exit /b 1 )

rem ---- 3. Uji cepat sebelum dikemas (berhenti bila ada yang rusak) ----
python tests\test_panel.py >nul 2>nul
if errorlevel 1 (
  echo [PERINGATAN] tests\test_panel.py gagal. Jalankan:  python tests\test_panel.py  untuk melihat penyebabnya.
  pause & exit /b 1
)

rem ---- 4. Kemas ----
pyinstaller synop.spec --noconfirm
if errorlevel 1 ( echo [GAGAL] PyInstaller gagal. Lihat pesan di atas. & pause & exit /b 1 )

echo.
echo SELESAI. Jalankan:  dist\SynopOtomatis\SynopOtomatis.exe
echo Baca docs\PANDUAN_PEMASANGAN.md untuk pemasangan di PC stasiun.
pause
endlocal
