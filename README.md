# SYNOP Auto

**A station-focused observation workflow for BMKG Satu (BMKGSoft v2).**

SYNOP Auto combines a browser-automation bot, a validated observation form and dashboard, SQLite-backed scheduling and delivery history, and operational diagnostics.

> **Operational safety:** `V7SATU.py` can submit real observations. Start with validation and `--dry-run`, review the generated SYNOP code and the live form, and only then run a live submission. This project automates the BMKG Satu user interface; it does not use an official BMKG API. Website changes can affect browser automation.

## What it does

- **Collects observations** through a mobile-friendly web form and dashboard, or reads rows from an Excel workbook.
- **Validates data before submission** using shared field rules, dropdown options, and QC checks. The browser form and bot use the same validator and field schema.
- **Automates hourly SYNOP entry** in BMKG Satu with Selenium and Chrome, using UTC observation slots and a configurable local-time execution schedule.
- **Protects against accidental duplicate sends** with a persistent SQLite status log. If a failure occurs after the final submit action and delivery is uncertain, the slot is flagged for manual review instead of being blindly resent.
- **Recovers from common browser and field failures** with per-field retries, page reload/browser restart retries, session checks and limited process restarts.
- **Offers observation and audit tools:** copy a previous hour or a range of hours, import/export Excel, filter and export history, and review delivery status and SYNOP codes.
- **Supports operational notifications** through optional Telegram messages and local failure alarms.
- **Includes optional Windows remote access** through `jalankan_remote.bat` and a temporary Cloudflare Tunnel.

## Workflow

```text
Observation form / Excel
          |
          v
Shared schema + validator + QC
          |
          v
SQLite observations and delivery log
          |
          v
V7SATU.py -> BMKG Satu via Selenium/Chrome
```

The checked-in `config.yaml` selects the **web form database** as the bot's input (`features.data_source: db`). Excel remains an alternative input source. The form app and the bot are separate processes: start the app to enter observations, then start the bot to process them.

## Main capabilities

### Bot and SYNOP checks

- Selects the observation date and hour for each slot in **UTC**, so the selected date stays correct across midnight.
- Supports observer selection, `Send & Update` when a slot already exists on the website, and configurable dry-run operation.
- Checks required and conditional cloud fields, cloud layers, vertical visibility, rain overrides, and evaporation/radiation/sunshine fields.
- Handles low, middle, and high cloud layers, including additional layers when enabled.
- Can compare the generated SYNOP code with the source data and check QFF/QFE consistency.
- Can handle BMKG Satu session expiry, popup handling, and the post-submit QC correction dialog.
- Retries individual field actions before retrying a row. Row recovery can reload the page or open a fresh browser, subject to configured attempt and time limits.
- Uses the SQLite send log to track pending, running, sent, failed, skipped, and manual-check states. Previously sent slots are not sent again automatically.

### Form and dashboard

- Shows the 24 hourly UTC slots for a selected UTC date, with observation completeness and bot delivery status.
- Runs server-side validation as fields change and prevents saving data with validation errors.
- Supports optional observer names, quick templates, previous-hour copying (including across UTC midnight), and copy-by-time-range.
- Supports per-hour execution-time overrides and a global default schedule. Scheduling limits follow the website's observation window.
- Provides import/export for observation workbooks, paginated/filterable audit history, and Excel export.
- Offers actions to review or reset eligible stuck/failed delivery states. A slot already marked as sent is protected from unsafe edits or resets.

### Recent form-entry improvements

- The "copy from previous hour" action copies the complete supported observation in one click.
- Fast dropdown selection uses click-and-verify behavior, with the established input path available as a fallback.
- Numeric field fast-entry is configurable under `speed.fast_input`.
- Evaporation, radiation, sunshine duration, iE, and land-condition fields are ordered at the bottom of the form; iE is a coded dropdown. Time-dependent fields are hidden outside the applicable UTC hour.

## Requirements

- Python 3.10 or later is recommended.
- Google Chrome installed on the machine that runs the bot.
- Network access to BMKG Satu. Selenium Manager may need network access to locate or obtain a compatible ChromeDriver.
- Windows is required for the supplied `jalankan_remote.bat` helper. The bot itself uses Selenium and may work on other desktop platforms, but this project is configured and operated primarily on Windows.

Python packages are listed in [`requirements.txt`](requirements.txt). `pyautogui` is used as an optional desktop-interaction fallback; core browser automation uses Selenium.

## Setup

Run these commands from the project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a **local** `.env` file in the project root. There is no committed credentials file; replace the example values and never commit `.env`:

```dotenv
BMKG_STATION_ID=your_station_login_id
BMKG_PASSWORD=your_bmkg_password

# Strongly recommended for any network access; required by jalankan_remote.bat.
WEB_PIN=replace_with_a_long_random_pin

# Optional Telegram notifications:
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

The bot can prompt for missing BMKG credentials when run interactively, but configuring them in `.env` is recommended. `WEB_PIN` is optional for local-only use; without it, the web application has no PIN login. **Do not expose the app to a LAN or the public internet without setting a strong PIN.**

Review [`config.yaml`](config.yaml) before operating:

| Setting | Purpose |
| --- | --- |
| `station.name` | Station label selected in BMKG Satu; it must match the website option. |
| `features.data_source` | `db` reads observations saved through `app.py`; `excel` reads the workbook at `paths.excel`. The checked-in configuration uses `db`. |
| `paths.db`, `paths.excel` | SQLite database and optional Excel workbook paths. Relative paths are resolved from the project directory. |
| `runtime.timezone_offset_hours` | Local time offset used to derive execution times from UTC observation slots; the current configuration is UTC+7 (WIB). |
| `web.menit_sebelum` | Default number of minutes before the observation hour for the bot to begin. Per-slot overrides can be set in the dashboard. |
| `runtime.retry_past_minutes` | Retry window for eligible failed/interrupted slots. This is not the same as forcing every old slot to run. |
| `runtime.max_field_attempts`, `max_row_attempts`, `max_row_menit` | Limits for field and row recovery. |
| `features.verify_sandi`, `sandi_block_on_mismatch` | Enable generated-code comparison; optionally block sending on a mismatch. |
| `features.qc_enabled`, `qc_strict` | Enable QC checks and decide whether strict findings block a row. |
| `features.allow_update` | Allow updating a slot that already has data on the website. |
| `features.penguapan_strict`, `rain_override_strict` | Decide whether failed evaporation/radiation or rain-override entry blocks a row. |
| `speed.fast_select`, `speed.fast_input`, `speed.scale` | Tune supported browser entry paths. Verify changes with a dry run before live use. |
| `notify.*` | Select Telegram message types, daily recap time, screenshots, and local failure alarm behavior. |

Observer names and dropdown/rule data are maintained in `core/options.json`, `core/rules.json`, and `core/rules_qc.json`. Use names that are active in the configured observer list.

## Run the web form and dashboard

For local access on the same PC:

```powershell
python app.py --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>. If `WEB_PIN` is set, sign in with that PIN. The app creates its SQLite database at the configured `paths.db` location.

For access from other devices on the same trusted LAN, bind to the network interfaces and set `WEB_PIN` first:

```powershell
python app.py --host 0.0.0.0 --port 8080
```

Allow the port through Windows Firewall only when appropriate. Do not assume a LAN is private or trusted.

## Run the bot safely

### 1. Enter and validate data

With the configured database input, start the form app, enter the desired UTC slots, and save them. The form validates data before saving.

For an Excel workbook, set `features.data_source: excel` and `paths.excel` in `config.yaml`, then validate it:

```powershell
python check_excel.py
```

`check_excel.py` validates Excel input only. Excel workbooks are station-specific data and are not included in this repository. Required base columns include `waktu_eksekusi`, `jam_input`, `visibility`, `ww`, `w1`, `w2`, `cloud_cover_oktas_m`, and `land_cond`; optional columns include vertical visibility, rain override, evaporation/radiation, and additional cloud layers.

### 2. Validate and do a dry run

To validate the bot's configured input and exit before opening a browser:

```powershell
python V7SATU.py --check-only
```

Run a browser dry run for one observer and one UTC hour:

```powershell
python V7SATU.py --observer "Observer Name" --no-gui --dry-run --jam 17:00
```

The bot logs in, fills the form, and proceeds to Preview without performing the final submission. Review the browser, console output, snapshots, and generated SYNOP code. The observer name must match an active option.

### 3. Submit live observations

Only after reviewing the data and dry-run result, start live operation:

```powershell
python V7SATU.py --observer "Observer Name" --no-gui
```

The normal live command can submit real observations. For a limited live run, add a UTC-hour filter:

```powershell
python V7SATU.py --observer "Observer Name" --no-gui --jam 17:00,18:00
```

Useful options:

| Option | Behavior |
| --- | --- |
| `--dry-run` | Fill the website through Preview without the final send. |
| `--check-only` | Validate the bot's current input and exit before browser work. |
| `--observer "Name"` | Select an observer without the GUI picker. |
| `--no-gui` | Use terminal observer input instead of the GUI picker if no observer was specified. |
| `--jam 07:00,08:00` | Process only the listed UTC hours. |
| `--process-past` | Force overdue slots to run immediately. Use only for an intentional catch-up; it is not needed for future scheduled hours. |

Without `--process-past`, overdue slots are normally skipped unless the send log identifies an eligible failed/interrupted slot still inside `runtime.retry_past_minutes`. Always inspect the dashboard and the BMKG Satu website after an ambiguous send result. A `[CEK-MANUAL]` status means verify the website before taking any retry action.

## Optional remote access on Windows

`jalankan_remote.bat` starts the web app on `127.0.0.1:8080` in a separate window and launches a Cloudflare Quick Tunnel. It requires a non-empty `WEB_PIN` in `.env`. If `cloudflared` is missing, the script attempts to install it using Windows Package Manager (`winget`); the first installation may require closing and rerunning the script.

When the tunnel starts, open the printed `https://....trycloudflare.com` link on your phone and enter the web PIN. The temporary link changes each time. Close the tunnel window or press Ctrl+C to stop remote access; the helper then closes the app window.

**Treat the tunnel link as public.** Use a strong PIN, share the URL only with trusted users, do not send the PIN through the same public channel as the link, and stop the tunnel when finished. Do not use this helper without confirming that the PIN login works on your installation.

## Diagnostics and notifications

- `python tools/pantau_web.py --help` lists the web-monitor modes. `jelajah` inspects the live form without filling or sending; `dryrun` runs the bot through Preview; `kirim` is a live-send mode and requires `--izinkan-kirim`.
- Monitoring reports are written under `pantau_out/`. They may contain observer names, screenshots, page data, and observations; inspect and sanitize them before sharing.
- Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` to enable Telegram notifications. Configure message types under `notify:` in `config.yaml`. To send a test message, run `python core/notify.py --test`.
- `collect_web_info.py` and `collect_rules_matrix.py` are utilities for collecting website field and rule information. Treat their output as operational data.

## Tests

Tests are provided as individual Python scripts. For example:

```powershell
python tests/test_validator.py
python tests/test_bot_flow.py
python tests/test_rev32_bot.py
python tests/test_penguapan.py
python tests/test_app.py
```

`tests/test_form_salin.py` exercises the browser form with Node.js and `jsdom`; it reports a skip when those are unavailable. Some integration checks require local browser/software setup or a suitable local workbook.

## Project layout

| Path | Role |
| --- | --- |
| `V7SATU.py` | Main Selenium bot, scheduler, retries, and submission flow. |
| `app.py` | Flask form, dashboard, API, imports/exports, schedule controls, and history. |
| `config.yaml` | Station, paths, input source, runtime, browser, QC, speed, and notification settings. |
| `core/config.py` | YAML and `.env` loading, credentials, and project-relative paths. |
| `core/fields.py` | Field metadata used by the bot's generic browser-entry helpers. |
| `core/formschema.py` | Shared form sections, options, and conditional field states. |
| `core/validator.py`, `core/qc.py` | Input validation and consistency checks. |
| `core/synop_check.py` | Generated SYNOP code verification. |
| `core/obsdb.py`, `core/db.py` | SQLite observation storage, schedule, send status, and audit history. |
| `core/notify.py` | Optional Telegram notifications and local failure alarm. |
| `core/options.json`, `core/rules*.json` | Website option, validation, and QC reference data. |
| `web/` | Flask templates for the dashboard, observation form, login, and history. |
| `tools/pantau_web.py` | Live website behavior and timing monitor. |
| `check_excel.py` | Standalone Excel validation utility. |
| `tests/` | Validator, form, database, bot-flow, recovery, QC, and integration checks. |
| `collect_web_info.py`, `collect_rules_matrix.py` | Website inspection and rule-collection utilities. |
| `legacy/V6SATU.py` | Retained legacy implementation; use `V7SATU.py` for the current workflow. |

Runtime data such as `.env`, Excel workbooks, SQLite databases, Chrome profiles, snapshots, and monitoring output is intentionally local and should not be committed or shared without review.
