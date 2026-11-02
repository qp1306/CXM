#!/usr/bin/env python3
"""CXM offline XY capture review. NEVER moves motors or saves calibration.

Reads exported GET_POSITION mcu lines. Validates known calibration moves and
two consecutive Y-then-X homing snapshots. No Moonraker, network or G-code.
Results always remain provisional and require real hardware confirmation.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import re
import sys
from cxm_xy_measure import CoreXYTransform, infer_dock_xy

FORMAT = "CXM_XY_CAPTURE_V1"
NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
COUNTER = re.compile(r"(?<![a-z0-9_])([a-z][a-z0-9_]{1,40}):(-?\d+)(?=\s|$)")


def steps_from_snapshot(text, names):
    """Read exactly one Klipper GET_POSITION mcu line, not cartesian reports."""
    if not isinstance(text, str) or len(text) > 10000:
        raise ValueError("Snapshot must be short GET_POSITION output")
    lines = []
    for line in text.splitlines():
        match = re.search(r"(?:^|\s)(?://\s*)?mcu:\s*(.+)$", line.strip())
        if match:
            lines.append(match.group(1))
    if len(lines) != 1:
        raise ValueError("Exactly one GET_POSITION mcu line required per snapshot")
    raw = lines[0]
    matches = list(COUNTER.finditer(raw))
    values = {}
    for match in matches:
        name = match.group(1)
        if name in values:
            raise ValueError("Duplicate MCU counter: " + name)
        values[name] = int(match.group(2))
    if not matches or re.sub(COUNTER, "", raw).strip():
        raise ValueError("Invalid MCU step count line")
    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError("Missing counters: " + ", ".join(missing))
    return tuple(values[name] for name in names)


def _dict(obj, label, fields):
    if not isinstance(obj, dict) or set(obj) != set(fields):
        raise ValueError(label + " requires precisely: " + ", ".join(fields))
    return obj


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(label + " must be finite")
    return result


def _delta(pair, names):
    p = _dict(pair, "Snapshot pair", ("before", "after"))
    a = steps_from_snapshot(p["before"], names)
    b = steps_from_snapshot(p["after"], names)
    return tuple(end - start for end, start in zip(b, a))


def analyze(payload):
    """Offline, always non-authoritative review of signed MCU motor steps."""
    _dict(payload, "Capture file", ("format", "synthetic", "names",
                                     "conditions", "calibration", "homing",
                                     "endstops", "bounds"))
    if payload["format"] != FORMAT:
        raise ValueError("Unsupported CXM capture format")
    if type(payload["synthetic"]) is not bool:
        raise ValueError("synthetic must be boolean")
    names = payload["names"]
    if not isinstance(names, list) or len(names) != 2 or len(set(names)) != 2 or not all(
            isinstance(n, str) and NAME.fullmatch(n) for n in names):
        raise ValueError("Two distinct CoreXY stepper names required")
    condition_names = (
        "motor_directions_checked", "endstop_positions_checked",
        "stationary_at_snapshots", "same_mcu_session", "no_extra_motion",
        "y_then_x_confirmed", "endstop_triggers_confirmed")
    conditions = _dict(payload["conditions"], "conditions", condition_names)
    if any(type(value) is not bool or not value for value in conditions.values()):
        raise ValueError("Missing capture-condition confirmation")

    calibration = _dict(payload["calibration"], "calibration", ("x","y"))
    xcal = _dict(calibration["x"], "calibration.x", (
        "known_distance_mm","before","after"))
    ycal = _dict(calibration["y"], "calibration.y", (
        "known_distance_mm","before","after"))
    x_mm = _number(xcal["known_distance_mm"], "calibration.x.known_distance_mm")
    y_mm = _number(ycal["known_distance_mm"], "calibration.y.known_distance_mm")
    if not (1 <= x_mm <= 100 and 1 <= y_mm <= 100):
        raise ValueError("Known positive calibration moves must be 1 to 100 mm")
    x_steps = _delta({"before":xcal["before"], "after":xcal["after"]}, names)
    y_steps = _delta({"before":ycal["before"], "after":ycal["after"]}, names)
    matrix = CoreXYTransform.calibrate(x_mm, x_steps, y_mm, y_steps)

    homing = _dict(payload["homing"], "homing", ("y", "x"))
    yhome = _dict(homing["y"], "homing.y", ("before","after"))
    xhome = _dict(homing["x"], "homing.x", ("before","after"))
    if steps_from_snapshot(yhome["after"], names) != steps_from_snapshot(
            xhome["before"], names):
        raise ValueError("Discontinuous counters between Y and X homing")
    y_delta = _delta(yhome, names)
    x_delta = _delta(xhome, names)
    endstops = _dict(payload["endstops"], "endstops", ("x","y"))
    bounds = _dict(payload["bounds"], "bounds", ("x","y"))
    result = infer_dock_xy(
        matrix=matrix,y_home_motor_steps=y_delta,x_home_motor_steps=x_delta,
        x_endstop=_number(endstops["x"],"endstops.x"),
        y_endstop=_number(endstops["y"],"endstops.y"),
        x_bounds=bounds["x"],y_bounds=bounds["y"])
    return {
        "status": "SIMULATION_ONLY" if payload["synthetic"] else "PROVISIONAL_UNVERIFIED",
        "save_permitted": False,
        "motion_performed": False,
        "raw_dock_xy_mm": {"x": round(result.raw_x,6), "y": round(result.raw_y,6)},
        "travel_mm": {"x": round(result.x_travel,6), "y": round(result.y_travel,6)},
        "cross_axis_mm": {
            "during_y_home_x":round(result.y_cross_axis,6),
            "during_x_home_y":round(result.x_cross_axis,6)},
        "stepper_names": names,
        "warnings": [
            "NOT calibrated or verified, regardless of step-count arithmetic.",
            "Motor steps do not prove physical position, clearance or pickup.",
            "Capture conditions still require independent real hardware validation.",
            "X docking adjustment is not applied; do not double-correct it.",
            "No data has been saved or sent to Klipper."
        ]
    }


def _line(a,b):
    return f"Recv: // mcu: stepper_x:{a} stepper_y:{b}"


def synthetic_example():
    """Made-up counters producing X=180, Y=172. Not real machine data."""
    return {
        "format":FORMAT,"synthetic":True,"names":["stepper_x","stepper_y"],
        "conditions":{
            "motor_directions_checked":True,"endstop_positions_checked":True,
            "stationary_at_snapshots":True,"same_mcu_session":True,
            "no_extra_motion":True,"y_then_x_confirmed":True,
            "endstop_triggers_confirmed":True},
        "calibration":{
            "x":{"known_distance_mm":20,"before":_line(0,0),
                 "after":_line(1600,1600)},
            "y":{"known_distance_mm":20,"before":_line(1600,1600),
                 "after":_line(3200,0)}},
        "homing":{
            "y":{"before":_line(3200,0),"after":_line(18400,-15200)},
            "x":{"before":_line(18400,-15200),"after":_line(30800,-2800)}},
        "endstops":{"x":335,"y":362},"bounds":{"x":[0,335],"y":[0,362]}
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description="CXM offline XY review (no motion, no save)")
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--example",action="store_true",
                        help="Print synthetic fixture JSON")
    choice.add_argument("--input",type=Path,help="Read snapshot JSON")
    options=parser.parse_args(argv)
    if options.example:
        print(json.dumps(synthetic_example(),indent=2))
        return 0
    try:
        if options.input.stat().st_size > 250000:
            raise ValueError("Capture file too large")
        data=json.loads(options.input.read_text(encoding="utf-8"))
        print(json.dumps(analyze(data),indent=2))
        return 0
    except (OSError,UnicodeError,ValueError,KeyError,TypeError) as exc:
        print("CXM XY review REJECTED: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
