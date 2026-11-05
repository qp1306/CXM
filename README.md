# CXM Control Centre

**CXM V0.8.2 development release** — GitHub-driven updater, protected AutoSave, and a view of disk-saved T0–T11 profiles (not yet active in Klipper).

CXM is being built for a **single carriage-mounted extruder, shared filament switch and multiple exchangeable hotends** (T0–T11). Tool pickup/dropoff control is intentionally **not** enabled in this release.

## Already installed V0.2 or V0.3? Upgrade to V0.8.2

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

## V0.8.0 — Cartographer 3D+1 / BTC2 Z calibration engine (OFFLINE ONLY)

Built by analyzing the user's separately supplied working Voron StealthChanger BTC2 `btc2/calibration/z_calibration.cfg` v4 and `btc2/calibration/btc_auto_global_z.cfg` v9, **without changing or committing the BTC2 configuration**. CXM's permanent single extruder / detachable hotend architecture remains independent.

Two new standalone Python files contain **math only**:

- `scripts/cxm_z_math.py`: requires exactly **three complete Cartographer Touch probe results per hotend** (not raw individual taps), takes the **median**, and validates **full three-result range ≤0.020 mm**; T0 also requires a raw reference residual within **±0.025 mm** of fresh Touch-home. Proposed relative Z for tool N is median(N) minus median(T0), while T0 is fixed at 0.
- Verification requires exactly **five fresh complete Touch results per hotend**; sorts the five readings and chooses the **tightest consecutive three-reading window** (on a tie, earliest window), checking cluster range ≤0.020 mm, offset error vs previously stored T1–T11 master Z ≤±0.025 mm, and overall min-to-max **tool-offset error spread ≤0.040 mm**. Reports also show the full five-reading range so one rejected outlier remains visible. A mathematical PASS is not a physical test and never alters verification flags.
- `scripts/cxm_z_review.py`: generates/validates strict JSON input and returns explicit `SIMULATION_ONLY` or `PROVISIONAL_UNVERIFIED`, `save_permitted=false`, and `hardware_motion=false`. The mathematical engine supports tool counts **1 through 12**. No Klipper/Moonraker access, heating, G-code, storage or offset application is present.
- Proven BTC2 starting defaults: **70°C bed**, **140°C nozzle**, **Touch nozzle limit 149°C**, T0 touch reference; these are offline validation defaults, **not automatic heater commands**. Its currently successful **0.750 mm global Z maximum-change** is recorded separately from the much tighter Touch and master-offset verification limits. This maximum change is NOT a probe quality threshold.

To run the example **without any MCU** after updating:

```bash
python3 ~/CXM/scripts/cxm_z_review.py --example > /tmp/cxm_z_demo.json
python3 ~/CXM/scripts/cxm_z_review.py --input /tmp/cxm_z_demo.json
```

This uses 12 **fabricated** hotends. Expected overall values: `overall_math_pass=true`, `save_permitted=false`, `hardware_motion=false`; both calibration and verification report `SIMULATION_ONLY`. Only the synthetic input is written to `/tmp`. Nothing touches the printer's configuration.

In **Z Calibration**, the new offline panel displays the exact current design parameters and CLI instructions. The existing per-hotend Z states, T0 reference indication, maintenance lockouts and disabled physical actions remain unchanged.

**Not yet implemented / prerequisites before motion:** validate actual Cartographer 3D+1 Touch firmware and nozzle-contact safety on the CXM printer; MCU, endstops, extruder/carriage rigidity, hotend identity and seating; same probe point and temperature, independent trial repeats with removal/reseating; safe global-Z sign/convention; robust backup/revision guards; and controlled runtime application. The user-supplied BTC2 setup is only the working reference, not proof the different CXM coupling is repeatable.

## V0.8.1 — Touch sample reliability and repeatable re-docking (offline)

The existing BTC2 **tightest 3 of 5 results** verification, 0.020 mm intra-cluster tolerance, ±0.025 mm tool offset error, 0.040 mm overall error spread and 0.750 mm global Z correction limit remain **unchanged**.

New pure-Python `scripts/cxm_z_reliability.py` adds an **advisory** full-five-reading quality audit (proposed CXM threshold: full-five spread >0.040 mm). It explicitly lists which individual readings were excluded from the chosen tightest-three cluster and marks possible outliers. It **does not replace or loosen BTC2 verification**. The synthetic V0.8.0 sample has one high outlier in every tool's five readings (full span ~0.106 mm): BTC2 math still passes, but the new quality report must say `REVIEW_REQUIRED`.

Also new: mathematical consistency checks for at least **two independently supplied post-reseat trial sets** beyond baseline calibration. Each trial must provide three complete Cartographer Touch results per selected hotend including T0; it checks range ≤0.020 mm, a provisional 0.025 mm per-hotend relative Z drift from the baseline, and a 0.025 mm trial-to-trial drift. These 0.025 mm re-docking thresholds are new CXM engineering review values; they are not established BTC2 hardware limits.

**Crucial:** data files cannot prove that a hotend was actually removed, seated, independently identified or contacted the bed. Even with satisfactory mathematical re-dock consistency, the reviewer always returns `independent_reseating_confirmed=false`, `ready_for_commissioning=false`, and `save_permitted=false`. Missing re-dock trials report `NOT_PROVIDED`, not a pass; existing V0.8.0 input files remain accepted.

After installing, run:

```bash
python3 ~/CXM/scripts/cxm_z_review.py --example > /tmp/cxm_z_demo.json
python3 ~/CXM/scripts/cxm_z_review.py --input /tmp/cxm_z_demo.json --summary
```

Expected synthetic results: `btc2_math_pass=true`, `quality_status=REVIEW_REQUIRED`, `flagged_hotends=[T0..T11]`, `reseat_status=MATH_PASS_UNVERIFIED`, `physical_reseating_verified=false`, `ready_for_commissioning=false`. The synthetic re-dock trial sets are fabricated, **not physical tests**. Without `--summary` the detailed per-tool outlier and re-dock data are returned.

All hardware controls remain disabled on the Pi-only setup. The Z Calibration page displays the reliability methodology and run instructions. Nothing in this release changes stored calibration values, Klipper, Cartographer, printer movement, tool-readiness flags or the BTC2 printer.

## V0.8.2 — Dock Calibration live Klipper preflight (NO MOTION)

Following successful basic XY/Z movement commissioning, Dock Calibration now includes **read-only Moonraker status**. On opening the tab or pressing **Refresh**, the browser queries:
- `GET /printer/info`
- `GET /printer/objects/list`
- `GET /printer/objects/query?toolhead&idle_timeout` (plus `print_stats` only when actually present)

It displays Klipper state, XYZ **reported** homing, idle/print state and **current carriage position**. These are informational: a Klipper-reported homed XYZ is **not** proof of physically correct axis direction, the real dock position, a safe clearance or any tool pickup. If a live API call fails or returns a non-ready state, the display fails closed and does not pretend the printer is ready for calibration. Status refresh changes **no** readiness or saving permissions.

Fixed misleading static text from MCU-free development:
- Replaced `No MCU connected` in Dock Calibration with a neutral warning that stored dock coordinates are not currently active in Klipper.
- Replaced the fixed `XYZ homing: Not verified` label with the live reported homing state **and explicitly retained physical verification pending**.
- `Active hotend` now says `Not integrated` rather than implying that Klipper itself is disconnected.

**Still intentionally unavailable:** automatic Y-then-X XY dock capture, motor movement, approach dock, Test Pickup, Repeat Test, and any hotend commissioning. No G-code is issued; the current V0.7.0 XY calculations remain offline. Manual provisional XYZ editing still requires all **three** valid coordinates, deliberate acceptance, and the backend's existing Klipper idle safety gate. No changes to Klipper macros, `printer.cfg`, active tool, hardware or Z math. The working V0.8.1 release remains the rollout baseline.

**Acceptance:** install through the existing Updates page while Klipper is idle. Open Dock Calibration. If Klipper reports Ready and XYZ homed, expect live indicators `Ready (reported)`, `XYZ homed (reported)`, current XYZ position from Moonraker, and a separate `physical validation pending` label. Confirm `Measure dock XY`, `Approach dock` and `Test pickup` remain disabled. No invented dock XYZ should be saved.
