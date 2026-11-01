# CXM Control Centre

Version 0.1 — clean Klipper + Moonraker + Mainsail installation foundation.

Designed for the CXChanger single-extruder / multiple-hotend printer. This release installs only a dark read-only dashboard and a GitHub updater. It does not modify printer.cfg, add Klipper macros, or control tool motion.

## First install on the printer

Run these commands over SSH on a machine with an ordinary Mainsail nginx installation. The first installation command is **dry-run only**:

~~~bash
curl -fLsS https://raw.githubusercontent.com/qp1306/CXM/main/scripts/cxm_manager.py -o /tmp/cxm_manager.py
python3 /tmp/cxm_manager.py install
python3 /tmp/cxm_manager.py install --apply
python3 /tmp/cxm_manager.py verify
~~~

Then visit `http://YOUR-PRINTER-IP/cxm/`, open **Updates**, and click **Check for Updates**.

**Important:** The installer assumes the common Mainsail nginx site at `/etc/nginx/sites-available/mainsail`, Moonraker at `~/printer_data/config/moonraker.conf`, and a clean checkout at `~/CXM`. If your setup differs, use `--config-dir`, `--nginx-site` and/or `--path`. The script refuses unfamiliar nginx layouts rather than guessing.

## Updates

The CXM page uses Moonraker's documented `/machine/update/refresh`, `/machine/update/status` and `/machine/update/upgrade` endpoints, scoped only to the CXM updater. Future commits to `main` can be checked and installed through the page. Updates require confirmation and the printer must be idle.

The initial Moonraker updater uses `channel: dev` to track main commits. Web-only updates do not restart Klipper. Future macro changes may require a carefully controlled Klipper reload; do not interpret an updater's successful Git pull as proof macros are loaded.

## Safety and data

- This is a development starter; not verified on the user's actual printer yet.
- Tool cards display placeholders, not real attached-tool status.
- Actual dock calibration and AutoSave will be implemented and tested separately.
- Future live configuration and calibration data go in the printer data/config directory, not the Git checkout, so Moonraker can update a clean repository.
- Avoid exposing the Moonraker API to the public internet.
- The installer requires `--apply` for writes and backs up files it changes.

Source: https://moonraker.readthedocs.io/en/latest/external_api/update_manager/