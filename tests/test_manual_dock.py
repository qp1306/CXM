"""Hardware-free regression tests for manual motor-on dock alignment."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_manual as m

class Store:
    def read(self):
        return {'revision':'a'*64,'migration_required':False,
                'config':{'globals':{'tool_count':3},
                          'tools':[{'maintenance_lockout':False} for _ in range(3)]}}

class ManualDockTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.command_log=[]
        motors={name:True for name in ('stepper_x','stepper_y','stepper_z','stepper_z1','stepper_z2','stepper_z3')}
        self.state={'toolhead':{'homed_axes':'xyz','position':[309.4,66.0,25.0]},
                    'idle_timeout':{'state':'Idle'},
                    'print_stats':{'state':'standby'},
                    'stepper_enable':{'steppers':motors},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'},
                    'gcode_macro _CXM_NATIVE':{'current_tool':-2},
                    'gcode_macro _CXM_TEST_STATE':{'running':0},
                    'configfile':{'settings':{'stepper_x':{'position_min':0,'position_max':335},
                                             'stepper_y':{'position_min':0,'position_max':362}}}}
        def rpc(path,payload=None):
            if path=='/printer/info':return {'state':'ready'}
            if path.startswith('/printer/objects/query?'):return {'status':self.state}
            if path=='/printer/gcode/script':
                script=payload['script']
                self.command_log.append(script)
                if 'G1 X' in script:
                    self.state['toolhead']['position'][0]+=float(script.split('G1 X')[1].split()[0])
                elif 'G1 Y' in script:
                    self.state['toolhead']['position'][1]+=float(script.split('G1 Y')[1].split()[0])
                return {}
            raise AssertionError('Unexpected Moonraker API: '+path)
        self.patcher=patch.object(m,'_rpc',side_effect=rpc)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
    def test_motor_on_live_capture(self):
        d=m.capture(tool=0,expected_revision='a'*64,
          acknowledgement='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON',store=self.store)
        self.assertEqual(d['xy'],{'x':309.4,'y':66.0})
        self.assertFalse(d['saved'])
        self.assertFalse(d['verified'])
        self.assertEqual(self.command_log,['M400'])
    def test_supervised_tiny_x_jog_restores_modal_state(self):
        d=m.jog(tool=0,axis='x',distance=0.1,expected_revision='a'*64,
          acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertAlmostEqual(d['position']['x'],309.5)
        self.assertIn('SAVE_GCODE_STATE NAME=CXM_MANUAL_JOG',self.command_log[0])
        self.assertIn('RESTORE_GCODE_STATE NAME=CXM_MANUAL_JOG MOVE=0',self.command_log[0])
    def test_transient_post_jog_busy_settles_without_repeat_motion(self):
        original=m._check
        calls=[0]
        def check(*args):
            calls[0]+=1
            if calls[0] in (2,3):
                raise m.ManualDockError('Printer is busy; manual dock motion disabled')
            return original(*args)
        with patch.object(m,'_check',side_effect=check),patch.object(m.time,'sleep'):
            result=m.jog(tool=0,axis='x',distance=0.1,expected_revision='a'*64,
                acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertTrue(result['jogged'])
        self.assertEqual(len(self.command_log),1)
        self.assertEqual(calls[0],4)
    def test_busy_before_jog_is_not_retried_or_moved(self):
        self.state['idle_timeout']['state']='Printing'
        with self.assertRaisesRegex(m.ManualDockError,'Printer is busy'):
            m.jog(tool=0,axis='x',distance=0.1,expected_revision='a'*64,
                  acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertEqual(self.command_log,[])
    def test_transient_post_capture_busy_settles_without_repeat_capture(self):
        original=m._check
        calls=[0]
        def check(*args):
            calls[0]+=1
            if calls[0]==2:
                raise m.ManualDockError('Printer is busy; manual dock motion disabled')
            return original(*args)
        with patch.object(m,'_check',side_effect=check),patch.object(m.time,'sleep'):
            result=m.capture(tool=0,expected_revision='a'*64,
                acknowledgement='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON',store=self.store)
        self.assertTrue(result['captured'])
        self.assertEqual(self.command_log,['M400'])
    def test_nonbusy_sensor_fault_after_jog_never_retries(self):
        original=m._check
        calls=[0]
        def check(*args):
            calls[0]+=1
            if calls[0]==2:
                self.state['gcode_button cxm_tool_detect']['state']='RELEASED'
            return original(*args)
        with patch.object(m,'_check',side_effect=check):
            with self.assertRaisesRegex(m.ManualDockError,'MOUNTED hotend'):
                m.jog(tool=0,axis='x',distance=0.1,expected_revision='a'*64,
                      acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertEqual(len(self.command_log),1)
        self.assertEqual(calls[0],2)

    def test_no_motion_when_carriage_empty(self):
        self.state['gcode_button cxm_tool_detect']['state']='RELEASED'
        with self.assertRaisesRegex(m.ManualDockError,'requires a MOUNTED hotend'):
            m.jog(tool=0,axis='x',distance=0.1,expected_revision='a'*64,
              acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertEqual(self.command_log,[])
    def test_stale_native_identity_is_not_tool_identity_during_manual_alignment(self):
        self.state['gcode_macro _CXM_NATIVE']['current_tool']=1
        result=m.status(0,self.store)
        self.assertTrue(result['ready'])
        self.assertEqual(result['identity_source'],'operator_selected')
        self.assertEqual(result['native_tool_identity'],1)
        self.assertEqual(self.command_log,[])

    def test_allow_unknown_native_identity_after_invalidation(self):
        self.state['gcode_macro _CXM_NATIVE']['current_tool']=-2
        self.state['gcode_macro _CXM_NATIVE']['ready']=0
        self.state['gcode_macro _CXM_NATIVE']['fault']=1
        result=m.status(0,self.store)
        self.assertTrue(result['ready'])
        self.assertEqual(result['sensor'],'PRESSED')
        self.assertEqual(result['identity_source'],'operator_selected')
    def test_no_motion_when_unhomed_or_motor_off(self):
        self.state['toolhead']['homed_axes']='xy'
        with self.assertRaises(m.ManualDockError):
            m.status(0,self.store)
        self.state['toolhead']['homed_axes']='xyz'
        self.state['stepper_enable']['steppers']['stepper_x']=False
        with self.assertRaises(m.ManualDockError):
            m.status(0,self.store)
    def test_no_motion_if_boundary_exceeded(self):
        self.state['toolhead']['position'][0]=334.0
        with self.assertRaisesRegex(m.ManualDockError,'guarded physical travel'):
            m.jog(tool=0,axis='x',distance=1.0,expected_revision='a'*64,
              acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertEqual(self.command_log,[])
    def test_disallow_running_native_test(self):
        self.state['gcode_macro _CXM_TEST_STATE']['running']=1
        with self.assertRaises(m.ManualDockError):
            m.capture(tool=0,expected_revision='a'*64,
              acknowledgement='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON',store=self.store)
        self.assertEqual(self.command_log,[])

if __name__=='__main__':unittest.main()
