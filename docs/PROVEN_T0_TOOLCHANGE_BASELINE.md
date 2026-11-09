# CXM — proven T0 pickup and drop-off baseline (10 November 2026)

## Operator-verified physical motion

The operator manually ran BOTH sequences in Mainsail at **F6000 mm/min** and reported that pickup and drop-off worked smoothly and reliably. Z stayed at **25.00 mm** throughout the demonstrations. No automatic toolchanger motion has yet been proven using these updated macros.

**Saved accepted T0 physical dock datum (Control Centre):**
- `dock_x = 304.60625 mm` (Mainsail used rounded `X304.60`)
- `dock_y = 65.60000 mm`

**Manual engagement and withdrawal positions:**
- Mounted-side X: **309.00 mm** (rounded manual absolute coordinate)
- Release-side X: **304.60 mm** (rounded manual absolute coordinate)
- Y at dock: **65.60 mm**
- Y away from dock: **165.60 mm** (`dock_y + 100.00`)
- Observed lateral travel: **+4.40 mm** when picking up; **−4.40 mm** when dropping off

### PICKUP (EMPTY -> T0 mounted)

1. Start `X304.60 Y165.60 Z25.00`, sensor RELEASED.
2. `G1 Y65.60 F6000` — enter along constant release-side X.
3. `G1 X309.00 F6000` — engage the carriage with T0.
4. `G1 Y165.60 F6000` — withdraw with T0, sensor PRESSED.

### DROP-OFF (T0 mounted -> EMPTY)

1. Start `X309.00 Y165.60 Z25.00`, sensor PRESSED.
2. `G1 Y65.60 F6000` — enter along constant mounted-side X.
3. `G1 X304.60 F6000` — release T0 into dock.
4. `G1 Y165.60 F6000` — withdraw with empty carriage, sensor RELEASED.

## Repeatability and speed-factor evidence

On 10 November 2026 the operator repeated the full pickup/drop-off G-code
many times while varying the Mainsail `M220` speed factor through
**200%, 300%, 400%, 500%, 600% and 700%**, reporting smooth motion and
alternating `FILAMENT PRESENT` / `FILAMENT ABSENT` events without a
reported pickup/dropoff failure. The log contains command timestamps and
speed-factor changes, not measured toolchange durations or a guaranteed
per-move applied feed rate. Consequently **F6000** is the commissioned
command baseline. The operator should set `M220 S100` before initial
automatic-macro verification, then raise the factor independently if desired,
so the first automated comparison is reproducible.

## Configuration translation

Global `cxm_shift_x = +4.4` and `cxm_safe_clearance_y = 100.0`. Standard profile travel, approach, latch `F6000`. Native geometry uses **saved dock X as the release-side X**, not the mounted-side X.

The saved `X304.60625` is the measured step-resolution datum; the native target `X309.00625` is 0.00625 mm away from the rounded manual `X309.00`. This tiny difference has NOT been physically tested at exact native precision; supervised verification remains necessary.

The safe-Y staging value is calculated **per tool** from `dock_y + cxm_safe_clearance_y`. Other tools' XY datums are not inferred from T0. The operator should not overwrite existing saved dock XY based on the rounded manual values.

## Deploy

```bash
cd ~/CXM
git pull
python3 scripts/cxm_apply_proven_t0.py              # dry-run / inspect
python3 scripts/cxm_native_install.py               # dry-run / inspect
python3 scripts/cxm_apply_proven_t0.py --apply      # backed-up motion globals; requires empty carriage
python3 scripts/cxm_native_install.py --apply      # backed-up native macro update
sudo systemctl restart cxm-config.service
```

One Klipper `RESTART` is required to load the updated native macro file, followed by homing and automatic native geometry synchronisation through the Control Centre. Protect the 4-Z gantry against the previously observed drop on motors-off/restart. Neither installer commands physical motion. No successful physical run of the revised automatic macro is claimed by these test scripts.
