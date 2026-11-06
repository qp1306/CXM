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
        self.homed='xyz'
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
                    'toolhead':{'homed_axes':self.homed,'position':self.position},
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
        self.assertTrue(any('Release only X/Y motors' in x for x in r['blockers']))

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

    def test_no_known_validation_in_session_still_allows_manual_dock(self):
        c.KNOWN_SESSION.update(pid=None,at=0.0)
        r=self.readiness('dock')
        self.assertTrue(r['ready'],r['blockers'])
        self.assertFalse(r['known_verified'])

    def test_release_prepare_requires_powered_xy_and_four_z(self):
        self.steppers['stepper_x']=True
        self.steppers['stepper_y']=True
        r=self.readiness('prepare')
        self.assertTrue(r['ready'],r['blockers'])
        self.steppers['stepper_z2']=False
        r=self.readiness('prepare')
        self.assertFalse(r['ready'])

    def test_release_prepare_requires_z20(self):
        self.steppers['stepper_x']=True
        self.steppers['stepper_y']=True
        self.position[2]=19.0
        r=self.readiness('prepare')
        self.assertFalse(r['ready'])
        self.assertTrue(any('20 mm' in x for x in r['blockers']))

    def test_direct_dock_requires_xyz_homed(self):
        self.homed='z'
        r=self.readiness('dock')
        self.assertFalse(r['ready'])
        self.assertTrue(any('Home X/Y/Z' in x for x in r['blockers']))

    def test_release_runs_only_x_y_disable_commands(self):
        motors={
            'stepper_x':False,'stepper_y':False,
            'stepper_z':True,'stepper_z1':True,'stepper_z2':True,'stepper_z3':True}
        with patch.object(c,'query_readiness',return_value={'ready':True,'blockers':[]}):
            with patch.object(c,'_rpc',side_effect=[
                {}, {'status':{'stepper_enable':{'steppers':motors}}}]) as rpc:
                resp=c.release_xy_for_dock(tool=0,expected_revision='a'*64,
                    acknowledgement='I_CONFIRM_Z_SUPPORTED_RELEASE_XY',store=Store())
        self.assertTrue(resp['release_confirmed'])
        call=rpc.call_args_list[0]
        self.assertEqual(call[0][0],'/printer/gcode/script')
        self.assertEqual(call[0][1]['script'].splitlines(),[
            'SET_STEPPER_ENABLE STEPPER=stepper_x ENABLE=0',
            'SET_STEPPER_ENABLE STEPPER=stepper_y ENABLE=0'])
        self.assertNotIn('stepper_z',call[0][1]['script'])
        self.assertNotIn('G28',call[0][1]['script'])

    def test_release_confirmation_fails_if_z_motor_off(self):
        motors={'stepper_x':False,'stepper_y':False,
                'stepper_z':True,'stepper_z1':True,'stepper_z2':True,'stepper_z3':False}
        with patch.object(c,'query_readiness',return_value={'ready':True,'blockers':[]}):
            with patch.object(c,'_rpc',side_effect=[
                {}, {'status':{'stepper_enable':{'steppers':motors}}}]):
                with self.assertRaises(c.MeasurementError):
                    c.release_xy_for_dock(tool=0,expected_revision='a'*64,
                        acknowledgement='I_CONFIRM_Z_SUPPORTED_RELEASE_XY',store=Store())

    def test_release_fails_closed_without_ack(self):
        with patch.object(c,'_rpc') as rpc:
            with self.assertRaises(c.MeasurementError):
                c.release_xy_for_dock(tool=0,expected_revision='a'*64,
                    acknowledgement='',store=Store())
        rpc.assert_not_called()

    def test_known_check_allowed_only_when_all_axes_powered(self):
        self.steppers['stepper_x']=True
        self.steppers['stepper_y']=True
        r=self.readiness('known')
        self.assertTrue(r['ready'],r['blockers'])

if __name__=='__main__':
    unittest.main()
