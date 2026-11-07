# CxChanger T0 supervised test — 7 November 2026

This procedure covers XY dock measurement and a slow T0 pickup/dropoff only.
It does not commission printing, heaters, filament handling, Z offsets or T1+.
Software tests use simulated hardware; the actual mechanism still needs testing.

## Update and settings

Install the reviewed CXM source, then reload the webpage. The existing backend
reloads itself when Python sources change. This update does not change printer.cfg
or the already physically tested homing override. Do not rerun the old homing installer.

If Settings requests migration, use **Back up and migrate configuration**.
Schema 3 preserves old coordinates but invalidates their motion acceptance.
Review these settings before measuring:

| Setting | Meaning | Initial value to inspect |
|---|---|---|
| X datum correction | Added to raw Lineux X | 0 mm unless a measured correction is needed |
| Y datum correction | Added to raw Lineux Y | 0 mm unless a measured correction is needed |
| X latch travel | Relative leftward release/engagement | −4.8 mm |
| Y dodge | Relative retreat around the dock | +14 mm |
| Y safe clearance | Relative clearance from each dock Y | +44 mm |

These distances are the current software defaults, not measurements of your
assembled mechanism. Migration retains the previous X correction: an old +3 mm
or −3 mm setting is NOT automatically appropriate for the new locking-hole datum.
The legacy absolute Safe Y field is not used by this motion engine.

## Measure T0

1. Confirm the gantry is level, all four Z drives hold reliably, the bed/nozzle
   and the entire homing path are clear. Stop if the rear-right Z drive skips.
   Use a cold, idle printer, with no other page or host sending movement.
2. Open **Dock Calibration**, select **T0**, and use **Home & Z20**.
3. Use **Release X/Y**. Leave all four Z motors powered. Hand-align the hotend
   locking screw with the centre of the dock's large hole: this defines datum D.
4. Confirm the initial Lineux +3 mm X jog and subsequent Y/X homing have a clear
   physical path. **Measure dock XY** performs that movement; it is not a dry run.
5. Inspect raw Lineux XY and converted CxChanger datum XY. Copy the CxChanger
   datum to the draft and **Save dock XY**. Do not reuse the old motion acceptance.
6. Rehome using **Home & Z20** from a physically clear position. Do not hand-move
   X/Y afterwards. Keep G-code XY offsets/G92 cleared before commissioning;
   these tests are not a coordinate-transform or lost-step detector.

## Inspect the expected movement

Let D=(dock X,dock Y), L=X latch travel (negative), B=Y dodge,
and S=dock Y + safe clearance. Staging moves Y first, then X, to (D.x,S).
The starting carriage must be on or beyond that safe Y line.

| Step | Dropoff (starts with T0 attached) | Pickup (starts with carriage empty) |
|---|---|---|
| 1 | (D.x,D.y) | (D.x,D.y+B) |
| 2 | (D.x+L,D.y) | (D.x+L,D.y+B) |
| 3 | (D.x+L,D.y+B) | (D.x+L,D.y) |
| 4 | (D.x,D.y+B) | (D.x,D.y) |
| 5 | (D.x,S) | (D.x,S) |

The path matches the supplied marked CxChanger diagram. It contains no Z,
heater, extruder or homing commands. Staging is 10 mm/s, ordinary test travel
4 mm/s, and latch movement 3 mm/s at 100% speed override.
Manual and automatic tests now use the same saved geometry.

## First physical cycle

1. Verify the real `cxm_tool_detect` switch: PRESSED means T0 is attached;
   RELEASED means the carriage is empty. A signal alone does not prove the
   hotend identity or mechanical latch. Verify the dock occupancy visually.
2. If T0 is attached and its dock is empty, click **Drop off T0** once.
   Watch every segment. Pass requires T0 supported by its dock, carriage empty,
   RELEASED, and return to staging without scraping, binding or lost steps.
3. Click **Pick up T0** once. Pass requires the reverse path, a fully seated
   hotend, PRESSED and return to staging without binding.
4. Drop off once more. Only after both directions pass, run **1** repeat cycle,
   inspect, then **3** cycles. Each cycle ends with an empty carriage.

Stop immediately with the printer's emergency stop if the path is wrong or
anything binds. **Stop after current cycle** is not an emergency stop. A failed
sensor transition requires inspection; do not clear the fault and blindly retry.
Do not adjust settings, update software, or operate Mainsail motion controls
during a test. These checks do not detect every collision or establish a printer-wide lock.

Send back: saved datum XY, the five geometry/correction settings above, initial
switch state, which segment failed (if any), final switch state and the exact
on-screen result. A short video of the first single dropoff is useful.
