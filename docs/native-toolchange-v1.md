# CXM native Klipper toolchange — commissioning branch

This branch replaces Python-generated pickup/drop-off G-code with native
Klipper macros based on the operator-supplied CxChanger \`toolchange-EN.cfg\`.
**Do not install onto a moving printer.** This is a supervised XY-only
commissioning controller, not completed printing/tool-heater integration.

## Architecture
- Lineux and \`cxm_cxchanger.plan\` retain the accepted dock XY measurement,
  locking-hole datum and geometry validation. They do not generate movement.
- \`cxm_native_toolchange.cfg\` owns the pickup, release, tool-select and
  supervised test sequence. It uses the existing four live
  \`CXM_FAST_VERIFY\` checks after each physical pickup/dropoff.
- \`server/cxm_native.py\` only synchronizes calibration variables,
  preflights requests and sends named Klipper macros.
- Python movement generator files \`cxm_multi.py\` and \`cxm_rapid.py\`
  were deleted. Original T0/T1 Python movement functions were removed.
- Test supports two or three accepted docks, 1–20 cycles in tested profiles.
  Experimental Sprint/Race/Boost remain limited to one supervised cycle.
  \`CXM_TEST_STOP\` requests stop at the next observed completed tool pair.
  Requests can queue while Klipper is executing: **physical emergency stop
  remains mandatory for immediate danger**.

## Deployment preflight
1. Review the native macro against the actual dock hardware. Existing
   \`CXM_SELECT_TOOL\` definitions in other Klipper includes must be
   deliberately migrated; the installer refuses duplicate macro names.
2. With carriage physically EMPTY, tools docked, printer idle, run:
   \`python3 ~/CXM/scripts/cxm_native_install.py\`
3. Only after reviewing changes, run:
   \`python3 ~/CXM/scripts/cxm_native_install.py --apply\`
   This backs up the existing config and adds the macro include.
4. One deliberate **Klipper RESTART** is necessary after an include
   changes. Perform the already-tested full CXM \`G28\` sequence and
   confirm XYZ homed, motors powered and physical Z >=20 mm.
5. Control Centre -> Tools: click **Sync saved dock XY to Klipper**.
   This writes \`SET_GCODE_VARIABLE\` values into active macros; **no
   further Klipper restart** is needed for routine settings sync.
   Sync invalidates all remembered tool identity.
6. Inspect physical carriage EMPTY, tick approval and click
   **Confirm EMPTY in Klipper**. This checks the switch four times.
7. Pick T0 and T1 (both previously individually accepted). Run
   one supervised Standard pass. Verify physical seating and carriage
   switch after *every* pickup/dropoff. Then expand to T2 and subsequently
   to the last physically demonstrated speed profile.
8. If an operation faults, **do not retry or automatically reset**.
   Inspect tool and dock. Only when the physical carriage is EMPTY,
   Klipper has returned to idle and geometry is still synchronized,
   use the separately acknowledged recovery action.

## Deliberately not copied from the source machine
The older toolchange file's hard-coded negative-Y dock positions,
extruder/heater switching, 15,000 mm/s^2 toolchange acceleration,
automatic Z hop, filament sensor pin, save_variables physical tool
restore, global M109 override and G-code offsets are **not** imported.
Those depend on different hardware and require separate commissioning.
The actual CXM saved locking-hole coordinates, safe Y clearance and
existing tested Standard/Faster/Performance/Sprint/Race/Boost speeds
are the source of truth.

## Validation
\`python3 scripts/validate_cxm_native.py\` parses all Jinja macros
and checks original CxChanger waypoint order for T0–T11.
\`node --check web/cxm-multi.js\` and
\`node --check web/cxm-native-control.js\` check browser syntax.
These are **software-only checks**. Final acceptance requires supervised
physical testing on the CXM printer.
