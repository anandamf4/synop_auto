# -*- coding: utf-8 -*-
"""Rev 38c: chip Telegram tidak berkedut. Jalankan dari folder proyek:  python terapkan_rev38c.py   (aman diulang, tahan CRLF)"""
from pathlib import Path
EDITS=[["panel/index.html", ".pl::before{content:\"\";width:6px;height:6px;border-radius:50%;background:currentColor}.pl.live::before{animation:pulse 1.6s infinite}\n.ok{background:var(--okb);color:var(--ok)}.wt{background:var(--wnb);color:var(--wn)}.of{background:var(--ofb);color:var(--of)}.er{background:var(--erb);color:var(--er)}", ".pl::before{content:\"\";width:6px;height:6px;border-radius:50%;background:currentColor}.pl.live::before{animation:pulse 1.6s infinite}\n.chips .pl{animation:none}\n.ok{background:var(--okb);color:var(--ok)}.wt{background:var(--wnb);color:var(--wn)}.of{background:var(--ofb);color:var(--of)}.er{background:var(--erb);color:var(--er)}"], ["panel/index.html", "async function muat(){const r=await api('/api/ringkas');if(!r||!r.proses)return;const nb=!R||R.snap_gagal!==r.snap_gagal;R=r;$('stasiun').innerHTML=`${esc(R.stasiun)}<br>${R.rev}`;\n $('tg').innerHTML=`<span class=\"pl ${R.telegram?'ok':'of'}\">Telegram ${R.telegram?'aktif':'belum diatur'}</span>`;if(nb)menu();render(false)}\nsetInterval(()=>{if(R)$('utc').textContent='UTC '+new Date().toISOString().substr(11,8)},1000);", "async function muat(){const r=await api('/api/ringkas');if(!r||!r.proses)return;const nb=!R||R.snap_gagal!==r.snap_gagal;R=r;$('stasiun').innerHTML=`${esc(R.stasiun)}<br>${R.rev}`;\n put('tg',`<span class=\"pl ${R.telegram?'ok live':'of'}\">Telegram ${R.telegram?'aktif':'belum diatur'}</span>`);   /* ditulis hanya bila berubah; hanya titiknya yang berdenyut */if(nb)menu();render(false)}\nsetInterval(()=>{if(R)$('utc').textContent='UTC '+new Date().toISOString().substr(11,8)},1000);"]]
CAT="  [2026-11-26] Rev 38c - panel/index.html: chip 'Telegram aktif' tidak lagi berkedut tiap 3 dtk (ditulis ulang tiap polling -> animasi pop); kini ditulis hanya saat berubah dan\n               hanya titiknya yang berdenyut (sama seperti pil 'Jalan').\n"
def baca(p):
    b=p.read_bytes().decode("utf-8");return b.replace("\r\n","\n"),("\r\n" if "\r\n" in b else "\n")
def tulis(p,s,nl):p.write_bytes(s.replace("\n",nl).encode("utf-8"))
gagal=0
for f,lama,baru in EDITS:
    p=Path(f)
    if not p.exists():print("TIDAK ADA ",f);gagal+=1;continue
    s,nl=baca(p)
    if baru in s:print("sudah      ",f)
    elif lama in s:tulis(p,s.replace(lama,baru,1),nl);print("DIPASANG   ",f)
    else:print("GAGAL      ",f,"- teks asli tidak ditemukan (pastikan rev 38 sudah terpasang)");gagal+=1
H=Path("docs/SYNOP_UPGRADE_HANDOFF.txt")
if H.exists():
    s,nl=baca(H)
    if "Rev 38c" in s:print("sudah       handoff")
    else:
        k=s.rfind("\n"+"#"*80+"\n#  AKHIR FILE");s=(s[:k].rstrip("\n")+"\n"+CAT+s[k:]) if k>=0 else s.rstrip("\n")+"\n"+CAT
        tulis(H,s,nl);print("DIPASANG    handoff")
print("\nSELESAI - jalankan build_exe.bat" if not gagal else "\n%d bagian GAGAL"%gagal)
