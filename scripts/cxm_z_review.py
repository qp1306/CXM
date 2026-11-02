#!/usr/bin/env python3
"""Offline CXM Touch Z math and reliability review. No printer connection."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from cxm_z_math import calibrate, verify
from cxm_z_reliability import touch_quality, reseat_repeatability

FORMAT="CXM_Z_TOUCH_RESULTS_V1"

def synthetic_example(count=12):
    """MADE-UP results: T0–T11; not readings from any actual hotend."""
    if type(count) is not int or not 1<=count<=12:
        raise ValueError("Invalid synthetic tool count (1..12)")
    offsets=[0.000,0.070,-0.294,-0.198,0.114,0.186,
             -0.112,0.033,-0.051,0.128,-0.091,0.042]
    calibration={}; verification={}; stored={}; reseat=[{},{}]
    for index,offset in enumerate(offsets[:count]):
        key=f"T{index}"
        center=0.003+offset
        calibration[key]=[round(center+d,6) for d in (-0.006,0.0,0.005)]
        # Deliberate high outlier tests tightest-3-of-5, not all-five range.
        verification[key]=[round(center+d,6) for d in (-0.006,0.0,0.004,0.007,0.100)]
        stored[key]=offset
        # Two FABRICATED re-dock trial captures; no actual physical events.
        for cycle, deviation in enumerate((0.001,-0.002)):
            reseat[cycle][key]=[round(center+deviation+d,6)
                                for d in (-0.004,0.0,0.004)]
    return dict(format=FORMAT,synthetic=True,tool_count=count,
                calibration=calibration,verification=verification,
                stored_offsets=stored,reseat_trials=reseat)

def analyze(doc):
    required={"format","synthetic","tool_count","calibration","verification","stored_offsets"}
    allowed=required|{"reseat_trials"}
    if not isinstance(doc,dict) or not required.issubset(doc) or not set(doc)<=allowed:
        raise ValueError("Unexpected measurement input schema")
    if doc["format"]!=FORMAT or type(doc["synthetic"]) is not bool:
        raise ValueError("Invalid input format or simulation flag")
    count=doc["tool_count"]; sim=doc["synthetic"]
    cal=calibrate(doc["calibration"],count,synthetic=sim)
    ver=verify(doc["verification"],doc["stored_offsets"],count,synthetic=sim)
    quality=touch_quality(doc["verification"],count)
    reseat=reseat_repeatability(doc["calibration"],count,doc.get("reseat_trials"))
    return {
        "format":FORMAT,"calibration":cal.to_dict(),
        "verification":ver.to_dict(),
        "measurement_quality":quality,
        "redock_repeatability":reseat,
        # Preserve BTC2 mathematical tolerance checks; excess full-five
        # variation is independently flagged rather than silently accepted.
        "overall_math_pass":cal.passed_math and ver.passed_math,
        "review_required":quality["review_required"],
        # No input file can prove physical removal or re-seating. This gate
        # stays closed even when synthetic or uploaded trial maths passes.
        "additional_reseat_tests_required":True,
        "ready_for_commissioning":False,
        "save_permitted":False,"hardware_motion":False,
    }

def main(argv=None):
    parser=argparse.ArgumentParser(description="CXM Cartographer Z OFFLINE reviewer (no motion)")
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--example",action="store_true",help="Print fabricated input JSON")
    choice.add_argument("--input",type=Path,help="Review a saved JSON input")
    parser.add_argument("--tool-count",type=int,default=12,help="Synthetic tool count 1..12")
    parser.add_argument("--summary",action="store_true",
                        help="Print compact reliability and repeatability report for --input")
    args=parser.parse_args(argv)
    try:
        if args.example:
            if args.summary:
                raise ValueError("--summary requires --input")
            print(json.dumps(synthetic_example(args.tool_count),indent=2,allow_nan=False))
        else:
            if args.tool_count!=12:
                raise ValueError("--tool-count is only valid with --example")
            if args.input.stat().st_size > 100000:
                raise ValueError("Input file too large")
            doc=json.loads(args.input.read_text(encoding="utf-8"),
                parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))
            output=analyze(doc)
            if args.summary:
                output={
                    "status":output["calibration"]["status"],
                    "tool_count":output["calibration"]["tool_count"],
                    "btc2_math_pass":output["overall_math_pass"],
                    "quality_status":output["measurement_quality"]["status"],
                    "advisory_full_five_range_mm":output["measurement_quality"]["advisory_full_five_spread_mm"],
                    "flagged_hotends":output["measurement_quality"]["flagged_hotends"],
                    "reseat_status":output["redock_repeatability"]["status"],
                    "reseat_trial_count":output["redock_repeatability"]["received_trials"],
                    "physical_reseating_verified":False,
                    "ready_for_commissioning":False,
                    "save_permitted":False,
                    "hardware_motion":False,
                }
            print(json.dumps(output,indent=2,allow_nan=False))
        return 0
    except (ValueError,TypeError,KeyError,OSError,UnicodeError) as e:
        print("CXM Z OFFLINE REVIEW REJECTED: "+str(e),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
