"""CXM Touch Z reliability diagnostics — pure offline analysis only.

Advisory full-five range 0.040 mm is a NEW CXM review threshold, NOT
a replacement for the field-proven BTC2 tightest-three acceptance rules.
Reseat calculations compare independently supplied cycles but cannot
prove that a physical undock/re-dock occurred.
No G-code, filesystem modifications, network or hardware calls.
"""
from __future__ import annotations

from statistics import median

from cxm_z_math import RANGE_TOL, ZERO_TOL, number, validate

# NEW advisory CXM thresholds, explicitly not changed BTC2 tool maths.
FULL_FIVE_REVIEW_MM = 0.040
RESEAT_OFFSET_TOL_MM = 0.025
MIN_RESEAT_CYCLES = 2


def touch_quality(verification, tool_count, full_range_review_mm=FULL_FIVE_REVIEW_MM):
    """Audit ALL 5 samples; preserve BTC2's chosen three without overriding it."""
    limit = number(full_range_review_mm, "full five review threshold")
    if not 0 < limit <= 0.2:
        raise ValueError("Invalid full-five review threshold")
    data = validate(verification, tool_count, 5)
    details = {}
    flagged = []
    for tool, samples in data.items():
        # Identical tie breaking to cxm_z_math.tightest_three:
        # sort ascending; choose the first of three consecutive 3-windows.
        ordered = sorted(enumerate(samples), key=lambda pair: (pair[1], pair[0]))
        windows = [ordered[pos:pos + 3] for pos in range(3)]
        chosen = min(windows, key=lambda trio: trio[-1][1] - trio[0][1])
        center = float(chosen[1][1])
        chosen_indices = {idx for idx, _ in chosen}
        excluded = [
            {"sample_index": i + 1, "contact_mm": value,
             "distance_from_cluster_median_mm": value - center,
             "suspected_outlier": abs(value - center) > limit}
            for i, value in enumerate(samples) if i not in chosen_indices
        ]
        full_span = max(samples) - min(samples)
        alert = full_span > limit
        if alert:
            flagged.append(tool)
        details[tool] = {
            "full_five_range_mm": full_span,
            "tightest_three_range_mm": chosen[-1][1] - chosen[0][1],
            "selected_sample_indices": sorted(idx + 1 for idx in chosen_indices),
            "excluded_readings": excluded,
            "suspected_outliers": [x for x in excluded if x["suspected_outlier"]],
            "review_required": alert,
            "reason": "Full five-reading spread exceeds advisory review threshold" if alert
                      else "No excess full-five variation",
        }
    return {
        "status": "REVIEW_REQUIRED" if flagged else "NO_ALERTS",
        "review_required": bool(flagged),
        "advisory_full_five_spread_mm": limit,
        "flagged_hotends": flagged,
        "tools": details,
        "affects_btc2_math_pass": False,
        "readiness_or_save_permitted": False,
        "warning": "Advisory only: the five-reading spread is not the BTC2 tightest-three tolerance.",
    }


def reseat_repeatability(calibration, tool_count, trials,
                         *, sample_range_tolerance_mm=RANGE_TOL,
                         relative_drift_tolerance_mm=RESEAT_OFFSET_TOL_MM,
                         t0_zero_tolerance_mm=ZERO_TOL):
    """Compare 2+ independently supplied POST-reseat trials against calibration.

    Every trial must contain T0 and all selected hotends, each with three
    complete Touch results. Repeated *physical* undock/re-dock cannot be
    authenticated by a JSON file; the result never grants commissioning.
    """
    baseline = validate(calibration, tool_count, 3)
    names = [f"T{i}" for i in range(tool_count)]
    if trials is None:
        return {
            "status": "NOT_PROVIDED", "passed_math": False,
            "required_new_trials": MIN_RESEAT_CYCLES,
            "received_trials": 0, "tools": {},
            "independent_reseating_confirmed": False,
            "commissioning_allowed": False,
            "warning": "Requires independently verified removal, pickup and new Touch captures.",
        }
    if not isinstance(trials, list):
        raise ValueError("Reseat trials must be a list")
    if not MIN_RESEAT_CYCLES <= len(trials) <= 10:
        raise ValueError("Reseat requires 2 to 10 separate Touch trial sets")
    for label, value, cap in [
        ("sample range", sample_range_tolerance_mm, 0.1),
        ("relative drift", relative_drift_tolerance_mm, 0.2),
        ("T0 zero", t0_zero_tolerance_mm, 0.1),
    ]:
        test = number(value, label)
        if not 0 < test <= cap:
            raise ValueError("Invalid " + label + " tolerance")
    baseline_medians = {name: float(median(baseline[name])) for name in names}
    baseline_offsets = {name: baseline_medians[name] - baseline_medians["T0"]
                        for name in names}
    rows = {name: [] for name in names}
    for cycle_index, candidate in enumerate(trials):
        data = validate(candidate, tool_count, 3)
        centers = {name: float(median(data[name])) for name in names}
        for name in names:
            values = data[name]
            offset = centers[name] - centers["T0"]
            span = max(values) - min(values)
            drift = offset - baseline_offsets[name]
            passed = (span <= sample_range_tolerance_mm
                      and abs(drift) <= relative_drift_tolerance_mm
                      and (name != "T0" or abs(centers[name]) <= t0_zero_tolerance_mm))
            rows[name].append({
                "trial": cycle_index + 1, "median_contact_mm": centers[name],
                "three_result_range_mm": span,
                "measured_relative_offset_mm": offset if name != "T0" else 0.0,
                "delta_vs_original_calibration_mm": drift,
                "passed_math": passed,
            })
    summary = {}
    for name in names:
        cycle_offsets = [result["measured_relative_offset_mm"] for result in rows[name]]
        drift_span = max(cycle_offsets) - min(cycle_offsets)
        passed = (all(result["passed_math"] for result in rows[name])
                  and drift_span <= relative_drift_tolerance_mm)
        summary[name] = {
            "original_relative_offset_mm": baseline_offsets[name] if name != "T0" else 0.0,
            "cycle_to_cycle_drift_range_mm": drift_span,
            "passed_math": passed,
            "trials": rows[name],
        }
    all_pass = all(row["passed_math"] for row in summary.values())
    return {
        "status": "MATH_PASS_UNVERIFIED" if all_pass else "MATH_FAIL_UNVERIFIED",
        "passed_math": all_pass,
        "required_new_trials": MIN_RESEAT_CYCLES,
        "received_trials": len(trials),
        "per_trial_max_range_mm": sample_range_tolerance_mm,
        "relative_drift_limit_mm": relative_drift_tolerance_mm,
        "tools": summary,
        "independent_reseating_confirmed": False,
        "commissioning_allowed": False,
        "warning": "Cannot validate actual tool removal/reseat, tool identity, or sensor contact from input files.",
    }
