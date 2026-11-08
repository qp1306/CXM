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
