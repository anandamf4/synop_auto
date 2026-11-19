# -*- coding: utf-8 -*-
"""
collect_rules_matrix.py  -  Tahap F0.5 (SYNOP-UPGRADE-HANDOFF)

TUJUAN
  Menurunkan aturan validator LANGSUNG dari perilaku web (bukan tebakan):
    - Jenis awan apa yang boleh dipilih untuk tiap kode CL / CM / CH      (R13)
    - Field apa yang aktif/nonaktif untuk tiap kode, termasuk "/"         (N1, R12)
    - Kapan Tinggi Puncak / Sudut Elevasi / Arah Sebenarnya aktif         (R5, R14)
    - Efek tutupan total (0..9, "/") terhadap field lain                  (R15)
    - Kapan kolom "Hujan takaran terakhir" (rainfall_last_mm) aktif,
      berdasarkan ww / W1 / W2                                            (fitur override hujan)
    - Opsi dropdown yang tadinya disabled (elevasi lapisan 2, dst.)

VERSI 2 (perbaikan dari uji --limit 2):
  Eksperimen sebelumnya saling mewarisi isian form (mis. tutupan total "0"
  otomatis mengubah CL/CM/CH menjadi 0 dan menonaktifkan semua detail awan).
  Sekarang form DIKEMBALIKAN ke kondisi awal sebelum tiap eksperimen dan
  sebelum tiap kode yang diuji (reset_to_baseline). Kegagalan reset dicatat
  di laporan ("reset_failures"). Laporan juga diringkas per field penting.

CARA KERJA (HANYA MEMBACA)
  Skrip hanya: membuka dropdown, memilih opsi (mengubah TAMPILAN form), dan
  mengklik toggle lapisan. Skrip TIDAK PERNAH menekan Preview / Send / Submit /
  Update. Perubahan hanya di layar browser dan tidak tersimpan selama Anda tidak
  menekan tombol kirim. Setelah selesai, TUTUP browser tanpa menyimpan apa pun.
  Jika muncul popup, skrip hanya menekan tombol OK/Tutup/Batal/Cancel.

PRASYARAT
  - Satu folder dengan collect_web_info.py (fungsi login dll dipakai ulang).
  - Kredensial lewat BMKG_STATION_ID / BMKG_PASSWORD atau ditanya di terminal.

CARA PAKAI
    python collect_rules_matrix.py                    # semua eksperimen (+-10-20 menit)
    python collect_rules_matrix.py --limit 2          # uji cepat: 2 opsi per eksperimen
    python collect_rules_matrix.py --only cl,cm,ch    # sebagian saja
      pilihan --only: weather, cover, cl, cm, ch, layers

HASIL (folder rules_YYYYMMDD_HHMMSS/)
    rules_matrix.json   data lengkap (disimpan bertahap, aman jika terhenti)
    rules_report.txt    ringkasan terbaca manusia
    popups.json         popup yang muncul selama eksperimen
    form_akhir.png/.html
"""
import argparse
import json
import os
import re
import time
import traceback
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import collect_web_info as cwi  # harus satu folder

log = cwi.log

SECTIONS = {
    "AWAN RENDAH": {
        "type": "cloud_low_type_cl", "cover": "cloud_low_cover_oktas",
        "jenis": "AWAN RENDAH|k1|b2|Jenis", "jumlah": "AWAN RENDAH|k1|b3|Jumlah",
    },
    "AWAN MENENGAH": {
        "type": "cloud_med_type_cm", "cover": "cloud_med_cover_oktas",
        "jenis": "AWAN MENENGAH|k1|b2|Jenis", "jumlah": "AWAN MENENGAH|k1|b3|Jumlah",
    },
    "AWAN TINGGI": {
        "type": "cloud_high_type_ch", "cover": "cloud_high_cover_oktas",
        "jenis": "AWAN TINGGI|k1|b2|Jenis", "jumlah": "AWAN TINGGI|k1|b3|Jumlah",
    },
}
ALLOWED_POPUP_BUTTONS = ["ok", "oke", "tutup", "close", "batal", "cancel"]
RAIN_KEY = "rainfall_last_mm"
POPUPS = []  # dikumpulkan selama eksperimen
RESTORE_KEYS = {"cloud_cover_oktas_m", "present_weather_ww", "past_weather_w1", "past_weather_w2"}
BASE = {"values": {}, "order": []}  # kondisi awal form (diisi di main)
RESET_FAILS = []

# --------------------------------------------------------------------------- #
#  JavaScript                                                                  #
# --------------------------------------------------------------------------- #
JS_FIND_LI = r"""
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const e = document.getElementById(arguments[0]);
if (!e) return null;
const li = Array.from(e.querySelectorAll('li')).find(
  x => norm(x.innerText) === arguments[1] && x.getAttribute('aria-disabled') !== 'true');
return li || null;
"""

JS_POPUPS = r"""
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const allowed = arguments[0];
const out = [];
document.querySelectorAll('.swal2-container.swal2-backdrop-show, .ant-modal-wrap').forEach(el => {
  const st = getComputedStyle(el);
  if (st.display === 'none' || st.visibility === 'hidden') return;
  const btns = Array.from(el.querySelectorAll('button'));
  const names = btns.map(b => norm(b.innerText));
  let action = 'none';
  const ok = btns.find(b => allowed.includes(norm(b.innerText).toLowerCase()));
  if (ok) { ok.click(); action = 'klik:' + norm(ok.innerText); }
  out.push({text: norm(el.innerText).slice(0, 300), buttons: names, action: action});
});
return out;
"""


# --------------------------------------------------------------------------- #
#  Utilitas dasar                                                              #
# --------------------------------------------------------------------------- #
def norm(s):
    return " ".join(str(s).split())


def same(a, b):
    a, b = norm(a), norm(b)
    return a == b or (a and b and (a.startswith(b) or b.startswith(a)))


def get_field(driver, key):
    for f in cwi.collect_fields(driver):
        if f["key"] == key:
            return f
    return None


def handle_popups(driver, context):
    try:
        found = driver.execute_script(JS_POPUPS, ALLOWED_POPUP_BUTTONS)
    except Exception:
        return
    for p in found or []:
        p["context"] = context
        POPUPS.append(p)
        log(f"   ℹ️ popup: {p['text'][:80]!r} -> {p['action']}")
        if p["action"] == "none":
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                from selenium.webdriver.common.keys import Keys
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
    if found:
        time.sleep(0.4)


def select_by_text(driver, key, text, settle=0.6):
    """Pilih satu opsi dropdown berdasar teks persis. Mengubah tampilan saja."""
    f = get_field(driver, key)
    if f is None:
        return False, "field tidak ditemukan"
    if f["disabled"]:
        return False, "field disabled"
    if same(f["value"], text):
        return True, "sudah terpilih"
    cid = f["controls"]
    combos = driver.find_elements(
        By.XPATH, f"//div[@role='combobox' and @aria-controls='{cid}']")
    if not combos:
        return False, "combobox tidak ditemukan"
    for _ in range(2):
        if not cwi.attempt_click(driver, combos[0]):
            continue
        try:
            WebDriverWait(driver, 4).until(
                lambda d: d.execute_script(cwi.JS_MENU_OPEN, cid))
        except TimeoutException:
            cwi.close_dropdown(driver)
            continue
        li = driver.execute_script(JS_FIND_LI, cid, norm(text))
        if li is None:
            cwi.close_dropdown(driver)
            return False, "opsi tidak ada / disabled"
        if not cwi.attempt_click(driver, li):
            cwi.close_dropdown(driver)
            continue
        end = time.time() + 3
        while time.time() < end:
            nf = get_field(driver, key)
            if nf and same(nf["value"], text):
                time.sleep(settle)
                handle_popups(driver, f"{key} = {text[:40]}")
                return True, "ok"
            time.sleep(0.2)
    return False, "nilai tidak berubah"


def snapshot_state(driver, section=None):
    fs = cwi.collect_fields(driver)
    if section:
        fs = [f for f in fs if f["section"] == section]
    return {f["key"]: {"disabled": f["disabled"], "value": f["value"], "kind": f["kind"]}
            for f in fs}


def compact(state):
    return {
        "disabled_keys": sorted(k for k, v in state.items() if v["disabled"]),
        "values": {k: v["value"] for k, v in state.items() if v["value"]},
    }


def options_status(driver, key):
    f = get_field(driver, key)
    if f is None:
        return None
    if f["disabled"]:
        return {"field": "disabled"}
    opts, err = cwi.read_options(driver, f["controls"])
    if opts is None:
        return {"error": err}
    return {
        "enabled": [norm(o["text"] or o["title"]) for o in opts if not o["disabled"]],
        "disabled": [norm(o["text"] or o["title"]) for o in opts if o["disabled"]],
    }


def enabled_option_texts(driver, key):
    st = options_status(driver, key)
    return (st or {}).get("enabled", [])


def restore(driver, key, original):
    if original:
        ok, msg = select_by_text(driver, key, original)
        if not ok:
            log(f"   ⚠️ gagal memulihkan {key}: {msg}")


def code_of(text):
    t = norm(text)
    return t.split(" ", 1)[0] if t else t


def reset_to_baseline(driver, label=""):
    """
    Kembalikan dropdown cuaca/awan ke nilai awal (urutan DOM: tutupan total ->
    CL/NCL/Jenis/Jumlah -> CM... -> CH...), dua putaran bila perlu.
    Tidak menyentuh stasiun / tanggal / jam / observer.
    """
    failed = []
    for _ in range(2):
        failed = []
        for key in BASE["order"]:
            want = BASE["values"].get(key)
            if not want:
                continue
            f = get_field(driver, key)
            if f is None:
                failed.append(key)
                continue
            if same(f["value"], want):
                continue
            if f["disabled"]:
                failed.append(key)
                continue
            ok, _msg = select_by_text(driver, key, want)
            if not ok:
                failed.append(key)
        if not failed:
            break
    if failed:
        log(f"   ⚠️ reset belum sempurna ({label}): {failed}")
        RESET_FAILS.append({"at": label, "keys": failed})
    return not failed


# --------------------------------------------------------------------------- #
#  Eksperimen                                                                  #
# --------------------------------------------------------------------------- #
def exp_weather(driver, key, label, baseline, limit):
    f = get_field(driver, key)
    if f is None:
        return {"error": "field tidak ditemukan"}
    original = f["value"]
    texts = enabled_option_texts(driver, key)
    if limit:
        texts = texts[:limit]
    base_dis = {k: v["disabled"] for k, v in baseline.items()}
    res = {"original": original, "options": {}}
    for n, t in enumerate(texts, 1):
        log(f"[{label}] {n}/{len(texts)} {t[:50]}")
        ok, msg = select_by_text(driver, key, t)
        rec = {"value": t, "selected": ok, "msg": msg}
        if ok:
            st = snapshot_state(driver)
            changed = {k: ("DISABLED" if v["disabled"] else "enabled")
                       for k, v in st.items()
                       if k in base_dis and v["disabled"] != base_dis[k]}
            rec["changed_vs_baseline"] = changed
            if RAIN_KEY in st:
                rec[RAIN_KEY] = {"disabled": st[RAIN_KEY]["disabled"],
                                 "value": st[RAIN_KEY]["value"]}
        res["options"][code_of(t)] = rec
    restore(driver, key, original)
    reset_to_baseline(driver, f"akhir {label}")
    return res


def exp_cover_total(driver, limit):
    key = "cloud_cover_oktas_m"
    f = get_field(driver, key)
    if f is None:
        return {"error": "field tidak ditemukan"}
    original = f["value"]
    texts = enabled_option_texts(driver, key)
    if limit:
        texts = texts[:limit]
    res = {"original": original, "options": {}}
    reset_to_baseline(driver, "awal tutupan total")
    for n, t in enumerate(texts, 1):
        log(f"[tutupan total] {n}/{len(texts)} {t[:50]}")
        reset_to_baseline(driver, f"sebelum tutupan total {code_of(t)}")
        ok, msg = select_by_text(driver, key, t)
        rec = {"value": t, "selected": ok, "msg": msg}
        if ok:
            rec.update(compact(snapshot_state(driver)))
        res["options"][code_of(t)] = rec
    reset_to_baseline(driver, "akhir tutupan total")
    return res


def exp_type(driver, section, limit):
    cfg = SECTIONS[section]
    f = get_field(driver, cfg["type"])
    if f is None:
        return {"error": "field tipe tidak ditemukan"}
    original = f["value"]
    texts = enabled_option_texts(driver, cfg["type"])
    if limit:
        texts = texts[:limit]
    res = {"original": original, "codes": {}}
    reset_to_baseline(driver, f"awal {section}")
    for n, t in enumerate(texts, 1):
        log(f"[{section}] {n}/{len(texts)} {t[:60]}")
        reset_to_baseline(driver, f"sebelum {section} {code_of(t)}")
        ok, msg = select_by_text(driver, cfg["type"], t)
        rec = {"value": t, "selected": ok, "msg": msg}
        if ok:
            rec.update(compact(snapshot_state(driver, section)))
            rec["cover_options"] = options_status(driver, cfg["cover"])
            rec["jenis_options"] = options_status(driver, cfg["jenis"])
            rec["jumlah_options"] = options_status(driver, cfg["jumlah"])
            effects = {}
            jo = rec["jenis_options"] or {}
            jenis_list = jo.get("enabled", [])
            if limit:
                jenis_list = jenis_list[:limit]
            for j in jenis_list:
                ok2, m2 = select_by_text(driver, cfg["jenis"], j)
                if ok2:
                    effects[j] = compact(snapshot_state(driver, section))
                else:
                    effects[j] = {"selected": False, "msg": m2}
            rec["jenis_effects"] = effects
        res["codes"][code_of(t)] = rec
    reset_to_baseline(driver, f"akhir {section}")
    return res


def exp_layers(driver, limit):
    """Toggle lapisan tambahan: opsi Jenis, dan field/opsi dependen per Jenis."""
    res = {}
    reset_to_baseline(driver, "awal layers")
    for t in cwi.collect_toggles(driver):
        reset_to_baseline(driver, "sebelum toggle")
        sec, col, tid = t["section"], t["col"], t["id"]
        name = f"{sec}#{t['ordinal_in_section']} (kolom {col}, id {tid})"
        log(f"[layer] {name}")
        was_on = driver.execute_script(cwi.JS_IS_CHECKED, tid)
        if not was_on:
            cwi.click_toggle(driver, tid)
            handle_popups(driver, f"toggle {tid}")
        jenis_key = f"{sec}|k{col}|b2|Jenis"
        rec = {"toggle_id": tid, "col": col, "jenis_options": options_status(driver, jenis_key),
               "jenis_effects": {}, "dependent_options": {}}
        jenis_list = (rec["jenis_options"] or {}).get("enabled", [])
        if limit:
            jenis_list = jenis_list[:limit]
        for j in jenis_list:
            ok, msg = select_by_text(driver, jenis_key, j)
            if not ok:
                rec["jenis_effects"][j] = {"selected": False, "msg": msg}
                continue
            sec_fields = cwi.collect_fields(driver)
            st = {f["key"]: {"disabled": f["disabled"], "value": f["value"], "kind": f["kind"]}
                  for f in sec_fields if f["section"] == sec}
            rec["jenis_effects"][j] = compact(st)
            # opsi dropdown lapisan ini yang aktif & belum pernah dibaca
            for f in sec_fields:
                if (f["section"] == sec and f["col"] == col and f["kind"] == "select"
                        and not f["disabled"] and f["key"] != jenis_key
                        and f["key"] not in rec["dependent_options"]):
                    rec["dependent_options"][f["key"]] = options_status(driver, f["key"])
        res[name] = rec
        if not was_on:  # kembalikan toggle ke keadaan semula
            cwi.click_toggle(driver, tid)
            handle_popups(driver, f"toggle {tid} off")
    reset_to_baseline(driver, "akhir layers")
    return res


# --------------------------------------------------------------------------- #
#  Laporan                                                                     #
# --------------------------------------------------------------------------- #
SHORT_IDS = {
    "cloud_low_cover_oktas": "NCL", "cloud_med_cover_oktas": "NCM", "cloud_high_cover_oktas": "NCH",
    "cloud_low_type_cl": "CL", "cloud_med_type_cm": "CM", "cloud_high_type_ch": "CH",
    "cloud_vertical_vis": "VertVis", "cloud_cover_oktas_m": "Total", RAIN_KEY: "Hujan",
}
WATCH_L1 = {
    "AWAN RENDAH": ["cloud_low_cover_oktas", "AWAN RENDAH|k1|b2|Jenis", "AWAN RENDAH|k1|b3|Jumlah",
                    "cloud_low_base_1", "cloud_low_peak_1", "AWAN RENDAH|k1|b6|Arah Gerak",
                    "cloud_elevation_1_angle_ec", "AWAN RENDAH|k1|b8|Arah Sebenarnya"],
    "AWAN MENENGAH": ["cloud_med_cover_oktas", "AWAN MENENGAH|k1|b2|Jenis", "AWAN MENENGAH|k1|b3|Jumlah",
                      "cloud_med_base_1", "AWAN MENENGAH|k1|b5|Arah"],
    "AWAN TINGGI": ["cloud_high_cover_oktas", "AWAN TINGGI|k1|b2|Jenis", "AWAN TINGGI|k1|b3|Jumlah",
                    "cloud_high_base_1", "AWAN TINGGI|k1|b5|Arah"],
}


def short(key):
    if key in SHORT_IDS:
        return SHORT_IDS[key]
    if "|" in key:
        parts = key.split("|")
        name = parts[-1].replace("Arah Sebenarnya", "Sbnr").replace("Arah Gerak", "Gerak")
        return f"{name}{parts[1][1:]}"
    m = re.match(r"cloud_(?:low|med|high)_(base|peak)_(\d)", key)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    m = re.match(r"cloud_elevation_(\d)_angle_ec", key)
    if m:
        return f"elev{m.group(1)}"
    return key


def status_line(keys, disabled, all_keys):
    parts = []
    for k in keys:
        if k in all_keys:
            parts.append(f"{short(k)}:{'OFF' if k in disabled else 'on'}")
    return " ".join(parts)


def autofill(values, keys):
    out = {short(k): norm(values[k])[:14] for k in keys if values.get(k)}
    return out


def layer_watch(sec, col, all_keys):
    keys = []
    for k in all_keys:
        if f"|k{col}|" in k:
            keys.append(k)
        elif re.search(rf"_(?:base|peak)_{col}$", k) or re.search(rf"elevation_{col}_angle_ec$", k):
            is_low = "_low_" in k or k.startswith("cloud_elevation")
            if ((sec == "AWAN RENDAH" and is_low) or (sec == "AWAN MENENGAH" and "_med_" in k)
                    or (sec == "AWAN TINGGI" and "_high_" in k)):
                keys.append(k)
    return keys


def build_report(results):
    ak = results.get("baseline_keys", {})
    orig = results.get("originals", {})
    L = ["LAPORAN collect_rules_matrix.py (v2)", f"Waktu: {results['meta']['waktu']}",
         f"Eksperimen: {results['meta']['eksperimen']}  (limit={results['meta']['limit']})",
         "Kondisi awal form: " + ", ".join(
             f"{short(k)}={norm(orig.get(k, ''))[:22]!r}" for k in
             ("cloud_cover_oktas_m", "cloud_low_type_cl", "cloud_med_type_cm", "cloud_high_type_ch",
              "present_weather_ww", "past_weather_w1", "past_weather_w2")),
         f"Reset gagal: {len(RESET_FAILS)} kali (lihat reset_failures di JSON)", ""]

    # ---- hujan ----
    L.append("=== KAPAN 'Hujan takaran terakhir' (rainfall_last_mm) AKTIF ===")
    for name, label in (("ww", "ww"), ("w1", "W1"), ("w2", "W2")):
        data = results.get(name)
        if not data or "options" not in data:
            L.append(f"  {label}: (tidak dijalankan)")
            continue
        en = [c for c, r in data["options"].items()
              if r.get(RAIN_KEY) and not r[RAIN_KEY]["disabled"]]
        tot = [c for c, r in data["options"].items() if r.get("selected")]
        L.append(f"  {label}: aktif pada {len(en)} dari {len(tot)} kode -> {en}")
        others = {}
        for c, r in data["options"].items():
            for k, v in (r.get("changed_vs_baseline") or {}).items():
                if k != RAIN_KEY:
                    others.setdefault(k, []).append(c)
        for k, cs in others.items():
            L.append(f"      juga mengubah {k}: pada kode {cs[:25]}{' ...' if len(cs) > 25 else ''}")
    L.append("")

    # ---- tutupan total ----
    L.append("=== TUTUPAN TOTAL (cloud_cover_oktas_m) ===")
    cov = results.get("cover")
    watch = ["cloud_low_type_cl", "cloud_med_type_cm", "cloud_high_type_ch", "cloud_vertical_vis",
             "cloud_low_cover_oktas", "cloud_med_cover_oktas", "cloud_high_cover_oktas", RAIN_KEY]
    if cov and "options" in cov:
        all_all = set(k for v in ak.values() for k in v)
        for c, r in cov["options"].items():
            if not r.get("selected"):
                L.append(f"  [{c}] gagal dipilih: {r.get('msg')}")
                continue
            dis = set(r.get("disabled_keys", []))
            L.append(f"  [{c}] {norm(r['value'])[:40]}")
            L.append(f"        status : {status_line(watch, dis, all_all)}")
            L.append(f"        isi otomatis: {autofill(r.get('values', {}), watch)}")
    else:
        L.append("  (tidak dijalankan)")
    L.append("")

    # ---- CL / CM / CH ----
    for sec, name in (("AWAN RENDAH", "cl"), ("AWAN MENENGAH", "cm"), ("AWAN TINGGI", "ch")):
        L.append(f"=== {sec}: aturan per kode ({name.upper()}) ===")
        data = results.get(name)
        if not data or "codes" not in data:
            L.append("  (tidak dijalankan)\n")
            continue
        keys = WATCH_L1[sec]
        for code, r in data["codes"].items():
            if not r.get("selected"):
                L.append(f"  [{code}] gagal dipilih: {r.get('msg')}")
                continue
            jo = r.get("jenis_options") or {}
            jen = [code_of(x) for x in jo["enabled"]] if "enabled" in jo else "field nonaktif"
            jbl = [code_of(x) for x in jo.get("disabled", [])] if "enabled" in jo else []
            co = r.get("cover_options") or {}
            cbl = [code_of(x) for x in co.get("disabled", [])] if "disabled" in co else co
            dis = set(r.get("disabled_keys", []))
            L.append(f"  [{code}] {norm(r['value'])[:60]}")
            L.append(f"        Jenis boleh: {jen}  diblok: {jbl}")
            L.append(f"        Opsi tutupan lapisan diblok: {cbl}")
            L.append(f"        status : {status_line(keys, dis, allk_set(ak, sec))}")
            L.append(f"        isi otomatis: {autofill(r.get('values', {}), keys)}")
            for j, e in (r.get("jenis_effects") or {}).items():
                if "disabled_keys" in e:
                    L.append(f"          jenis {code_of(j)} -> "
                             f"{status_line(keys, set(e['disabled_keys']), allk_set(ak, sec))}")
                else:
                    L.append(f"          jenis {code_of(j)} -> gagal: {e.get('msg')}")
        L.append("")

    # ---- layer ----
    L.append("=== LAPISAN TAMBAHAN (toggle) ===")
    lay = results.get("layers")
    if lay:
        for name, r in lay.items():
            m = re.match(r"(AWAN \w+)#", name)
            sec = m.group(1) if m else ""
            jo = r.get("jenis_options") or {}
            L.append(f"  {name}")
            L.append(f"      Jenis boleh: {[code_of(x) for x in jo.get('enabled', [])]}"
                     f" | diblok: {[code_of(x) for x in jo.get('disabled', [])]}")
            keys = layer_watch(sec, r.get("col"), allk_set(ak, sec))
            for j, e in (r.get("jenis_effects") or {}).items():
                if "disabled_keys" in e:
                    L.append(f"      jenis {code_of(j)} -> "
                             f"{status_line(keys, set(e['disabled_keys']), allk_set(ak, sec))}")
                else:
                    L.append(f"      jenis {code_of(j)} -> gagal: {e.get('msg')}")
            for k, o in (r.get("dependent_options") or {}).items():
                n = len((o or {}).get("enabled", []))
                L.append(f"      opsi {short(k)}: {n} opsi aktif")
    else:
        L.append("  (tidak dijalankan)")
    L.append("")
    L.append(f"Popup selama eksperimen: {len(POPUPS)} (lihat popups.json)")
    return "\n".join(L)


def allk_set(ak, sec):
    return list(ak.get(sec, []))  # urutan DOM dipertahankan


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #
PETUNJUK = """
============================================================
 LANGKAH MANUAL:
  1. Di browser: pilih Stasiun, Tanggal, Jam, Observer; tutup popup;
     tunggu form SYNOP tampil penuh. Pastikan semua toggle lapisan OFF.
  2. Setelah itu JANGAN menyentuh browser; skrip akan mengubah isian
     form secara otomatis (sekitar 10-20 menit untuk semua eksperimen).
  3. Skrip TIDAK menekan Preview/Send/Update. Setelah selesai,
     TUTUP browser tanpa menyimpan apa pun.
============================================================
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="weather,cover,cl,cm,ch,layers")
    ap.add_argument("--limit", type=int, default=0, help="batasi jumlah opsi per eksperimen (uji cepat)")
    args = ap.parse_args()
    only = [x.strip() for x in args.only.split(",") if x.strip()]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.getcwd(), f"rules_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    log(f"📁 Hasil: {out_dir}")

    opts = Options()
    opts.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=opts)
    results = {"meta": {"waktu": datetime.now().isoformat(timespec="seconds"),
                        "eksperimen": only, "limit": args.limit}}

    def save():
        results["reset_failures"] = RESET_FAILS
        with open(os.path.join(out_dir, "rules_matrix.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "popups.json"), "w", encoding="utf-8") as f:
            json.dump(POPUPS, f, ensure_ascii=False, indent=2)

    try:
        cwi.login(driver)
        print(PETUNJUK)
        input("Tekan ENTER jika form SYNOP sudah tampil penuh... ")
        if not driver.find_elements(By.ID, cwi.FORM_MARKER_ID):
            log("⚠️ Form belum tampil; hasil bisa tidak lengkap.")

        bf = cwi.collect_fields(driver)
        baseline = snapshot_state(driver)
        results["baseline"] = compact(baseline)
        results["originals"] = {k: v["value"] for k, v in baseline.items() if v["kind"] == "select"}
        keys_by_section = {}
        for f in bf:
            keys_by_section.setdefault(f["section"], []).append(f["key"])
        results["baseline_keys"] = keys_by_section
        BASE["values"] = {f["key"]: f["value"] for f in bf if f["kind"] == "select"}
        BASE["order"] = [f["key"] for f in bf if f["kind"] == "select"
                         and (f["key"] in RESTORE_KEYS or f["section"] in SECTIONS)]
        log(f"📌 Kondisi awal disimpan ({len(BASE['order'])} dropdown akan dipulihkan antar eksperimen)")
        save()

        steps = [
            ("weather", lambda: [
                results.__setitem__("ww", exp_weather(driver, "present_weather_ww", "ww", baseline, args.limit)),
                save(),
                results.__setitem__("w1", exp_weather(driver, "past_weather_w1", "W1", baseline, args.limit)),
                save(),
                results.__setitem__("w2", exp_weather(driver, "past_weather_w2", "W2", baseline, args.limit)),
            ]),
            ("cover", lambda: results.__setitem__("cover", exp_cover_total(driver, args.limit))),
            ("cl", lambda: results.__setitem__("cl", exp_type(driver, "AWAN RENDAH", args.limit))),
            ("cm", lambda: results.__setitem__("cm", exp_type(driver, "AWAN MENENGAH", args.limit))),
            ("ch", lambda: results.__setitem__("ch", exp_type(driver, "AWAN TINGGI", args.limit))),
            ("layers", lambda: results.__setitem__("layers", exp_layers(driver, args.limit))),
        ]
        for name, fn in steps:
            if name not in only:
                continue
            log(f"\n▶️ Eksperimen: {name}")
            t0 = time.time()
            try:
                fn()
            except Exception as e:
                log(f"❌ Eksperimen {name} gagal: {e}\n{traceback.format_exc()}")
                results[f"error_{name}"] = str(e)
            save()
            log(f"⏱️ {name} selesai dalam {time.time() - t0:.0f}s")

        cwi.save_snapshot(driver, out_dir, "form_akhir")
        report = build_report(results)
        with open(os.path.join(out_dir, "rules_report.txt"), "w", encoding="utf-8") as f:
            f.write(report)
        save()
        log(f"\n✅ Selesai. Kirim ke chat: rules_report.txt dan rules_matrix.json\n   di {out_dir}")
        log("   Tutup browser TANPA menyimpan/menekan tombol apa pun.")
    except Exception as e:
        log(f"❌ Error: {e}\n{traceback.format_exc()}")
        save()
    finally:
        input("\nTekan ENTER untuk menutup browser... ")
        driver.quit()


if __name__ == "__main__":
    main()
