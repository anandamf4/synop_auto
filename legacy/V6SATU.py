from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from datetime import datetime, timezone, timedelta
import time
import pandas as pd
import pyautogui
import os
import sys
import traceback
from pathlib import Path

# 🔑 Data login dan pilihan
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.config import get_credentials, load_config

CFG = load_config()
STATION_ID, PASSWORD = get_credentials()
STASIUN_YANG_DIPILIH = CFG["station"]["name"]
nama_observer = input("Masukkan nama observer: ")


# === BACA DATA EXCEL ===
def baca_data_terbaru(silent=False):
    """Fungsi untuk membaca data terbaru dari file excel dengan format yang konsisten"""
    if not silent:
        print("\n🔍 Memuat data terbaru dari file...")
    try:
        df = pd.read_excel(r"legacy/INPUT_PARAMETER.xlsx")
        df['waktu_eksekusi'] = pd.to_datetime(df['waktu_eksekusi'])
        df['jam_input'] = df['jam_input'].astype(str).str.zfill(5)
        if not silent:
            print("✅ Data berhasil dimuat")
        return df
    except Exception as e:
        print(f"❌ Gagal memuat data: {str(e)}")
        return None

# 🔧 Setup driver
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
service = Service()
driver = webdriver.Chrome(service=service, options=chrome_options)

#=============================== GENERAL ======================================#
def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView(true);", element)
    try:
        element.click()
    except:
        driver.execute_script("arguments[0].click();", element)


def wait_for_presence(driver, locator, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))
    except Exception as e:
        print(f"❌ Timeout menunggu keberadaan elemen {locator}: {e}")
        return None


def wait_for_clickable(driver, locator, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
    except Exception as e:
        print(f"❌ Timeout menunggu elemen dapat diklik {locator}: {e}")
        return None


def save_debug_snapshot(driver, tag="debug"):
    try:
        base = os.path.join(os.getcwd(), "snapshots")
        os.makedirs(base, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        png = os.path.join(base, f"{ts}_{tag}.png")
        html = os.path.join(base, f"{ts}_{tag}.html")
        try:
            driver.save_screenshot(png)
            print(f"📸 Screenshot saved: {png}")
        except Exception as e:
            print(f"⚠️ Gagal simpan screenshot: {e}")
        try:
            with open(html, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"📄 HTML snapshot saved: {html}")
        except Exception as e:
            print(f"⚠️ Gagal simpan page source: {e}")
    except Exception as e:
        print(f"⚠️ save_debug_snapshot error: {e}\n{traceback.format_exc()}")


def pilih_opsi_unsur(driver, unsur):
    try:
        opsi_list = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, f"//li[contains(text(), '{unsur}')]"))
        )
        if opsi_list:
            safe_click(driver, opsi_list[0])
            print(f"✅ Opsi dipilih (mengandung '{unsur}'): {opsi_list[0].text}")
            return True
        print(f"❌ Tidak ada opsi mengandung '{unsur}' ditemukan")
        return False
    except Exception as e:
        print(f"❌ Gagal pilih opsi '{unsur}': {e}")
        return False


def pilih_dropdown_ant_select(driver, id_div, nilai, timeout=12, max_attempts=2):
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            container = wait_for_presence(driver, (By.ID, id_div), timeout=timeout)
            if not container:
                print(f"⚠️ [{attempt}] Container {id_div} tidak ditemukan")
                time.sleep(0.6)
                continue
            driver.execute_script("arguments[0].scrollIntoView(true);", container)

            dropdown = wait_for_clickable(driver, (By.XPATH, f"//div[@id='{id_div}']//div[contains(@class,'ant-select-selection__rendered')]"), timeout=timeout)
            if not dropdown:
                print(f"⚠️ [{attempt}] Dropdown {id_div} tidak clickable")
                time.sleep(0.6)
                continue
            safe_click(driver, dropdown)
            time.sleep(0.5)

            search_input = wait_for_presence(driver, (By.XPATH, f"//div[@id='{id_div}']//input[contains(@class,'ant-select-search__field')]"), timeout=timeout)
            if search_input:
                search_input.clear()
                search_input.send_keys(nilai)
                time.sleep(0.3)
                search_input.send_keys(Keys.ENTER)
                time.sleep(0.8)
                print(f"✅ {id_div} dipilih dengan '{nilai}'")
                return True

            opsi = wait_for_clickable(driver, (By.XPATH, f"//div[@id='{id_div}']//li[contains(normalize-space(.),'{nilai}')]"), timeout=timeout)
            if opsi:
                safe_click(driver, opsi)
                print(f"✅ {id_div} dipilih dengan '{nilai}' (fallback tanpa input search)")
                time.sleep(0.8)
                return True

            print(f"⚠️ [{attempt}] Tidak menemukan input atau opsi untuk {id_div} dengan nilai '{nilai}'")
            time.sleep(0.6)
        except Exception as e:
            print(f"⚠️ [{attempt}] Gagal pilih {id_div} dengan '{nilai}': {e}")
            time.sleep(0.6)
    try:
        save_debug_snapshot(driver, f"pilih_dropdown_{id_div}_{nilai}")
    except Exception:
        pass
    print(f"❌ Gagal pilih {id_div} dengan '{nilai}' setelah {max_attempts} percobaan")
    return False


def isi_input_text(driver, id_input, nilai, timeout=12):
    try:
        input_field = wait_for_presence(driver, (By.ID, id_input), timeout=timeout)
        if not input_field:
            return False
        driver.execute_script("arguments[0].scrollIntoView(true);", input_field)
        input_field.clear()
        input_field.send_keys(str(nilai))
        input_field.send_keys(Keys.RETURN)
        print(f"✅ {id_input} diisi dengan {nilai}")
        return True
    except Exception as e:
        print(f"❌ Gagal isi {id_input}: {e}")
        try:
            save_debug_snapshot(driver, f"isi_input_{id_input}")
        except Exception:
            pass
        return False


def attempt_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        try:
            element.click()
            return True
        except Exception:
            try:
                ActionChains(driver).move_to_element(element).pause(0.1).click().perform()
                return True
            except Exception:
                driver.execute_script("arguments[0].click();", element)
                return True
    except Exception as e:
        print(f"⚠️ attempt_click gagal: {e}")
        return False


def pilih_opsi_ant_select(driver, combobox, target_teks, nama_field):
    aria_id = combobox.get_attribute("aria-controls")
    if not aria_id:
        print(f"❌ {nama_field}: aria-controls tidak ditemukan")
        return False

    def nilai_terpilih():
        values = combobox.find_elements(
            By.CSS_SELECTOR, ".ant-select-selection-selected-value"
        )
        if not values:
            return ""
        return (values[0].get_attribute("title") or values[0].text).strip()

    try:
        if target_teks in nilai_terpilih():
            print(f"✅ {nama_field} sudah berisi '{target_teks}'")
            return True

        target_normalized = " ".join(target_teks.split())
        for attempt in range(2):
            if not attempt_click(driver, combobox):
                continue

            try:
                WebDriverWait(driver, 3).until(
                    EC.visibility_of_element_located((By.ID, aria_id))
                )
            except TimeoutException:
                if attempt == 0:
                    combobox.send_keys(Keys.SPACE)
                continue

            opsi = WebDriverWait(driver, 5).until(
                lambda d: next(
                    (
                        item
                        for item in d.find_elements(
                            By.XPATH, f"//div[@id='{aria_id}']//li"
                        )
                        if item.is_displayed()
                        and target_normalized in " ".join(item.text.split())
                        and item.get_attribute("aria-disabled") != "true"
                    ),
                    False,
                )
            )
            if not attempt_click(driver, opsi):
                continue

            WebDriverWait(driver, 3).until(
                lambda _: target_normalized in " ".join(nilai_terpilih().split())
            )
            print(f"✅ {nama_field} dipilih: {target_teks}")
            return True

        print(
            f"❌ {nama_field}: menu '{aria_id}' tidak terbuka "
            f"atau opsi '{target_teks}' tidak berhasil dipilih"
        )
    except Exception as e:
        print(
            f"❌ {nama_field}: gagal memilih '{target_teks}': "
            f"{type(e).__name__}: {e}"
        )
    return False


def click_button_by_text(driver, button_text, timeout=10, exact=False):
    normalized = button_text.strip().lower()
    if exact:
        xpath = f"//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='{normalized}']"
    else:
        xpath = f"//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{normalized}')]"
    try:
        button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        if not attempt_click(driver, button):
            raise Exception("click action gagal")
        print(f"✅ Tombol '{button_text}' berhasil diklik")
        return True
    except Exception as e:
        print(f"❌ Gagal klik tombol '{button_text}': {e}")
        return False


def wait_for_modal_to_disappear(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(
                "return document.querySelectorAll('div.swal2-container.swal2-center.swal2-backdrop-show, div.ant-modal-wrap').length === 0;"
            )
        )
        return True
    except Exception:
        return False


def wait_for_send_ok_button(driver, timeout=12):
    qc_popup_xpath = (
        "//div[contains(@class,'swal2-container') and contains(@class,'swal2-backdrop-show')]"
        "//div[contains(@class,'swal2-popup') and "
        ".//div[contains(@class,'swal2-title') and contains(translate(normalize-space(.),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'koreksi qc')]]"
    )
    qc_submit_xpath = (
        qc_popup_xpath
        +
        "//button[translate(normalize-space(.),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='submit']"
    )
    ok_xpath = "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']"
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            for button in driver.find_elements(By.XPATH, qc_submit_xpath):
                if button.is_displayed() and button.is_enabled():
                    if not attempt_click(driver, button):
                        print("❌ Tombol Submit pada popup Koreksi QC gagal diklik")
                        return False
                    print("✅ Popup Koreksi QC terdeteksi; tombol Submit berhasil diklik")

                    try:
                        WebDriverWait(driver, timeout).until(
                            lambda d: not any(
                                popup.is_displayed()
                                for popup in d.find_elements(
                                    By.XPATH, qc_popup_xpath
                                )
                            )
                            or any(
                                button.is_displayed()
                                for button in d.find_elements(
                                    By.XPATH, ok_xpath
                                )
                            )
                        )
                    except TimeoutException:
                        print("⚠️ Popup Koreksi QC belum menutup setelah Submit")
                        return False
                    return True

            for button in driver.find_elements(By.XPATH, ok_xpath):
                if button.is_displayed():
                    print("✅ Popup Koreksi QC tidak muncul; tombol OK alur normal terdeteksi")
                    return True
        except Exception as e:
            print(f"⚠️ Error saat memeriksa konfirmasi setelah SEND: {e}")
        time.sleep(0.5)

    print(
        f"⚠️ Popup Koreksi QC maupun tombol OK tidak muncul setelah SEND "
        f"({timeout}s)"
    )
    return False


def click_button_containing_words(driver, words, timeout=10):
    try:
        buttons = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.XPATH, "//button"))
        )
        words = [w.strip().lower() for w in words if w.strip()]
        for btn in buttons:
            try:
                text = btn.text.strip().lower()
                if text and all(word in text for word in words):
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    try:
                        btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)
                    print(f"✅ Tombol dengan teks '{text}' berhasil diklik")
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        print(f"❌ Gagal mencari tombol berdasarkan kata: {e}")
        return False


def wait_for_submit_progress(driver, timeout=10):
    start = time.time()
    print(f"⏳ Menunggu progress submit selama {timeout}s...")
    while time.time() - start < timeout:
        try:
            if driver.find_elements(By.XPATH, "//div[contains(@id,'send-gts-message')]"):
                print("✅ Deteksi modal send-gts-message muncul")
                return True
            if driver.find_elements(By.XPATH, "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send to inaswitching')]"):
                print("✅ Deteksi tombol 'Send to INASwitching' muncul")
                return True
            if driver.find_elements(By.XPATH, "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"):
                print("✅ Deteksi tombol 'Send' muncul")
                return True
            if driver.find_elements(By.XPATH, "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']"):
                print("✅ Deteksi tombol 'OK' muncul")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    print("⚠️ Tidak ada progress submit terdeteksi setelah klik")
    return False


#========================================= AWAN RENDAH ======================================#
def isi_jenis_dan_jumlah_awan_Rendah(driver, jenis_target, jumlah_target):
    try:
        combobox_jenis = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@id='cloud_low_cover_oktas']/ancestor::div[contains(@class,'row')]/following-sibling::div[contains(@class,'row')]//div[@role='combobox']"
            ))
        )
        aria_id_jenis = combobox_jenis.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Jenis Awan Rendah): {aria_id_jenis}")
        if not pilih_opsi_ant_select(
            driver, combobox_jenis, jenis_target, "Jenis Awan Rendah"
        ):
            return False
        time.sleep(0.5)

        combobox_jumlah = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@id='cloud_low_cover_oktas']/ancestor::div[contains(@class,'row')]/following-sibling::div[contains(@class,'row')][2]//div[@role='combobox']"
            ))
        )
        aria_id_jumlah = combobox_jumlah.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Jumlah Awan Rendah): {aria_id_jumlah}")
        if not pilih_opsi_ant_select(
            driver, combobox_jumlah, jumlah_target, "Jumlah Awan Rendah"
        ):
            return False
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal isi Jenis/Jumlah Awan Rendah: {type(e).__name__}: {e}")
        return False


def pilih_arah_sebenarnya(driver, target_teks):
    try:
        combobox = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@id='cloud_elevation_1_angle_ec']/ancestor::div[contains(@class,'row')]/following-sibling::div//div[@role='combobox']"
            ))
        )
        aria_id = combobox.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Arah Sebenarnya): {aria_id}")

        safe_click(driver, combobox)
        time.sleep(0.5)

        opsi = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH, f"//div[@id='{aria_id}']//li[contains(normalize-space(),\"{target_teks}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi)
        safe_click(driver, opsi)
        print(f"✅ Arah Sebenarnya dipilih: {target_teks}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal pilih Arah Sebenarnya: {e}")
        try:
            save_debug_snapshot(driver, f"pilih_arah_sebenarnya_{target_teks}")
        except Exception:
            pass
        return False


def klik_switch_jika_type(driver, id_div_cloud_type="cloud_low_type_cl", id_label_switch="775"):
    try:
        selected = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, f"//div[@id='{id_div_cloud_type}']//div[contains(@class,'ant-select-selection-selected-value')]"))
        )
        nilai = selected.get_attribute("title").strip()
        print(f"✅ Tipe awan rendah terpilih: {nilai}")

        if nilai.startswith("2") or nilai.startswith("3") or nilai.startswith("9"):
            print(f"🔔 Tipe awan {nilai} memerlukan klik switch.")
            label = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, f"//label[@for='{id_label_switch}']"))
            )
            safe_click(driver, label)
            print(f"✅ Switch dengan label for='{id_label_switch}' diklik.")
            return True

        print(f"ℹ️ Tipe awan {nilai} tidak memerlukan klik switch.")
        return False

    except Exception as e:
        print(f"❌ Gagal cek & klik switch: {e}")
        return False

def isi_jenis_dan_jumlah_awan_rendah_2(driver, jenis_target, jumlah_target):
    try:
        row_jenis = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'row mt-5 pr-1')]"))
        )
        combobox_jenis = row_jenis.find_element(By.XPATH, ".//div[@role='combobox']")
        aria_id_jenis = combobox_jenis.get_attribute("aria-controls")
        print(f"✅ ID combobox Jenis Awan Rendah 2: {aria_id_jenis}")

        safe_click(driver, combobox_jenis)
        time.sleep(0.5)

        opsi_jenis = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, f"//div[@id='{aria_id_jenis}']//li[contains(normalize-space(),\"{jenis_target}\")]"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi_jenis)
        safe_click(driver, opsi_jenis)
        print(f"✅ Jenis Awan Rendah 2 dipilih: {jenis_target}")
        time.sleep(0.5)

        combobox_jumlah = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH, "//div[contains(@class,'row mt-5 pr-1')]/following-sibling::div//div[@role='combobox']"
            ))
        )
        aria_id_jumlah = combobox_jumlah.get_attribute("aria-controls")
        print(f"✅ ID combobox Jumlah Awan Rendah 2: {aria_id_jumlah}")

        safe_click(driver, combobox_jumlah)
        time.sleep(0.5)

        opsi_jumlah = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, f"//div[@id='{aria_id_jumlah}']//li[contains(normalize-space(),\"{jumlah_target}\")]"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi_jumlah)
        safe_click(driver, opsi_jumlah)
        print(f"✅ Jumlah Awan Rendah 2 dipilih: {jumlah_target}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal isi Jenis/Jumlah Awan Rendah 2: {e}")
        return False

def pilih_arah_2(driver, target_teks):
    try:
        combobox = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@id='cloud_low_peak_2']/parent::div/following-sibling::div//div[@role='combobox']"
            ))
        )
        aria_id = combobox.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Arah 2): {aria_id}")

        safe_click(driver, combobox)
        time.sleep(0.5)

        opsi = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH, f"//div[@id='{aria_id}']//li[contains(normalize-space(),\"{target_teks}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi)
        safe_click(driver, opsi)
        print(f"✅ Arah Awan Rendah 2 dipilih: {target_teks}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal pilih Arah Awan Rendah 2: {e}")
        try:
            save_debug_snapshot(driver, f"pilih_arah_2_{target_teks}")
        except Exception:
            pass
        return False

def pilih_arah_sebenarnya_2(driver, target_teks):
    try:
        combobox = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@id='cloud_elevation_2_angle_ec']/ancestor::div[contains(@class,'row')]/following-sibling::div//div[@role='combobox']"
            ))
        )
        aria_id = combobox.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Arah Sebenarnya 2): {aria_id}")

        safe_click(driver, combobox)
        time.sleep(0.5)

        opsi = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH, f"//div[@id='{aria_id}']//li[contains(normalize-space(),\"{target_teks}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi)
        safe_click(driver, opsi)
        print(f"✅ Arah Sebenarnya 2 dipilih: {target_teks}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal pilih Arah Sebenarnya 2: {e}")
        try:
            save_debug_snapshot(driver, f"pilih_arah_sebenarnya_2_{target_teks}")
        except Exception:
            pass
        return False

def pilih_arah_Awan_Rendah(driver, target_teks):
    try:
        combobox = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@id='cloud_low_peak_1']/parent::div/following-sibling::div//div[@role='combobox']"
            ))
        )
        aria_id = combobox.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Arah Awan Rendah): {aria_id}")
        if not pilih_opsi_ant_select(
            driver, combobox, target_teks, "Arah Awan Rendah"
        ):
            return False
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal pilih Arah Awan Rendah: {type(e).__name__}: {e}")
        try:
            save_debug_snapshot(driver, f"pilih_arah_awan_rendah_{target_teks}")
        except Exception:
            pass
        return False

#========================================= AWAN MENENGAH ======================================#
def isi_jenis_dan_jumlah_awan_menengah(driver, jenis_target, jumlah_target):
    try:
        combobox_jenis = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@id='cloud_med_cover_oktas']/ancestor::div[contains(@class,'row')]/following-sibling::div[contains(@class,'row')]//div[@role='combobox']"
            ))
        )
        aria_id_jenis = combobox_jenis.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Jenis Awan Menengah): {aria_id_jenis}")

        safe_click(driver, combobox_jenis)
        time.sleep(0.5)

        opsi_jenis = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                f"//div[@id='{aria_id_jenis}']//li[contains(normalize-space(),\"{jenis_target}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi_jenis)
        safe_click(driver, opsi_jenis)
        print(f"✅ Jenis Awan Menengah dipilih: {jenis_target}")
        time.sleep(0.5)

        combobox_jumlah = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@id='cloud_med_cover_oktas']/ancestor::div[contains(@class,'row')]/following-sibling::div[contains(@class,'row')][2]//div[@role='combobox']"
            ))
        )
        aria_id_jumlah = combobox_jumlah.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Jumlah Awan Menengah): {aria_id_jumlah}")

        safe_click(driver, combobox_jumlah)
        time.sleep(0.5)

        opsi_jumlah = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                f"//div[@id='{aria_id_jumlah}']//li[contains(normalize-space(),\"{jumlah_target}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi_jumlah)
        safe_click(driver, opsi_jumlah)
        print(f"✅ Jumlah Awan Menengah dipilih: {jumlah_target}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal isi Jenis/Jumlah Awan Menengah: {e}")
        return False

def pilih_arah_Awan_Menengah(driver, target_teks):
    try:
        combobox = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@id='cloud_med_base_1']/parent::div/following-sibling::div//div[@role='combobox']"
            ))
        )
        aria_id = combobox.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Arah Awan Menengah): {aria_id}")

        safe_click(driver, combobox)
        time.sleep(0.5)

        opsi = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH, f"//div[@id='{aria_id}']//li[contains(normalize-space(),\"{target_teks}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi)
        safe_click(driver, opsi)
        print(f"✅ Arah Awan Menengah dipilih: {target_teks}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal pilih Arah Awan Menengah: {e}")
        try:
            save_debug_snapshot(driver, f"pilih_arah_awan_menengah_{target_teks}")
        except Exception:
            pass
        return False

#===================================== AWAN TINGGI ======================================#
def isi_jenis_dan_jumlah_awan_Tinggi(driver, jenis_target, jumlah_target):
    try:
        combobox_jenis = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@id='cloud_high_cover_oktas']/ancestor::div[contains(@class,'row')]/following-sibling::div[contains(@class,'row')]//div[@role='combobox']"
            ))
        )
        aria_id_jenis = combobox_jenis.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Jenis Awan Tinggi): {aria_id_jenis}")

        safe_click(driver, combobox_jenis)
        time.sleep(0.5)

        opsi_jenis = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                f"//div[@id='{aria_id_jenis}']//li[contains(normalize-space(),\"{jenis_target}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi_jenis)
        safe_click(driver, opsi_jenis)
        print(f"✅ Jenis Awan Tinggi dipilih: {jenis_target}")
        time.sleep(0.5)

        combobox_jumlah = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH,
                "//div[@id='cloud_high_cover_oktas']/ancestor::div[contains(@class,'row')]/following-sibling::div[contains(@class,'row')][2]//div[@role='combobox']"
            ))
        )
        aria_id_jumlah = combobox_jumlah.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Jumlah Awan Tinggi): {aria_id_jumlah}")

        safe_click(driver, combobox_jumlah)
        time.sleep(0.5)

        opsi_jumlah = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                f"//div[@id='{aria_id_jumlah}']//li[contains(normalize-space(),\"{jumlah_target}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi_jumlah)
        safe_click(driver, opsi_jumlah)
        print(f"✅ Jumlah Awan Tinggi dipilih: {jumlah_target}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal isi Jenis/Jumlah Awan Tinggi: {e}")
        return False

def pilih_arah_Awan_Tinggi(driver, target_teks):
    try:
        combobox = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//input[@id='cloud_high_base_1']/parent::div/following-sibling::div//div[@role='combobox']"
            ))
        )
        aria_id = combobox.get_attribute("aria-controls")
        print(f"✅ Dapat aria-controls ID (Arah Awan Tinggi): {aria_id}")

        safe_click(driver, combobox)
        time.sleep(0.5)

        opsi = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH, f"//div[@id='{aria_id}']//li[contains(normalize-space(),\"{target_teks}\")]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", opsi)
        safe_click(driver, opsi)
        print(f"✅ Arah Awan Tinggi dipilih: {target_teks}")
        time.sleep(0.5)
        return True

    except Exception as e:
        print(f"❌ Gagal pilih Arah Awan Tinggi: {e}")
        try:
            save_debug_snapshot(driver, f"pilih_arah_awan_tinggi_{target_teks}")
        except Exception:
            pass
        return False

#=================================================Pengiriman=========================================================# 
def submit_with_retry(driver, action_name, action_func, max_attempts=3):
    """
    Retry logic untuk submission actions dengan exponential backoff.
    Jika semua attempt gagal, save debug snapshot.
    """
    start_time = time.time()
    for attempt in range(1, max_attempts + 1):
        try:
            attempt_start = time.time()
            print(f"🔄 [{attempt}/{max_attempts}] Mencoba {action_name}...")
            if action_func():
                elapsed = time.time() - attempt_start
                print(f"✅ {action_name} berhasil pada attempt {attempt} ({elapsed:.2f}s)")
                return True
            else:
                elapsed = time.time() - attempt_start
                wait_time = 1 + (attempt - 1) * 0.5
                if attempt < max_attempts:
                    print(f"⏳ {action_name} gagal ({elapsed:.2f}s), menunggu {wait_time}s sebelum retry...")
                    time.sleep(wait_time)
        except Exception as e:
            elapsed = time.time() - attempt_start
            wait_time = 1 + (attempt - 1) * 0.5
            print(f"⚠️ [{attempt}] Exception saat {action_name} ({elapsed:.2f}s): {e}")
            if attempt < max_attempts:
                print(f"⏳ Menunggu {wait_time}s sebelum retry...")
                time.sleep(wait_time)

    total_elapsed = time.time() - start_time
    print(f"❌ {action_name} gagal setelah {max_attempts} percobaan (total {total_elapsed:.2f}s)")
    try:
        save_debug_snapshot(driver, f"failed_{action_name}")
    except Exception:
        pass
    return False


def wait_for_preview_modal(driver, timeout=10):
    modal_xpaths = [
        "//div[@id='modal-preview' and contains(@class,'show') and contains(@class,'modal') and @aria-modal='true']",
        "//div[contains(@class,'swal2-container') and contains(@class,'swal2-center')]",
        "//div[contains(@class,'ant-modal-wrap') and not(contains(@style,'display: none'))]",
    ]
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: any(
                el.is_displayed()
                for xpath in modal_xpaths
                for el in d.find_elements(By.XPATH, xpath)
            )
        )
        return True
    except Exception:
        return False

def Preview(driver):
    try:
        preview_xpath = "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='preview & generate sandi']"
        try:
            fill_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, preview_xpath))
            )
        except Exception:
            fill_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn.mr-1.btn-warning.btn-sm"))
            )

        if not attempt_click(driver, fill_button):
            raise Exception("Klik Preview gagal")

        print("✅ Tombol Preview berhasil diklik")
        time.sleep(0.5)
        if not wait_for_preview_modal(driver, timeout=10):
            print("⚠️ Tombol Preview diklik, tetapi preview modal tidak muncul dalam 10 detik")
            save_debug_snapshot(driver, "preview_clicked_no_modal")
            return False
        return True
    except Exception as e:
        print(f"❌ Gagal klik tombol Preview: {e}")
        return False


def Preview_OK(driver):
    ok_xpath = (By.XPATH, "//div[@id='modal-preview']//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']")
    try:
        ok_btn = wait_for_clickable(driver, ok_xpath, timeout=12)
        if not ok_btn:
            print("❌ Tombol Preview OK tidak ditemukan di modal preview berdasarkan teks")
            return False

        if not attempt_click(driver, ok_btn):
            print("❌ Tombol Preview OK ditemukan tetapi klik gagal")
            save_debug_snapshot(driver, "preview_ok_click_failed")
            return False

        print("✅ Tombol Preview OK berhasil diklik")
        return True
    except Exception as e:
        print(f"❌ Gagal klik tombol 'ok': {e}")
        try:
            save_debug_snapshot(driver, "preview_ok_exception")
        except Exception:
            pass
        return False


def SEND_GTS(driver):
    # [FIX] Tambah pre-wait modal + verifikasi in_modal untuk mencegah klik tombol yang salah
    modal_send_xpath = "//div[contains(@id,'send-gts-message')]//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"
    modal_xpath = "//div[contains(@class,'swal2-container') or contains(@class,'ant-modal-wrap')]//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"
    send_exact_xpath = "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='send']"
    timeout = 15
    poll = 0.25
    start = time.time()

    # Pre-wait: tunggu modal GTS benar-benar muncul sebelum mencari tombol SEND
    print(f"⏳ Menunggu modal GTS muncul sebelum mencari tombol SEND (maks 10s)...")
    modal_appeared = False
    modal_indicators = [
        "//div[contains(@id,'send-gts-message')]",
        "//div[contains(@class,'swal2-container') and contains(@class,'swal2-backdrop-show')]",
        "//div[contains(@class,'ant-modal-wrap') and not(contains(@style,'display: none'))]",
    ]
    wait_modal_start = time.time()
    while time.time() - wait_modal_start < 10:
        for xpath in modal_indicators:
            try:
                els = driver.find_elements(By.XPATH, xpath)
                if els and any(e.is_displayed() for e in els):
                    print(f"✅ Modal GTS terdeteksi ({xpath.split(']')[0]}...)")
                    modal_appeared = True
                    break
            except Exception:
                pass
        if modal_appeared:
            time.sleep(0.5)
            break
        time.sleep(0.3)

    if not modal_appeared:
        print("⚠️ Modal GTS tidak terdeteksi dalam 10s, tetap mencoba cari tombol SEND...")

    print(f"⏳ Mencari tombol SEND (poll {poll}s) sampai {timeout}s...")
    try:
        while time.time() - start < timeout:
            try:
                # 1) Prioritas: tombol SEND di modal send-gts-message
                try:
                    modal_buttons = driver.find_elements(By.XPATH, modal_send_xpath)
                except Exception as e:
                    print(f"⚠️ Error mencari tombol SEND di modal send-gts-message: {e}")
                    modal_buttons = []
                for btn in modal_buttons:
                    try:
                        if btn and btn.is_displayed():
                            elapsed = time.time() - start
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            print(f"✅ Tombol SEND berhasil diklik (modal send-gts-message) setelah {elapsed:.2f}s")
                            if wait_for_send_ok_button(driver, timeout=12):
                                return True
                            print("⚠️ Tombol OK belum muncul setelah klik SEND di modal; menunggu ekstra sebelum retry...")
                            time.sleep(2)
                            continue
                    except Exception:
                        continue

                # 2) Cari tombol SEND hanya di dalam modal dengan verifikasi JS
                try:
                    modal_only_candidates = driver.find_elements(By.XPATH, modal_xpath)
                except Exception:
                    modal_only_candidates = []

                for btn in modal_only_candidates:
                    try:
                        if btn and btn.is_displayed():
                            text = btn.text.strip().lower()
                            if text != 'send':
                                continue
                            in_modal = driver.execute_script(
                                """
                                var el = arguments[0];
                                while (el) {
                                    var cls = (el.className || '').toString();
                                    if (cls.includes('swal2-container') ||
                                        cls.includes('ant-modal-wrap') ||
                                        (el.id && el.id.includes('send-gts-message'))) {
                                        return true;
                                    }
                                    el = el.parentElement;
                                }
                                return false;
                                """, btn
                            )
                            if not in_modal:
                                print(f"⚠️ Tombol '{text}' ditemukan tapi bukan di modal, dilewati")
                                continue
                            elapsed = time.time() - start
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            print(f"✅ Tombol SEND berhasil diklik (modal verified) setelah {elapsed:.2f}s")
                            if wait_for_send_ok_button(driver, timeout=12):
                                return True
                            print("⚠️ Tombol OK belum muncul setelah klik SEND modal verified; retry...")
                            time.sleep(2)
                    except Exception:
                        continue

                # 3) Fallback: cari by text dengan verifikasi in_modal
                candidates = []
                try:
                    candidates.extend(driver.find_elements(By.XPATH, send_exact_xpath))
                except Exception:
                    pass

                for btn in candidates:
                    try:
                        if btn and btn.is_displayed():
                            text = btn.text.strip().lower()
                            if text != 'send':
                                continue
                            in_modal = driver.execute_script(
                                """
                                var el = arguments[0];
                                while (el) {
                                    var cls = (el.className || '').toString();
                                    if (cls.includes('swal2-container') ||
                                        cls.includes('ant-modal-wrap') ||
                                        (el.id && el.id.includes('send-gts-message'))) {
                                        return true;
                                    }
                                    el = el.parentElement;
                                }
                                return false;
                                """, btn
                            )
                            if not in_modal:
                                print(f"⚠️ Tombol 'send' di luar modal, dilewati untuk menghindari klik salah")
                                continue
                            elapsed = time.time() - start
                            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            print(f"✅ Tombol SEND berhasil diklik (by text, in modal) setelah {elapsed:.2f}s")
                            if wait_for_send_ok_button(driver, timeout=12):
                                return True
                            print("⚠️ Tombol OK belum muncul setelah klik SEND; retry...")
                            time.sleep(2)
                    except Exception:
                        continue

            except Exception as e:
                print(f"⚠️ Exception selama polling SEND_GTS loop: {e}")
            time.sleep(poll)
    except Exception as e:
        print(f"⚠️ Exception saat polling SEND_GTS: {e}")

    print("❌ Tombol SEND tidak ditemukan berdasarkan teks maupun modal XPath")
    try:
        save_debug_snapshot(driver, "failed_send_gts")
    except Exception:
        pass
    return False


def SEND_INASWITCH(driver):
    try:
        buttons = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//button"))
        )
        for btn in buttons:
            text = btn.text.strip().lower()
            if "send to inaswitching" in text:
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
                print("✅ Tombol 'Send to INASwitching' berhasil diklik")
                return True
        print("❌ Tombol 'Send to INASwitching' tidak ditemukan berdasarkan teks")
        return False
    except Exception as e:
        print(f"❌ Gagal klik tombol 'Send to INASwitching': {e}")
        return False

def SEND_SEND_SUBMIT(driver):
    if click_button_by_text(driver, "send & submit", timeout=8, exact=False):
        time.sleep(1)
        if wait_for_submit_progress(driver, timeout=8):
            print("✅ Tombol 'Send & Submit' berhasil diklik dan progress terdeteksi")
            return True
        print("⚠️ Tombol 'Send & Submit' diklik tetapi progress tidak terdeteksi")
        return False
    if click_button_containing_words(driver, ["send", "submit"], timeout=8):
        time.sleep(1)
        if wait_for_submit_progress(driver, timeout=8):
            print("✅ Tombol 'Send & Submit' berhasil diklik (fallback) dan progress terdeteksi")
            return True
        print("⚠️ Tombol 'Send & Submit' diklik (fallback) tetapi progress tidak terdeteksi")
        return False
    print("❌ Tombol 'Send & Submit' tidak ditemukan")
    return False


def SEND_INASWITCH_SUBMIT(driver):
    if click_button_by_text(driver, "send to inaswitching", timeout=8, exact=False):
        time.sleep(1)
        if wait_for_submit_progress(driver, timeout=8):
            print("✅ Tombol 'Send to INASwitching' berhasil diklik dan progress terdeteksi")
            return True
        print("⚠️ Tombol 'Send to INASwitching' diklik tetapi progress tidak terdeteksi")
        return False
    if click_button_containing_words(driver, ["send", "inaswitching"], timeout=8):
        time.sleep(1)
        if wait_for_submit_progress(driver, timeout=8):
            print("✅ Tombol 'Send to INASwitching' berhasil diklik (fallback) dan progress terdeteksi")
            return True
        print("⚠️ Tombol 'Send to INASwitching' diklik (fallback) tetapi progress tidak terdeteksi")
        return False
    print("❌ Tombol 'Send to INASwitching' tidak ditemukan")
    return False


def SEND_GTS_OK(driver):
    try:
        ok_btn = wait_for_clickable(driver, (
            By.XPATH,
            "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']"
        ), timeout=10)
        if ok_btn:
            driver.execute_script("arguments[0].scrollIntoView(true);", ok_btn)
            try:
                ok_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", ok_btn)
            print("✅ Tombol SEND GTS OK berhasil diklik")
            return True
        print("❌ Tombol GTS OK tidak ditemukan berdasarkan teks")
        return False
    except Exception as e:
        print(f"❌ Gagal klik tombol 'ok': {e}")
        return False


#=================================================Main Browser=======================================================#
def login(driver):
    print("\n" + "="*60)
    print("🌐 MEMULAI PROSES LOGIN")
    print("="*60)

    print("🌐 Membuka halaman login...")
    driver.get("https://bmkgsatu.bmkg.go.id/login")
    time.sleep(2)

    try:
        print("⏳ Menunggu email field...")
        email_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "login-email"))
        )
        print("✅ Email field ditemukan")
        driver.execute_script("arguments[0].scrollIntoView(true);", email_input)
        time.sleep(0.2)
        email_input.clear()
        time.sleep(0.2)
        email_input.send_keys(STATION_ID)
        print(f"✅ Email ({STATION_ID}) diisi")
        time.sleep(0.2)
    except Exception as e:
        print(f"❌ Error saat mengisi email: {e}")
        raise

    try:
        print("⏳ Menunggu password field...")
        password_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "login-password"))
        )
        print("✅ Password field ditemukan")
        driver.execute_script("arguments[0].scrollIntoView(true);", password_input)
        time.sleep(0.2)
        password_input.clear()
        time.sleep(0.2)
        password_input.send_keys(PASSWORD)
        print("✅ Password dimasukkan")
        time.sleep(0.2)
    except Exception as e:
        print(f"❌ Error saat mengisi password: {e}")
        raise

    try:
        print("⏳ Mencari tombol login atau menekan ENTER...")
        password_input.send_keys(Keys.RETURN)
        print("✅ ENTER ditekan")
        time.sleep(2)
    except Exception as e:
        print(f"⚠️ ENTER tidak berhasil: {e}")
        try:
            print("⏳ Mencari tombol submit...")
            submit_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            driver.execute_script("arguments[0].click();", submit_button)
            print("✅ Tombol login diklik via JavaScript")
            time.sleep(2)
        except Exception as e2:
            print(f"❌ Gagal klik tombol login: {e2}")
            raise

    WebDriverWait(driver, 20).until(EC.url_contains("/dashboard"))
    print("✅ Login berhasil")

    print("🌐 Membuka halaman sinoptik...")
    driver.get("https://bmkgsatu.bmkg.go.id/meteorologi/sinoptik")
    time.sleep(2)


def has_opencv():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def klik_tombol_oke_popup(image_path=r"legacy/OK.PNG", max_wait=20):
    print("🔍 Mendeteksi tombol Oke pada popup...")
    use_confidence = has_opencv()
    if not use_confidence:
        print("⚠️ OpenCV tidak ditemukan. Mencoba tanpa confidence parameter.")
    for i in range(max_wait):
        if use_confidence:
            lokasi = pyautogui.locateOnScreen(image_path, confidence=0.8)
        else:
            lokasi = pyautogui.locateOnScreen(image_path)
        if lokasi:
            center = pyautogui.center(lokasi)
            pyautogui.moveTo(center.x, center.y, duration=0.3)
            pyautogui.click()
            print(f"✅ Tombol OK berhasil diklik pada {center}")
            return True
        else:
            print(f"⏳ Menunggu tombol OK muncul... ({i+1}/{max_wait})")
            time.sleep(1)
    print("❌ Gagal menemukan tombol OK popup.")
    return False


def memilih_stasiun(driver):
    print("🏢 Memilih stasiun...")
    stasiun_dropdown = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Stasiun')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"))
    )
    safe_click(driver, stasiun_dropdown)
    time.sleep(0.3)
    pilih_opsi_unsur(driver, STASIUN_YANG_DIPILIH)
    print("✅ Stasiun dipilih")


def memilih_observer(driver):
    print("🏢 Memilih nama observer...")
    for attempt in range(1, 4):
        try:
            observer_dropdown = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//label[contains(text(), 'Nama Observer')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"
                ))
            )
            safe_click(driver, observer_dropdown)
            time.sleep(1.5)  # tambah delay agar opsi dropdown sempat muncul

            if pilih_opsi_unsur(driver, nama_observer):
                print("✅ Observer dipilih")
                return True  # [FIX] hanya print sukses kalau benar-benar berhasil

            print(f"⚠️ Attempt {attempt}/3: Opsi observer tidak ditemukan, retry...")
            time.sleep(1)

        except Exception as e:
            print(f"⚠️ Attempt {attempt}/3: Exception saat pilih observer: {e}")
            save_debug_snapshot(driver, f"observer_attempt_{attempt}_failed")
            time.sleep(1)

    print("❌ Gagal memilih observer setelah 3 percobaan")
    save_debug_snapshot(driver, "observer_gagal_total")
    return False  # [FIX] return False agar caller tahu gagal


def memilih_tanggal(driver):
    local_now = datetime.now()
    utc_target_time = local_now - timedelta(hours=7)
    utc_date = utc_target_time.strftime("%Y-%m-%d")
    print(f"Memilih tanggal: {utc_date}...")
    datepicker_button = driver.find_element(By.ID, "input-datepicker")
    try:
        WebDriverWait(driver, 15).until(
            EC.invisibility_of_element_located((By.XPATH, "//div[contains(@class, 'position-absolute') and contains(@class, 'bg-light')]"))
        )
        print("Overlay disappeared, proceeding to click datepicker...")
    except Exception as e:
        print(f"Overlay still present or not found: {e}")
        try:
            overlay = driver.find_element(By.XPATH, "//div[contains(@class, 'position-absolute') and contains(@class, 'bg-light')]")
            driver.execute_script("arguments[0].style.display = 'none';", overlay)
            print("Overlay dismissed via JavaScript.")
        except Exception as e:
            print(f"Could not dismiss overlay: {e}")

    try:
        driver.execute_script("arguments[0].click();", datepicker_button)
        print("Datepicker button clicked via JavaScript.")
    except Exception as e:
        print(f"Failed to click datepicker button via JavaScript: {e}")
        time.sleep(1)
        datepicker_button.click()

    xpath_date = f"//div[@role='button' and @data-date='{utc_date}']"
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.element_to_be_clickable((By.XPATH, xpath_date))).click()
        print(f"✅ Tanggal '{utc_date}' berhasil dipilih.")
        time.sleep(0.5)
    except Exception as e:
        print(f"⚠️ Gagal memilih tanggal {utc_date}: {e}. Memastikan datepicker ditutup...")
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)


def isi_per_jam(driver, row):
    try:
        print(f"\n⏰ Memilih jam {row['jam_input']}...")
        jam_wrap = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Jam')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"))
        )
        safe_click(driver, jam_wrap)
        time.sleep(1)

        jam_raw = str(row['jam_input'])
        if ":" in jam_raw:
            jam_str = jam_raw.strip()[:2] + ":00"
        else:
            jam_str = str(int(float(jam_raw))).zfill(2) + ":00"

        if not pilih_opsi_unsur(driver, jam_str):
            print(f"❌ Opsi jam {jam_str} tidak bisa dipilih")
            return False
        print(f"✅ Jam {jam_str} dipilih")
        return True
    except Exception as e:
        print(f"❌ Gagal pilih jam: {e}")
        return False


def Fill_AWS_Digi(driver):
    try:
        fill_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.swal2-confirm.btn.btn-primary"))
        )
        fill_button.click()
        print("✅ Tombol Fill pada popup berhasil diklik")
        return True
    except Exception:
        print("ℹ️ Tidak ada popup AWS Digi atau tombol Fill tidak muncul")
        return False


def isi_data(driver, row):
    try:
        print("📝 Mengisi data parameter...")

        # ── WAJIB (abort jika gagal) ──────────────────────────────────────────
        if not pilih_dropdown_ant_select(driver, "present_weather_ww", str(row['ww']).zfill(2)):
            return False
        if not pilih_dropdown_ant_select(driver, "past_weather_w1", str(row['w1'])):
            return False
        if not pilih_dropdown_ant_select(driver, "past_weather_w2", str(row['w2'])):
            return False
        if not isi_input_text(driver, "visibility_vv", str(row['visibility'])):
            return False
        cloud_cover_oktas_m = str(row['cloud_cover_oktas_m']).strip()
        if not pilih_dropdown_ant_select(driver, "cloud_cover_oktas_m", cloud_cover_oktas_m):
            return False

        if cloud_cover_oktas_m in {"/ - Cloud", "/ -"}:
            print(
                f"ℹ️ cloud_cover_oktas_m = '{cloud_cover_oktas_m}', "
                "melewati pengisian awan dan langsung mengisi land_cond"
            )
            if not pilih_dropdown_ant_select(driver, "land_cond", str(row['land_cond'])):
                return False
            print("✅ Data berhasil diisi")
            return True

        # ================ AWAN RENDAH ========================================#
        cloud_low_type = str(row['cloud_low_type_cl']).strip()
        cloud_low_type_code = cloud_low_type.split("-", 1)[0].strip()
        if not pilih_dropdown_ant_select(driver, "cloud_low_type_cl", cloud_low_type):
            return False  # WAJIB

        if cloud_low_type_code == "0":
            print(f"⚠️ Awan rendah tidak diisi karena cloud_low_type_cl = '{cloud_low_type}'")
        else:
            required_low_fields = (
                "cloud_low_cover_oktas",
                "awan_rendah_jenis",
                "awan_rendah_jumlah",
                "cloud_arah_awan_rendah",
            )
            missing_low_fields = [
                field
                for field in required_low_fields
                if pd.isna(row[field]) or not str(row[field]).strip()
            ]
            if missing_low_fields:
                print(
                    "❌ Data awan rendah wajib kosong: "
                    + ", ".join(missing_low_fields)
                )
                return False

            if not pilih_dropdown_ant_select(driver, "cloud_low_cover_oktas", str(row['cloud_low_cover_oktas'])):
                print("❌ cloud_low_cover_oktas gagal dipilih")
                return False

            if not isi_jenis_dan_jumlah_awan_Rendah(driver, str(row['awan_rendah_jenis']), str(row['awan_rendah_jumlah'])):
                print("❌ Jenis/Jumlah Awan Rendah gagal diisi")
                return False

            jenis_awan_rendah = str(row['awan_rendah_jenis']).strip()
            kode_jenis_awan_rendah = jenis_awan_rendah.split("-", 1)[0].strip()
            peak_dan_arah_sebenarnya_aktif = kode_jenis_awan_rendah in {"8", "9"}

            if pd.notna(row['cloud_low_base_1']):
                if not isi_input_text(driver, "cloud_low_base_1", str(int(float(row['cloud_low_base_1'])))):
                    print("⚠️ cloud_low_base_1 gagal diisi (field tidak aktif), dilewati")
            else:
                print("⚠️ cloud_low_base_1 kosong di Excel, dilewati")

            if peak_dan_arah_sebenarnya_aktif:
                if pd.notna(row['cloud_low_peak_1']):
                    peak_1_ok = isi_input_text(driver, "cloud_low_peak_1", str(int(float(row['cloud_low_peak_1']))))
                    if not peak_1_ok:
                        print("⚠️ cloud_low_peak_1 gagal diisi (field tidak aktif untuk jenis awan ini), dilewati")
                else:
                    peak_1_ok = False
                    print("⚠️ cloud_low_peak_1 kosong di Excel, dilewati")

                # Elevasi hanya dicoba jika peak berhasil
                if peak_1_ok and pd.notna(row['cloud_elevation_1_angle_ec']):
                    if not pilih_dropdown_ant_select(driver, "cloud_elevation_1_angle_ec", str(row['cloud_elevation_1_angle_ec'])):
                        print("⚠️ cloud_elevation_1_angle_ec gagal dipilih (field tidak aktif), dilewati")
                elif not peak_1_ok and pd.notna(row['cloud_elevation_1_angle_ec']):
                    print("⚠️ cloud_elevation_1_angle_ec dilewati karena cloud_low_peak_1 tidak aktif")

                # Arah sebenarnya tetap dicoba terlepas dari peak
                if pd.notna(row['cloud_arah_sebenarnya_1']):
                    if not pilih_arah_sebenarnya(driver, str(row['cloud_arah_sebenarnya_1'])):
                        print("⚠️ cloud_arah_sebenarnya_1 gagal dipilih (field tidak aktif), dilewati")
            else:
                print(
                    f"ℹ️ cloud_low_peak_1 dan cloud_arah_sebenarnya_1 dilewati karena "
                    f"jenis awan rendah '{jenis_awan_rendah}' bukan 8 atau 9"
                )

            if pd.notna(row['cloud_arah_awan_rendah']):
                if not pilih_arah_Awan_Rendah(driver, str(row['cloud_arah_awan_rendah'])):
                    print("❌ cloud_arah_awan_rendah gagal dipilih")
                    return False

            # [TOLERAN] Awan rendah kedua
            if pd.notna(row['awan_rendah_2_jenis']):
                if not klik_switch_jika_type(driver):
                    print("⚠️ klik_switch_jika_type gagal, dilewati")

                if pd.notna(row['cloud_low_base_2']):
                    cloud_low_base_2 = str(int(float(row['cloud_low_base_2'])))
                else:
                    cloud_low_base_2 = ""

                if not isi_jenis_dan_jumlah_awan_rendah_2(driver, str(row['awan_rendah_2_jenis']), str(row['awan_rendah_2_jumlah'])):
                    print("⚠️ Jenis/Jumlah Awan Rendah 2 gagal diisi, dilewati")

                if cloud_low_base_2:
                    if not isi_input_text(driver, "cloud_low_base_2", cloud_low_base_2):
                        print("⚠️ cloud_low_base_2 gagal diisi (field tidak aktif), dilewati")

                if cloud_low_type_code != "1":
                    if pd.notna(row['cloud_low_peak_2']):
                        cloud_low_peak_2 = str(int(float(row['cloud_low_peak_2'])))
                    else:
                        cloud_low_peak_2 = ""

                    if cloud_low_peak_2:
                        peak_2_ok = isi_input_text(driver, "cloud_low_peak_2", cloud_low_peak_2)
                        if not peak_2_ok:
                            print("⚠️ cloud_low_peak_2 gagal diisi (field tidak aktif untuk jenis awan ini), dilewati")
                    else:
                        peak_2_ok = False
                        print("⚠️ cloud_low_peak_2 kosong di Excel, dilewati")

                    # Elevasi hanya dicoba jika peak berhasil
                    if peak_2_ok and pd.notna(row['cloud_elevation_2_angle_ec']):
                        if not pilih_dropdown_ant_select(driver, "cloud_elevation_2_angle_ec", str(row['cloud_elevation_2_angle_ec'])):
                            print("⚠️ cloud_elevation_2_angle_ec gagal dipilih (field tidak aktif), dilewati")
                    elif not peak_2_ok and pd.notna(row['cloud_elevation_2_angle_ec']):
                        print("⚠️ cloud_elevation_2_angle_ec dilewati karena cloud_low_peak_2 tidak aktif")

                    # Arah sebenarnya 2 tetap dicoba
                    if pd.notna(row['cloud_arah_sebenarnya_2']):
                        if not pilih_arah_sebenarnya_2(driver, str(row['cloud_arah_sebenarnya_2'])):
                            print("⚠️ cloud_arah_sebenarnya_2 gagal dipilih (field tidak aktif), dilewati")

                if pd.notna(row['cloud_arah_2']):
                    if not pilih_arah_2(driver, str(row['cloud_arah_2'])):
                        print("⚠️ cloud_arah_2 gagal dipilih, dilewati")
            else:
                print("ℹ️ Awan rendah kedua dilewati karena awan_rendah_2_jenis kosong (NaN)")

        # ================ AWAN MENENGAH ======================================#
        cloud_med_type = str(row['cloud_med_type_cm'])
        if not pilih_dropdown_ant_select(driver, "cloud_med_type_cm", cloud_med_type):
            return False  # WAJIB

        if cloud_med_type == "0 -":
            print("⚠️ Awan menengah tidak diisi karena cloud_med_type_cm = '0 -'")
        else:
            # [TOLERAN] detail awan menengah
            if not pilih_dropdown_ant_select(driver, "cloud_med_cover_oktas", str(row['cloud_med_cover_oktas'])):
                print("⚠️ cloud_med_cover_oktas gagal dipilih, dilewati")

            if not isi_jenis_dan_jumlah_awan_menengah(driver, str(row['awan_menengah_jenis_1']), str(row['awan_menengah_jumlah_1'])):
                print("⚠️ Jenis/Jumlah Awan Menengah gagal diisi, dilewati")

            if pd.notna(row['cloud_med_base_1']):
                if not isi_input_text(driver, "cloud_med_base_1", str(int(float(row['cloud_med_base_1'])))):
                    print("⚠️ cloud_med_base_1 gagal diisi (field tidak aktif), dilewati")
            else:
                print("⚠️ cloud_med_base_1 kosong di Excel, dilewati")

            if pd.notna(row['cloud_arah_menengah_1']):
                if not pilih_arah_Awan_Menengah(driver, str(row['cloud_arah_menengah_1'])):
                    print("⚠️ cloud_arah_menengah_1 gagal dipilih, dilewati")

        # ================ AWAN TINGGI ========================================#
        cloud_high_type = str(row['cloud_high_type_ch'])
        if not pilih_dropdown_ant_select(driver, "cloud_high_type_ch", cloud_high_type):
            return False  # WAJIB

        if cloud_high_type == "0 -":
            print("⚠️ Awan tinggi tidak diisi karena cloud_high_type_ch = '0 -'")
        else:
            cover_val = str(row.get('cloud_high_cover_oktas', '')).strip()
            if cover_val in ("", "-", "nan", "NaN"):
                print("⚠️ cloud_high_cover_oktas kosong atau '-', melewati pengisian awan tinggi")
            else:
                if not pilih_dropdown_ant_select(driver, "cloud_high_cover_oktas", cover_val):
                    print(f"⚠️ Gagal pilih cloud_high_cover_oktas='{cover_val}', melewati detail awan tinggi")
                else:
                    if not isi_jenis_dan_jumlah_awan_Tinggi(driver, str(row['awan_tinggi_jenis']), str(row['awan_tinggi_jumlah'])):
                        print("⚠️ Gagal isi jenis/jumlah awan tinggi, dilewati")

                    if pd.notna(row.get('cloud_high_base_1')) and str(row.get('cloud_high_base_1')).strip() not in ("", "-", "nan", "NaN"):
                        if not isi_input_text(driver, "cloud_high_base_1", str(int(float(row['cloud_high_base_1'])))):
                            print("⚠️ Gagal isi cloud_high_base_1, dilewati")
                    else:
                        print("⚠️ cloud_high_base_1 kosong, dilewati")

                    arah_tinggi = row.get('cloud_arah_tinggi')
                    if pd.notna(arah_tinggi) and str(arah_tinggi).strip() not in ("", "-", "nan", "NaN"):
                        if not pilih_arah_Awan_Tinggi(driver, str(arah_tinggi)):
                            print("⚠️ Gagal pilih arah awan tinggi, dilewati")

        # ================ KEADAAN TANAH ======================================#
        if not pilih_dropdown_ant_select(driver, "land_cond", str(row['land_cond'])):
            return False  # WAJIB

        print("✅ Data berhasil diisi")
        return True

    except Exception as e:
        print(f"❌ Gagal mengisi data: {e}")
        return False

# Sinyal khusus untuk trigger recovery (bukan error biasa)
SESSION_RECOVERY_NEEDED = "SESSION_RECOVERY_NEEDED"
MAX_ROW_RECOVERY = 2  # maksimal berapa kali recovery per baris


def recover_session(current_driver, max_attempts=3):
    """
    Tutup browser saat ini, buka baru, login ulang, pilih stasiun & tanggal.
    Return: (new_driver, success_bool)
    """
    print("\n" + "="*60)
    print("🔄 MEMULAI PEMULIHAN SESI BROWSER")
    print("="*60)

    # Tutup browser lama
    try:
        current_driver.quit()
        print("✅ Browser lama berhasil ditutup")
    except Exception as e:
        print(f"⚠️ Gagal tutup browser lama (mungkin sudah crash): {e}")

    time.sleep(3)

    for attempt in range(1, max_attempts + 1):
        print(f"\n🔄 Recovery attempt {attempt}/{max_attempts}...")
        new_driver = None
        try:
            # Buka browser baru
            chrome_options_new = Options()
            chrome_options_new.add_argument("--start-maximized")
            service_new = Service()
            new_driver = webdriver.Chrome(service=service_new, options=chrome_options_new)
            print("✅ Browser baru berhasil dibuka")

            # Login, popup, stasiun, tanggal
            login(new_driver)
            klik_tombol_oke_popup()
            memilih_stasiun(new_driver)
            memilih_tanggal(new_driver)

            print("✅ Sesi berhasil dipulihkan — siap melanjutkan pengisian")
            return new_driver, True

        except Exception as e:
            print(f"❌ Recovery attempt {attempt} gagal: {e}")
            try:
                if new_driver:
                    save_debug_snapshot(new_driver, f"recovery_attempt_{attempt}_failed")
                    new_driver.quit()
            except Exception:
                pass

            if attempt < max_attempts:
                wait_time = 5 * attempt  # 5s, 10s, 15s
                print(f"⏳ Menunggu {wait_time}s sebelum retry recovery...")
                time.sleep(wait_time)

    print("❌ Semua attempt recovery gagal, baris akan dilewati")
    return None, False

def cek_ww_field_error(driver):
    """
    Cek apakah field present_weather_ww dalam kondisi error/merah di form.
    Ant Design menambahkan class 'has-error' pada wrapper field yang tidak valid.
    """
    try:
        error_els = driver.find_elements(
            By.XPATH,
            "//div[@id='present_weather_ww']/ancestor::div[contains(@class,'has-error')]"
        )
        return bool(error_els)
    except Exception:
        return False


def fallback_ww_mist_ke_haze(driver, row):
    """
    Fallback otomatis: jika ww=10 (Mist) dan Preview gagal karena RH < 95%,
    ganti ww ke 05 (Haze) lalu klik Preview ulang.

    Return:
        True  → fallback berhasil, Preview OK sudah diklik
        False → fallback tidak berlaku atau tetap gagal
    """
    ww_val = str(row.get('ww', '')).zfill(2)

    # Hanya berlaku jika ww=10
    if ww_val != "10":
        print(f"ℹ️ ww={ww_val}, bukan Mist (10) — fallback tidak berlaku")
        return False

    # Cek konfirmasi: apakah field ww memang merah di form?
    ww_error = cek_ww_field_error(driver)
    print(f"🔍 Status error field ww di form: {'MERAH ❌' if ww_error else 'tidak terdeteksi'}")

    print("\n⚠️ FALLBACK WW MIST→HAZE:")
    print("   ww=10 (Mist) kemungkinan ditolak karena RH < 95%")
    print("   Mengganti ww 10 → 05 (Haze) secara otomatis...")

    # Ganti ww ke 05
    if not pilih_dropdown_ant_select(driver, "present_weather_ww", "05"):
        print("❌ Gagal mengganti ww ke 05, fallback dibatalkan")
        save_debug_snapshot(driver, "fallback_ww_ganti_gagal")
        return False

    print("✅ ww berhasil diganti ke 05 (Haze)")
    time.sleep(0.5)

    # Klik Preview ulang
    print("🔄 Mengklik Preview ulang setelah ganti ww...")
    if not submit_with_retry(driver, "Preview_fallback_ww", lambda: Preview(driver), max_attempts=3):
        print("❌ Preview masih gagal setelah ganti ww ke 05")
        save_debug_snapshot(driver, "fallback_ww_preview_gagal")
        return False

    time.sleep(1)

    # Klik Preview OK
    if not submit_with_retry(driver, "Preview_OK_fallback_ww", lambda: Preview_OK(driver), max_attempts=3):
        print("❌ Preview OK masih gagal setelah ganti ww ke 05")
        save_debug_snapshot(driver, "fallback_ww_preview_ok_gagal")
        return False

    print("✅ Fallback ww 10→05 berhasil, Preview OK sudah diklik")
    return True

def main():
    global driver  # perlu global agar driver bisa diganti setelah recovery

    login(driver)
    klik_tombol_oke_popup()
    memilih_stasiun(driver)
    memilih_tanggal(driver)

    df_sebelumnya = None
    last_check_time = time.time()
    observer_selected = False

    while True:
        df_awal = baca_data_terbaru(silent=True)
        if df_awal is None:
            print("🔄 Menunggu 30 detik sebelum mencoba lagi...")
            time.sleep(30)
            continue

        df_sebelumnya = df_awal.copy()

        for index in range(len(df_awal)):
            print(f"\n🔄 Membaca ulang data sebelum memproses baris {index+1}")
            df = baca_data_terbaru(silent=True)
            if df is None or index >= len(df):
                print(f"⚠️ Data tidak valid untuk baris {index+1}, melewati...")
                continue

            if not df.iloc[index].equals(df_sebelumnya.iloc[index]):
                print(f"\n⚠️ PERHATIAN: Data baris {index+1} berubah!")
                for col in df.columns:
                    if str(df.iloc[index][col]) != str(df_sebelumnya.iloc[index][col]):
                        print(f"📌 {col}: {df_sebelumnya.iloc[index][col]} → {df.iloc[index][col]}")
                df_sebelumnya = df.copy()

            row = df.iloc[index]
            waktu_eksekusi = row['waktu_eksekusi'].to_pydatetime()
            sekarang = datetime.now()

            if waktu_eksekusi < sekarang:
                print(f"⏩ Melewati baris {index+1} karena waktu eksekusi {waktu_eksekusi} sudah lewat")
                continue

            waktu_tunggu = (waktu_eksekusi - sekarang).total_seconds()
            print(f"\n⏳ Menunggu sampai {waktu_eksekusi} untuk eksekusi baris {index+1}...")

            # Countdown + monitoring perubahan Excel
            while waktu_tunggu > 0:
                sekarang = datetime.now()
                waktu_tunggu = (waktu_eksekusi - sekarang).total_seconds()

                if time.time() - last_check_time >= 2:
                    df_baru = baca_data_terbaru(silent=True)
                    if df_baru is not None and index < len(df_baru):
                        if not df_baru.iloc[index].equals(df.iloc[index]):
                            print(f"\n⚠️ PERHATIAN: Data baris {index+1} berubah selama countdown!")
                            for col in df.columns:
                                if str(df_baru.iloc[index][col]) != str(df.iloc[index][col]):
                                    print(f"📌 {col}: {df.iloc[index][col]} → {df_baru.iloc[index][col]}")
                            row = df_baru.iloc[index]
                            waktu_eksekusi = row['waktu_eksekusi'].to_pydatetime()
                            df = df_baru
                            df_sebelumnya = df.copy()
                            sekarang = datetime.now()
                            waktu_tunggu = (waktu_eksekusi - sekarang).total_seconds()
                    last_check_time = time.time()

                mins, secs = divmod(max(0, waktu_tunggu), 60)
                print(f"\r⏳ Akan dieksekusi dalam: {int(mins):02d}:{int(secs):02d}", end="", flush=True)
                time.sleep(1)

            print("\n🚀 Eksekusi dimulai...")

            # ── LOOP RECOVERY PER BARIS ───────────────────────────────────────
            row_recovery_count = 0
            row_processed = False

            while row_recovery_count <= MAX_ROW_RECOVERY and not row_processed:

                if row_recovery_count > 0:
                    print(f"\n🔁 Mengulang baris {index+1} setelah recovery "
                          f"(attempt {row_recovery_count}/{MAX_ROW_RECOVERY})...")

                try:
                    print(f"\n🚀 Memproses baris {index+1} pada {datetime.now()}")
                    print(f"🔎 observer_selected: {observer_selected}")

                    if not isi_per_jam(driver, row):
                        raise Exception("Gagal pilih jam")

                    time.sleep(2)
                    Fill_AWS_Digi(driver)
                    time.sleep(1)

                    if not observer_selected:
                        # Tambah wait eksplisit: tunggu dropdown observer benar-benar siap
                        print("⏳ Menunggu form dan dropdown observer siap...")
                        wait_for_clickable(
                            driver,
                            (By.XPATH, "//label[contains(text(), 'Nama Observer')]/following-sibling::div//div[contains(@class,'ant-select-selection__rendered')]"),
                            timeout=15
                        )
                        if memilih_observer(driver):
                            observer_selected = True
                        else:
                            # Observer gagal tapi tidak fatal — form masih bisa diisi
                            # observer_selected tetap False agar dicoba ulang di baris berikutnya
                            print("⚠️ Observer gagal dipilih, melanjutkan pengisian tanpa observer...")

                    # ── TITIK DETEKSI UTAMA ──────────────────────────────────
                    # Jika form pengisian tidak muncul = web/sesi bermasalah
                    form_appeared = wait_for_presence(
                        driver, (By.ID, "present_weather_ww"), timeout=15
                    )
                    if not form_appeared:
                        save_debug_snapshot(
                            driver,
                            f"form_not_appeared_row_{index+1}_recovery_{row_recovery_count}"
                        )
                        raise Exception(
                            f"{SESSION_RECOVERY_NEEDED}: Form pengisian tidak muncul "
                            f"setelah Fill_AWS_Digi pada baris {index+1}. "
                            f"Kemungkinan web error, popup tidak muncul, atau sesi expired."
                        )
                    # ────────────────────────────────────────────────────────

                    wait_for_clickable(
                        driver,
                        (By.XPATH, "//div[@id='present_weather_ww']//div[contains(@class,'ant-select-selection__rendered')]"),
                        timeout=15
                    )

                    if not isi_data(driver, row):
                        raise Exception("Gagal isi data; membatalkan pengiriman untuk baris ini")

                    # 🔒 SUBMISSION CHAIN
                    time.sleep(1)
                    if not submit_with_retry(driver, "Preview", lambda: Preview(driver), max_attempts=3):
                        raise Exception("Gagal klik Preview setelah 3 percobaan")

                    time.sleep(1)
                    print("🔄 [1/3] Mencoba Preview_OK...")
                    preview_ok_berhasil = False
                    ww_error_terdeteksi = False

                    for attempt in range(1, 4):
                        if attempt > 1:
                            print(f"🔄 [{attempt}/3] Mencoba Preview_OK...")

                        if Preview_OK(driver):
                            preview_ok_berhasil = True
                            print(f"✅ Preview_OK berhasil pada attempt {attempt}")
                            break

                        ww_val = str(row.get('ww', '')).zfill(2)
                        if ww_val == "10" and cek_ww_field_error(driver):
                            print(f"🔍 Terdeteksi error ww=10 (Mist) setelah attempt {attempt}")
                            print("⚡ Langsung ke fallback tanpa menunggu retry berikutnya")
                            ww_error_terdeteksi = True
                            break

                        if attempt < 3:
                            wait_time = 1 + (attempt - 1) * 0.5
                            print(f"⏳ Preview_OK gagal ({attempt}/3), menunggu {wait_time}s sebelum retry...")
                            time.sleep(wait_time)
                        else:
                            print("❌ Preview_OK gagal setelah 3 percobaan")
                            save_debug_snapshot(driver, "preview_ok_gagal_3x")

                    if not preview_ok_berhasil:
                        print("⚠️ Preview OK gagal, memeriksa apakah perlu fallback ww Mist→Haze...")
                        fallback_berhasil = fallback_ww_mist_ke_haze(driver, row)
                        if not fallback_berhasil:
                            raise Exception("Gagal klik Preview OK setelah percobaan dan fallback ww")
    
                    time.sleep(1)
                    if not submit_with_retry(driver, "Send_And_Submit", lambda: SEND_SEND_SUBMIT(driver), max_attempts=2):
                        raise Exception("Gagal klik Send & Submit setelah 2 percobaan")

                    print("ℹ️ Menggunakan alur Send & Submit")
                    if not submit_with_retry(driver, "Send_INASWITCH_Submit", lambda: SEND_INASWITCH_SUBMIT(driver), max_attempts=2):
                        print("⚠️ Tombol Send to INASwitching & Submit tidak ditemukan, fallback ke Send to INASwitching")
                        if not submit_with_retry(driver, "SEND_INASWITCH", lambda: SEND_INASWITCH(driver), max_attempts=3):
                            raise Exception("Gagal klik SEND INASWITCH setelah 3 percobaan")

                    print("⏳ Menunggu popup GTS muncul (3s buffer)...")
                    time.sleep(3)
                    print("📨 Menunggu popup SEND final...")
                    if not submit_with_retry(driver, "SEND_GTS_final", lambda: SEND_GTS(driver), max_attempts=3):
                        raise Exception("Gagal klik SEND GTS final setelah 3 percobaan")

                    time.sleep(1)
                    if not submit_with_retry(driver, "SEND_GTS_OK", lambda: SEND_GTS_OK(driver), max_attempts=3):
                        raise Exception("Gagal klik SEND GTS OK setelah 3 percobaan")

                    print("✅✅✅ PENGIRIMAN BERHASIL ✅✅✅")
                    row_processed = True  # tandai sukses, keluar dari loop recovery

                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Error saat memproses baris {index+1}: {error_msg}")

                    # ── Cek apakah perlu recovery sesi ──────────────────────
                    if SESSION_RECOVERY_NEEDED in error_msg:
                        if row_recovery_count < MAX_ROW_RECOVERY:
                            row_recovery_count += 1
                            print(f"\n⚠️ DETEKSI MASALAH SESI/WEB — memulai recovery "
                                  f"({row_recovery_count}/{MAX_ROW_RECOVERY})...")

                            new_driver, recovery_ok = recover_session(driver)

                            if recovery_ok:
                                driver = new_driver          # ganti driver global
                                observer_selected = False    # reset, sesi baru belum pilih observer
                                print(f"✅ Recovery berhasil, mengulang baris {index+1}...")
                                time.sleep(2)
                                # lanjut iterasi while (mengulang baris)
                            else:
                                print(f"❌ Recovery gagal total, melewati baris {index+1}")
                                row_recovery_count = MAX_ROW_RECOVERY + 1  # paksa keluar loop
                        else:
                            print(f"❌ Sudah mencoba recovery {MAX_ROW_RECOVERY}x, "
                                  f"melewati baris {index+1}")
                            row_recovery_count += 1  # keluar loop
                    else:
                        # Error biasa (bukan masalah sesi) — langsung skip baris
                        print("🔄 Melanjutkan ke baris berikutnya...")
                        row_recovery_count = MAX_ROW_RECOVERY + 1  # paksa keluar loop

            time.sleep(2)

        print("\n✅ Semua data dalam file telah diproses")
        print("🔄 Memeriksa data baru dalam 10 detik...")
        time.sleep(10)


if __name__ == "__main__":
    main()