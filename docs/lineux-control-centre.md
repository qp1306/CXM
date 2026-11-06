# CXM / Lineux live dock measurement — experimental integration

This is a separate feature branch. No change to the current running printer, GitHub `main`, or the tested Homing Override V2.0 until deliberately installed.

## Architecture

1. The original Lineux `dock_locate_calibrate.py` is vendored *unchanged* under `vendor/lineux/`, checked against SHA256 `b243104c0d711720802424ddc8c89b44f878577516f09058fc47a8c312632d8d`.
2. `scripts/cxm_lineux_install.py` is a one-time dry-run / `--apply` installer. It verifies physical X/Y motor settings from active `printer.cfg` and computes the required Lineux `xy_resolution` and endstops. It backs up before writing. It never moves axes or restarts Klipper automatically. The Klipper module must be installed as a native extra before the command is available.
   Existing `dock_locate_calibrate.cfg` files are preserved byte-for-byte when their four numeric engine settings and the `DOCK_CALIBRATION` command are semantically identical, even if comments and descriptions differ. Unknown sections, additional executable G-code, or changed machine settings fail closed.
3. `server/cxm_lineux.py` is a loopback-only bridge called through the existing same-origin, LAN-only CXM API. It checks Klipper readiness, active Lineux parameters, active homing override, selected tool, maintenance lockout, and saved revision before running a fixed command. It captures the command's report using unique G-code response markers; any missing/ambiguous result fails closed.
4. The existing `Dock Calibration → 1 · Automatic XY dock measurement` UI now contains Lineux readiness and explicit start controls. The result is always **PROVISIONAL**. User may copy only X/Y to the selected tool's existing draft. The optional global `x_docking_adjust` is **not** applied by default and is labelled separately.
5. The existing `2 · Align dock position` requires a separate Z value and deliberately confirmed XYZ AutoSave. `3 · Test and verify` and pickup remain disabled until independent physical verification.

## Critical differences from Lineux's original working printer

- **CXM's tested `G28 X` homes Y before X.** The unmodified Lineux module calls `G28 Y` first, then `G28 X`, so **Y will be homed twice**. This has not been tested on CXM with the module installed. Monitor for collisions, extra steps and endstop behaviour. Do not assume the original script's output is immediately accurate.
- The original Lineux module uses unscoped `SET_KINEMATIC_POSITION`; it changes Klipper's perceived homing state. It makes no physical clearance check and is not a tool-presence detector.
- A manually positioned carriage can invalidate reported X/Y coordinates. The operator must physically establish and confirm a clear Z height and unobstructed Y/X path before any movement. Do not rely only on software homing flags. The backend requires *reported Z homed and at least Z15* but those alone do not prove clearance.
- This feature is an **experimental supervised movement** mode, not production-ready automation. Until duplicate homing, MCU counter signs, repeatability and physical dock position are validated on the real printer, **do not enable unattended measurement, docking or pickup**.

## One-time installation (only after reviewing and merging the PR)

From the Pi (assuming `~/CXM` contains updated CXM source):

```bash
python3 ~/CXM/scripts/cxm_lineux_install.py
```

Review motor settings, endstops, module destination, and include count. If correct:

```bash
python3 ~/CXM/scripts/cxm_lineux_install.py --apply
```

Then do a deliberate **Klipper `RESTART`** in Mainsail when no printing or movement is occurring. Open CXM Control Centre → Dock Calibration, select a tool and select **Check printer & engine**. The command will remain locked out until the preflight passes and the operator explicitly confirms clearance. If Python extras directory is not writable, stop and correct permissions knowingly; don't run a generic sudo-installer without reviewing ownership.

To run bridge tests locally:

```bash
python3 -m unittest discover -s tests -p 'test_lineux_bridge.py' -v
node --check web/cxm-lineux.js
```

No coordinate changes are saved by starting a measurement or copying X/Y to the draft.

## Rollback

The one-time installer puts timestamped copies in `~/printer_data/config/cxm_backups/lineux-<stamp>/`. Restore the prior `printer.cfg` and reinstall the original plugin/CFG if needed, then explicitly RESTART Klipper. Do not remove files while Klipper is moving. The UI will show NOT READY if the module is no longer active. `CXM_variables.cfg` is never edited by this integration except through the existing deliberate dock XYZ AutoSave.