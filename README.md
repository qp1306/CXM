# CXM Control Centre

**CXM V0.9.0 commissioning development release** — GitHub-driven updater, protected AutoSave, and a view of disk-saved T0–T11 profiles (not yet active in Klipper).

CXM is being built for a **single carriage-mounted extruder, shared filament switch and multiple exchangeable hotends** (T0–T11). Tool pickup/dropoff control is intentionally **not** enabled in this release.

## CxChanger movement architecture (schema 3)

**Lineux Hot Swap is calibration only. CxChanger is the motion engine.** The Lineux endstop-assisted `DOCK_LOCATE_CALIBRATE` still measures hand-aligned carriage XY. For each tool, align the **CxChanger hotend locking screw with the centre of the large dock hole** before measuring; this is the required mechanical datum. The provisional Lineux raw position is kept distinct from the CxChanger X/Y datum that the pickup/dropoff engine uses.

- **Settings:** `x_docking_adjust` and `y_docking_adjust` convert measured raw X/Y to the actual locking-hole datum (default 0; do not mistake these for latch travel). `cxm_shift_x` is lateral engagement/release travel, `cxm_dodge_y` is the Y mechanical dodge, and `cxm_safe_clearance_y` is **relative to each dock's Y**. CxChanger always stages at `dock_y + cxm_safe_clearance_y`; the prior absolute `safe_y` is retained on disk for legacy compatibility but **not used** for CxChanger motion.
- **Native movement:** `server/cxm_cxchanger.py` implements the original CxChanger pickup/dropoff order independently of Lineux. T0 one-click, manual supervised tests, and repeatability tests all use this single engine. It does not move Z, modify heaters, or call Lineux when changing tools. The planner supports per-tool datum X/Y for T0–T11; automated physical switching of T1+ still awaits commissioning.
- **Existing installations:** After **Updates → Install CXM Update**, open Settings and use **Back up and migrate configuration**. This is an **explicit schema 2 → 3** migration, not an automatic rewrite. Existing dock XY is retained for reference, but its movement acceptance and previous verification flags are deliberately reset. No unreviewed old coordinates can start a T0 motion. The migration makes an atomic backup; it does not edit printer.cfg or restart Klipper.
- **New calibration:** In Settings review X/Y datum corrections and CxChanger X latch / dodge / safe clearance. In Dock Calibration: Home & Z20 → Release X/Y (leave all four Z motors ON) → manually align locking screw in the dock's large hole → Measure dock XY (Lineux) → Copy **CxChanger datum X/Y** → Save dock XY. Both Lineux raw X/Y and the accepted, converted CxChanger dock XY are stored with a backup. Save is not physical verification. Rehome XYZ and perform **one supervised T0 dropoff or pickup** with the real carriage switch, then use a small repeat test. No Klipper restart is needed for calibration/settings changes.

**Safety:** Start with the correct carriage switch state and no print active. Homing XYZ, four powered Z motors, powered X/Y, Z≥20, safe XY area, a matching configuration revision, operator supervision and final sensor transition remain required. Any sensor/position mismatch fails closed; never blindly replay a failed motion. An emergency requires the printer's actual emergency stop, not the repeat-test Stop After Cycle control.

---

## Already installed V0.2 or V0.3? Upgrade to V0.9.3

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

## V0.9.0 - actual commissioning workbench; NO printer motion

This release makes the previous empty **Testing** page usable for live diagnostics and offline analysis of real hardware data. It does not yet implement unattended physical toolchanging.

**New Testing page:**
1. **Live machine preflight** reads Klipper info, object availability, reported toolhead homing and XYZ, idle/print state, extruder thermistor and local CXM config revision. It inspects any available `configfile` homing-override settings and warns about the specific CXM issue: `set_position_z: 0` combined with unconditional `G1 Z10`. This is a diagnostic warning, not certification of a different override.
2. **Prove AutoSave without a Klipper process restart:** first capture process evidence and the config revision, change a harmless disk-only field while idle, then compare. Backend GET `/cxm/api/v1/runtime` combines Moonraker's `/printer/info.process_id` with Linux `/proc/<pid>/stat` start ticks and the kernel boot ID, then returns a truncated hash of that identity. A changed disk revision AND identical process identity supports **the same running Klipper process** before and after AutoSave. If either item is unavailable or unchanged, the result is explicitly inconclusive/incomplete. It **does not** prove that runtime Klipper macro variables were updated and cannot exclude every possible in-process reload.
3. **Real CoreXY MCU-step reviewer:** paste the three `GET_POSITION` `mcu:` lines (before Y, after Y, after X), known +X and +Y calibration steps, configured positive endstop coordinates and optional known starting XY. The pure client-side reviewer computes the motor transform, rejects singular transforms, wrong homing sign, cross-axis drift above 0.15 mm and out-of-bounds results, and displays provisional reconstructed XY only. No calls to G-code endpoints, heaters or movement. A `Load real 6 Nov reference data` button reproduces our actual known-position test with measured +X=(800,800) steps/5 mm, +Y=(800,-800) steps/5 mm, starting motors (4814,27252), Y-home (46739,-14673), X-home (53139,-8273), X endstop 335, Y endstop 362. It reconstructs X295.00000/Y99.96875 from known X295/Y100, a 0.03125 mm Y difference. This is one sample, not demonstrated repeatability.
4. **Export diagnostic JSON:** records the current read-only machine snapshot, optional real-counter inputs and review result for reproducible faultfinding; no credentials and no motion calls.

**Not commissioned:** no automatic motor counter capture/homing, no physical approach or tool pickup/dropoff, no reliable coupling-sensor verification, no heating, no live tool variable synchronisation, no automatic Touch Z probing. The shared extruder thermistor is currently disconnected; it must be verified before any heater test.

**Why G28 motion is locked:** the current printer.cfg supplied by the operator contains `[homing_override]`, `axes: xyz`, `set_position_z: 0`, and an unconditional `G91; G1 Z10; G90` before every XY home. Actual GET_POSITION snapshots showed +8000 Z motor steps after `G28 Y` and another +8000 steps after `G28 X`. This can add physical Z movement despite the apparent Z coordinate. Do not run an automatic dock-calibration G28 from a dock until the active homing configuration has been backed up, reviewed, corrected and physically tested. **Changing printer.cfg necessarily requires a deliberate Klipper configuration reload.**

### Operator no-restart evidence test

1. Install V0.9.0 through the existing CXM-only Updates page while Klipper is idle. Refresh the browser after the updater reports the new installed source.
2. Open **Testing**, click **Refresh real diagnostics** and confirm live status can be obtained.
3. Click **A - Capture baseline**. A valid process identity and configuration revision are required.
4. For the current uncommissioned T0 bench only, change **Hotends in use** in Tools from 1 to 2 while idle. Wait for the disk AutoSave confirmation.
5. Return to Testing and click **C - Compare after AutoSave**. PASS requires the new disk revision and the exact same Linux Klipper process identity. It is a test of process continuity and disk persistence only. If identity is missing, report INCONCLUSIVE; if revision is unchanged, report INCOMPLETE.
6. Restore Hotends in use to 1. No G-code, Klipper restart or manual macro edit should be involved in this disk-only test.

**Runtime boundary:** Disk config updates and CXM webpage source upgrades do not require a Klipper restart merely to be stored or shown. A separate explicitly verified runtime sync stage is still needed for updated tool variables to take effect in active macros. Editing printer.cfg, loaded Klipper macro definitions or MCU pin assignments **does** require a deliberate Klipper RESTART (firmware restart only when specifically required), ideally after an idle backup. Neither CXM's update workflow nor this testing page automatically restarts Klipper.

**Documentation:** The 16-page illustrated CXM Control Centre Operator Guide V0.9.0 contains the seven-tab walkthrough, real 6 November screenshots (some historical UI versions), a schematic of the new Testing page, restart evidence workflow, actual XY step-count example and staged T0 commissioning sequence. The guide is delivered separately as a PDF in the ChatGPT conversation; this repository documents the supported actions and limitations as text.

**Validation:** `python3 -m unittest discover -s tests -v`, `node --check web/cxm-testing.js`, `node --check web/cxm-test-math.js`, and `node --test tests/test_commissioning_ui.cjs`, plus existing project CI. All Testing actions fail closed and do not make a tool READY.

## V0.9.1 — Single-page dock calibration (UI consolidation)

The normal XY measurement-review workflow now lives entirely on **Dock Calibration**, directly above **2 · Align dock position**. The previously embedded counter reviewer has been removed from **Testing**; Testing keeps its live diagnostic status, restart-free AutoSave evidence, and diagnostic JSON export for faultfinding.

In Dock Calibration, select T0–T11, view real Klipper status, load the 6 November reference dataset to verify the calculator, or choose **Start new T0 capture** to review newly gathered MCU step-count snapshots. Enter verified CoreXY calibration step deltas and the three GET_POSITION MCU snapshots; **Calculate provisional XY** uses the existing pure offline maths and validates cross-axis drift, homing sign, bounds and finite values.

**Copy proposed X/Y to dock draft** is only offered for a newly started manual capture that has no known-position reference, has a finite valid result, matches the selected hotend and has the operator's explicit physical-clearance acknowledgement. The past reference dataset can never be copied by its example button. A final confirmation copies only raw X and Y into the selected hotend's *unsaved* draft; it preserves Z, does not apply x_docking_adjust, never posts to the backend, does not move, heat or unlock the printer, and never marks a tool physically verified. The existing full XYZ acceptance, Klipper idle check, revision-gated AutoSave and backup system are unchanged.

**Not yet integrated:** live MCU capture, automated Y-then-X homing, automatic docking, pickup/dropoff and live Klipper activation of saved coordinates. Do not invoke G28 from a parked hotend before the Z homing-override fault is fixed and the entire path is physically inspected. This release is a front-end-only layout/workflow consolidation: **no Klipper restart or modification to printer.cfg**.

**Verification:** install V0.9.1 using Updates, hard-refresh the page, open Dock Calibration and click Load 6 Nov reference test → Calculate provisional XY; expect X295.00000 / Y99.96875 and a disabled Copy proposed X/Y button. Click Start new T0 capture and confirm the three snapshot fields and known references are cleared. The Testing page must no longer contain the XY calculator.


## Historical V0.9.2 note — superseded by V0.9.3

**Do not apply the old V0.9.2 homing installer from a previously downloaded script.** It removed the automatic Y-before-X dependency when G28 X was requested. That violates CXM's mechanical safety requirement. The current `scripts/cxm_homing_fix.py` in V0.9.3 replaces it and supports conversion from either the original or previously applied V0.9.2 configuration.

## Hardware commissioning: homing override correction (X/Y-only G28 Z-drift fix)

This **optional, operator-applied** patch addresses the CXM gantry rising another 10 mm on each \`G28 Y\` / \`G28 X\`. The existing \`printer.cfg\` has \`[homing_override]\`, \`axes: xyz\`, unconditional \`set_position_z: 0\`, and a 10 mm relative Z lift. The actual 6 November captures showed **+8,000 Z motor counts** on both an XY-only Y home and a subsequent X home.

The smallest safe fix changes the override to \`axes: z\`, so individual \`G28 Y\` and \`G28 X\` are performed by native Klipper XY homing and **do not run the override's forced Z reset or lift**. Full \`G28\` still invokes the override, using the original first Z10 lift, Y → X → Cartographer Z at X195/Y170, and final Z5 lift. The patch also makes \`G28 Z\` home missing X/Y axes before moving to the Cartographer location. Note that Klipper **no longer forces Y first when \`G28 X\` is invoked alone**: use \`G28 Y\` followed by \`G28 X\` as separate commands for the CXM measurement procedure. The machine must be physically clear along the entire homing path and initial full-home lift.

In SSH on the Pi after updating the CXM Git repo:

\`\`\`bash
python3 ~/CXM/scripts/cxm_homing_fix.py
python3 ~/CXM/scripts/cxm_homing_fix.py --apply
\`\`\`

The first command prints the exact proposed diff and **never edits**. The second fails closed unless Moonraker confirms Ready/Idle, makes a timestamped backup at \`printer.cfg.cxm-before-homing-<timestamp>.bak\`, edits only the known \`[homing_override]\`, atomically writes, and verifies bytes. It neither moves the printer nor restarts Klipper. Never run \`--apply\` if the preflight differs from the expected configuration, or if a print or calibration is in progress.

**One deliberate Klipper \`RESTART\` is required** because this modifies \`printer.cfg\`, unlike ordinary CXM disk-only AutoSave. After safely parking and verifying clearance, use Mainsail Console \`RESTART\`. Confirm Klipper reconnects and a complete **full** \`G28\` still homes Y first, X second and Cartographer Z. **Do not** perform an uninspected full \`G28\` from a dock or when the physical 10 mm Z lift is unsafe. With the nozzle clear and Z homed, record \`GET_POSITION\`, run \`G28 Y\`, record \`GET_POSITION\`, then \`G28 X\` and record again. Neither individual XY homing operation should advance any Z MCU step counters. If Z changes unexpectedly, stop, do not enable the automatic dock measurement and investigate other macros or firmware. The full original backup can be restored manually after stopping Klipper; then a deliberate \`RESTART\` is needed again.

This patch does **not** enable live endstop travel capture or pickup motion in CXM Control Centre, and does **not** solve extruder thermistor disconnection or independent Z-step loss. It is a necessary XY-only homing prerequisite before live dock-calibration motion.


## V0.9.3 — G28 X MUST home Y before X, and XY-only G28 must not lift Z

**Non-negotiable safety invariant:** All normal \`G28 X\` and \`G28 X Y\` commands must automatically home **Y then X**, with no operator-dependent sequence. Standalone \`G28 Y\` homes Y. Full \`G28\` continues the established 10 mm initial Z clearance, Y → X → Cartographer Z at X195/Y170, then Z5. Z-only commands retain the existing Cartographer homing override and home missing XY axes if necessary.

This release corrects V0.9.2's unacceptable loss of the \`G28 X\`→Y-first dependency. The revised installer adds a public \`[gcode_macro G28]\` with \`rename_existing: G28.1\` and preserves a \`[homing_override]\` limited to \`axes: z\`. Both the Y and X native homing calls use the private \`G28.1\` alias so the forced \`set_position_z: 0\` and \`G1 Z10\` do **not** execute during XY-only homing. The Z override's own G28 commands are rewritten to call that private alias while executing under the override's recursion guard. This combination was checked against Klipper's actual \`homing_override.py\` and \`gcode_macro.py\` command-registration model.

**Operator rule:** Do not enter \`G28.1\` directly; that is a private implementation alias. Use ordinary \`G28\`, \`G28 X\`, \`G28 Y\` or \`G28 Z\`. G28 X will execute a Y home first even if Y is already homed, as the user requires.

**Important physical limitation:** The new XY-only homing deliberately does not generate a Z hop. Clear the *entire* Y-then-X travel path, not just the starting position, before any movement. Full/Z homing still uses the original forced initial Z clearance and must be independently verified at the actual gantry position. Do not enable live dock calibration until the hardware tests below pass.

### Installer: use CURRENT v0.9.3 script, not a stale cached copy

\`\`\`bash
curl -fLsS https://raw.githubusercontent.com/qp1306/CXM/main/scripts/cxm_homing_fix.py \
  -o /tmp/cxm_homing_fix_v093.py
python3 /tmp/cxm_homing_fix_v093.py
# Inspect the entire proposed diff; ensure [gcode_macro G28] is added.
# Then, only if Klipper is ready/idle and the diff is correct:
python3 /tmp/cxm_homing_fix_v093.py --apply
\`\`\`

Preflight is read-only; \`--apply\` fails closed unless Moonraker reports idle, the exact known original/v0.9.2 override is present, and no obvious duplicate public G28 macro exists in the main config or neighbouring config files. It backs up the current config with a timestamp, writes atomically, and verifies the file. It **does not** issue motion or restart Klipper.

Since the change affects \`printer.cfg\`, a **single intentional Klipper \`RESTART\`** is required after applying, while physically parked and safe. No separate RESTART is required for the webpage update or normal disk-only CXM AutoSave.

### Mandatory acceptance before enabling any dock motion

1. Preflight must display a \`[gcode_macro G28]\` with \`rename_existing: G28.1\`, \`axes: z\` override, and changed internal \`G28.1 Y/X/Z\` calls.
2. After a deliberate \`RESTART\`, physically verify a safe Z clearance path. Home safely under supervision.
3. With XYZ homed and the entire XY path clear, record \`GET_POSITION\`, run **one normal \`G28 X\`**, and record \`GET_POSITION\`. Observe the carriage move **to Y endstop first and then X endstop**. The four Z MCU step counters must not change.
4. Repeat once from a suitable safe reference point. Do not call G28.1 manually. Stop if the sequence, steps or physical clearances deviate.
5. In Testing diagnostics, the new config is labelled \`Y-first wrapper installed · Z-only override · PHYSICAL TEST PENDING\`. A green hardware certification is **not** inferred from code alone.

The new Jinja test suite renders command sequences for \`G28 X\`, \`G28 X Y\`, \`G28 Y\`, full \`G28\`, \`G28 Z\` with axes homed/unhomed, and mixed X/Z cases. These tests establish *intended command expansion*, not real-world motor clearance, repeatability or firmware integration.

If an old v0.9.2 \`--apply\` was already used, the v0.9.3 installer supports upgrading that configuration, but Klipper must still be retested physically before dock calibration is unlocked.
