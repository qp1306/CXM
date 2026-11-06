"""No hardware access. Regression tests for existing CXM Lineux config preservation."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cxm_lineux_install import verify_existing_cfg

EXISTING = """# CXM dock-location calibration; Klipper module remains original/unchanged.
# CHECK LIVE printer.cfg endstops and microsteps before using.
[dock_locate_calibrate]
xy_resolution: 0.00625
x_endstop: 335.0
y_endstop: 362.0
calibrate_move_x: 3.0

[gcode_macro DOCK_CALIBRATION]
description: Calculate provisional CXM dock XY (manual supervised test only)
gcode:
    DOCK_LOCATE_CALIBRATE
"""


class ExistingLineuxConfigTests(unittest.TestCase):
    def check(self, text):
        return verify_existing_cfg(text, resolution=0.00625,
                                   xstop=335.0, ystop=362.0)

    def test_existing_user_file_accepted_unmodified(self):
        self.assertTrue(self.check(EXISTING))

    def test_comments_and_description_are_not_significant(self):
        changed=EXISTING.replace('CXM dock-location calibration', 'Another comment')
        changed=changed.replace('Calculate provisional CXM dock XY (manual supervised test only)',
                                'Original Lineux calculation')
        self.assertTrue(self.check(changed))

    def test_wrong_step_resolution_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check(EXISTING.replace('xy_resolution: 0.00625',
                                        'xy_resolution: 0.0125'))

    def test_wrong_endstop_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check(EXISTING.replace('y_endstop: 362.0',
                                        'y_endstop: 320.0'))

    def test_different_move_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check(EXISTING.replace('calibrate_move_x: 3.0',
                                        'calibrate_move_x: 4.0'))

    def test_dangerous_macro_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check(EXISTING.replace('    DOCK_LOCATE_CALIBRATE',
                                        '    SET_KINEMATIC_POSITION'))

    def test_duplicate_engine_option_rejected(self):
        with self.assertRaises(Exception):
            self.check(EXISTING.replace('xy_resolution: 0.00625',
                                       'xy_resolution: 0.00625\nxy_resolution: 0.00625'))

    def test_extra_executable_setting_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check(EXISTING.replace('calibrate_move_x: 3.0',
                                       'calibrate_move_x: 3.0\nunsafe_option: 1'))


if __name__ == '__main__':
    unittest.main()
