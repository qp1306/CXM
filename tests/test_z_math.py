"""Offline Cartographer Touch Z maths: T0–T11 and fail-closed safety."""
from __future__ import annotations
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from cxm_z_math import calibrate,verify,tightest_three
from cxm_z_review import synthetic_example,analyze

class TestZMath(unittest.TestCase):
    def test_12_tool_pass_is_not_hardware_verification(self):
        result=analyze(synthetic_example())
        self.assertTrue(result["overall_math_pass"])
        self.assertFalse(result["save_permitted"])
        self.assertFalse(result["hardware_motion"])
        for key in ["calibration","verification"]:
            section=result[key]
            self.assertEqual(section["status"],"SIMULATION_ONLY")
            self.assertEqual(len(section["tools"]),12)
            self.assertEqual(section["global_z_max_change_mm"],0.750)
            self.assertEqual(section["bed_c"],70)
            self.assertEqual(section["nozzle_c"],140)
            self.assertFalse(section["save_permitted"])
            self.assertFalse(section["motion_performed"])
        self.assertAlmostEqual(result["calibration"]["tools"]["T1"]["proposed_offset_mm"],0.070)
        self.assertEqual(result["calibration"]["tools"]["T0"]["proposed_offset_mm"],0.0)

    def test_tightest_three_and_outlier_diagnostics(self):
        mid,span,raw=tightest_three([0.003,0.002,0.004,0.007,0.450])
        self.assertAlmostEqual(mid,0.003)
        self.assertAlmostEqual(span,0.002)
        self.assertGreater(raw,0.4)

    def test_calibration_rejects_t0_residual_and_outlier(self):
        fixture=synthetic_example(2)
        fixture["calibration"]["T0"]=[0.028,0.030,0.032]
        fixture["calibration"]["T1"]=[0.065,0.070,0.105]
        result=analyze(fixture)
        self.assertFalse(result["calibration"]["passed_math"])
        self.assertFalse(result["calibration"]["tools"]["T0"]["passed_math"])
        self.assertFalse(result["calibration"]["tools"]["T1"]["passed_math"])

    def test_verification_rejects_bad_saved_master_offset(self):
        fixture=synthetic_example(2)
        fixture["stored_offsets"]["T1"]=0.1
        result=analyze(fixture)
        self.assertFalse(result["verification"]["passed_math"])
        self.assertFalse(result["verification"]["tools"]["T1"]["passed_math"])

    def test_verification_rejects_aggregate_spread_above_040(self):
        fixture=synthetic_example(3)
        fixture["stored_offsets"]["T1"]=0.048
        fixture["stored_offsets"]["T2"]=-0.272
        result=analyze(fixture)
        self.assertFalse(result["verification"]["passed_math"])
        self.assertGreater(result["verification"]["overall_error_spread_mm"],0.040)

    def test_verification_rejects_no_tight_cluster(self):
        fixture=synthetic_example(1)
        fixture["verification"]["T0"]=[0,0.04,0.08,0.12,0.16]
        self.assertFalse(analyze(fixture)["verification"]["passed_math"])

    def test_rejects_wrong_count_missing_invalid_numbers_and_limits(self):
        fixture=synthetic_example(3);fixture["tool_count"]=13
        with self.assertRaisesRegex(ValueError,"1 to 12"):analyze(fixture)
        fixture=synthetic_example(2);fixture["calibration"]["T1"]=[1.0,1.0]
        with self.assertRaisesRegex(ValueError,"exactly 3 complete"):analyze(fixture)
        fixture=synthetic_example(2);fixture["verification"]["T1"].pop()
        with self.assertRaisesRegex(ValueError,"exactly 5 complete"):analyze(fixture)
        fixture=synthetic_example(2);fixture["stored_offsets"]["T0"]=True
        with self.assertRaisesRegex(ValueError,"numeric"):analyze(fixture)
        fixture=synthetic_example(2);fixture["stored_offsets"]["T0"]=0.005
        with self.assertRaisesRegex(ValueError,"must be zero"):analyze(fixture)
        fixture=synthetic_example(2);fixture["calibration"]["T1"][1]=float("nan")
        with self.assertRaisesRegex(ValueError,"finite"):analyze(fixture)
        fixture=synthetic_example(2);del fixture["calibration"]["T1"]
        with self.assertRaisesRegex(ValueError,"exactly selected"):analyze(fixture)
        with self.assertRaisesRegex(ValueError,"<=149"):
            calibrate(synthetic_example(1)["calibration"],1,nozzle_c=150)
        with self.assertRaisesRegex(ValueError,"Invalid range"):
            calibrate(synthetic_example(1)["calibration"],1,range_tolerance=0.750)

    def test_fake_samples_not_ready_even_if_synthetic_false(self):
        fixture=synthetic_example(12);fixture["synthetic"]=False
        result=analyze(fixture)
        self.assertEqual(result["calibration"]["status"],"PROVISIONAL_UNVERIFIED")
        self.assertEqual(result["verification"]["status"],"PROVISIONAL_UNVERIFIED")
        self.assertFalse(result["save_permitted"])

    def test_cli_roundtrip_no_writes(self):
        source=Path(__file__).resolve().parents[1]/"scripts"/"cxm_z_review.py"
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/"demo.json"
            first=subprocess.run([sys.executable,str(source),"--example"],capture_output=True,text=True,check=True)
            file.write_text(first.stdout)
            second=subprocess.run([sys.executable,str(source),"--input",str(file)],capture_output=True,text=True,check=True)
            self.assertIn('"overall_math_pass": true',second.stdout)
            self.assertIn('"save_permitted": false',second.stdout)
            self.assertEqual(list(Path(root).iterdir()),[file])

if __name__=="__main__":
    unittest.main()
