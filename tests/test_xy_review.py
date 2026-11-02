"""CXM V0.7 offline MCU capture validation; NEVER initiates real motion."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from cxm_xy_review import analyze, synthetic_example, steps_from_snapshot


class CaptureTest(unittest.TestCase):
    def test_exact_mcu_counter_parser(self):
        a=steps_from_snapshot(
            "mcu: stepper_x:-233 stepper_y:400 toolboard:7",
            ["stepper_x","stepper_y"])
        self.assertEqual(a,(-233,400))
        b=steps_from_snapshot(
            "Recv: // mcu: stepper_x:10 stepper_y:-33 stepper_z:700",
            ["stepper_x","stepper_y"])
        self.assertEqual(b,(10,-33))
        for raw in (
            "stepper: stepper_x:10 stepper_y:20",
            "mcu: stepper_x:1 stepper_x:2 stepper_y:3",
            "mcu: stepper_x:1 stepper_y:2.5",
            "mcu: stepper_y:3",
            "mcu: stepper_x:1 stepper_y:2\nmcu: stepper_x:2 stepper_y:3",
            "mcu: stepper_x:1 stepper_y:2 garbage"):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                steps_from_snapshot(raw,["stepper_x","stepper_y"])

    def test_valid_synthetic_review_stays_unverified(self):
        doc=synthetic_example()
        out=analyze(doc)
        self.assertEqual(out["status"],"SIMULATION_ONLY")
        self.assertEqual(out["raw_dock_xy_mm"],{"x":180.0,"y":172.0})
        self.assertEqual(out["travel_mm"],{"x":155.0,"y":190.0})
        self.assertFalse(out["save_permitted"])
        self.assertFalse(out["motion_performed"])
        self.assertEqual(len(out["warnings"]),5)

    def test_non_synthetic_still_never_marked_ready(self):
        doc=synthetic_example()
        doc["synthetic"]=False
        self.assertEqual(analyze(doc)["status"],"PROVISIONAL_UNVERIFIED")
        self.assertFalse(analyze(doc)["save_permitted"])

    def test_rejects_invalid_capture_conditions(self):
        doc=synthetic_example()
        for condition in list(doc["conditions"]):
            bad=copy.deepcopy(doc);bad["conditions"][condition]=False
            with self.subTest(condition=condition),self.assertRaisesRegex(ValueError,"capture-condition"):
                analyze(bad)
        doc["conditions"]["undocumented"]=True
        with self.assertRaisesRegex(ValueError,"requires precisely"):
            analyze(doc)

    def test_rejects_disconnected_homing_counters(self):
        doc=synthetic_example()
        doc["homing"]["x"]["before"]="mcu: stepper_x:999 stepper_y:100"
        with self.assertRaisesRegex(ValueError,"Discontinuous"):
            analyze(doc)

    def test_rejects_cross_axis_movement(self):
        doc=synthetic_example()
        doc["homing"]["x"]["after"]="mcu: stepper_x:30900 stepper_y:-2800"
        with self.assertRaisesRegex(ValueError,"Cross-axis"):
            analyze(doc)

    def test_rejects_wrong_direction_or_bounds(self):
        d=synthetic_example()
        d["homing"]["x"]["after"]="mcu: stepper_x:6000 stepper_y:-27600"
        with self.assertRaisesRegex(ValueError,"direction"):
            analyze(d)
        d=synthetic_example()
        d["bounds"]["x"]=[200,335]
        with self.assertRaisesRegex(ValueError,"mechanical envelope"):
            analyze(d)

    def test_strict_rejects_extra_settings_and_invalid_numbers(self):
        d=synthetic_example()
        d["save"]=True
        with self.assertRaisesRegex(ValueError,"requires precisely"):
            analyze(d)
        d=synthetic_example()
        d["endstops"]["x"]=float("nan")
        with self.assertRaisesRegex(ValueError,"finite"):
            analyze(d)
        d=synthetic_example()
        d["calibration"]["x"]["known_distance_mm"]=False
        with self.assertRaisesRegex(ValueError,"numeric"):
            analyze(d)

    def test_cli_offline_example_round_trip_without_config(self):
        script=Path(__file__).resolve().parents[1]/"scripts"/"cxm_xy_review.py"
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"synthetic.json"
            sample=subprocess.run([sys.executable,str(script),"--example"],
                                   capture_output=True,text=True,check=True)
            path.write_text(sample.stdout)
            review=subprocess.run([sys.executable,str(script),"--input",str(path)],
                                  capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(review.stdout)["status"],"SIMULATION_ONLY")
            self.assertEqual(list(Path(temp).iterdir()),[path])


if __name__=="__main__":
    unittest.main()
