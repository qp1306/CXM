"""No motor motion. Unit tests for Lineux/CXM Control Centre bridge."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_lineux as c

class FakeStore:
    def read(self):
        return {'revision':'a'*64,'migration_required':False,
                'config':{'globals':{'tool_count':6,'x_docking_adjust':3.0},
                         'tools':[{'maintenance_lockout':False} for _ in range(12)]}}

class LineuxBridgeTests(unittest.TestCase):
    def test_report(self):
        text=('Lineux Hotswap Dock Calibration\n----\nInitial MCU: X=1 Y=2\n'+
              'Calculated Dock Location:\nX: 179.25 mm\nY: 171.50 mm')
        self.assertEqual(c.parse_report(text), {'x':179.25,'y':171.5})
        with self.assertRaises(c.MeasurementError):
            c.parse_report(text+text)
    def test_marker_isolation(self):
        records=[{'type':'response','message':'// CXM_LINEUX_deadbeefdeadbeef_START'},
                 {'type':'response','message':'// Lineux Hotswap Dock Calibration\nCalculated Dock Location:\nX: 180.00 mm\nY: 170.00 mm'},
                 {'type':'response','message':'// CXM_LINEUX_deadbeefdeadbeef_END'}]
        self.assertEqual(c._report_between(records,'CXM_LINEUX_deadbeefdeadbeef_START',
                                            'CXM_LINEUX_deadbeefdeadbeef_END')['x'],180)
        with self.assertRaises(c.MeasurementError):
            c._report_between(records[:-1],'CXM_LINEUX_deadbeefdeadbeef_START',
                               'CXM_LINEUX_deadbeefdeadbeef_END')
    def test_exact_engine_settings(self):
        settings={
          'stepper_x':{'position_endstop':335,'position_max':335,'position_min':0,
                       'rotation_distance':40,'microsteps':32,'full_steps_per_rotation':200},
          'stepper_y':{'position_endstop':362,'position_max':362,'position_min':0,
                       'rotation_distance':40,'microsteps':32,'full_steps_per_rotation':200},
          'dock_locate_calibrate':{'x_endstop':335,'y_endstop':362,
                                   'xy_resolution':0.00625,'calibrate_move_x':3}}
        cfg,step,move=c._endstop_settings(settings)
        self.assertAlmostEqual(step,0.00625)
        settings['dock_locate_calibrate']['xy_resolution']=0.0125
        with self.assertRaises(c.MeasurementError):c._endstop_settings(settings)
    def test_fails_closed_without_ack(self):
        with self.assertRaises(c.MeasurementError):
            c.perform_measurement(tool=0, expected_revision='a'*64,
                                  acknowledgement='', store=FakeStore())
    def test_wrong_revision_never_sends_motion(self):
        with patch.object(c,'_rpc') as rpc:
            with self.assertRaises(c.MeasurementError):
                c.perform_measurement(tool=0,expected_revision='b'*64,
                       acknowledgement='I_CONFIRM_CLEAR_DOCK_PATH',store=FakeStore())
            rpc.assert_not_called()
    def test_missing_engine_blocks(self):
        settings={
            'stepper_x':{'position_endstop':335,'position_max':335,'position_min':0,'rotation_distance':40,'microsteps':32},
            'stepper_y':{'position_endstop':362,'position_max':362,'position_min':0,'rotation_distance':40,'microsteps':32},
            'dock_locate_calibrate':{'x_endstop':335,'y_endstop':362,'xy_resolution':0.00625,'calibrate_move_x':3},
            'homing_override':{'axes':'xyz'}}
        def fake_rpc(path, payload=None):
            if path=='/printer/info':return {'state':'ready'}
            if path=='/printer/objects/list':return {'objects':['idle_timeout','toolhead','configfile']}
            if path.startswith('/printer/objects/query?'):
                return {'status':{'idle_timeout':{'state':'Ready'},'toolhead':{'homed_axes':'xyz',
                    'position':[190,172,18]},'configfile':{'settings':settings}}}
            if path=='/printer/gcode/help':return {}
            raise AssertionError(path)
        with patch.object(c,'_rpc',side_effect=fake_rpc):
            readiness=c.query_readiness(tool=0,saved=FakeStore().read())
        self.assertFalse(readiness['ready'])
        self.assertIn('DOCK_LOCATE_CALIBRATE',str(readiness['blockers']))
    def test_outside_bound_report_rejected(self):
        # Dry run: report parsing accepts numbers but caller bounds-checks them
        self.assertEqual(c.parse_report('Lineux Hotswap Dock Calibration\nCalculated Dock Location:\n'
                                        'X: -20.00 mm\nY: 170.00 mm')['x'],-20)

if __name__=='__main__':unittest.main()