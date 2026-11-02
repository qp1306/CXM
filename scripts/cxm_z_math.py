"""Pure BTC2 v4 Cartographer Touch Z maths for CXM T0-T11. NO Klipper or saves."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from statistics import median
import math

RANGE_TOL = 0.020
ZERO_TOL = 0.025
OVERALL_TOL = 0.040
NOZZLE_C = 140.0
BED_C = 70.0
TOUCH_MAX_C = 149.0
GLOBAL_Z_MAX_CHANGE_MM = 0.750  # Separate from probe quality!

def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(name + " must be finite")
    return value

def validate(samples, count, required):
    if type(count) is not int or not 1 <= count <= 12:
        raise ValueError("tool count must be 1 to 12")
    names = {f"T{i}" for i in range(count)}
    if not isinstance(samples, dict) or set(samples) != names:
        raise ValueError("exactly selected T0..Tn tools must be provided")
    result = {}
    for i in range(count):
        key = f"T{i}"
        values = samples[key]
        if not isinstance(values, (tuple, list)) or len(values) != required:
            raise ValueError(f"{key} requires exactly {required} complete Touch results")
        result[key] = [number(v, f"{key}[{j}]") for j, v in enumerate(values)]
    return result

def parameters(nozzle_c, bed_c, range_tolerance, zero_tolerance, overall_tolerance=None):
    nozzle = number(nozzle_c, "nozzle_c")
    bed = number(bed_c, "bed_c")
    if not 0 < nozzle <= TOUCH_MAX_C:
        raise ValueError("Nozzle Touch temperature must be >0 and <=149 C")
    if not 0 < bed <= 150:
        raise ValueError("Bed temperature must be >0 and <=150 C")
    if not 0 < number(range_tolerance, "range tolerance") <= 0.1:
        raise ValueError("Invalid range tolerance")
    if not 0 < number(zero_tolerance, "zero tolerance") <= 0.1:
        raise ValueError("Invalid zero tolerance")
    if overall_tolerance is not None and not 0 < number(overall_tolerance, "overall tolerance") <= 0.2:
        raise ValueError("Invalid overall tolerance")
    return nozzle, bed

def tightest_three(values):
    """BTC2: of five sorted complete Touch results, choose tightest 3-window.
    First (lowest) window wins on a tie; report raw five-reading range too.
    """
    ordered = sorted(values)
    candidates = [ordered[i:i+3] for i in range(3)]
    trio = min(candidates, key=lambda v: v[-1]-v[0])
    return float(trio[1]), float(trio[-1]-trio[0]), float(ordered[-1]-ordered[0])

@dataclass(frozen=True)
class Review:
    mode: str
    status: str
    passed_math: bool
    save_permitted: bool
    motion_performed: bool
    tool_count: int
    nozzle_c: float
    bed_c: float
    global_z_max_change_mm: float
    tolerances_mm: dict
    tools: dict
    overall_error_spread_mm: float | None
    warnings: list[str]

    def to_dict(self):
        return asdict(self)

def response(mode, synthetic, passed, count, nozzle, bed, tolerances, tools, spread=None):
    return Review(
        mode=mode, status="SIMULATION_ONLY" if synthetic else "PROVISIONAL_UNVERIFIED",
        passed_math=bool(passed), save_permitted=False, motion_performed=False,
        tool_count=count, nozzle_c=nozzle, bed_c=bed,
        global_z_max_change_mm=GLOBAL_Z_MAX_CHANGE_MM,
        tolerances_mm=tolerances, tools=tools, overall_error_spread_mm=spread,
        warnings=[
            "Offline calculation is not a real tool calibration.",
            "Each number must originate from a completed, validated Cartographer Touch operation.",
            "Hotend coupling and re-docking repeatability require physical verification.",
            "Global Z limit 0.750 mm is NOT a Touch tolerance.",
            "No printer motion, G-code, saved changes, or commissioned-ready flags.",
        ])

def calibrate(samples, count, *, synthetic=False, nozzle_c=NOZZLE_C, bed_c=BED_C,
              range_tolerance=RANGE_TOL, zero_tolerance=ZERO_TOL):
    """3 COMPLETE Touch results/tool, median and full min/max range."""
    nozzle, bed = parameters(nozzle_c,bed_c,range_tolerance,zero_tolerance)
    readings = validate(samples,count,3)
    centers = {key:float(median(values)) for key,values in readings.items()}
    rows = {}
    for i in range(count):
        key = f"T{i}"
        values = readings[key]
        span = max(values)-min(values)
        okay = span <= range_tolerance and (i != 0 or abs(centers[key]) <= zero_tolerance)
        rows[key] = dict(
            median_contact_mm=centers[key], range_mm=span,
            t0_reference=(i==0),
            proposed_offset_mm=0.0 if i==0 else centers[key]-centers["T0"],
            passed_math=okay)
    return response("CALIBRATE",synthetic,all(r["passed_math"] for r in rows.values()),
                    count,nozzle,bed,{"repeatability":range_tolerance,"t0_zero":zero_tolerance},rows)

def verify(samples, stored_offsets, count, *, synthetic=False, nozzle_c=NOZZLE_C,
           bed_c=BED_C,range_tolerance=RANGE_TOL,zero_tolerance=ZERO_TOL,
           overall_tolerance=OVERALL_TOL):
    """5 COMPLETE readings/tool; tightest 3; compare to T0 and stored Z."""
    nozzle, bed = parameters(nozzle_c,bed_c,range_tolerance,zero_tolerance,overall_tolerance)
    readings = validate(samples,count,5)
    if not isinstance(stored_offsets,dict) or set(stored_offsets) != set(readings):
        raise ValueError("Stored offsets must contain exactly selected tools")
    stored={k:number(v,"stored "+k) for k,v in stored_offsets.items()}
    if abs(stored["T0"])>1e-9:
        raise ValueError("T0 relative offset must be zero")
    metrics={k:tightest_three(v) for k,v in readings.items()}
    t0=metrics["T0"][0]
    rows={}; errors=[]
    for i in range(count):
        k=f"T{i}"
        center,cluster_range,full_range=metrics[k]
        relative=0.0 if i==0 else center-t0
        error=0.0 if i==0 else relative-stored[k]
        if i: errors.append(error)
        okay=cluster_range<=range_tolerance and (i==0 or abs(error)<=zero_tolerance)
        rows[k]=dict(
            median_contact_mm=center, t0_reference=(i==0),
            measured_relative_mm=relative,stored_offset_mm=stored[k],
            error_mm=error,tightest_three_range_mm=cluster_range,
            full_five_range_mm=full_range,passed_math=okay)
    spread=max(errors)-min(errors) if errors else 0.0
    good=all(r["passed_math"] for r in rows.values()) and spread<=overall_tolerance
    return response("VERIFY",synthetic,good,count,nozzle,bed,
                    {"repeatability":range_tolerance,
                     "tool_offset_error":zero_tolerance,
                     "overall_error_spread":overall_tolerance},
                    rows,spread)
