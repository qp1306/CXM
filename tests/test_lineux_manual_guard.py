"""Read-only tests: a manually moved carriage must never be treated as known XY."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'server'))
import cxm_lineux as c

class Store:
    def read(self):
        return {'revision':'a'*64,'migration_required':False,
                'config':{'globals':{'tool_count':6,'x_docking_adjust':3.0},
                          'tools':[{'maintenance_lockout':False} for _ in range(12)]}}

class ManualDockSafetyTests(unittest.TestCase):
    def setUp(self):
        self.steppers={
            'stepper_x':False,'stepper_y':False,
            'stepper_z':True,'stepper_z1':True,
            'stepper_z2':True,'stepper_z3':True,
        }
        self.position=[290.0,97.0,20.0,0.0]
        self.objects=['idle_timeout','toolhead','configfile','stepper_enable']
        self.pid=4321
        c.KNOWN_SESSION.update(pid=self.pid,at=time.monotonic())

    def readiness(self,mode):
        settings={
            'stepper_x':{'position_endstop':335.0,'position_max':335.0,'position_min':0.0,
                         'rotation_distance':40.0,'microsteps':32.0},
            'stepper_y':{'position_endstop':362.0,'position_max':362.0,'position_min':0.0,
                         'rotation_distance':40.0,'microsteps':32.0},
            'homing_override':{'axes':'z'},
            'dock_locate_calibrate':{'xy_resolution':0.00625,
                'x_endstop':335.0,'y_endstop':362.0,'calibrate_move_x':3.0},
        }
        def fake_rpc(path,payload=None):
            if path=='/printer/info': return {'state':'ready','process_id':self.pid}
            if path=='/printer/objects/list': return {'objects':self.objects}
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'idle_timeout':{'state':'Ready'},
                    'toolhead':{'homed_axes':'xyz','position':self.position},
                    'configfile':{'settings':settings},
                    'stepper_enable':{'steppers':self.steppers},
                }}
            if path=='/printer/gcode/help': return {'DOCK_LOCATE_CALIBRATE':'Lineux','RESPOND':'Echo'}
            raise AssertionError('unexpected '+path)
        with patch.object(c,'_rpc',side_effect=fake_rpc):
            return c.query_readiness(tool=0,saved=Store().read(),mode=mode)

    def test_known_fails_when_xy_disabled_despite_homed_axes(self):
        r=self.readiness('known')
        self.assertFalse(r['ready'])
        self.assertTrue(any('KNOWN XY INVALID' in x for x in r['blockers']))
        self.assertEqual(r['status']['known_start_xy_mm'],self.position[:2])

    def test_dock_allows_manual_unknown_xy_with_four_z_energized(self):
        r=self.readiness('dock')
        self.assertTrue(r['ready'],r['blockers'])
        self.assertTrue(r['known_verified'])
        self.assertEqual(r['status']['xy_motor_enabled'],{'x':False,'y':False})
        self.assertFalse(r['status']['xy_position_is_known'])

    def test_dock_rejects_xy_energized(self):
        self.steppers['stepper_x']=True
        r=self.readiness('dock')
        self.assertFalse(r['ready'])
        self.assertTrue(any('X/Y steppers OFF' in x for x in r['blockers']))

    def test_all_four_z_must_be_energized(self):
        self.steppers['stepper_z3']=False
        r=self.readiness('dock')
        self.assertFalse(r['ready'])
        self.assertTrue(any('All four Z steppers' in x for x in r['blockers']))

    def test_unsafe_stale_x_335_blocks_lineux_first_jog(self):
        self.position[0]=335.0
        r=self.readiness('dock')
        self.assertFalse(r['ready'])
        self.assertTrue(any('software margin' in x for x in r['blockers']))

    def test_missing_stepper_status_blocks(self):
        self.objects.remove('stepper_enable')
        r=self.readiness('dock')
        self.assertFalse(r['ready'])
        self.assertTrue(any('Cannot verify stepper motor power' in x for x in r['blockers']))

    def test_no_known_validation_in_session_blocks_dock(self):
        c.KNOWN_SESSION.update(pid=None,at=0.0)
        r=self.readiness('dock')
        self.assertFalse(r['ready'])
        self.assertTrue(any('known-position validation' in x for x in r['blockers']))

    def test_known_check_allowed_only_when_all_axes_powered(self):
        self.steppers['stepper_x']=True
        self.steppers['stepper_y']=True
        r=self.readiness('known')
        self.assertTrue(r['ready'],r['blockers'])

if __name__=='__main__':
    unittest.main()
