"""Hardware-free tests for CoreXY dock travel geometry."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cxm_xy_measure import CoreXYTransform, infer_dock_xy


class GeometryTest(unittest.TestCase):
    def setUp(self):
        # 80 motor steps/mm, example sign convention ONLY.
        self.matrix=CoreXYTransform.calibrate(
            20.0, (1600,1600), 20.0,(1600,-1600))
        self.base=dict(matrix=self.matrix, x_endstop=335.0,y_endstop=362.0,
                       x_bounds=(0.0,335.0),y_bounds=(0.0,362.0))

    def test_known_x_y_starting_position(self):
        result=infer_dock_xy(**self.base,
            y_home_motor_steps=(15200,-15200), # +Y=190
            x_home_motor_steps=(12400,12400))  # +X=155
        self.assertAlmostEqual(result.raw_x,180.0)
        self.assertAlmostEqual(result.raw_y,172.0)
        self.assertEqual(result.status,'PROVISIONAL_UNVERIFIED')

    def test_calibrates_reversed_motor_wiring_signs(self):
        m=CoreXYTransform.calibrate(20,(-1600,1600),20,(1600,1600))
        r=infer_dock_xy(**{**self.base,'matrix':m},
            y_home_motor_steps=(15200,15200),
            x_home_motor_steps=(-12400,12400))
        self.assertAlmostEqual(r.raw_x,180.0)
        self.assertAlmostEqual(r.raw_y,172.0)

    def test_rejects_cross_axis_motion(self):
        with self.assertRaisesRegex(ValueError,"Cross-axis"):
            infer_dock_xy(**self.base,
                y_home_motor_steps=(16000,-14000),
                x_home_motor_steps=(12400,12400))

    def test_rejects_out_of_bounds_position(self):
        with self.assertRaisesRegex(ValueError,"mechanical envelope"):
            infer_dock_xy(**self.base,
                y_home_motor_steps=(15200,-15200),
                x_home_motor_steps=(28000,28000))

    def test_rejects_wrong_motion_direction(self):
        with self.assertRaisesRegex(ValueError,"direction"):
            infer_dock_xy(**self.base,
                y_home_motor_steps=(15200,-15200),
                x_home_motor_steps=(-12400,-12400))

    def test_rejects_invalid_matrix_and_numbers(self):
        with self.assertRaises(ValueError):
            CoreXYTransform.calibrate(20,(1600,1600),20,(1600,1600))
        with self.assertRaises(ValueError):
            CoreXYTransform.calibrate(20,(1600,1600),0,(1600,-1600))
        with self.assertRaises(ValueError):
            infer_dock_xy(**self.base,
                y_home_motor_steps=(math.nan,100),
                x_home_motor_steps=(12400,12400))
        with self.assertRaises(ValueError):
            infer_dock_xy(**{**self.base,'x_bounds':(400,0)},
                y_home_motor_steps=(15200,-15200),
                x_home_motor_steps=(12400,12400))

    def test_tolerance_limits_cross_axis_displacement(self):
        # Construct a 0.05 mm unintended X movement during Y home.
        r=infer_dock_xy(**self.base,
             y_home_motor_steps=(15204,-15196),
             x_home_motor_steps=(12400,12400),
             cross_axis_tolerance_mm=0.1)
        self.assertAlmostEqual(r.y_cross_axis,0.05)
        with self.assertRaises(ValueError):
            infer_dock_xy(**self.base,
                y_home_motor_steps=(15204,-15196),
                x_home_motor_steps=(12400,12400),
                cross_axis_tolerance_mm=0.01)


if __name__=="__main__":
    unittest.main()
