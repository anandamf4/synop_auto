# -*- coding: utf-8 -*-
"""
core/health.py - F3.9: health check selector (hanya MEMBACA halaman; tidak mengklik/mengisi apa pun).

Tujuan: tahu lebih awal bila web BMKG Satu berubah (id/label hilang atau bergeser) sebelum jam kirim.
  kerangka : elemen halaman sinoptik yang SELALU ada (stasiun, tanggal, jam, observer) -> dicek berkala saat menunggu.
  form     : field berid pada core/fields.py yang aktif 'selalu' -> dicek sesudah jam dipilih, SEBELUM pengisian & SEND.
Modul ini tidak mengimpor selenium: terima `execute_script` milik driver (mudah diuji dengan fungsi palsu).
"""
from core.fields import FIELDS

KERANGKA_ID = ("input-datepicker", "input-jam", "select-observer")
KERANGKA_LABEL = ("stasiun", "tanggal", "jam", "nama observer")

_JS = ("var ids=arguments[0], lab=arguments[1], ls=[].slice.call(document.querySelectorAll('label')).map(function(l){"
       "return (l.textContent||'').replace(/\\s+/g,' ').trim().toLowerCase();});"
       "return ids.filter(function(i){return !document.getElementById(i);}).concat("
       "lab.filter(function(t){return !ls.some(function(x){return x.indexOf(t)===0;});}).map(function(t){return 'label:'+t;}));")


def id_form():
    """Id field form yang wajib ada begitu form terbuka: tipe pilih/isi (berid) dengan aktif 'selalu'."""
    return [k for k, v in FIELDS.items() if v["tipe"] in ("pilih", "isi") and v["aktif"] == "selalu"]


def periksa(execute_script, form=False):
    """Daftar elemen yang HILANG (id, atau 'label:<teks>'). Kosong = sehat. Galat membaca halaman -> ['(tidak terbaca: ...)']."""
    ids = list(KERANGKA_ID) + (id_form() if form else [])
    try:
        return list(execute_script(_JS, ids, list(KERANGKA_LABEL)) or [])
    except Exception as e:
        return [f"(tidak terbaca: {type(e).__name__})"]
