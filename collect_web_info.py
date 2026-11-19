# -*- coding: utf-8 -*-
"""
collect_web_info.py  -  Tahap F0.2 + F0.4 (SYNOP-UPGRADE-HANDOFF)

Fungsi (HANYA MEMBACA, tidak pernah klik Preview/Send/Submit):
  1. Login ke BMKG Satu, lalu menunggu Anda membuka form SYNOP sampai tampil.
  2. Merekam SEMUA field form: id, seksi (AWAN RENDAH dst.), kolom, baris, label,
     status disabled, dan nilai saat ini.
  3. Membuka tiap dropdown yang aktif dan menyalin SEMUA teks opsinya
     (bahan core/options.json).
  4. Memetakan semua toggle "tambah lapisan awan" (id, seksi, kolom, tooltip)
     dan menguji efeknya: field apa yang aktif setelah toggle diklik.
     Semua toggle dikembalikan ke keadaan semula di akhir.
  5. Menyimpan HTML + screenshot + report.txt yang bisa dibaca manusia.

Cara pakai:
    python collect_web_info.py
    python collect_web_info.py --no-toggles      # lewati uji toggle
    python collect_web_info.py --skip-options    # lewati salin opsi dropdown

Kredensial: dibaca dari environment BMKG_STATION_ID / BMKG_PASSWORD (atau file
.env jika python-dotenv terpasang). Jika tidak ada, akan ditanyakan di terminal.
Password TIDAK ditulis ke file mana pun.

Hasil ada di folder:  web_info_YYYYMMDD_HHMMSS/
    fields.json   -> semua field + key + status
    options.json  -> {key: {label, section, options:[...]}}
    toggles.json  -> semua toggle + efeknya
    report.txt    -> ringkasan terbaca manusia
    form_awal.html/.png, form_toggle_aktif.html/.png
"""
import argparse
import base64
import getpass
import json
import os
import time
import traceback
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:  # opsional
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

LOGIN_URL = "https://bmkgsatu.bmkg.go.id/login"
SINOPTIK_URL = "https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik"
FORM_MARKER_ID = "present_weather_ww"
CLOUD_SECTIONS = ("AWAN RENDAH", "AWAN MENENGAH", "AWAN TINGGI")

# --------------------------------------------------------------------------- #
#  JavaScript (dijalankan di browser)                                          #
# --------------------------------------------------------------------------- #
JS_COMMON = r"""
const txt = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
const CLOUD = ['AWAN RENDAH', 'AWAN MENENGAH', 'AWAN TINGGI'];
function nearLabel(el) {
  let p = el.parentElement;
  for (let i = 0; i < 5 && p; i++, p = p.parentElement) {
    const l = p.querySelector('label');
    if (l && txt(l)) return txt(l);
  }
  return '';
}
function ctx(el) {
  const body = el.closest('.card-body');
  const h = body ? body.querySelector('h5') : null;
  const section = h ? txt(h) : '';
  let col = -1, row = -1, label = '';
  if (CLOUD.includes(section)) {
    const colsRow = body.querySelector('.collapse > .row');
    if (colsRow) {
      const cols = Array.from(colsRow.children);
      const c = cols.find(x => x.contains(el));
      if (c) {
        col = cols.indexOf(c);
        const rows = Array.from(c.children);
        const r = rows.find(x => x.contains(el));
        if (r) {
          row = rows.indexOf(r);
          const lab = cols[0] ? Array.from(cols[0].children)[row] : null;
          label = lab ? txt(lab) : '';
        }
      }
    }
  } else {
    label = nearLabel(el);
  }
  return {section, col, row, label};
}
"""

JS_FIELDS = JS_COMMON + r"""
const out = [];
document.querySelectorAll('.ant-select, input.form-control, textarea.form-control').forEach(el => {
  if (el.closest('.customizer, .ant-select-dropdown')) return;
  const isSel = el.classList.contains('ant-select');
  const c = ctx(el);
  const combo = isSel ? el.querySelector('[role=combobox]') : null;
  const valEl = isSel ? el.querySelector('.ant-select-selection-selected-value') : null;
  out.push({
    kind: isSel ? 'select' : 'input',
    id: el.id || '',
    section: c.section, col: c.col, row: c.row, label: c.label,
    disabled: isSel ? el.classList.contains('ant-select-disabled') : !!el.disabled,
    value: isSel ? (valEl ? (valEl.getAttribute('title') || txt(valEl)) : '') : (el.value || ''),
    controls: combo ? (combo.getAttribute('aria-controls') || '') : '',
    visible: el.offsetParent !== null
  });
});
return out;
"""

JS_TOGGLES = JS_COMMON + r"""
const out = [];
document.querySelectorAll('input.custom-control-input[type=checkbox]').forEach(el => {
  if (el.name !== 'check-button' || el.closest('.customizer')) return;
  const c = ctx(el);
  const wrap = el.closest('.d-flex');
  const tip = wrap ? wrap.querySelector('svg[title]') : null;
  out.push({
    id: el.id, section: c.section, col: c.col, row: c.row,
    checked: !!el.checked, disabled: !!el.disabled,
    tooltip: tip ? tip.getAttribute('title') : ''
  });
});
return out;
"""

JS_OPTIONS = r"""
const e = document.getElementById(arguments[0]);
if (!e) return null;
return Array.from(e.querySelectorAll('li')).map(li => ({
  text: (li.innerText || '').replace(/\s+/g, ' ').trim(),
  title: li.getAttribute('title') || '',
  disabled: li.getAttribute('aria-disabled') === 'true'
}));
"""

JS_MENU_OPEN = r"""
const e = document.getElementById(arguments[0]);
return !!e && e.offsetParent !== null && e.querySelectorAll('li').length > 0;
"""

JS_IS_CHECKED = "var e=document.getElementById(arguments[0]); return e ? !!e.checked : null;"


# --------------------------------------------------------------------------- #
#  Utilitas                                                                    #
# --------------------------------------------------------------------------- #
def log(msg):
    print(msg, flush=True)


def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def attempt_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        try:
            element.click()
        except Exception:
            try:
                ActionChains(driver).move_to_element(element).pause(0.1).click().perform()
            except Exception:
                driver.execute_script("arguments[0].click();", element)
        return True
    except Exception as e:
        log(f"   ! klik gagal: {e}")
        return False


def full_screenshot(driver, path):
    try:
        data = driver.execute_cdp_cmd(
            "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}
        )
        with open(path, "wb") as f:
            f.write(base64.b64decode(data["data"]))
    except Exception:
        try:
            driver.save_screenshot(path)
        except Exception as e:
            log(f"   ! screenshot gagal: {e}")


def save_snapshot(driver, out_dir, tag):
    full_screenshot(driver, os.path.join(out_dir, f"{tag}.png"))
    try:
        with open(os.path.join(out_dir, f"{tag}.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)
    except Exception as e:
        log(f"   ! simpan HTML gagal: {e}")
    log(f"📸 Snapshot disimpan: {tag}.png / {tag}.html")


def make_keys(fields):
    """Beri 'key' stabil: id kalau ada, kalau tidak seksi|kolom|baris|label."""
    seen = {}
    for f in fields:
        key = f["id"] or "|".join(
            p for p in (f["section"], f"k{f['col']}", f"b{f['row']}", f["label"]) if p
        )
        seen[key] = seen.get(key, 0) + 1
        f["key"] = key if seen[key] == 1 else f"{key}#{seen[key]}"
    return fields


def collect_fields(driver):
    return make_keys(driver.execute_script(JS_FIELDS))


def collect_toggles(driver):
    toggles = driver.execute_script(JS_TOGGLES)
    ordinal = {}
    for t in toggles:
        ordinal[t["section"]] = ordinal.get(t["section"], 0) + 1
        t["ordinal_in_section"] = ordinal[t["section"]]
    return toggles


# --------------------------------------------------------------------------- #
#  Login                                                                       #
# --------------------------------------------------------------------------- #
def login(driver):
    station_id = os.environ.get("BMKG_STATION_ID") or input("Station ID : ").strip()
    password = os.environ.get("BMKG_PASSWORD") or getpass.getpass("Password   : ")
    log("🌐 Membuka halaman login...")
    driver.get(LOGIN_URL)
    email = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "login-email"))
    )
    email.clear()
    email.send_keys(station_id)
    pw = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "login-password"))
    )
    pw.clear()
    pw.send_keys(password)
    pw.send_keys(Keys.RETURN)
    WebDriverWait(driver, 30).until(EC.url_contains("/dashboard"))
    log("✅ Login berhasil")
    driver.get(SINOPTIK_URL)
    time.sleep(2)


# --------------------------------------------------------------------------- #
#  Salin opsi dropdown                                                         #
# --------------------------------------------------------------------------- #
def close_dropdown(driver):
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        driver.execute_script("if (document.activeElement) document.activeElement.blur();")
    except Exception:
        pass
    time.sleep(0.2)


def read_options(driver, controls_id):
    """Buka satu dropdown, salin teks opsi, tutup lagi. Tidak memilih apa pun."""
    if not controls_id:
        return None, "aria-controls kosong"
    combos = driver.find_elements(
        By.XPATH, f"//div[@role='combobox' and @aria-controls='{controls_id}']"
    )
    if not combos:
        return None, "combobox tidak ditemukan"
    for _ in range(2):
        if not attempt_click(driver, combos[0]):
            continue
        try:
            WebDriverWait(driver, 4).until(
                lambda d: d.execute_script(JS_MENU_OPEN, controls_id)
            )
        except TimeoutException:
            close_dropdown(driver)
            continue
        opts = driver.execute_script(JS_OPTIONS, controls_id)
        close_dropdown(driver)
        return opts, None
    return None, "menu tidak terbuka"


def collect_options(driver, fields, options, only_keys=None):
    selects = [
        f for f in fields
        if f["kind"] == "select" and not f["disabled"]
        and (only_keys is None or f["key"] in only_keys)
        and f["key"] not in options
    ]
    for n, f in enumerate(selects, 1):
        opts, err = read_options(driver, f["controls"])
        tag = f"[{n}/{len(selects)}] {f['key']}"
        if opts is None:
            log(f"⚠️ {tag}: {err}")
            continue
        options[f["key"]] = {
            "label": f["label"], "section": f["section"], "col": f["col"],
            "current_value": f["value"], "options": opts,
        }
        log(f"✅ {tag}: {len(opts)} opsi")
    return options


# --------------------------------------------------------------------------- #
#  Uji toggle (efek + pemulihan)                                               #
# --------------------------------------------------------------------------- #
def click_toggle(driver, toggle_id):
    labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{toggle_id}']")
    if not labels:
        return False
    safe_click(driver, labels[0])
    time.sleep(1.0)
    return True


def test_toggles(driver, toggles, options, out_dir):
    """
    Klik toggle berurutan (sesuai urutan DOM) dan catat field yang menjadi aktif.
    Toggle sebelumnya dibiarkan aktif agar ketergantungan antar-lapisan terlihat.
    Di akhir semua dikembalikan ke keadaan semula (urutan terbalik).
    """
    clicked = []
    for t in toggles:
        tid = t["id"]
        t["effect"] = {"clicked": False}
        if t["disabled"]:
            t["effect"]["note"] = "toggle disabled, dilewati"
            continue
        before = {f["key"]: f for f in collect_fields(driver)}
        state_before = driver.execute_script(JS_IS_CHECKED, tid)
        log(f"🔘 Toggle {tid} ({t['section']}, kolom {t['col']}): klik...")
        if not click_toggle(driver, tid):
            t["effect"]["note"] = "label tidak ditemukan"
            continue
        clicked.append((tid, state_before))
        state_after = driver.execute_script(JS_IS_CHECKED, tid)
        after_fields = collect_fields(driver)
        after = {f["key"]: f for f in after_fields}
        newly_enabled, newly_disabled = [], []
        for k, fa in after.items():
            fb = before.get(k)
            if fb is None:
                continue
            if fb["disabled"] and not fa["disabled"]:
                newly_enabled.append({"key": k, "label": fa["label"], "kind": fa["kind"],
                                      "col": fa["col"]})
            elif not fb["disabled"] and fa["disabled"]:
                newly_disabled.append({"key": k, "label": fa["label"]})
        t["effect"] = {
            "clicked": True, "checked_before": state_before, "checked_after": state_after,
            "newly_enabled": newly_enabled, "newly_disabled": newly_disabled,
        }
        log(f"   → aktif baru: {[e['key'] for e in newly_enabled] or '(tidak ada)'}")
        # salin opsi dropdown yang baru aktif
        new_keys = {e["key"] for e in newly_enabled if e["kind"] == "select"}
        if new_keys:
            collect_options(driver, after_fields, options, only_keys=new_keys)

    save_snapshot(driver, out_dir, "form_toggle_aktif")

    # pulihkan
    for tid, state_before in reversed(clicked):
        now = driver.execute_script(JS_IS_CHECKED, tid)
        if now is not None and state_before is not None and now != state_before:
            click_toggle(driver, tid)
            now2 = driver.execute_script(JS_IS_CHECKED, tid)
            log(f"↩️ Toggle {tid} dipulihkan: {'OK' if now2 == state_before else 'GAGAL, cek manual'}")
    return toggles


# --------------------------------------------------------------------------- #
#  Laporan                                                                     #
# --------------------------------------------------------------------------- #
def build_report(fields, options, toggles, meta):
    L = []
    L.append("LAPORAN collect_web_info.py")
    L.append(f"Waktu     : {meta['waktu']}")
    L.append(f"Form siap : {meta['form_ready']}")
    L.append("")
    L.append("=== TOGGLE (tambah lapisan awan) ===")
    for t in toggles:
        eff = t.get("effect", {})
        L.append(
            f"id={t['id']:>5} | {t['section']} | kolom {t['col']} | urutan ke-{t['ordinal_in_section']} "
            f"di seksi | awal={'ON' if t['checked'] else 'off'}"
        )
        L.append(f"          tooltip: {t['tooltip']}")
        if eff.get("clicked"):
            ne = [e["key"] for e in eff["newly_enabled"]]
            L.append(f"          efek   : mengaktifkan {len(ne)} field -> {ne}")
        elif eff:
            L.append(f"          efek   : tidak diuji ({eff.get('note', '-')})")
    L.append("")
    L.append("=== FIELD PER SEKSI ===")
    sections = []
    for f in fields:
        if f["section"] not in sections:
            sections.append(f["section"])
    for s in sections:
        L.append(f"\n[{s or '(tanpa seksi)'}]")
        for f in fields:
            if f["section"] != s:
                continue
            st = "DISABLED" if f["disabled"] else "aktif"
            opt = ""
            if f["key"] in options:
                opt = f" | {len(options[f['key']]['options'])} opsi"
            L.append(f"  - {f['key']}  (label='{f['label']}', {f['kind']}, kolom {f['col']}, {st}{opt})"
                     f"  nilai='{f['value']}'")
    L.append("")
    L.append("=== DROPDOWN DISABLED YANG OPSINYA BELUM TERAMBIL ===")
    miss = [f for f in fields if f["kind"] == "select" and f["key"] not in options]
    if not miss:
        L.append("  (tidak ada)")
    for f in miss:
        L.append(f"  - {f['key']} (label='{f['label']}', disabled={f['disabled']})")
    L.append("  Catatan: dropdown yang disabled karena kondisi form (mis. elevasi saat jenis awan")
    L.append("  bukan 8/9, atau NCH saat CH='/') baru bisa disalin jika kondisinya dibuat aktif.")
    L.append("  Jalankan ulang dengan form dalam kondisi berbeda; hasilnya digabung nanti.")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #
PETUNJUK = """
============================================================
 LANGKAH MANUAL (sekali saja):
  1. Di browser yang terbuka: pilih Stasiun, Tanggal, Jam, dan Observer.
  2. Jika muncul popup (mis. 'Fill'), tutup/klik sesuai kebiasaan Anda.
  3. Tunggu sampai form SYNOP (kolom cuaca & awan) tampil penuh.
     Tips: isi CL dengan jenis 8 atau 9 (Cu/Cb) dan CM/CH bukan '/'
     supaya lebih banyak dropdown aktif dan opsinya ikut terambil.
  4. JANGAN klik Preview/Send. Kembali ke terminal ini, tekan ENTER.
============================================================
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-toggles", action="store_true", help="lewati uji toggle")
    ap.add_argument("--skip-options", action="store_true", help="lewati salin opsi dropdown")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.getcwd(), f"web_info_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    log(f"📁 Hasil akan disimpan di: {out_dir}")

    opts = Options()
    opts.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=opts)

    try:
        login(driver)
        print(PETUNJUK)
        input("Tekan ENTER jika form SYNOP sudah tampil... ")

        form_ready = bool(driver.find_elements(By.ID, FORM_MARKER_ID))
        if not form_ready:
            log(f"⚠️ Field '{FORM_MARKER_ID}' tidak ditemukan. Form mungkin belum tampil; "
                f"hasil bisa tidak lengkap.")
        save_snapshot(driver, out_dir, "form_awal")

        fields = collect_fields(driver)
        log(f"🔎 {len(fields)} field terdeteksi")

        options = {}
        if not args.skip_options:
            log("\n📋 Menyalin opsi dropdown yang aktif...")
            collect_options(driver, fields, options)

        toggles = collect_toggles(driver)
        log(f"\n🔘 {len(toggles)} toggle terdeteksi: {[t['id'] for t in toggles]}")
        if toggles and not args.no_toggles:
            test_toggles(driver, toggles, options, out_dir)

        meta = {"waktu": datetime.now().isoformat(timespec="seconds"), "form_ready": form_ready}
        with open(os.path.join(out_dir, "fields.json"), "w", encoding="utf-8") as f:
            json.dump(fields, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "options.json"), "w", encoding="utf-8") as f:
            json.dump(options, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "toggles.json"), "w", encoding="utf-8") as f:
            json.dump(toggles, f, ensure_ascii=False, indent=2)
        report = build_report(fields, options, toggles, meta)
        with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
            f.write(report)
        log(f"\n✅ Selesai. Kirim isi folder berikut ke chat:\n   {out_dir}")
        log("   (minimal: report.txt, options.json, toggles.json, fields.json)")
    except Exception as e:
        log(f"❌ Error: {e}\n{traceback.format_exc()}")
        try:
            save_snapshot(driver, out_dir, "error")
        except Exception:
            pass
    finally:
        input("\nTekan ENTER untuk menutup browser... ")
        driver.quit()


if __name__ == "__main__":
    main()
