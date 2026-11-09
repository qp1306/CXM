# CXM clean installation and repeatable reset — 10 November 2026

## What has been validated

Run from the repository root:

```bash
cd ~/CXM
python3 -m unittest discover -s tests -p test_clean_install.py -v
python3 scripts/validate_cxm_native.py
```

The test suite constructs **a temporary, empty printer_data/config** and
runs both CXM macro installers in dry-run and apply modes. It checks that:
- No prior CXM datastore, macros, or Lineux files are needed.
- Default bootstrap creates 12 uncalibrated profiles, with +4.4 mm X
  engagement and +100 mm Y retreat geometry.
- The fast guard installs before the native toolchanger.
- Both installers create backups, are idempotent, and do not alter non-CXM
  `printer.cfg` settings.
- Duplicate native macros cause a refusal before any changes.
- All T0–T11 coordinates can be saved on the first attempt with a blank store.
- A native Klipper geometry sync emits only `SET_GCODE_VARIABLE`, never G0/G1.
- Manual alignment dispatches `CXM_MANUAL_DOCK_JOG`; only the guarded Klipper
  macro executes the incremental `G1`, `G91` and modal restoration.

The test has **no Moonraker connection and never moves motors**. It does not
prove a real Pi systemd/Nginx installation, motors/stepper timing, nozzle
alignment, collision clearance or the physical operation of other docks.

## Do not wipe the printer

**Not CXM reset candidates:** `printer.cfg`, MCU or CAN definitions,
homing_override, Cartographer, four-Z-motor settings, motor tuning, bed
levelling configuration, Moonraker, Mainsail, Nginx, and other unrelated
macros. Do not delete the existing `~/CXM` git checkout just to prove a
fresh configuration; that can break Moonraker's updater.

**CXM-owned state to archive, not directly delete:**
`~/printer_data/config/CXM_variables.cfg`, associated
`~/printer_data/config/cxm_backups/` history,
`cxm_native_toolchange.cfg`, `cxm_fast_guard.cfg`, and old CxChanger/Lineux
files *only if their exact identity and references have been audited*.
Native macro includes must never be orphaned or duplicated.

### Before any real printer reset

1. Stop all prints and motion. Physically inspect the carriage; all hotends
   must be docked, with an EMPTY carriage. Confirm the presence sensor is
   RELEASED. **Resolve or physically secure the rear-right Z gantry drop
   risk before any Klipper restart.**
2. Take an external archive of the *whole* config directory including
   `printer.cfg` and `cxm_backups`:
   ```bash
   stamp=$(date -u +%Y%m%dT%H%M%SZ)
   tar -czf "$HOME/cxm-config-before-reset-$stamp.tar.gz" -C "$HOME/printer_data" config
   tar -tzf "$HOME/cxm-config-before-reset-$stamp.tar.gz" | head
   cd ~/CXM && git rev-parse HEAD
   ```
3. Check the archived T0 reference
   **X304.60625 / Y65.60000** and the current T0–T11 coordinates.
   A clean schema starts with **no accepted dock coordinates** by design.
   Never assume the saved values will survive a deliberate blank-state reset.
4. Run the hardware-free clean-room tests above before touching any live files.
5. Audit installed includes and service paths. Prepare an explicit file-by-file
   removal/restore list; don't issue broad `rm CXM*`, delete
   `printer.cfg`, or remove the CXM git checkout.

After explicitly approving a real machine reset, the sequence should be
*invalidate native tool state → archive/selectively remove CXM-only state →
initialise fresh datastore → install guard → install native Klipper macros →
make one safe Klipper RESTART → home XYZ → calibrate T0 → Save →
verify T0 single pickup/dropoff*.
This requires live preflight; the CI test **does not** perform the real
machine reset or authorise unsupervised restart.

## Baseline after clean install

Saved T0 datum after operator re-calibration:
`dock_x = 304.60625`, `dock_y = 65.6`.
Mounted-side X = `dock_x + 4.4`. Safe staging Y = `dock_y + 100.0`.

- PICKUP: empty carriage at release-side X and safe Y → Y down to dock →
  X+4.4 latch → Y up to safety line, switch PRESSED.
- DROP-OFF: mounted carriage at mounted-side X and safe Y → Y down to dock →
  X−4.4 release → Y up to safety line, switch RELEASED.

Motion is owned by `_CXM_PICKUP_MOTION`,
`_CXM_RELEASE_MOTION`, `CXM_SELECT_TOOL`, and
`CXM_MANUAL_DOCK_JOG`. Python handles configuration, read-only checks,
backup, and named macro dispatch—not physical G1 commands.
