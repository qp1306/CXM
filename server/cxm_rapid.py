"""CXM rapid mechanical XY cycle: one Klipper script per complete tool pair.

Unlike legacy 6-RPC pickup/dropoff loops, this runs four synchronous
carriage-switch safety gates *inside Klipper*, after each M400. The
verified movement geometry and motor speeds are imported, never
reimplemented. Each pair ends EMPTY, allowing the CXM UI Stop button
to stop before the next pair. No Z, heaters, extrusion or homing here.

This is a supervised commissioning mode, not a production slicer
toolchanger; real printing needs heater/tool identity integration.
"""
from __future__ import annotations

import math

from cxm_cxchanger import (automatic_script, faster_cycle_script,
                           performance_cycle_script, sprint_cycle_script,
                           race_cycle_script, PERFORMANCE_TRAVEL_FEED,
                           SPRINT_TRAVEL_FEED, RACE_TRAVEL_FEED)
from cxm_t0 import SAFE_FEED, TEST_FEED, LATCH_FEED

GATE="CXM_FAST_VERIFY"
SAMPLE_INTERVAL_MS=80
SETTLE_MS=150
SAMPLE_COUNT=4

def _number(value,name):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError("CXM rapid: invalid "+name)
    return float(value)

def _movement(path,kind,profile):
    if profile=="standard":
        script=automatic_script(path,kind,at_stage=True,
                                safe_feed=SAFE_FEED,test_feed=TEST_FEED,
                                latch_feed=LATCH_FEED)
    elif profile=="faster":
        script=faster_cycle_script(path,kind,at_stage=True,
                                   test_feed=TEST_FEED,latch_feed=LATCH_FEED)
    elif profile=="performance":
        script=performance_cycle_script(path,kind,at_stage=True)
    elif profile=="sprint":
        script=sprint_cycle_script(path,kind,at_stage=True)
    elif profile=="race":
        script=race_cycle_script(path,kind,at_stage=True)
    else:
        raise ValueError("Unknown rapid clear-travel profile")
    parts=script.splitlines()
    if parts[0]!="G90" or parts[-1]!="M400":
        raise ValueError("CXM motion engine script shape changed")
    # Exactly the proven X/Y motion section. The caller supplies G90 and
    # M400 explicitly so native Klipper gates run BETWEEN completed moves.
    return parts[1:-1]

def _verify(signal,*,x=None,y=None,min_y=None):
    if signal not in ("PRESSED","RELEASED"):
        raise ValueError("Invalid CXM carriage state")
    s=GATE+" EXPECT="+signal
    if min_y is not None:s+=" MIN_Y=%.5f"%_number(min_y,"minimum safe Y")
    if x is not None:s+=" X=%.5f"%_number(x,"staging X")
    if y is not None:s+=" Y=%.5f"%_number(y,"staging Y")
    return s

def _four_native_samples(signal,*,x,y):
    # Early wrong sensor state fails immediately; four positive reads
    # separated by 80ms prove no transient drop during the check.
    # Klipper Jinja evaluates each separate macro at its turn.
    # Klipper G4 queues dwell time rather than guaranteeing wall-time
    # completion before the next macro expands. Force M400 after EACH
    # dwell so every sample is genuinely separated in physical time.
    lines=["G4 P%d"%SETTLE_MS,"M400"]
    for i in range(SAMPLE_COUNT):
        if i:lines.extend(["G4 P%d"%SAMPLE_INTERVAL_MS,"M400"])
        lines.append(_verify(signal,x=x,y=y))
    return lines

def pair_script(paths,tool,travel_profile="standard"):
    """Emit exactly one pickup AND dropoff for an accepted XY dock.

    Preconditions: the CXM service already verified the printer, its
    active Klipper process, empty carriage and accepted saved geometry.
    The first and last native guards independently verify live hardware.
    """
    if type(tool) is not int or tool not in paths:
        raise ValueError("CXM rapid tool is not a prepared accepted dock")
    if type(paths) is not dict or len(paths)<2:
        raise ValueError("CXM rapid requires at least two accepted docks")
    p=paths[tool]
    x=_number(p["dock_reference_xy"]["x"],"dock X")
    y=_number(p["safe_y"],"staging Y")
    minimum=min(_number(v["safe_y"],"safe Y") for v in paths.values())
    if y<minimum or y>362 or x<5 or x>330:
        raise ValueError("CXM rapid staging is outside safe XY limits")
    travel_feed=(RACE_TRAVEL_FEED if travel_profile=="race" else
                 SPRINT_TRAVEL_FEED if travel_profile=="sprint" else
                 PERFORMANCE_TRAVEL_FEED if travel_profile=="performance" else
                 1800 if travel_profile=="faster" else SAFE_FEED)
    lines=[
        "G90",
        _verify("RELEASED",min_y=minimum),
        # Native CxChanger safe staging: reach the target safe Y before
        # making ANY cross-dock X movement.
        "G1 Y%.5f F%d"%(y,travel_feed),
        "G1 X%.5f F%d"%(x,travel_feed),
        "M400",
        _verify("RELEASED",x=x,y=y),
    ]
    lines.extend(_movement(p,"pickup",travel_profile))
    lines.append("M400")
    lines.extend(_four_native_samples("PRESSED",x=x,y=y))
    # Keep the proven dropoff motion completely unchanged.
    lines.extend(_movement(p,"dropoff",travel_profile))
    lines.append("M400")
    lines.extend(_four_native_samples("RELEASED",x=x,y=y))
    # Last gate requires a verified EMPTY carriage, accepted staging XY,
    # homing, motor power, printer pause/print status and Z>=20.
    return "\n".join(lines)

# A single HTTP request for the entire supervised T0/T1(/T2) pass removes
# the Python↔Moonraker round-trip at EVERY tool boundary. All 4+4 native
# status gates within each pair are still present. Stream mode intentionally
# cannot promise Stop-after-current-pair: while Klipper is processing the
# uninterrupted script, another queued G-code stop cannot take effect
# until the script is finished. Use the physical emergency stop instead.
MAX_NATIVE_STREAM_TOOLS=3

def stream_script(paths,selected,travel_profile='standard'):
    """One uninterrupted Klipper script with a guarded pickup/dropoff per tool.

    Caller must perform the same strict selection/calibration/preflight as
    the individual Rapid mode. The stream is limited to three tools and
    one completed cycle, and does not support unattended repeats.
    """
    if (type(selected) is not list or
            not 2<=len(selected)<=MAX_NATIVE_STREAM_TOOLS or
            any(type(n) is not int for n in selected) or
            selected != sorted(set(selected))):
        raise ValueError('CXM native stream needs 2–3 distinct ascending tool IDs')
    if type(paths) is not dict or set(selected)!=set(paths):
        raise ValueError('CXM native stream must match its validated dock paths')
    scripts=[pair_script(paths,tool,travel_profile) for tool in selected]
    if any(x.count('CXM_FAST_VERIFY EXPECT=PRESSED')!=4 or
           x.count('CXM_FAST_VERIFY EXPECT=RELEASED')!=6
           for x in scripts):
        raise ValueError('CXM stream native safety gate count changed')
    # Each script ends with four live RELEASED samples, and the next
    # starts with a fresh RELEASED/XYZ/steppers/offsets safety check.
    # Klipper runs this as one ordered G-code script, fail-closing on a
    # failed gate before the next tool can move.
    return '\n'.join(scripts)
