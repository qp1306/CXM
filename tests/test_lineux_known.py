"""No hardware use. Test Lineux known-position arithmetic and fail-closed motion gate."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import cxm_lineux as c

class Store:
    def read(self):
        return {'revision':'a'*64,'migration_required':False,
                'config':{'globals':{'tool_count':6,'x_docking_adjust':3.0},
                          'tools':[{'maintenance_lockout':False} for _ in range(12)]}}

class KnownPositionTests(unittest.TestCase):
    def setUp(self):
        c.KNOWN_SESSION.update(pid=None,at=0.0)

    def test_3mm_jog_bias_and_correction(self):
        d=c.evaluate_known_position(raw_xy={'x':192.0,'y':170.0},
                                    known_xy=[195.0,170.0],calibration_move_x=3.0)
        self.assertTrue(d['passed'])
        self.assertEqual(d['raw_error_mm'],{'x':-3.0,'y':0.0})
        self.assertEqual(d['jog_corrected_error_mm'],{'x':0.0,'y':0.0})
        self.assertFalse(d['save_permitted'])

    def test_rejects_without_physical_clearance(self):
        with patch.object(c,'_rpc') as rpc:
            with self.assertRaises(c.MeasurementError):
                c.perform_known_check(tool=0,expected_revision='a'*64,
                                      acknowledgement='',
                                      store=Store())
            rpc.assert_not_called()

    def test_raw_match_without_compensation_is_not_silently_approved(self):
        d=c.evaluate_known_position(raw_xy={'x':195.0,'y':170.0},
                                    known_xy=[195.0,170.0],calibration_move_x=3.0)
        self.assertFalse(d['passed'])
        self.assertEqual(d['jog_corrected_error_mm']['x'],3.0)

    def test_bad_y_rejected(self):
        d=c.evaluate_known_position(raw_xy={'x':192.0,'y':171.0},
                                    known_xy=[195.0,170.0],calibration_move_x=3.0)
        self.assertFalse(d['passed'])

    def test_success_requires_matching_session_pid(self):
        pre={'ready':True,'status':{'known_start_xy_mm':[195.0,170.0],
                                   'initial_x_jog_mm':3.0,'klipper_pid':4273}}
        with patch.object(c,'query_readiness',return_value=pre):
            with patch.object(c,'_run_original_lineux',return_value={'x':192.0,'y':170.0}):
                d=c.perform_known_check(tool=0,expected_revision='a'*64,
                                        acknowledgement='I_CONFIRM_HOMED_KNOWN_XY_CLEAR_PATH',
                                        store=Store())
        self.assertTrue(d['passed'])
        self.assertEqual(c.KNOWN_SESSION['pid'],4273)

    def test_failed_known_position_never_opens_dock_gate(self):
        pre={'ready':True,'status':{'known_start_xy_mm':[195.0,170.0],
                                   'initial_x_jog_mm':3.0,'klipper_pid':4273}}
        with patch.object(c,'query_readiness',return_value=pre):
            with patch.object(c,'_run_original_lineux',return_value={'x':188.0,'y':170.0}):
                d=c.perform_known_check(tool=0,expected_revision='a'*64,
                                        acknowledgement='I_CONFIRM_HOMED_KNOWN_XY_CLEAR_PATH',
                                        store=Store())
        self.assertFalse(d['passed'])
        self.assertIsNone(c.KNOWN_SESSION['pid'])

if __name__=='__main__':
    unittest.main()
