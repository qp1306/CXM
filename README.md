# CXM Control Centre

**CXM** is a Raspberry Pi–hosted commissioning and control interface for a custom **Voron 2.4 CoreXY CxChanger-style hotend toolchanger**. It uses a **single carriage-mounted extruder** and exchangeable hotends. Klipper macros perform physical pickup, dropoff and camera travel; a local Python service provides state, configuration and API endpoints; the browser interface provides dock calibration, Tool XY calibration, verification and testing.

> **Field-tested installation snapshot: 15 November 2026.** Six tools (T0–T5) were physically tested for camera alignment and XY-offset correction, including saved-offset fine adjustment and repeat verification. Camera↔dock diagonal transfer was also observed working in both directions. **This is a commissioning milestone, not a production-print release.**
>
> **Repository sync warning:** This README documents the working *printer installation* captured on 15 November 2026. The GitHub source tree must not be assumed identical until a file-by-file comparison and sync from the unredacted live installation has been completed. Do **not** deploy older repository macros over the verified printer.

## What CXM actually does

- **Dock XY:** captures and persists each tool's physical dock coordinates, with accepted geometry subsequently synchronized to Klipper's native toolchanger state.
- **Native toolchange:** Klipper's `cxm_native_toolchange.cfg` carries the actual X/Y movement commands. A presence sensor distinguishes **PRESSED = hotend fitted** from **RELEASED = carriage empty**. The sensor does not identify *which* hotend is mounted; that comes from selected/native state.
- **Camera Tool XY:** T0 establishes the camera datum. T1–T5 each store X/Y correction relative to T0. Selecting a tool returns to the **currently saved corrected position**; manual fine-jogging and Save XY overwrite the full correction, rather than losing or double-applying the old offset.
- **Camera Verification:** visits selected hotends, applies each saved XY correction, and gives a visual hold over the camera to check centering.
- **Fast transfers:** the installed commissioning macro uses a common **Y105 mm dock transfer line** and diagonal travel to/from the camera; the final latch/release movements remain separate, tested dock operations.
- **Web Control Centre:** served locally at `/cxm/`, with Tool XY, Dock Calibration, test controls and related service pages; can be linked from Mainsail custom navigation.
- **Configuration persistence:** `CXM_variables.cfg` is the auto-managed saved profile for up to 12 hotends (6 enabled on the captured printer).

## Architecture

```text
Mainsail / CXM browser (/cxm/)
          │
          ▼
CXM frontend (web/*.js, index.html)
          │ HTTP API
          ▼
CXM Python backend (server/*.py, cxm-config.service)
          │ Moonraker RPC / configuration updates
          ▼
Klipper macros (cxm_native_toolchange.cfg and related includes)
          │
          ▼
CoreXY motion + carriage presence sensor + camera
```

The **Python service does not replace the proven Klipper pickup/dropoff movement** with a separate Python motion script. The physical toolchange path is defined in the Klipper macros.

## Field-test status — 15 November 2026

| Capability | Evidence / status |
|---|---|
| T0 camera reference | Field-tested |
| Six-tool (T0–T5) camera verification | Field-tested; user confirmed all aligned |
| Reuse saved XY offsets on tool selection | Field-tested with Calibration Reload v3 |
| Fine-jog, overwrite XY offsets, re-verify | Field-tested |
| Camera ↔ dock diagonal transfers | Field-tested in both directions |
| Shared dock transfer Y=105 mm | Retained in tested movement |
| Cold mechanical toolchange testing | Commissioning use; do not infer unlimited repeatability |
| Z calibration / QGL stability | Outstanding independent validation |
| Heater and thermistor switching | Not established as production-ready |
| Tool changes while printing / slicer integration | Not established as production-ready |
| Full clean reinstall and recovery test | Not yet demonstrated |

Some `offset_xy_accepted` and `offset_xy_verified` datastore flags were still `False` in the review export even though physical optical verification succeeded. **Do not equate the UI's formal commissioning flags with the observed camera alignment.**

## Current on-printer layout

| Location | Role |
|---|---|
| `~/CXM/server/` | Python configuration, runtime, API and native integration |
| `~/CXM/web/` | Control Centre frontend |
| `~/CXM/scripts/` | Maintenance/install/reconciliation scripts |
| `~/CXM/tests/` | Automated regression tests |
| `~/printer_data/config/printer.cfg` | Main Klipper configuration and include chain |
| `~/printer_data/config/cxm_native_toolchange.cfg` | Active native toolchange and camera macros |
| `~/printer_data/config/CXM_variables.cfg` | Live calibration and tool data (machine-specific) |
| `~/printer_data/config/cxm_fast_guard.cfg` | Motion profile support |
| `~/printer_data/config/CXM_detection.cfg` | Presence-sensor configuration |
| `~/printer_data/config/.theme/navi.json` | Mainsail sidebar link to CXM |

Not every printer-specific configuration should be published unchanged. Hardware IDs, calibration state and network addresses must be reviewed before sharing.

## Operating sequence: Tool XY

1. Confirm the native tool identity and physical presence sensor agree.
2. Select or mount **T0**, visually centre it on the camera, and save **T0 camera reference**.
3. Select **T1** (or any other calibrated tool). The Tool XY card should use that tool's *saved* correction rather than starting from the raw T0 datum.
4. Make a small XY jog only if needed; **Save Tn XY** replaces that tool's previous total X/Y correction.
5. Run **Camera Verification** to check the corrected position.
6. Repeat for T2–T5. The current six-tool installation has been confirmed to align during this loop.

A physical camera alignment demonstrates the nozzle's projected XY registration. It does **not** by itself validate dock engagement, Z offsets, heater behavior or print reliability.

## Configuration and operation cautions

- The local archive `CXM_Golden_FULL_2026-11-15.tar.gz` is the **authoritative private recovery snapshot**, not this repository. The user verified its gzip integrity and SHA-256 both on Pi and Mac.
- Never commit that full backup: it may contain passwords, credentials and machine identifiers.
- A separate `CXM_Golden_REVIEW_2026-11-15.zip` was sanitized for inspection; its redaction removed complete source lines, leaving some Python/JS syntactically invalid. **Do not deploy or publish these redacted files as functioning code.**
- Do not overwrite the proven Y105 motion or saved calibrations with historical installers without an explicit diff and a real printer test.
- Run existing tests against a staged copy, not by resetting working production calibration on the printer.
- Klipper config changes generally require a controlled Klipper reload; web-only changes may need only a browser refresh. Follow the relevant installer instructions and never assume an arbitrary reinstall is safe.

## Source publication plan

1. Keep the verified 15 November full archive private and immutable.
2. Produce a new **source-only** export from the running Pi, retaining valid code but excluding credentials, historical backup directories, machine-specific secrets and live calibration secrets.
3. Compare that export with the GitHub tree before replacing or deleting files. Run Python, JavaScript and available automated tests.
4. Commit the clean code on a review branch, document exact file differences, and merge only after verification.
5. Preserve the original branch history and a clear rollback point.

## Related project

[`qp1306/cxm-toolchanger`](https://github.com/qp1306/cxm-toolchanger) is a **different CXT toolchanger engine**. Its `CXT_*` commands and installation instructions should not be conflated with this CXM Control Centre's `CXM_*` implementation.

## Project status

**Mechanical and optical calibration: working in the six-hotend field test. Complete production-print integration: still in commissioning.**

The original repository README contained a long migration history with earlier positions, Y-clearance rules, installer sequences and code paths. Those historical procedures are not reliable instructions for the verified November 15 setup; consult the installed snapshot and compare source before attempting any upgrade.
