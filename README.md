# CXM Control Centre

**CXM V0.7.2 development release** — GitHub-driven updater, protected AutoSave, and a view of disk-saved T0–T11 profiles (not yet active in Klipper).

CXM is being built for a **single carriage-mounted extruder, shared filament switch and multiple exchangeable hotends** (T0–T11). Tool pickup/dropoff control is intentionally **not** enabled in this release.

## Already installed V0.2 or V0.3? Upgrade to V0.7.2

Use **Updates → Check for Updates → Install CXM Update** in CXM Control Centre, then refresh the webpage. V0.5.1 retains a guided **Dock Calibration** tab. Select any enabled T0–T11, enter or nudge proposed X/Y/Z, then **Accept XYZ · AutoSave**. The three numbers are committed atomically with a backup and optimistic revision check. The tool-card Calibrate button now opens the editor, but **never initiates motion**. **No new terminal installation or Klipper restart is required.** The Tools page has a **Hotends in use (1–12)** selector which AutoSaves the global tool count. It shows **all selected hotend cards** from T0 up to the chosen count, including individually disabled profiles. Disabled tools are clearly labelled, remain protected from calibration commands and can be enabled deliberately in Settings. Reducing the count hides higher-numbered cards without modifying any of their saved calibration settings or Enabled flags. Visible cards show values from `CXM_variables.cfg`: saved dock XYZ, relative offsets and approach/dock speeds. **Edit** opens that tool's profile in Settings. Pickup and calibration remain disabled. The summary displays Safe Y, X docking adjustment, and enabled/available tool count.

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
 

## V0.4 dock-editor safety

The accepted coordinates are **saved, provisional, unverified and not active in Klipper**. Motion, pickup/dropoff, repeated tests, automatic XY measurement and tool-switch verification remain disabled until the real controller, endstops and CXM macros are integrated. The configuration backend supports `POST /cxm/api/v1/dock` for one validated atomic XYZ save. No new installer step is needed: the existing config service detects Python changes and restarts independently of Klipper. Backups remain outside Git.

## V0.5.0 dock editor usability correction

The Accept XYZ button is now disabled for missing, invalid, or unchanged coordinates. The editor preserves unsuccessful drafts, restores editable fields after successful saves, and warns before discarding an unsaved draft on refresh or hotend switch. Stage labels now distinguish editable tasks from future hardware checks. No new installer or Klipper restart.

## V0.5 stable tool colours and Axiscope camera preview

Tool cards and dock selector use persistent T0–T11 colour accents. Tool number labels remain mandatory. The **XYZ Offsets** page discovers enabled webcams through Moonraker's `GET /server/webcams/list`. A compatible same-origin MJPEG webcam may be displayed with an optional crosshair and visual zoom. Camera feeds on a different origin must be made available through the printer's existing webcam proxy before CXM will display them.

All X/Y movement, automatic centring and offset recording buttons are disabled until actual hardware is connected, homed and safety-tested. The crosshair is visual only; it is not calibrated to millimetres. Displayed XY values are saved configuration, not Axiscope measurements. No backend, Klipper macros or `printer.cfg` changes.

## V0.5.1 — fixed '12 selected, 6 shown'

The count controls the number of visible cards. Selecting 12 shows T0–T11, even if T6–T11 are marked **Disabled** in the separate safety setting. The dashboard reports both **shown** and **enabled** totals, and the individual Enabled flags are never silently changed. This is a display-only update: no Python service, toolchange scripts or saved profiles are modified.

## V0.6 readiness-state migration — important

This release **does not** automatically rewrite your `CXM_variables.cfg`. It first loads the old schema-1 file **read-only** and shows a migration button under **Settings**. When the printer is confirmed idle or is the known MCU-free development instance, choose **Back up and migrate configuration** after reviewing the confirmation. CXM makes a timestamped backup of the original and atomically writes schema 2. The API rejects config edits until this explicit migration succeeds. It does **not** modify `printer.cfg` or restart Klipper.

- `tool_count` selects T0–T(n−1), whether or not calibrated. There are no more generic `enabled` flags in schema 2.
- `maintenance_lockout` is the separate, deliberate operator block. When migrating a legacy config, a tool previously disabled *within T0–T5* is kept locked out; T6–T11 were disabled by default and are treated as selected-but-unverified when included in `tool_count`. **Review any old manual disables on T6–T11 before commissioning**, because v1 cannot distinguish manual disable from its original default. All tools remain unable to move or be marked READY until new physical verification.
- Existing saved dock XYZ, offsets XYZ, approach speed, dock speed, safe Y and X docking adjustment are retained exactly. All new verification/acceptance flags start `false`, including `commissioned`.
- Verification flags are **not** editable through the normal Settings API, and the preview never reports READY in MCU-free development mode. Saved zero offsets do not imply successful calibration.
- Changed dock XYZ invalidates previous dock/pickup/dropoff verification; changed offsets invalidate corresponding offset acceptance/verification; changed speeds, maintenance override or global clearance settings invalidate associated commissioning/verification.
- The **Tools**, **Dock Calibration**, **Axiscope** and **Settings** views display the same tool count and readiness wording. The tool selector is a keyboard-accessible custom-coloured dropdown with native-select fallback.
- Existing Axiscope work and its nonmoving camera preview are preserved. Pickup, jog, calibration measurement and real hardware controls are still disabled.

**Test before entering real calibration data:** Confirm migration warning, click the deliberate migration button only after the backup explanation, check saved values and rollback history, test the 6→12→6 display and re-load, test T10 NOT CALIBRATED/NOT READY, test maintenance lockout on a spare tool, ensure T0 remains unverified and that the camera/motion controls are disabled. Never enter invented dock coordinates.

## V0.5.2 — Global tool count across every screen

**Hotends in use** is now the visibility selector for the Tools cards, Dock Calibration dropdown, Axiscope XY selector and comparison table, and the Settings hotend selector. Select 12 to display T0–T11 in all locations regardless of individual Enabled flags. Disabled hotends are labelled **Disabled** and remain safe: pickup/motion disabled, and Dock Calibration draft fields and AutoSave are read-only until explicitly enabled via Settings. Profiles outside the chosen count are hidden rather than deleted. Saved variables and the V0.5 Axiscope camera functionality remain unchanged.

## V0.6.1 — Maintenance lockout visibility

Settings now displays a large, full-width **MAINTENANCE LOCKOUT** panel immediately under the selected hotend. Its 82 × 46 px ON/OFF switch and clear LOCKED OUT or UNLOCKED status replace the former small checkbox. A change AutoSaves through the existing revision-checked config endpoint. Removing an existing lockout requires deliberate confirmation. **Unlocked does not mean Ready**: no tool may move or be picked up until calibration and hardware verification are separately implemented and passed. No changes to Klipper, the Python service, tool offsets, webcam, or tool-count settings are required.

## V0.6.2 — compact safety panel

The maintenance lockout panel in Settings is modestly shorter: minimum height 140px (previously 158px), internal padding 18×22px (previously 22×26px), and the switch 74×42px (previously 82×46px). Heading, status and spacing are slightly reduced. Full-width layout, unlocked blue/locked red colours, prominent safety wording, AutoSave, confirmation on unlocking, and hardware safety rules are unchanged. This is a front-end styling release, requiring no Python service change or Klipper restart.

## V0.7.0 — Offline automatic XY dock measurement lab

We have added hardware-free Python modules `scripts/cxm_xy_measure.py` and `scripts/cxm_xy_review.py`, plus tests. These can parse Klipper `GET_POSITION` MCU step-counter snapshots, infer a CoreXY transform from verified X-only and Y-only calibration moves, check Y-then-X homing capture continuity, reject cross-axis motion/out-of-bounds data, and output **only provisional** raw dock XY. Klipper's step counts are cumulative commanded pulses, not a guarantee of physical displacement or tool pickup. The new Dock Calibration section displays hardware readiness, with all measurement/homing buttons disabled.

**No MCU required for the demonstration:**

```bash
python3 ~/CXM/scripts/cxm_xy_review.py --example > /tmp/cxm_xy_demo.json
python3 ~/CXM/scripts/cxm_xy_review.py --input /tmp/cxm_xy_demo.json
```

Expected simulated output: `status=SIMULATION_ONLY`, `raw_dock_xy_mm={x:180.0,y:172.0}` and `save_permitted=false`. This is **made-up data**, not a dock calibration. No printer or configuration file changes, network requests or G-code are performed. Real experiments require verified stepper directions, mechanically safe homing, full stop at each capture, unchanged MCU session and repeated measurement validation. The dock X adjustment is deliberately not applied by this tool; it must be handled separately after confirming the correct sign.

## V0.7.1 — Dedicated Z Calibration preparation

A dedicated **Z Calibration** navigation tab shows the T0 nozzle-to-bed reference procedure and per-tool T1–T11 relative nozzle-height calibration. It reads stored `offset_z`, `offset_z_accepted`, `offset_z_verified`, `reference_verified` and maintenance lockout status for each selected hotend. The T0 reference remains **NOT VERIFIED** unless explicitly verified, even when `offset_z=0.000`. Previously entered offsets are shown as saved numbers, never presented as measured results.

Important mechanical distinction: `dock_z` controls where a hotend parks/couples; `offset_z` compensates the interchangeable nozzle tip height during printing. A Cartographer permanently mounted to the carriage alone cannot establish the physical tip-height difference for every interchangeable hotend. If the installed Cartographer has a compatible, commissioned **Touch** capability, a contact-based reference might be possible; otherwise a separately validated common reference/measurement method is required. Verify the actual device model and physical travel/bed protection before choosing a method.

The proposed full calibration will: verify safe homing and T0 reference; measure hotend nozzle tips against the **same repeatable datum** with stable temperature and confirmed pickup; check physical sign, repeatability and undock/redock behaviour; then use an intentionally authorised, revision-checked AutoSave and runtime compensation path. Those operations are future work, **not implemented** in this release.

**MCU-free acceptance test:** open the new **Z Calibration** tab, check T0 reference is NOT VERIFIED, select T10 in the coloured dropdown, confirm its saved Z number is not labelled measured, verify T0–T11 comparison for tool count 12 (and T0–T5 when count 6), and confirm both **Start Z calibration** and **Accept measured Z** buttons are disabled. This change is view-only: no service restart, `printer.cfg` modification, G-code, nozzle motion or saved-offset changes.

## V0.7.2 — Dock Calibration workflow order

Dock Calibration now displays **1 · Automatic XY dock measurement**, then **2 · Align dock position** and **3 · Test and verify**. The measurement status panel is full-width at the top, while alignment and verification remain side-by-side underneath. Measurements are still offline-only until the MCU, endstops and motor motion are validated. Aligning coordinates still requires accepted X, Y and a separately established dock Z; the existing saved draft editor, safety locks, backup and rollback are preserved. No changes to scripts, Python services, active Klipper configuration or hardware movements. The single-extruder/hotend system keeps Axiscope and the dedicated Z Calibration page unchanged.
