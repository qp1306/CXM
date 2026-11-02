# Axiscope — preserved for later

**Snapshot:** `baseline/axiscope-v0.5.0`, pinned at commit `672d1303cf71fc21bd16db3656fcd34bf86583de`.

The complete existing Axiscope V0.5 functionality remains in `main` and in this snapshot. Do not remove or replace it when developing dock XY measurement.

## Existing capabilities (implemented, not necessarily tested on the Raspberry Pi)

- Stable T0–T11 tool colour identifiers in `web/cxm-tool-style.js` and tool cards.
- Dedicated `XYZ Offsets`/Axiscope screen.
- Moonraker webcam discovery through `/server/webcams/list`.
- Optional camera stream, overlaid crosshair and visual zoom.
- Saved-configuration XY comparison across enabled tools.
- X/Y movement, centre and measurement controls intentionally disabled.
- No controller, webcam measurements or movement validated yet.

## Revisit later

1. Verify the actual camera, stream and image orientation on the printer.
2. Establish T0 reference and a calibration target.
3. Determine separate X/Y pixel-to-mm factors, sign, image rotation and distortion.
4. Only enable jog controls after Klipper safety checks and verified macros.
5. Confirm multiple repeatable T0 and T1+ measurements before accepting offsets.
6. Preserve `CXM_variables.cfg` data; no image processing may automatically overwrite it.

**Do not conflate:** Axiscope tool-relative nozzle XY offsets versus physical hotend dock XY position. They are different calibrations.
