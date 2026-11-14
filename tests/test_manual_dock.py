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
        self.state={'webhooks':{'state':'ready'}, 'toolhead':{'axis_minimum':[0,0,0], 'axis_maximum':[335,362,350], 'homed_axes':'xyz','position':[309.4,66.0,25.0]},
                    'idle_timeout':{'state':'Idle'},
                    'print_stats':{'state':'standby'},
                    'stepper_enable':{'steppers':motors},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'},
                    'gcode_macro _CXM_NATIVE':{'current_tool':-2,'jog_revision':2},
                    'gcode_macro _CXM_TEST_STATE':{'running':0},
                    'configfile':{'settings':{'stepper_x':{'position_min':0,'position_max':335},
                                             'stepper_y':{'position_min':0,'position_max':362}}}}
        def rpc(path,payload=None):
            if path=='/printer/info':return {'state':'ready'}
            if path.startswith('/printer/objects/query?'):return {'status':self.state}
            if path=='/printer/gcode/script':
                script=payload['script']
                self.command_log.append(script)
                if script.startswith('CXM_MANUAL_DOCK_JOG '):
                    values=dict(item.split('=',1) for item in script.split()[1:])
                    axis=values['AXIS']
                    distance=float(values['DIST'])
                    self.state['toolhead']['position']['XYZ'.index(axis)]+=distance
                return {}
            raise AssertionError('Unexpected Moonraker API: '+path)
        self.patcher=patch.object(m,'_rpc',side_effect=rpc)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
    def test_readiness_uses_one_small_live_query(self):
        with patch.object(m, '_rpc', return_value={'status': self.state}) as rpc:
            self.assertTrue(m.status(0, self.store)['ready'])
        rpc.assert_called_once()
        self.assertNotIn('configfile', rpc.call_args.args[0])
        self.assertIn('webhooks=state', rpc.call_args.args[0])
        del self.state['toolhead']['axis_maximum']
        with self.assertRaisesRegex(m.ManualDockError, 'travel limits'):
            m.status(0, self.store)

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
        self.assertEqual(self.command_log[0],
                         'CXM_MANUAL_DOCK_JOG TOOL=0 AXIS=X DIST=0.1000')
        self.assertNotIn('G1 ',self.command_log[0])
    def test_axiscope_z_jog_and_clearances(self):
        def jog(distance):
            return m.jog(tool=0, axis='z', distance=distance, expected_revision='a'*64,
                         acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG', store=self.store)
        self.assertEqual(jog(-0.01)['z'],24.99)
        self.assertEqual(jog(0.01)['z'],25)
        for position, distance in ((20,-0.01),(349,0.1),(25,10)):
            self.state['toolhead']['position'][2]=position
            with self.assertRaises(m.ManualDockError):
                jog(distance)
        self.assertEqual(len(self.command_log),2)

    def test_camera_jog_requires_loaded_macro_before_dispatch(self):
        args=dict(tool=0,axis='z',distance=0.1,expected_revision='a'*64,
                  acknowledgement='I_APPROVE_SUPERVISED_CAMERA_JOG',store=self.store)
        del self.state['gcode_macro _CXM_NATIVE']['jog_revision']
        with self.assertRaisesRegex(m.ManualDockError,'outdated'):
            m.jog(**args)
        self.assertEqual(self.command_log,[])
        self.state['gcode_macro _CXM_NATIVE']['jog_revision']=1
        self.assertAlmostEqual(m.jog(**args)['z'],25.1)
        self.assertTrue(self.command_log[0].endswith(' CAMERA=1'))

    def test_dock_jog_requires_revision_two_before_movement(self):
        self.state['gcode_macro _CXM_NATIVE']['jog_revision']=1
        with self.assertRaisesRegex(m.ManualDockError,'revision 2'):
            m.jog(tool=0, axis='x', distance=1.0, expected_revision='a'*64,
                  acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertEqual(self.command_log,[])

    def test_micron_jog_in_both_directions(self):
        for axis in ('x', 'y'):
            for distance in (-0.001, 0.001):
                result = m.jog(tool=0, axis=axis, distance=distance, expected_revision='a'*64,
                               acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG', store=self.store)
                self.assertTrue(result['jogged'])
                self.assertEqual(self.command_log[-1], f'CXM_MANUAL_DOCK_JOG TOOL=0 AXIS={axis.upper()} DIST={distance:.4f}')

    def test_transient_post_jog_busy_settles_without_repeat_motion(self):
        original=m._check
        calls=[0]
        def check(*args, **kwargs):
            calls[0]+=1
            if calls[0] in (2,3):
                raise m.ManualDockError('Printer is busy; manual dock motion disabled')
            return original(*args, **kwargs)
        with patch.object(m,'_check',side_effect=check),patch.object(m.time,'sleep'):
            result=m.jog(tool=0,axis='x',distance=0.1,expected_revision='a'*64,
                acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertTrue(result['jogged'])
        self.assertEqual(len(self.command_log),1)
        self.assertEqual(calls[0],4)
    def test_consecutive_verified_jogs_during_idle_timeout_tail(self):
        head = self.state['toolhead']
        head.update(print_time=80.0, estimated_print_time=81.0)
        original = m._rpc.side_effect
        def rpc(path, payload=None):
            response = original(path, payload)
            if path == '/printer/gcode/script':
                self.state['idle_timeout']['state'] = 'Printing'
                head['print_time'] += 0.1
            return response
        with patch.object(m, '_rpc', side_effect=rpc), patch.object(m.time, 'sleep', side_effect=AssertionError):
            for i in range(2):
                m.jog(tool=0, axis='x', distance=0.1, expected_revision='a'*64,
                      acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG', store=self.store)
                self.assertTrue(m.status(0, self.store)['ready'])
            head['print_time'] += 0.1
            with self.assertRaisesRegex(m.ManualDockError, 'Printer is busy'):
                m.status(0, self.store)
        self.assertEqual(len(self.command_log), 2)

    def test_busy_before_jog_is_not_retried_or_moved(self):
        self.state['idle_timeout']['state']='Printing'
        with self.assertRaisesRegex(m.ManualDockError,'Printer is busy'):
            m.jog(tool=0,axis='x',distance=0.1,expected_revision='a'*64,
                  acknowledgement='I_APPROVE_SUPERVISED_MOTOR_ON_JOG',store=self.store)
        self.assertEqual(self.command_log,[])
    def test_transient_post_capture_busy_settles_without_repeat_capture(self):
        original=m._check
        calls=[0]
        def check(*args, **kwargs):
            calls[0]+=1
            if calls[0]==2:
                raise m.ManualDockError('Printer is busy; manual dock motion disabled')
            return original(*args, **kwargs)
        with patch.object(m,'_check',side_effect=check),patch.object(m.time,'sleep'):
            result=m.capture(tool=0,expected_revision='a'*64,
                acknowledgement='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON',store=self.store)
        self.assertTrue(result['captured'])
        self.assertEqual(self.command_log,['M400'])
    def test_nonbusy_sensor_fault_after_jog_never_retries(self):
        original=m._check
        calls=[0]
        def check(*args, **kwargs):
            calls[0]+=1
            if calls[0]==2:
                self.state['gcode_button cxm_tool_detect']['state']='RELEASED'
            return original(*args, **kwargs)
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

    def test_one_click_atomic_save_for_all_selected_tools(self):
        for selected in range(12):
            self.command_log.clear()
            class SavingStore(Store):
                def __init__(self):
                    self.stored={}
                def read(self):
                    d=super().read()
                    d['config']['globals']['tool_count']=12
                    d['config']['tools'].extend(
                        {'maintenance_lockout':False} for _ in range(9))
                    if self.stored:
                        d['revision']='b'*64
                        d['config']['tools'][selected].update(self.stored)
                    return d
                def save_dock(self,tool,xy,expected_revision):
                    self.stored={'dock_x':xy['x'],'dock_y':xy['y'],
                                 'dock_z':None,'dock_reference_accepted':True}
                    return {'saved':True,'backup':'verified.cfg'}
            store=SavingStore()
            self.state['gcode_macro _CXM_NATIVE']['current_tool']=0
            with patch('cxm_native.invalidate_for_config_edit') as invalidate:
                result=m.save(tool=selected,expected_revision='a'*64,
                    acknowledgement='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON',store=store)
            self.assertTrue(result['saved'])
            self.assertTrue(result['verified'])
            self.assertEqual(result['tool'],selected)
            self.assertEqual(result['xy'],{'x':309.4,'y':66.0})
            self.assertEqual(result['backup'],'verified.cfg')
            self.assertEqual(self.command_log,['M400'])
            invalidate.assert_called_once_with(
                permit_mounted_provisional_dock=True,store=store,tool=selected)

    def test_one_click_save_rejects_empty_sensor_without_side_effects(self):
        self.state['gcode_button cxm_tool_detect']['state']='RELEASED'
        with patch('cxm_native.invalidate_for_config_edit') as invalidate:
            with self.assertRaises(m.ManualDockError):
                m.save(tool=1,expected_revision='a'*64,
                    acknowledgement='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON',store=self.store)
        invalidate.assert_not_called()
        self.assertEqual(self.command_log,[])

    def test_one_click_save_rejects_stale_revision_before_motion(self):
        with patch('cxm_native.invalidate_for_config_edit') as invalidate:
            with self.assertRaisesRegex(m.ManualDockError,'Settings changed'):
                m.save(tool=1,expected_revision='f'*64,
                    acknowledgement='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON',store=self.store)
        invalidate.assert_not_called()
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
