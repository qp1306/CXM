# CXM Control Centre

**CXM V0.3.0 development release** — GitHub-driven updater, protected AutoSave, and a view of disk-saved T0–T11 profiles (not yet active in Klipper).

CXM is being built for a **single carriage-mounted extruder, shared filament switch and multiple exchangeable hotends** (T0–T11). Tool pickup/dropoff control is intentionally **not** enabled in this release.

## Already installed V0.2? Upgrade to V0.3

Use **Updates → Check for Updates → Install CXM Update** in CXM Control Centre, then refresh the webpage. **No new terminal installation or Klipper restart is required.** T0–T11 cards show values from the existing `CXM_variables.cfg`: enabled state, saved dock XYZ, relative offsets and approach/dock speeds. **Edit** opens that tool's profile in Settings. Pickup and calibration remain disabled. The summary displays Safe Y, X docking adjustment, and enabled/available tool count.

## Already installed V0.1.x? Install the V0.2 backend first

1. Open CXM Control Centre at `http://YOUR-PRINTER-IP/cxm/` and use **Updates → Check for Updates → Install CXM Update**.
2. Do the **one-time** backend/bootstrap setup over SSH, with a read-only preflight first:

```bash
python3 ~/CXM/scripts/cxm_config_install.py
python3 ~/CXM/scripts/cxm_config_install.py --apply
```

3. Reopen `http://YOUR-PRINTER-IP/cxm/`, select **Settings**. It should load the 12 tool profiles and AutoSave controls. No Klipper restart is required.

The installer will create `~/printer_data/config/CXM_variables.cfg` only if it does not exist, and **will not overwrite existing calibration**. It installs a `cxm-config.service` bound to `127.0.0.1:8765` and updates the existing CXM Nginx snippet to proxy `/cxm/api/`. Nginx and the CXM service reload; the original `printer.cfg`, Klipper macros and Moonraker updater remain untouched.

**This is an additional one-time install step**, not part of Moonraker's basic Git pull. After setup, new webpage code updates through the existing CXM Update button. The Python service monitors its source files and restarts itself through systemd when those files change, without restarting Klipper.

## V0.2–V0.3 AutoSave and data safety

- Central file: `~/printer_data/config/CXM_variables.cfg`, which stays outside `~/CXM` so Git updates cannot overwrite it.
- 12 tool profiles: enabled, dock XYZ, relative XYZ offsets and dock/approach speeds.
- Global values: configured tool count, safe Y and X docking adjustment.
- A field change in **Settings** triggers server-side range/type checks, optimistic revision checking and an **atomic disk write**. No Save button is required.
- Each accepted change first saves a timestamped backup to `~/printer_data/config/cxm_backups/`. Restore a prior backup from Settings; restoring also backs up the current file.
- Invalid values, conflicting edits and unverified printer states fail safely.
- The V0.3 overview displays the saved XYZ coordinates, offsets and speeds on all 12 tool cards, with explicit unverified/missing/disabled states. Unmeasured dock values remain blank; no invented calibration or temperatures.

**Important — not active in Klipper yet:** V0.2 saves to disk but does not include `CXM_variables.cfg` in `printer.cfg`, send `SET_GCODE_VARIABLE`, or move any printer hardware. Klipper will continue to show its MCU error on a hardware-free development machine. Live macro integration is a separate milestone. Do not use these stored values to enable unattended toolchanges.

## Security and future Klipper updates

The Python configuration API listens only on loopback. Nginx restricts the new `/cxm/api/` route to private LAN ranges, while the server requires same-origin JSON requests and restricts writes to an explicit parameter schema. **Do not expose CXM or Moonraker directly to the public internet.** This is not a substitute for securing the local network or for user authentication.

The source code updater remains `[update_manager CXM]` through Moonraker's native git_repo type. Normal saved calibration values are independent of software updates. Custom Klipper Python modules are not required.

## Tests

```bash
python3 -m unittest discover -s tests -v
node --check web/cxm-settings.js
node --check web/cxm-tool-cards.js
node --test tests/test_web_update_safety.cjs tests/test_tool_cards.cjs
```

## Initial V0.1 installation (new printer)

```bash
curl -fLsS https://raw.githubusercontent.com/qp1306/CXM/main/scripts/cxm_manager.py -o /tmp/cxm_manager.py
python3 /tmp/cxm_manager.py install
python3 /tmp/cxm_manager.py install --apply
python3 /tmp/cxm_manager.py verify
```

Then follow the V0.2 backend step above. The initial installer is dry-run by default.

Repository: https://github.com/qp1306/CXM
