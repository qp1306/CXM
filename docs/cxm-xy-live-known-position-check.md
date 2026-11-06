# CXM XY dock calibration: Stage 1 live **known-position** verification

This is the gate **before** the first physical dock measurement. No current dock
coordinates are changed. No changes to `printer.cfg`, `[homing_override]`,
`CXM_variables.cfg`, Axiscope, or any CXM Control Centre screens.

## Why the combined homing count works

A single `G28 X` on the proven CXM V2.0 override executes Y home followed by
X home. Recording both CoreXY `mcu:` motor counters immediately before and
immediately after gives the **net** signed XY travel. A transform fitted from
known +10 mm X/Y calibration jogs converts the combined steps back into
Cartesian movement. This does not require modifying the override to take an
intermediate Y-only snapshot. The test proves whether reconstructed **known**
starting position matches Klipper reported coordinates within **0.25 mm**.

It does not prove actual dock accuracy, missed-step absence, or tool clearance.
It cannot be used yet to determine an unknown manually seated dock position.

## Run on the printer over SSH

Make sure both axes and Z are already homed, Z is at least 10 mm, the printer
is idle, the X/Y travel path to the **positive** endstops is physically clear,
and the carriage has 10 mm of clearance towards positive X and Y. No tool
may be mechanically engaged with a dock during this exercise. In Mainsail,
keep an immediate **emergency stop** accessible. Never try this while printing.

Read-only preflight (NO motion):

```bash
python3 ~/CXM/scripts/cxm_xy_capture.py
```

If it reports `READ_ONLY_PREFLIGHT_PASSED`, review current state and expected
travel. Deliberately arm the known-position test (MOVES +10 mm X, then +10 mm
Y, then homes Y and X using one `G28 X`):

```bash
python3 ~/CXM/scripts/cxm_xy_capture.py --apply-known-check --confirm CLEAR_XY_PATH
```

Expected output: `KNOWN_POSITION_TEST_PASSED` with measured X and Y residuals
and `save_permitted=false`. A failed test means **no dock measurement is
allowed**. Send the full JSON output for review (including matrix and errors).

## Implementation limits

- Only connects to the local Moonraker HTTP API (`127.0.0.1:7125`).
- `GET_POSITION` snapshots are captured through Moonraker's `gcode_store`
  wrapped in unique `RESPOND` markers; missing/ambiguous snapshots are rejected.
- Requires both axes' configured endstops near `position_max`. Reads their
  positions from live `configfile.settings`, not remembered assumptions.
- Never assumes ideal CoreXY sign conventions: fits a 2×2 transform from
  measured positive X and Y jog pulses.
- Checks all reported Z stepper pulse counts across the test; XY-only motion
  must not move the gantry.
- Captured counters count *commanded* motor steps. Interleaving from a different
  client, MCU restart, lost steps, torque slip, or collision can invalidate
  inference; there is no atomic multi-client lock here.
- Do not run a manual-placement dock test until this baseline is repeatable
  and the parked-tool release/clearance trajectory is mechanically verified.
- This code makes **no attempt to disable motors, free the carriage, or
  apply a guess to any dock position**.