# CXM — XY dock measurement using endstop travel (design only)

Status: **OFFLINE REVIEW IMPLEMENTED / NOT SAFE FOR HARDWARE EXECUTION YET**. This file contains no motion commands. V0.5 Axiscope remains intact; work is developed on a separate feature branch.

## Machine-specific baseline

- Voron 2.4-style CoreXY: one permanent carriage extruder, multiple detachable hotends T0–T11.
- One shared filament lever switch at the permanent extruder; lever movement with filament loaded is indirect evidence, **not unconditional proof** of pickup. Do not trust this signal without a validated loaded-filament sensor model.
- Intended measurement method: manually seat the carriage at a selected dock while motors are disabled; engage motors **without moving carriage manually afterward**; then controlled homing travels first to Y endstop, followed by X endstop.
- Reported reference positions from existing project setup: X endstop 335.000 mm; Y endstop 362.000 mm. Must confirm against actual new Klipper configuration and sign/direction before use.
- `x_docking_adjust` is a separate correction (currently proposed +3.000 mm). Do not silently add it to the raw measured dock X or apply it twice.
- Store provisional XYZ values in `/home/pi/printer_data/config/CXM_variables.cfg`; application to Klipper is a separate stage.

## Fundamental measurement challenge

After steppers are disabled and the carriage has been moved by hand, Klipper **does not know its physical Cartesian position**. Ordinary `G28` homes the axes, but the final reported position alone is **not** evidence of how far the carriage travelled from the unknown starting point. Therefore, simply subtracting two reported `toolhead.position` values is wrong.

The experimental approach must capture the **actual step pulses issued** between the start point and each endstop trigger, using MCU/stepper tracking or a carefully validated homing instrumentation interface. The internal step counter and CoreXY transform must be proven stable across the homing operation; do not rely on guessed numbers. Unpowered manual movement itself is uncounted: the datum is the carriage position precisely at the beginning of the captured, motor-driven journey.

## Candidate measurement equations

Provided endstops are at the positive X/Y extremes, the carriage does not skip steps, and the recorded travels use the verified physical sign:

```
raw_dock_y = y_endstop_position - positive_y_travel_from_dock_to_trigger
raw_dock_x = x_endstop_position - positive_x_travel_from_dock_to_trigger
```

For illustration only: if endstops are X=335, Y=362 and verified travel is X=155, Y=190 mm, the inferred starting point is X=180, Y=172 mm. These are **example numbers, not actual CXM calibration values**.

CoreXY motors move in combinations of X and Y. Capture both motor step deltas and convert them via a **measured CoreXY sign-and-scale transform**, established on a homed printer with known short positive X and Y movements. The common idealized relation `A ∝ X+Y, B ∝ X−Y` is insufficient without knowing motor directions and steps/mm. Measure one axis at a time and reject significant unintended movement on the other axis.

## Required staged validation before any automated motion

1. Connect and verify MCU, limit switches, motor direction and axis travel limits.
2. Home normally with a verified clearance path; calibrate a CoreXY motor-step transform using small commanded X-only and Y-only moves.
3. Validate raw counter acquisition before/after homing at known, homed XY positions. Confirm inferred XY agrees with commanded XY after G28 and is repeatable.
4. Confirm that no raw-count reset, retiming, macro override, homing retract, park, or unexpected motion contaminates the step delta measurement. If it does, **stop and change measurement method**.
5. Physically establish safe Z, hotend clearance and dock geometry; do not blindly execute a normal G28 from an arbitrary parked hotend.
6. Only then use manual-placement measurement, cautiously and at a reduced test speed. User must explicitly arm each test and remain able to abort. Fail closed on unexpected switches, state or movement.
7. Take multiple measurements from the same manually seated point; compare variation to a tolerance established from hardware testing (do not promise 0.1 mm until observed).
8. Present the inferred XY as **PROVISIONAL**. Apply any docking X correction as a separately labelled computed coordinate. Never commit automatically after a homing move.
9. Upon deliberate acceptance, atomically save the calibrated coordinates with revision validation and backup; do not restart Klipper for merely saving the config.
10. Finally, verify physical pickup and dropoff through separate, cautious tests. A successful calculated dock coordinate is not proof of secure pickup.

## Safer fallback measurement method

If step-count travel across homing cannot be captured reliably, **home normally, jog to the dock with motors powered, and save the known Klipper position**. This avoids the unknown-position reconstruction and should remain an explicitly supported calibration route.

## Software architecture and constraints

- Standalone Python instrument/analysis layer for the experimental endstop travel calculation, with hardware interaction isolated behind an explicitly armed adapter.
- Pure, deterministic math functions and fixtures tested without MCU first.
- Home/homing trajectory stays under Klipper's safety model. Never use `SET_KINEMATIC_POSITION` to bypass limits without a formally reviewed procedure.
- Per-tool dry run: read-only preflight → explicit confirm → measurement → verify → human accept → atomic AutoSave.
- Tool count and all calibration parameters remain centralized. Multiple manual edit sources must not race `CXM_variables.cfg`; reject stale revisions.
- Always preserve existing Axiscope work and avoid changing its camera files for this milestone.

**Implemented:** the pure travel-to-dock maths, GET_POSITION MCU snapshot parser, CoreXY calibration from known moves, continuity checks and synthetic regression tests are in scripts/cxm_xy_measure.py and scripts/cxm_xy_review.py. The UI includes a noninteractive readiness panel. Nothing moves or saves. **Next milestone:** connect the MCU, identify the real stepper counter names, check homing direction and endstop safety, then implement an explicitly armed capture adapter that validates an uninterrupted sequence. Do not enable any automated motion without that verification.
