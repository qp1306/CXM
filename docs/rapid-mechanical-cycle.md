# CXM rapid mechanical toolcycle — first supervised test

This is a **new execution path**, not a change to accepted CxChanger
dock XY or tested pickup/dropoff geometry. It uses Klipper-local
`CXM_FAST_VERIFY` calls, evaluated *at runtime* between G-code moves,
instead of repeated 250ms Moonraker object-query requests. Each
individual tool is picked up AND dropped off as **one complete pair**.
The Control Centre's **Stop after current tool** remains effective
between complete pairs. Mechanical commissioning only: this is **not**
production slicer-driven toolchanging or a claim of completed heater,
XY/Z offset or hotend identity commissioning.

## One-time setup and backup

1. In Control Centre **Updates**, install the latest CXM code.
2. SSH into the Pi. With printer idle, tools correctly docked and carriage
   physically empty, run a read-only installer preflight:

   ```bash
   python3 ~/CXM/scripts/cxm_fast_guard_install.py
   ```

   Inspect proposed changes. Only if appropriate, apply:

   ```bash
   python3 ~/CXM/scripts/cxm_fast_guard_install.py --apply
   ```

   It creates `cxm_fast_guard.cfg`, adds **one**
   `[include cxm_fast_guard.cfg]` to `printer.cfg`, backs up the
   existing printer config in `cxm_backups/rapid-...`, and refuses
   unknown existing macros or changed guard files. It does not initiate
   physical movement or restart Klipper. It is idempotent. It does not
   touch the accepted dock XY values or modify the CxChanger geometry.
3. Once it is safe to restart, issue **RESTART** in Mainsail exactly
   once so Klipper loads the new macro. This clears XYZ homing.
4. Rehome using the established CXM **G28** Y→X→Cartographer Z
   procedure and confirm Z≥20 mm. Do not jog by hand after homing.
5. Select **Tools → Multi-tool XY cycle test**, **T0 and T1 only**,
   **1 repeat**, **Standard** staging travel (not Faster), and check
   **Rapid continuous Klipper mode**. Approve the physical safety
   confirmation and press **Start 1 cycle**.

Do not enable Rapid until both accepted docks have individually
completed slow pickup/dropoff with known safe geometry.

## What is faster without sacrificing sensor validation?

The original mode performs each movement through CXM's Python/Moonraker
round trips, with four post-movement samples taking around one second
per step. In Rapid mode Klipper processes a whole pickup/dropoff pair
without a new HTTP request between the two actions.

For each movement the generator:

- Uses the **unchanged** CxChanger pickup/dropoff coordinates,
  approach and latch feeds.
- Executes `M400` to finish physical moves before testing occupancy.
- Waits 150 ms, then confirms the exact expected carriage state **four
  times**, 80 ms apart. Each delay has its own `M400` so readings are
  genuinely separated in time, not merely queued.
- Checks homing, every X/Y/Z motor, Z≥20, accepted stage coordinates,
  active XY G-code offsets, print/pause state, and carriage switch from
  *inside Klipper* at every gate.
- Fails the entire G-code script on an unexpected signal. The CXM
  controller latches an uncertain tool fault and **never retries** a
  pickup/dropoff automatically.

The transfer route always goes to safe Y **before cross-dock X
movement**. Standard vs Faster (30 mm/s **clearance only**) remains a
separate opt-in choice. Rapid does NOT speed up the physical contact or
latch moves. The backend also checks Klipper process ID and config
revision, and holds the existing CXM movement lock.

## Expected operator observations

- **T0 and T1 both complete:** carriage RELEASED at the end, tool
  appropriately seated in its dock, no scraping, sensor gate successes,
  no fault. Next run can include T2 with operator supervision.
- **Wrong/missing switch state or stage position:** immediate G-code
  error, no next pair sent, latched CXM fault; physically inspect.
- **Stop:** finishes *current tool's* full pickup+dropoff pair then
  stops; physical E-stop or Moonraker emergency-stop for immediate danger.
- **Installed guard not loaded:** CXM rejects Rapid mode **before any
  motion**. After one safe Klipper RESTART and rehome it should be
  recognized. Simply copying the files to the Pi is insufficient.
- **Previously measured 21.73s T0/T1/T2 baseline** is from the old
  movement/verification path. The new mode has **not been physically
  measured or mechanically validated** yet. Do not promise a specific
  time improvement until its first supervised pass.

For any unexpectedly slow pair, inspect the per-pair time in the
Multi-tool panel, and report the exact error/event. Do not increase
clearance speed merely to conceal a sensor or G-code problem.


## Performance speed profile (opt-in; November 2026)

Rapid and movement speed are **independent settings**:

| Profile | Clear corridor / between docks | Guided approach / retract | Latch / release |
| --- | ---: | ---: | ---: |
| Standard (original) | 10 mm/s | 4 mm/s | 3 mm/s |
| Faster (original) | 30 mm/s | 4 mm/s | 3 mm/s |
| Performance (new) | **80 mm/s** | **8 mm/s** | **3 mm/s** |

The new Performance mode uses the same stored Lineux XY datum and the
same CxChanger pickup/dropoff geometry; it inserts the existing segmented
clear-corridor waypoints, with the clear travel ending **15 mm before**
the Y-dodge position (the Faster profile ends at 10 mm). The 3 mm/s
latch/unlatch movement is never accelerated. The four Klipper-local
sensor assertions and their M400-separated dwell intervals are
unchanged in Rapid mode. No Z/heater/extruder movements are added.

**This speed profile is software tested but NOT physically tested.**
Do not go directly from the old 10 mm/s commissioning profile to this
speed. Run one supervised 30 mm/s Faster pass at T0/T1 and inspect
all motion, nozzle seating, latch engagement, deposits and missed
steps. Only if that passes, run one T0/T1 Performance pass with **Rapid
Klipper** enabled and a clear emergency-stop route. Keep repeat=1.
Then expand to T2. If there is scraping, impact, a dropped tool, lost
steps, or an invalid sensor confirmation, STOP and revert to Faster.
Do not adjust feed rates in an existing Klipper macro to bypass this.

Performance profile is delivered entirely in the CXM Python service
and the Control Centre UI. If the **native rapid guard was already
installed** successfully, performance profile source updates do **NOT**
require another `printer.cfg` edit or Klipper RESTART. Update the
web source and reload the page; CXM Python service monitors its
changed source files and reloads outside of active multi-tool tests.

The previously reported ~21.73 second multi-step timer is **not a
measured mechanical travel benchmark**. For comparison, record actual
wall-clock duration and both switch states across the complete run.
Motion gains depend on the actual move distances, acceleration,
feedrate override and dock geometry.


## Larger toolchange speed stages — Sprint and Race

These are **opt-in physical test profiles**. They increase speed
dramatically without increasing printer-wide `max_velocity`,
`max_accel`, `square_corner_velocity` or Z motion settings.
The measured and accepted CxChanger X/Y datum, Y-dodge and 4.8 mm
latch geometry remain exactly unchanged, as do the Klipper-native
four PRESSED + four RELEASED sensor confirmation gates.

| Speed profile | Clear travel | Guided dock movement | Latch/unlatch | Evidence |
| --- | ---: | ---: | ---: | --- |
| Standard | 10 mm/s | 4 mm/s | 3 mm/s | Existing commissioning |
| Faster | 30 mm/s | 4 mm/s | 3 mm/s | Existing experimental |
| Performance | 80 mm/s | 8 mm/s | 3 mm/s | Existing experimental |
| **Stage 1 — Sprint** | **200 mm/s** | **40 mm/s** | **10 mm/s** | New; software-tested only |
| **Stage 2 — Race** | **400 mm/s** | **80 mm/s** | **20 mm/s** | New; software-tested only |

The original CxChanger `toolchange.cfg` defines fast travel of
`F24000` (400 mm/s) and its generic precision speed of `F5000`
(83.3 mm/s). This is **design context, not a guarantee** that a
particular 3D-printed dock, magnet or hotend mount can tolerate these
forces. Race approaches that original travel/precision envelope but
**does not** copy its optional 15,000 mm/s² acceleration. The user's
actual Klipper setting is 4,000 mm/s²; it stays untouched. With short
moves, actual velocity may fall well below requested `F24000`.

The cross-dock XY transfer runs outside the dock at safe Y before
crossing X. Each fast entry slows at a point **15 mm before the
Y-dodge position**. The remaining engagement/lever path is commanded
at the trial's guided/latch feed rates, not open-corridor speed.

### Required incremental mechanical verification

1. Upgrade the CXM source using Control Centre **Updates**. The
   previously installed Klipper native rapid guard still applies;
   there is **no further printer.cfg edit or Klipper RESTART**.
2. With the printer homed XYZ, Z≥20, dock seats visually checked and
   carriage empty, run **one** supervised T0/T1 pass in the last
   verified lower-speed profile. Do not run experimental speeds during
   a print or during any other G-code activity.
3. **Stage 1 Sprint:** select only T0/T1, one cycle, Rapid Klipper
   enabled, and Stage 1 Sprint (200/40/10). Confirm the emergency
   stop is immediately accessible. Approve and supervise each
   pickup/dropoff. Observe vibrations, coupling flex, hotend
   retention, lost steps and switch failures.
4. Only after a fully successful Stage 1 with **no mechanical impact,
   scraping, missed steps, false carriage sensor change or failed
   latch**, and with docks visually inspected, try **Stage 2 Race**
   with the same single T0/T1 cycle and Rapid enabled.
5. If both pass cleanly, repeat this validation with T2 in a new
   single supervised run. **The backend rejects multi-repeat
   Sprint/Race requests** until we have physical commissioning evidence.

**Failure handling:** Stop physically with E-stop for an imminent
impact; ordinary Stop only takes effect after the current full tool
pair. Do not clear and retry a latched fault without inspecting the
carriage and affected dock. A PRESSED switch alone cannot prove
mechanical tool seating, particularly at the new speeds. These are
test presets, **not a claim that CXM is ready for production printing**.

For an apples-to-apples comparison, record **actual wall-clock
duration**, the on-screen run profile, and whether the carriage is
physically empty at the end. Motion limits and short-segment
acceleration often matter more than a large requested feed rate.
