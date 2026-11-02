"""CXM V0.8.1: offline Touch outlier and re-dock safety regression tests."""
from __future__ import annotations
import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))

from cxm_z_reliability import touch_quality, reseat_repeatability
from cxm_z_review import synthetic_example, analyze

class ReliabilityTest(unittest.TestCase):
    def test_outliers_are_explicit_without_loosening_btc2_math(self):
        d=synthetic_example()
        result=analyze(d)
        self.assertTrue(result["overall_math_pass"])
        self.assertTrue(result["review_required"])
        self.assertEqual(result["measurement_quality"]["status"],"REVIEW_REQUIRED")
        self.assertEqual(result["measurement_quality"]["flagged_hotends"],
                         [f"T{i}" for i in range(12)])
        entry=result["measurement_quality"]["tools"]["T0"]
        self.assertAlmostEqual(entry["full_five_range_mm"],0.106)
        self.assertAlmostEqual(entry["tightest_three_range_mm"],0.007)
        self.assertEqual(entry["selected_sample_indices"],[2,3,4])
        self.assertEqual([x["sample_index"] for x in entry["excluded_readings"]],[1,5])
        self.assertEqual([x["sample_index"] for x in entry["suspected_outliers"]],[5])
        self.assertFalse(result["ready_for_commissioning"])
        self.assertFalse(result["save_permitted"])
        self.assertFalse(result["hardware_motion"])

    def test_no_alerts_for_clean_five_result_series(self):
        d=synthetic_example(2)
        for k in d["verification"]:
            center=d["stored_offsets"][k] + 0.003
            d["verification"][k]=[center+x for x in (-0.005,-0.003,0,0.003,0.006)]
        result=analyze(d)
        self.assertTrue(result["overall_math_pass"])
        self.assertFalse(result["review_required"])
        self.assertEqual(result["measurement_quality"]["status"],"NO_ALERTS")
        self.assertEqual(result["measurement_quality"]["tools"]["T0"]["suspected_outliers"],[])
        self.assertFalse(result["ready_for_commissioning"])

    def test_reseat_math_pass_still_not_physical_confirmation(self):
        d=synthetic_example()
        result=analyze(d)
        repeat=result["redock_repeatability"]
        self.assertTrue(repeat["passed_math"])
        self.assertEqual(repeat["status"],"MATH_PASS_UNVERIFIED")
        self.assertEqual(repeat["received_trials"],2)
        self.assertFalse(repeat["independent_reseating_confirmed"])
        self.assertFalse(repeat["commissioning_allowed"])
        self.assertEqual(result["additional_reseat_tests_required"],False)
        self.assertFalse(result["ready_for_commissioning"])

    def test_reseat_absent_or_one_cycle_never_approves(self):
        d=synthetic_example(2)
        del d["reseat_trials"]
        out=analyze(d)
        self.assertEqual(out["redock_repeatability"]["status"],"NOT_PROVIDED")
        self.assertTrue(out["additional_reseat_tests_required"])
        d["reseat_trials"]=synthetic_example(2)["reseat_trials"][:1]
        with self.assertRaisesRegex(ValueError,"2 to 10"):analyze(d)

    def test_reseat_rejects_straying_hotend_and_bed_reference(self):
        d=synthetic_example(3)
        for item in d["reseat_trials"][1]["T2"]:
            self.assertTrue(math.isfinite(item))
        d["reseat_trials"][1]["T2"]=[
            value+0.035 for value in d["reseat_trials"][1]["T2"]]
        out=analyze(d)
        self.assertFalse(out["redock_repeatability"]["tools"]["T2"]["passed_math"])
        self.assertEqual(out["redock_repeatability"]["status"],"MATH_FAIL_UNVERIFIED")
        self.assertTrue(out["additional_reseat_tests_required"])
        d=synthetic_example(3)
        d["reseat_trials"][0]["T0"]=[0.030,0.032,0.034]
        out=analyze(d)
        self.assertFalse(out["redock_repeatability"]["tools"]["T0"]["passed_math"])

    def test_reseat_rejects_bad_three_result_repeatability(self):
        d=synthetic_example(2)
        d["reseat_trials"][1]["T1"]=[0.060,0.077,0.095]
        out=analyze(d)
        self.assertFalse(out["redock_repeatability"]["tools"]["T1"]["passed_math"])
        self.assertTrue(out["additional_reseat_tests_required"])

    def test_reseat_requires_all_tools_each_cycle_and_finite_values(self):
        d=synthetic_example(3)
        del d["reseat_trials"][1]["T1"]
        with self.assertRaisesRegex(ValueError,"exactly selected"):analyze(d)
        d=synthetic_example(3)
        d["reseat_trials"][0]["T2"][1]=float("inf")
        with self.assertRaisesRegex(ValueError,"finite"):analyze(d)
        d=synthetic_example(3)
        d["reseat_trials"]={}
        with self.assertRaisesRegex(ValueError,"must be a list"):analyze(d)

    def test_rejects_non_existent_threshold_and_wrong_data_type(self):
        d=synthetic_example(2)
        with self.assertRaisesRegex(ValueError,"Invalid full-five"):
            touch_quality(d["verification"],2,full_range_review_mm=-1)
        with self.assertRaisesRegex(ValueError,"Invalid relative drift"):
            reseat_repeatability(d["calibration"],2,d["reseat_trials"],
                                 relative_drift_tolerance_mm=0.75)
        with self.assertRaisesRegex(ValueError,"numeric"):
            touch_quality(d["verification"],2,full_range_review_mm=True)

    def test_legacy_capture_is_compatible_but_reseat_required(self):
        d=synthetic_example(1)
        del d["reseat_trials"]
        old=analyze(d)
        self.assertTrue(old["overall_math_pass"])
        self.assertEqual(old["redock_repeatability"]["status"],"NOT_PROVIDED")
        self.assertFalse(old["ready_for_commissioning"])

if __name__=="__main__":
    unittest.main()
