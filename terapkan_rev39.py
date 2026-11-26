# -*- coding: utf-8 -*-
"""Rev 39: tampilan panel MENGIKUTI UKURAN LAYAR (monitor besar tidak lagi berisi huruf kecil + pinggir kosong).
Jalankan dari folder proyek:   python terapkan_rev39.py        (aman diulang, tahan CRLF)
Cara kerja: semua ukuran di panel/index.html (px) diubah ke rem; skala (ukuran huruf akar) dihitung otomatis dari lebar & tinggi jendela
(dasar rancangan 1280x650 -> di 2560x1440 jadi 2x, di 1920x1080 sekitar 1,5x; laptop kecil tetap 1x) dan ada tombol - / + untuk menyetel halus.
Yang diubah HANYA panel/index.html (cadangan sebelum rev 39: panel/index.html.rev39.bak, dibuat sekali) + satu baris di docs/SYNOP_UPGRADE_HANDOFF.txt.
Bila dist/SynopOtomatis/_internal/panel/index.html ada (hasil build), berkas itu ikut diperbarui sehingga tidak perlu build ulang.
PERHATIAN: jangan jalankan ulang terapkan_rev38*.py sesudah ini (teks px-nya sudah menjadi rem; skrip lama akan melapor GAGAL, tidak merusak apa pun)."""
import re
import shutil
from pathlib import Path

TARGET = ["panel/index.html", "dist/SynopOtomatis/_internal/panel/index.html"]
MARK = "/* rev39: ukuran dalam rem"
CAT = ("  [2026-11-26] Rev 39 - panel/index.html: tampilan mengikuti ukuran layar. AKAR (screenshot PC kantor, monitor besar): lebar konten dikunci .wrap{max-width:1200px} dan semua ukuran memakai px tetap\n"
       "               -> huruf kecil + pinggir kosong. Kini semua ukuran >2px diubah ke rem (px di @media dan garis 1-2px tetap), ukuran huruf akar = 16px x skala; skala otomatis =\n"
       "               min(lebar/1280, tinggi/650, 2,5) minimal 1 (laptop kecil tetap seperti semula; 2560x1440 -> 2x; 1920x1080 -> sekitar 1,5x), dihitung ulang saat jendela diubah ukurannya.\n"
       "               Tombol - / + (menyetel halus 70%-160%, tersimpan di localStorage 'zadj'; klik angka = kembali 100%). Hanya panel/index.html yang berubah; backend tidak.\n"
       "               CATATAN revisi berikutnya: ukuran di index.html kini rem (px/16) - jangan mencocokkan teks px lama. Berikutnya: salin panel\\index.html ke PC kantor, cek di monitor besar.\n")

SKALA_JS = """/* rev39: skala tampilan. Seluruh ukuran memakai rem; ukuran huruf akar = 16px x skala (otomatis dari ukuran jendela x penyetelan manual). */
let ZADJ=Math.min(1.6,Math.max(.7,parseFloat(localStorage.zadj)||1)),RZ=0;
function ukur(){const k=Math.max(1,Math.min(innerWidth/1280,innerHeight/650,2.5)),f=Math.min(3,Math.max(.7,k*ZADJ));document.documentElement.style.fontSize=(16*Math.round(f*100)/100)+'px';
 const v=document.getElementById('zv');if(v)v.textContent=Math.round(ZADJ*100)+'%'}
function zset(d){ZADJ=d===0?1:Math.min(1.6,Math.max(.7,Math.round((ZADJ+d)*10)/10));try{localStorage.zadj=ZADJ}catch(e){}ukur()}
addEventListener('resize',()=>{cancelAnimationFrame(RZ);RZ=requestAnimationFrame(ukur)});ukur();
"""
ZM_HTML = ('<span class="chip zm" title="Ukuran tampilan: otomatis mengikuti layar; setel halus di sini"><button type="button" onclick="zset(-.1)" aria-label="Perkecil tampilan">−</button>'
           '<button type="button" id="zv" onclick="zset(0)" aria-label="Kembalikan ukuran tampilan ke 100%" title="Klik: kembali 100%">100%</button><button type="button" onclick="zset(.1)" aria-label="Perbesar tampilan">+</button></span>')
ZM_CSS = (".zm{gap:.125rem;padding:.1875rem .375rem}.zm button{border:0;background:none;color:var(--tx);font:700 .8125rem inherit;cursor:pointer;min-width:1.5rem;height:1.5rem;border-radius:99px;padding:0 .25rem}"
          ".zm button:hover{background:var(--acs);color:var(--ac)}.zm #zv{font-weight:600;min-width:2.75rem}\n")


def rem(texto):
    """px (>2) -> rem (px/16), kecuali kondisi @media (ukuran jendela nyata). 1-2px (garis) dibiarkan."""
    simpan = []

    def jaga(m):
        simpan.append(m.group(0)); return "\x00%d\x00" % (len(simpan) - 1)

    t = re.sub(r"@media\s*\([^)]*\)", jaga, texto)

    def ubah(m):
        n = float(m.group(1))
        if n <= 2:
            return m.group(0)
        return ("%.5f" % (n / 16)).rstrip("0").rstrip(".") + "rem"
    t = re.sub(r"(?<![\w.$#])(\d+(?:\.\d+)?)px\b", ubah, t)
    return re.sub(r"\x00(\d+)\x00", lambda m: simpan[int(m.group(1))], t)


def terapkan(s):
    """s memakai \\n. Mengembalikan teks baru atau None bila sudah terpasang."""
    if MARK in s:
        return None
    a, b = s.index("<style>") + 7, s.index("</style>")
    css = rem(s[a:b])
    css = MARK + "; skala = ukur() di bawah */\n" + ZM_CSS + css
    s = s[:a] + css + s[b:]
    # ukuran inline (style="...px") pada HTML & templat JS; angka px hasil ukur di JS (+'px', ${d}px) tidak tersentuh
    awal, akhir = s.index("</style>"), len(s)
    s = s[:awal] + rem(s[awal:akhir])
    s = s.replace('<button class="chip btn" id="mm"', ZM_HTML + '<button class="chip btn" id="mm"', 1)
    i = s.index("<script>") + len("<script>")
    return s[:i] + "\n" + SKALA_JS + s[i:].lstrip("\n")


def baca(p):
    b = p.read_bytes().decode("utf-8"); return b.replace("\r\n", "\n"), ("\r\n" if "\r\n" in b else "\n")


def tulis(p, s, nl): p.write_bytes(s.replace("\n", nl).encode("utf-8"))


if __name__ == "__main__":
    gagal = 0
    for f in TARGET:
        p = Path(f)
        if not p.exists():
            if f == TARGET[0]:
                print("TIDAK ADA  ", f, "- jalankan dari folder proyek"); gagal += 1
            continue
        s, nl = baca(p)
        try:
            baru = terapkan(s)
        except ValueError:
            print("GAGAL      ", f, "- struktur berkas tidak dikenali (butuh <style>, <script>); berkas TIDAK diubah"); gagal += 1; continue
        if baru is None:
            print("sudah      ", f); continue
        bak = p.with_name(p.name + ".rev39.bak")
        if not bak.exists():
            shutil.copy2(p, bak)
        tulis(p, baru, nl); print("DIPASANG   ", f, "- cadangan:", bak.name)
    H = Path("docs/SYNOP_UPGRADE_HANDOFF.txt")
    if H.exists():
        s, nl = baca(H)
        if "Rev 39" in s:
            print("sudah       handoff")
        else:
            k = s.rfind("\n" + "#" * 80 + "\n#  AKHIR FILE")
            s = (s[:k].rstrip("\n") + "\n" + CAT + s[k:]) if k >= 0 else s.rstrip("\n") + "\n" + CAT
            tulis(H, s, nl); print("DIPASANG    handoff")
    print("\nSELESAI - buka ulang SynopOtomatis.exe (atau build_exe.bat bila dist belum ikut diperbarui)" if not gagal else "\n%d berkas GAGAL" % gagal)
