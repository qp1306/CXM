# CXM Control Centre

> **Current commissioning baseline — 10 November 2026**
>
> Pickup/drop-off use the repeatedly proven three-axis-commands-per-operation
> sequence, with T0 release-side X304.60625/Y65.60000, engagement X+4.4,
> Y clearance +100 and F6000. Klipper macros own ALL physical XY movement,
> including supervised manual jogging (`CXM_MANUAL_DOCK_JOG`).
> CXM Python only stores/rechecks coordinates and dispatches named macros.
>
> **Clean-install proof:** Run `python3 -m unittest discover -s tests -p
> test_clean_install.py -v` to exercise a temporary empty CXM datastore,
> first-time saves for T0–T11, and both macro installers without modifying a
> live printer. See [safe clean install checklist](docs/CXM_CLEAN_INSTALL_CHECKLIST.md).
> Do **not** delete `printer.cfg` or live CXM calibration to run these tests.
> Real automatic hardware movement still requires supervised commissioning.
>
> Sections below contain historical migration notes and may describe earlier
> control paths. Use the current checklist and proven baseline for new installs.


**Current scope: supervised motor-on manual dock XY commissioning with the original CxChanger native pickup/dropoff motion.**

The original Lineux auto measurement and MCU-step recalculation have been retired from the
active control path. Do not disable CoreXY motors or attempt to hand-drag the carriage.
CXM uses a carriage-mounted extruder and exchangeable hotends; calibration records a
provisional locking-hole XY datum, not a verified toolchange.

## Install manual calibration V2 (after GitHub update)

1. When Klipper is idle, update the repository and restart the Python service:
   `cd ~/CXM && git pull && sudo systemctl restart cxm-config.service`
2. Run the removal installer **without** apply first:
   `python3 ~/CXM/scripts/cxm_manual_calibration_install.py`
3. Review the exact module/include/config paths it intends to remove, then run:
   `python3 ~/CXM/scripts/cxm_manual_calibration_install.py --apply`
4. Run **RESTART** in Mainsail while the printer is clear of docks. This unregisters
   the old Klipper calibration module and reloads the unchanged native CxChanger macros.
5. Hard-refresh CXM Control Centre. Dock XY now shows manual jogging and capture.

The installer backs up `printer.cfg`, the old module and its calibration CFG before
removing only those recognised Lineux components. It never removes
`CXM_variables.cfg`, old coordinate backups, CxChanger native macros or homing
override. Old schema-3 `lineux_raw_x/y` and X/Y correction settings remain on disk
**only for backward-compatible loading**; manual capture does not use them and a new
save clears the old raw values.

## Clear All — recover from a failed toolchange or stuck test

When a failed sensor check leaves CXM showing a running test, fault or the
wrong mounted-tool identity, use **Tools → Load or unload → Clear All**.

1. Confirm the printer is completely stationary and not printing. Physically
   remove the hotend from the carriage and return it to its correct dock.
   **Do not force a mechanically trapped hotend or move the gantry to do this.**
2. Inspect that the carriage is genuinely EMPTY, all docks are unobstructed,
   and the filament-detection sensor reports `RELEASED`.
3. Tick the physical-empty approval, then select **Clear All errors & reset
   toolchanger**. The button remains disabled when the sensor reads
   `PRESSED`, geometry is unsynchronized or the operator hasn't approved.
4. The backend checks the current config revision, physical sensor and idle
   Klipper state, then invokes the **existing** Klipper
   `CXM_RECOVER CONFIRM=EMPTY` macro. The macro cancels a stuck delayed test,
   repeats real `RELEASED` sensor checks and resets only runtime toolchange
   state. The API re-reads Klipper before reporting success.

**Verified success:** `current_tool=-1`, `fault=0`, `test.running=0`,
`test.stop=0`, `test.state=idle`, sensor `RELEASED`.
This **never** homes or moves the printer, deletes dock coordinates,
resets tool XY/Z offsets or marks a new tool commissioned. Klipper macros
are unchanged, so no Klipper restart is required by this update.
If any guard fails, stop and inspect the machine rather than overriding it.
The CXM Python service auto-reloads updated sources when no tool cycle is active.

## First T0 release from the captured engaged dock position

Manual alignment may end with a mounted hotend already seated in its dock at
the saved locking-hole X/Y. Normal UNTOOL intentionally rejects that starting
position to avoid an unsafe approach. Use **Tools → Release from calibration
position** only for this special commissioning state.

The release uses a separate guarded Klipper macro `CXM_CALIBRATION_RELEASE`.
It requires the native T identity to match the selected mounted hotend, sensor
PRESSED, XYZ homed, all XY and quad Z motors powered, at least Z20, no active
test/print, accepted geometry, and physical current X/Y within **0.15 mm**
of the synchronised dock coordinates. The operator must physically verify the
mounted hotend is ALSO engaged in its own dock and approve the movement.
Then it performs only the existing CxChanger release tail:
X to latch-shift → Y dodge → X reset → Y safe staging.
Sensor RELEASED must verify before native tool identity becomes EMPTY.
Normal `CXM_SELECT_TOOL` and its inside-approach guard remain unchanged.

**Install one-time updated native Klipper macro before this button can work:**

```bash
cd ~/CXM
git pull
sudo systemctl restart cxm-config.service
python3 scripts/cxm_native_install.py       # dry-run and backup preflight
python3 scripts/cxm_native_install.py --apply
```

The installer backs up the previously installed native macro, checks duplicate
definitions and prints a diff. **Do not apply or RESTART while a hotend is
trapped between the carriage and dock or if the gantry is not mechanically
supported.** Restart can de-energise Z motors and move the gantry, especially
on a machine with an unresolved Z drive issue. Install/activate this feature
only after physically securing the machine and resolving that risk. After a
safe `RESTART`, Klipper resets native RAM tool identity to UNKNOWN; use the
existing native initialization with the physically mounted tool again and
verify the accepted geometry before any movement. This macro has not been
physically validated; supervise its first use with emergency stop accessible.
On an error, leave the machine untouched and inspect actual physical state
before re-enabling any automatic movement.

## New dock calibration procedure

- Home XYZ with the existing tested Y-first homing override. Keep ALL X/Y and four Z motors
  energised, confirm Z >= 20 mm and the selected hotend physically MOUNTED on the carriage (sensor PRESSED).
- Dock Calibration → select T0 → **Refresh live position**.
- Approve supervised jog, use 10 / 1 / 0.1 / 0.01 mm jog increments to align the
  locking screw with the centre of the correct dock hole. Every jog is guarded by
  homing, motor, PRESSED sensor, idle, physical axis limits and any conflicting native identity. The operator must verify the selected mounted hotend identity.
- Inspect alignment; approve and **Capture X/Y to draft**. This runs M400 and reads
  Klipper's live XY. No auto save, release motors, calibration G28 or toolchanging.
- Review and **Save dock XY**. Persisted calibration has revision checks and backups;
  previous native geometry is invalidated until explicitly synchronised again.
- Use the existing native synchronisation/confirm-empty workflow, then conduct ONE
  supervised slow pickup/dropoff with physical switch checks before repeat tests.
  Do not perform automatic X-window search until safe failure recovery is tested.

**Provenance limits:** Motor-on Klipper XY is a repeatable commanded position, not
an independent mechanical measurement. The carriage sensor only proves a binary
presence change, not perfect seating. Failed pickups must stop and require inspection.

**Mounted dock Save:** Manual alignment requires the selected hotend mounted and
sensor PRESSED. A provisional XY Save is permitted with the hotend still
mounted only while the native Klipper toolchanger is already fully invalidated
(ready=0, fault=1, current_tool=-2), no native test is running and the full
motor-on calibration preflight still passes. Saving writes configuration and a
backup only; it does NOT declare the mounted tool, synchronise geometry or
authorise motion. This exception does not apply to general settings edits.

**This release does not alter the existing CxChanger pickup/dropoff macro sequence.**
The 1 mm cross-tool safe-Y guard still applies; calibrate and evaluate each physical
dock Y before multi-tool cycles. Older release notes below are historical.

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


## Dock XY: motor-release state and long-running homing requests (7 Nov 2026)

The CXM API Nginx bootstrap previously used \`proxy_read_timeout 6s\`; the
supervised homing command may require longer, and the Python Moonraker bridge
allows up to 125 seconds. The gateway must allow more time than the backend.
A stale proxy can return an HTML 504 to Safari, which may surface the vague
"The string did not match the expected pattern" error. **An HTTP timeout
does not prove that the printer did not move.**

After updating CXM from **Updates**, SSH to the printer and run the
read-only Nginx installer preflight:

\`\`\`bash
python3 ~/CXM/scripts/cxm_config_install.py
\`\`\`

If preflight recognises the existing CXM configuration and reports the
150-second read timeout upgrade, apply it with a timestamped backup, Nginx
validation and reload:

\`\`\`bash
python3 ~/CXM/scripts/cxm_config_install.py --apply
\`\`\`

The installer recognises the exact original six-second CXM API block and
does not overwrite unrecognised/custom routes. It can restart only the
CXM config service and reload Nginx; it **does not alter printer.cfg, move
motors or restart Klipper**. Stop if preflight fails and inspect the output.

When X/Y steppers are already OFF and all four Z motors report ON, Dock XY
now labels **Step 2 COMPLETE** and blocks a duplicate release. Repeating
Release X/Y does not solve an unready measurement. If Step 4 is unavailable,
use **Refresh machine readiness** while Klipper is idle. If the reported X
position lacks the software margin required for the initial Lineux +3 mm jog,
do not seed fake coordinates, re-home from a dock, or jog X/Y after moving by
hand. Recover the carriage to a physically safe, clear homing location
under supervision, establish a fresh genuine home/centre park, then release
X/Y once for a new measurement attempt. This is a physical commissioning
step and cannot be made safe by an automatic webpage action alone.


## T1–T11 supervised pickup/dropoff — selected-hotend commissioning

The **Dock XY** hotend selector now chooses the test tool. Selecting T0 displays
the original proven T0 controller with its separate repeat-cycle controls.
Selecting T1–T11 displays new **single, supervised Pickup / Dropoff** buttons.
These use only the selected tool's accepted saved CxChanger locking-hole X/Y
datum and shared relative X-latch/Y-dodge/safe-clearance settings; **Lineux
is used for locating the datum, not moving the hotend**.

Each test is gated by Klipper READY/IDLE, genuine homing, at least Z20,
powered X/Y and four Z steppers, accepted XY datum, maintenance lockout,
safe XY waypoint bounds and a fresh approval. The shared
\`gcode_button cxm_tool_detect\` reports the physical **FILAMENT PRESENT**
(hotend on the carriage) or **FILAMENT ABSENT** (empty carriage) state. It
**does not electrically identify a hotend**. The hotend selected at the
beginning of Dock XY calibration (T0–T11) is the operator-declared tool
identity and supplies the corresponding CxChanger XY geometry.

- **Selected T1 + ABSENT** → after physical path approval, allow Pickup T1;
  expect the switch to become PRESENT.
- **Selected T1 + PRESENT** → after visually confirming the attached hotend
  is in fact T1, its dock is empty, and the dropoff route is safe, approve
  Dropoff T1; expect the switch to become ABSENT. A prior controller pickup
  is **not required**, e.g. if T1 was attached before the service restarted.
- A verified successful pickup that records another hotend (e.g. T1
  mounted but T2 selected) continues to block cross-tool motion. Switching
  the UI tool number alone does **not** prove the physical hotend changed.
- A prior unresolved T0 motion fault also blocks T1–T11 operations until
  it has been physically inspected and cleared.

The approval checkbox is the deliberate operator identity/path confirmation;
no duplicate modal or second 'already mounted' confirmation is required.
No tool electrical identity is inferred from the carriage switch.

For initial commissioning, test each newly installed T1/T2 individually:
save Lineux XY, physically verify every waypoint, approve the single
appropriate Pickup or Dropoff for the real presence state, inspect the
mechanism and switch after each move. Repeat cycles remain **T0-only**
until T1/T2 have completed individual physical tests.
These movements verify only the presence-switch transition, not tool seating
strength, heater or thermistor switching, Z offset or full commissioning.
No \`printer.cfg\` edits or Klipper restart are required simply for this web
and loopback-service update. The CXM service may restart itself to load new
Python code, which clears ephemeral mounted-tool identity.


## T1–T11 carriage sensor stabilisation and fault recovery

For selected-hotend pickup/dropoff, CXM now waits for **four consecutive**
PRESSED (pickup) or RELEASED (dropoff) readings from the actual Klipper
carriage switch, sampled roughly 150 ms apart within a 2.5-second
post-motion window. Checking begins **after** the ordered CxChanger motion
script completes and Klipper is idle. The read-only check does **not**
retry any tool movement or alter dock geometry. If the expected state
never stabilises, the original hard fault remains latched and later
moves remain blocked. T0's proven movement/sensor logic is not changed.

An earlier failed T1–T11 pickup can leave a latched fault if the switch was
temporarily RELEASED at verification and subsequently reads PRESSED.
Following **physical inspection**, the Dock XY panel offers a special,
no-motion clear action **only** for an actual failed-pickup fault with the
same selected tool and currently PRESSED switch. The operator must verify
the selected hotend is genuinely coupled/secure and that its dock is empty.
The backend then rechecks that PRESSED is stable for four samples and clears
**only that fault**. An unrelated dropoff fault while PRESSED stays blocked.
When the switch is RELEASED and the carriage is genuinely empty, the
existing inspected-empty fault-clear path still applies.

The switch establishes presence, **not hotend identity**; human inspection
still matters. An update of the CXM Python backend may restart the CXM
service and lose ephemeral fault records: absence of the old fault after an
update is not proof that the physical issue was fixed. Do not initiate
more motion until the real tool, coupler and dock have been inspected.



## Supervised multi-tool XY cycle test — mechanical commissioning only

The **Tools** page has a **Multi-tool XY cycle test** panel. It includes
only enabled/configured T0–T11 profiles whose CxChanger locking-hole
**Dock XY has been measured, saved and accepted**, with a valid guarded
CxChanger motion plan and no maintenance lockout. It is not conditional
on XY/Z offset acceptance, heaters or the global **READY** banner:
those are different, still-unfinished printing requirements.

For first commissioning, prove each tool **individually** with a slow,
supervised pickup and dropoff before attempting the combined pass.
For the aligned front row, select T0/T1/T2 in order. Each **complete cycle**
performs exactly two movements per selected tool:

    T0 Pickup → verify PRESENT → T0 Dropoff → verify ABSENT
    T1 Pickup → verify PRESENT → T1 Dropoff → verify ABSENT
    T2 Pickup → verify PRESENT → T2 Dropoff → verify ABSENT

The worker runs asynchronously on the loopback CXM service, preserving
live progress across browser refreshes. **Start requires** a physically
EMPTY carriage, confirmed by the carriage switch, genuinely homed XYZ,
Z ≥20 mm clearance, powered X/Y and four Z motors, Klipper ready and
idle with no print/paused job, and a valid unchanged configuration revision.
The operator must individually inspect every dock and the complete XY
motion route; start requires a fresh large checkbox approval. The
multi-tool pass uses the existing native CxChanger pickup/dropoff motion
script and speeds for each selected tool. **No Lineux movement, G28,
heater commands, extrusion or Z movement is issued**. Four consecutive
post-movement sensor samples must confirm the correct PRESSED/RELEASED
transition before moving to the next action.

The initial mode deliberately requires selected dock safe-Y staging
lines to be within **1 mm** of each other, because transfer between
misaligned dock rows has not been proven safe with this native stage
script. The backend rejects invalid/missing docks, wrong starts, missing
sensor, unresolved T0/T1+ faults, sensor mismatches, revision changes,
or active movement before issuing further moves. It acquires the same
shared CXM movement lock for the **entire pass**, so no other CXM
dock/tool commands can interleave. **Mainsail console commands are not
covered by that lock**: do not jog, start prints, issue custom G-code,
or restart the printer while the pass runs.

**Stop after current tool** completes the current pickup+dropoff pair
before stopping with an EMPTY carriage. It is not an emergency stop and
does not interrupt an in-progress G-code script. For immediate danger
use the printer's physical E-stop. A failed pickup or dropoff halts the
entire run with a latched T0 or T1+ fault; **no automatic retry or forced
dropoff** follows an uncertain pickup. Inspect actual coupling and dock,
then use the appropriate individual tool fault-recovery route.

Each supervised run may repeat the complete tool sequence **1–20 times**
(subject to the 240-movement limit). Unlimited repeats, tool heating,
extruder assignment, nozzle Z compensation and production toolchanging
remain out of scope. A pass
confirms mechanical motion and presence-sensor transitions only; it
does **not** mark tools commissioned or clear NOT READY labels. The
source update may restart only the CXM backend. During an active run,
its automatic source-reload monitor defers the restart until the pass
finishes, but external reboots/service restarts and printer emergencies
cannot be made safe by a web UI.

## Multi-tool XY cycle: optional faster clear-corridor travel

The **Tools → Multi-tool XY cycle test** panel now offers an **opt-in**
**Faster clear-travel mode (30 mm/s)** checkbox. It starts unchecked.
First run a successful supervised standard-speed pass.

- **Standard (default):** existing 600 mm/min (10 mm/s) Y-then-X staging;
  240 mm/min (4 mm/s) docking approach and retreat; 180 mm/min (3 mm/s)
  locking/releasing X motion.
- **Faster (opt-in):** 1800 mm/min (30 mm/s) only within the safe clearance
  corridor: speed drops to 4 mm/s 10 mm **before** the Y-dodge point;
  retreat remains slow until 10 mm **beyond** the Y-dodge point.
  Coupling, dodge, latch and final approach use the exact standard speeds.
  Same coordinates, Y-first safe staging, and M400 barriers. No Z motion,
  extrusion, heater commands, Lineux calibration or printer.cfg edits.
- Changing the profile revokes the existing approval. The mode cannot
  change mid-run. The backend accepts only standard and faster profiles,
  never arbitrary feed values. The regular T0 and T1+ single-tool motion
  scripts remain unchanged.
- Per-step event logs now include observed elapsed seconds (motion request
  plus post-motion sensor confirmation). Compare equivalent supervised
  passes, not commanded speed alone.

**First physical faster-mode test:** use only T0 and T1, already proven
individually, with an empty carriage and truly homed XYZ. Inspect that the
new fast corridor has clearance from other docks, magnets and projections.
Select the Faster checkbox, review the separate physical safety approval
and supervise one two-tool pass with access to the actual emergency stop.
Only add T2 if that passes. If rubbing, skipped steps or unusual sounds
occur, stop the machine, inspect, and revert to Standard. CI simulations
cannot prove clearance or mechanical suitability at higher feed rates.


## Multi-tool mechanical XY testing: selectable repeat count

The **Tools → Multi-tool XY cycle test** panel now includes a prominent
**Repeat complete tool cycles** numeric field. One cycle means one full
pickup and dropoff for **each selected, dock-accepted hotend** in ascending
order (for example T0 pickup/dropoff, T1 pickup/dropoff, T2 pickup/dropoff).
The default remains **one** cycle; select **1–20** for three tools. The
backend additionally limits the total to **240 individual movements**
regardless of the configured number of hotends. For more than six tools,
the UI lowers the allowed maximum to stay within this cap. The backend
independently rejects noninteger, negative, zero, excessive, or otherwise
invalid cycle counts **before any movement**. Old API clients without the
new field remain single-cycle.

A five-cycle T0/T1/T2 test therefore contains **30 sensor-verified
pickup/dropoff movements**, not five individual swaps. The event log
labels the current cycle, the page reports **completed cycles** separately
from **confirmed movements**, and a progress bar uses the requested number
of movements. The standard and optional faster clear-travel profiles both
support repeats without altering their proven docking/latch speeds.

Between *every complete cycle* the controller performs a fresh read-only
readiness check: same saved configuration revision and Klipper process,
homing/motor state, no latched motion fault, genuinely empty carriage
with stable sensor, and carriage still in the aligned safe-Y transfer
corridor. The next tool stage moves Y to its guarded safe coordinate
**before** moving X. Because all selected dock safe-Y lines must be
within 1 mm, a fully completed pass can restart at the last dock's safe
staging Y without requiring unnecessary manual repositioning.

**Stop after current tool** still completes the presently active
pickup/dropoff pair and does not start another tool. Progress counters
show how many complete cycles actually finished when stopped. A failed
pickup/dropoff **immediately halts all later tools and cycles**, retains
a tool fault for physical inspection, and never retries automatically.
Use the real printer emergency stop for immediate hazards. Every new
requested run requires a new physical safety approval; changing the
repeat count or travel profile revokes approval. This remains a
supervised, mechanical-only test—not print readiness.


## Diagnose pause time between tool movements (non-invasive)

The multi-tool test now records four separate elapsed periods for every
completed selected-tool pickup/dropoff. It **does not change the physical
docking motion, programmed speeds, Klipper idle safety check, M400
barriers, or the stable carriage-sensor verification**.

The Tools page live event log shows:

- **Preflight:** configuration reads, Klipper info/homing/motor-power/idle
  queries, and four pre-movement sensor readings. This phase is the
  likely delay *after the previous tool finishes and before the next
  tool begins moving*.
- **G-code:** Moonraker /printer/gcode/script execution including staging,
  X transfer, native CxChanger pickup/dropoff and M400 completion. A
  delay *at the staging position before entering the dock* belongs here.
- **Idle:** confirmation that Klipper is fully idle and carriage is at
  the correct end-of-operation safe XY position.
- **Sensor:** four consistent PRESSED/RELEASED samples after the move.

The event also includes **total elapsed seconds** (including preflight),
while the existing duration field retains the legacy G-code-and-check
semantics for compatibility. The web log now shows the most recent 48
events instead of 9, so T0/T1/T2 phase comparisons are visible after a
single test.

Compare one supervised standard/faster pass with an empty carriage and
known safe dock geometry. If **Preflight** dominates, focus on redundant
RPC calls or duplicate pre-sensor checks without weakening physical
verification. If **Idle** dominates, investigate Klipper idle_timeout
transition after M400 without blindly removing the barrier. If
**G-code** dominates, examine staging feed and the safe Y/X motion
segments separately from the coupling path. Changes to motion timing
must follow **measured** behaviour and be tested independently.


## Remove duplicated sensor verification between CXM multi-tool operations

Measured on an actual T0/T1/T2 six-movement pass: approximately 27.73
seconds overall, with **9.01 s preflight**, **6.00 s post-motion switch
verification**, **4.10 s Klipper idle checks**, and **8.61 s executed
G-code**. This made it clear that travel-feed increases alone would not
fix the observed pause between operations.

The multi-tool sequence now carries a **four-sample verified occupancy
result** forward. The first operation is backed by the original
four-consecutive-RELEASED startup check. Every successfully completed
pickup or dropoff is backed by the original four-consecutive PRESSED or
RELEASED post-motion check and Klipper's live idle/park verification.
For each following operation the controller still performs a **new live
switch read immediately before dispatching any G-code**, and checks that
it agrees with the previous stable result. It no longer waits for an
unnecessary *second set of four stable samples* before each move.

At the boundary between full repeat cycles, the original complete
readiness and four-stable-empty checks still run, and their verified
result becomes the next cycle's trusted starting state. Calls to the
internal step function without that verified result retain the old
four-sample precheck. A mismatch, failed four-sample postcheck,
invalid Klipper state, stale revision or missing motor/homing state
still **fails closed and stops all later motions**.

No change was made to the known-good CxChanger X/Y movement geometry,
Standard/Faster travel profiles, M400 barriers, lock/approach feeds,
four-sample **post-movement** confirmation or separate T0/T1+ controls.
The intended improvement is roughly the duplicated pre-movement
verification time (previously ~1 s per move), **not** a guarantee of
mechanical performance. Compare a supervised one-pass T0/T1 test before
and after installation using the live per-step timing diagnostics before
testing repeated three-tool cycles.


## Reduce redundant Moonraker queries during continuous multi-tool testing

The current known physical baseline is **21.74 seconds** for a
six-movement T0/T1/T2 test after removing duplicated pre-motion sensor
debouncing. A substantial part of the remaining software overhead was
the same three-request Klipper readiness procedure repeated before and
after every move: `/printer/info`, `/printer/objects/list`, and
`/printer/objects/query`.

The multi-tool worker now **discovers available Klipper objects once at
the beginning of a guarded run** and holds an immutable list scoped to
the Klipper process ID. Every single preflight, every after-motion idle
and parked-position check, and every between-cycle readiness check still
queries **fresh `/printer/info` and live toolhead/motor/idle/print status**.
The cached registry is used only if a fresh `/printer/info` confirms the
exact same ready Klipper process. A process change fails closed before
the cached list is used. An expected `print_stats` object that lacks a
live valid state also fails closed.

As a result each repeated _safe_context call uses two Moonraker GETs
rather than three, but all required physical and process safety
conditions remain verified on each step. Existing individual T0 and
T1–T11 routes **without** a cached registry still perform their
original discovery calls. No changes to G-code, M400, tool geometry,
motor speeds, restart behaviour, stop conditions or four-sample
post-motion carriage switch verification.

To validate: install the CXM update; physically inspect the empty
carriage and selected docks; run one supervised three-tool cycle at a
previously proven travel speed; compare the six per-phase diagnostics
with the earlier 21.74 s baseline. The change is software tested, **not**
yet measured on this printer.


## Multi-tool sensor/status query consolidation

Actual CXM measurements (November 2026) show all Klipper
`/printer/objects/query` calls take roughly **250 ms**, regardless of
whether one sensor or many status objects are requested. Moonraker's
`/printer/info` and `/printer/objects/list` each take only ~3.4 ms.
This explains why process-scoped object-list caching produced
negligible real-world savings.

The supervised multi-tool XY test now includes
`gcode_button cxm_tool_detect=state` in the *same live Moonraker status
response* used to check toolhead homing/position, stepper power,
idle_timeout, print_stats, virtual_sdcard and pause_resume. It makes
the carriage-switch signal available in the returned verified
preflight context. This replaces one separate 250 ms live sensor
query before each pickup and dropoff, at startup, and between passes.

No change to CxChanger motion paths, G-code, locking feed, the
post-G-code Klipper idle/XY/stepper check, **four consecutive sensor
readings after every movement**, repeat limits or stop/fault logic.
The initial and between-cycle **four consecutive empty samples** also
remain unchanged. The fused live status must explicitly report
PRESSED or RELEASED; missing/invalid sensor state fails closed before
movement. A prior stable sensor confirmation must match the expected
state; the new live combined status must independently agree. The
individual T0 and T1–T11 endpoints retain their old independent
sensor sampling.

The observed pre-optimization six-movement mechanical cycle takes
**21.73 seconds**. A ~250 ms reduction per fused preflight could
save approximately **1.5 seconds per T0/T1/T2 pass**; actual gains
must be measured on the printer. This release does not attempt to
reduce the validated post-movement debounce or Klipper idle checks.

**Before physical testing:** inspect the real carriage, confirm it
is empty, rehome the printer (last Klipper status reported
`homed_axes: ""`), verify Z>=20 mm clearance and inspect the full
selected XY path, then run **one** supervised pass at proven speed.
Stop on any unexpected sensor state or movement. The read-only
diagnostics script can be used to compare the new per-step timings.


## Rapid Klipper-local mechanical cycle (new, opt-in)

**The original individually proven CxChanger motion and slow multi-tool
commissioning test remain the default.** The Tools page now provides a
separate `Rapid continuous Klipper mode` checkbox that uses a
**single synchronous Klipper script per complete pickup/dropoff tool
pair**, with position/stepper/homing checks and **four independently
timed, in-process PRESSED and RELEASED sensor reads** after each
mechanical operation. It avoids the previous repeated 250ms HTTP sensor
polls and preserves Stop-after-current-tool-pair. The optional
30mm/s **clearance-only** travel rate remains an independent checkbox;
dock contact and latch feeds are unchanged.

This feature requires a **one-time backed-up Klipper macro install**;
the backend refuses to move if the loaded macro's protocol cannot be
verified. No firmware or printer.cfg update is performed merely by
installing the new CXM web source. The operator must run the dry-run
installer, explicitly `--apply`, and issue **one** safe Klipper RESTART
followed by full XYZ rehoming. The fast execution method is **not yet
validated on physical hardware** and does **not** commission the
printer for multi-hotend printing.

**Read the full safe installation and supervised T0/T1 first-test
procedure:** [Rapid mechanical cycle](docs/rapid-mechanical-cycle.md).


## Faster mechanical motion without increasing latch speed

After proving Rapid Klipper-local verification, the Tools page now
offers an **experimental, opt-in Performance movement** checkbox:
**80 mm/s clear corridor, 8 mm/s guided approach/retreat, unchanged
3 mm/s latch/unlatch.** The new clear-travel section ends 15 mm before
the Y-dodge location; path coordinates and CxChanger coupling
geometry remain identical. Performance is mutually exclusive with the
existing Faster 30 mm/s checkbox, and changing either speed option
revokes the current movement approval. Rapid Klipper execution is a
separate checkbox.

Existing Standard (10 / 4 / 3 mm/s), Faster (30 / 4 / 3 mm/s), direct
T0 and T1+ controls are unchanged. The new speed has only been validated
by automated tests, **not by the physical CXM**. Progress only after
one successful supervised Faster pass, then one Performance pass with
T0/T1 and one repeat, inspect physically, then add T2. The
Klipper-native safety guard remains at 4 confirmed samples after every
motion. **No additional Klipper restart** is required for this
UI/Python-only update when the rapid guard has already been installed
and loaded.

Full procedure: [Rapid mechanical test and Performance](docs/rapid-mechanical-cycle.md).


## Two larger, opt-in CXM XY speed trials (Sprint / Race)

The Tools → Multi-tool cycle page now offers **Stage 1 Sprint**
(**200 mm/s** clear, **40 mm/s** guided, **10 mm/s** latch) and
**Stage 2 Race** (**400/80/20 mm/s**) alongside existing Standard,
Faster and Performance speeds. These presets preserve every accepted
CXM dock coordinate and CxChanger locking path, slow to guided speed
15 mm before the Y-dodge point, and retain **four separately timed
Klipper carriage-switch checks after pickup and after dropoff** when
Rapid Klipper mode is enabled. There are no new Klipper macros or
`printer.cfg` edits, and no change to the printer's global
acceleration or velocity settings.

Both new speeds are **not physically validated** on this machine.
The backend prevents Sprint/Race multi-repeat requests; start with
one supervised T0/T1 Stage 1 cycle only after the last lower profile
passes, inspect the hardware, then one Stage 2 test only if Sprint
shows no mechanical or sensor failures. Changing profiles resets the
approval checkbox, and only one speed profile can be selected.
See [rapid and larger motion speed tests](docs/rapid-mechanical-cycle.md).


## Uninterrupted native Stream and Stage 3 Boost

The supervised mechanical Tool cycle now has a separate opt-in
**Uninterrupted Stream** execution mode. Unlike the per-tool
Rapid Klipper mode, this submits **one ordered Klipper script for
the entire T0/T1 or T0/T1/T2 pass**, removing Python/Moonraker
round-trips between dock releases and the next pickup. Each tool's
unchanged motion path still completes and checks four native PRESSED
readings after pickup and four RELEASED readings after dropoff with
M400-separated time windows. Any failed check aborts the entire script
and latches an all-tools uncertain-state fault. The 390ms settling
window after dropoff remains intentionally unchanged.

**Stop-after-current-tool is NOT available in Stream**, because
Klipper cannot be reliably interrupted between already-queued
commands by that Stop request. The Control Centre disables the
misleading Stop button and warns that a working physical emergency
stop is required. Standard and per-tool Rapid remain available with
their previous Stop-after-current-tool behaviour. Stream requires
2–3 accepted docks and exactly one cycle while uncommissioned.

A separate **Stage 3 Boost** requested speed test adds
**600 / 120 / 40 mm/s** (open / guided / latch). The 600mm/s
commanded travel may not be reached on 40mm segments under the
current 4000mm/s² acceleration. Both Stream and Boost are opt-in,
software-tested only, and must first pass a separately witnessed T0/T1
physical cycle using a previously proven lower speed. No saved
Lineux/CxChanger dock coordinates or printer.cfg settings change.

See [rapid mechanical cycle, Stream and Boost tests](docs/rapid-mechanical-cycle.md).
