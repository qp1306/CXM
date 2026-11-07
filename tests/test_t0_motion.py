"""T0 XY-only commissioning protections: no physical hardware required."""
import sys
import unittest
import itertools
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_t0 as c
from cxm_config import template

class Store:
    def __init__(self):
        self.data=template()
        self.data['globals']['tool_count']=1
        self.data['globals']['safe_y']=120.0 # legacy value, never used for motion
        self.data['globals']['cxm_safe_clearance_y']=54.12 # T0 datum 65.88 + 54.12 = 120
        self.data['tools'][0]['dock_x']=298.98
        self.data['tools'][0]['dock_y']=65.88
        self.data['tools'][0]['dock_reference_accepted']=True
        self.rev='a'*64
    def read(self):
        return {'config':self.data,'revision':self.rev,'migration_required':False}

class Machine:
    def __init__(self):
        self.pid=1234
        self.x=195.0
        self.y=170.0
        self.z=20.0
        self.sensor=False
        self.simulate_single_auto=False
        self.scripts=[]
        self.busy_reads_after_move=0
        self.busy_remaining=0
        self.busy_read_count=0
        self.axes='xyz'
        self.enabled=True
    def rpc(self,path,payload=None):
        if path=='/printer/info':
            return {'state':'ready','process_id':self.pid}
        if path=='/printer/objects/list':
            return {'objects':['idle_timeout','toolhead','stepper_enable',
                               'gcode_button carriage_t0',
                               'gcode_button cxm_tool_detect']}
        if path.startswith('/printer/objects/query?'):
            if 'gcode_button' in path:
                state='PRESSED' if self.sensor else 'RELEASED'
                return {'status':{
                    'gcode_button carriage_t0':{'state':state},
                    'gcode_button cxm_tool_detect':{'state':state},
                }}
            idle='Ready'
            if self.busy_remaining>0:
                self.busy_remaining-=1
                self.busy_read_count+=1
                idle='Printing'
            return {'status':{
                'idle_timeout':{'state':idle},
                'toolhead':{'homed_axes':self.axes,'position':[self.x,self.y,self.z,0]},
                'stepper_enable':{'steppers':{v:self.enabled for v in c.MOTORS}},
            }}
        if path=='/printer/gcode/script':
            script=payload['script']
            self.scripts.append(script)
            self.busy_remaining=self.busy_reads_after_move
            for line in script.splitlines():
                if line.startswith('G1'):
                    for term in line.split()[1:]:
                        if term.startswith('X'):self.x=float(term[1:])
                        if term.startswith('Y'):self.y=float(term[1:])
            if self.simulate_single_auto or len(self.scripts)>=2:
                self.sensor=not self.sensor
            return {}
        raise AssertionError('Unexpected request '+path)

class T0Test(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.machine=Machine()
        c.SESSION.update(pid=None,revision=None,stage=None,sensor=None,
                         samples={},last_action=None,xy=None,path=None)
        c.AUTO_STATE.update(pid=None,revision=None,fault=None,last_success=None)
        c.CYCLE_STATE.update(running=False,requested=0,completed=0,phase='idle',
                             stop_requested=False,error=None,last_result=None)
        self.patch=patch.object(c,'_rpc',side_effect=self.machine.rpc)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_confirm_staged_does_not_move_and_enables_first_dropoff(self):
        # Live printer is already at measured T0 staging, but backend lost
        # volatile stage state. Do not repeat a mechanical staging movement.
        self.machine.x=298.98
        self.machine.y=120.0
        self.machine.z=21.0
        self.machine.sensor=True
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.assertTrue(c.status(self.store)['can_confirm_staging'])
        self.assertEqual(c.SESSION['stage'],None)
        outcome=c.confirm_staging(store=self.store,
            expected_revision=self.store.rev,
            acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        self.assertEqual(outcome['status'],'SUPERVISED_T0_STAGING_CONFIRMED_NO_MOVEMENT')
        self.assertEqual(self.machine.scripts,[])
        status=c.status(self.store)
        self.assertEqual(status['stage'],'staged')
        self.assertEqual(status['last_action'],'stage')
        self.assertTrue(status['first_dropoff_ready'])
        self.assertFalse(status['can_confirm_staging'])
        self.assertFalse(status['sensor_calibrated'])

    def test_registered_mounted_sensor_after_staging_can_confirm_without_motion(self):
        # Exact field observation: position at dock staging, mounted sensor
        # recorded, stage=None but last_action='stage'. Previously stuck.
        self.machine.sensor=True
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(len(self.machine.scripts),1)
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        observed=c.status(self.store)
        self.assertEqual(observed['position_mm'][:2],[298.98,120.0])
        self.assertEqual(observed['sensor_samples'],{'mounted':'PRESSED'})
        self.assertEqual(observed['stage'],None)
        self.assertEqual(observed['last_action'],'stage')
        self.assertTrue(observed['can_confirm_staging'])
        self.assertFalse(observed['first_dropoff_ready'])
        before=list(self.machine.scripts)
        result=c.confirm_staging(store=self.store,expected_revision=self.store.rev,
            acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        self.assertEqual(result['status'],'SUPERVISED_T0_STAGING_CONFIRMED_NO_MOVEMENT')
        self.assertEqual(self.machine.scripts,before)
        ready=c.status(self.store)
        self.assertTrue(ready['first_dropoff_ready'])
        self.assertEqual(ready['stage'],'staged')
        self.assertFalse(ready['can_confirm_staging'])

    def test_stage_reconfirmation_never_allows_prior_pickup_or_dropoff(self):
        self.machine.x=298.98
        self.machine.y=120.0
        self.machine.sensor=True
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        for prior in ('pickup','dropoff','first_dropoff_pending'):
            c.SESSION['stage']=None
            c.SESSION['last_action']=prior
            self.assertFalse(c.status(self.store)['can_confirm_staging'])
            with self.assertRaisesRegex(c.T0Error,'Only an untouched first-cycle'):
                c.confirm_staging(store=self.store,expected_revision=self.store.rev,
                    acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        self.assertEqual(self.machine.scripts,[])

    def test_confirm_staging_rejects_wrong_position_sensor_and_ack(self):
        self.machine.x=298.98
        self.machine.y=120.0
        self.machine.sensor=True
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.machine.x=299.40  # exceeds 0.2 mm staging tolerance
        self.assertFalse(c.status(self.store)['can_confirm_staging'])
        with self.assertRaisesRegex(c.T0Error,'staging X/Y'):
            c.confirm_staging(store=self.store,expected_revision=self.store.rev,
                acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        self.machine.x=298.98
        self.machine.sensor=False
        self.assertFalse(c.status(self.store)['can_confirm_staging'])
        with self.assertRaisesRegex(c.T0Error,'does not match'):
            c.confirm_staging(store=self.store,expected_revision=self.store.rev,
                acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        self.machine.sensor=True
        with self.assertRaisesRegex(c.T0Error,'Confirm physical'):
            c.confirm_staging(store=self.store,expected_revision=self.store.rev,
                acknowledgement='NOT_CONFIRMED')
        with self.assertRaisesRegex(c.T0Error,'coordinates changed'):
            c.confirm_staging(store=self.store,expected_revision='0'*64,
                acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        self.assertEqual(self.machine.scripts,[])

    def test_confirm_staging_maintains_existing_klipper_safety_checks(self):
        self.machine.x=298.98
        self.machine.y=120.0
        self.machine.sensor=True
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        for attr,bad,good in (('axes','xy','xyz'),('enabled',False,True),
                              ('z',19.0,20.0)):
            setattr(self.machine,attr,bad)
            self.assertFalse(c.status(self.store)['ready'])
            with self.assertRaises(c.T0Error):
                c.confirm_staging(store=self.store,expected_revision=self.store.rev,
                    acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
            setattr(self.machine,attr,good)
        self.assertEqual(self.machine.scripts,[])

    def test_confirmation_requires_fresh_initial_mounted_state(self):
        self.machine.x=298.98
        self.machine.y=120.0
        self.machine.sensor=True
        self.assertFalse(c.status(self.store)['can_confirm_staging'])
        with self.assertRaisesRegex(c.T0Error,'Record the actual T0 MOUNTED'):
            c.confirm_staging(store=self.store,expected_revision=self.store.rev,
                acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        c.SESSION['last_action']='first_dropoff_pending'
        self.assertFalse(c.status(self.store)['can_confirm_staging'])
        with self.assertRaisesRegex(c.T0Error,'Only an untouched first-cycle'):
            c.confirm_staging(store=self.store,expected_revision=self.store.rev,
                acknowledgement='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED')
        self.assertEqual(self.machine.scripts,[])

    def test_repeat_three_complete_cycles_starting_with_t0_mounted(self):
        self.machine.sensor=True
        self.machine.simulate_single_auto=True
        result=c.repeat_t0_cycles(store=self.store,expected_revision=self.store.rev,
            cycles=3,
            acknowledgement='I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(result['status'],'T0_REPEAT_COMPLETE')
        self.assertTrue(result['initial_dropoff'])
        self.assertEqual(result['completed_cycles'],3)
        self.assertEqual(len(self.machine.scripts),7)
        self.assertFalse(self.machine.sensor,'Final carriage is empty')
        self.assertEqual(result['final_sensor'],'RELEASED')
        self.assertEqual(c.cycle_status()['phase'],'Complete')
        self.assertFalse(c.cycle_status()['running'])
        self.assertIsNone(c.AUTO_STATE['fault'])
        self.assertEqual(self.machine.x,self.store.data['tools'][0]['dock_x'])
        self.assertAlmostEqual(self.machine.y,
          self.store.data['tools'][0]['dock_y']+
          self.store.data['globals']['cxm_safe_clearance_y'])
        self.assertTrue(all(' Z' not in g for g in self.machine.scripts))

    def test_repeat_two_cycles_start_empty_and_ignore_manual_sensor_samples(self):
        self.machine.sensor=False
        self.machine.simulate_single_auto=True
        self.assertEqual(c.SESSION['samples'],{})
        result=c.repeat_t0_cycles(store=self.store,expected_revision=self.store.rev,
            cycles=2,
            acknowledgement='I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertFalse(result['initial_dropoff'])
        self.assertEqual(result['completed_cycles'],2)
        self.assertEqual(len(self.machine.scripts),4)
        self.assertFalse(self.machine.sensor)
        self.assertEqual(c.SESSION['samples'],{})

    def test_repeat_stop_finishes_current_cycle_without_extra_movements(self):
        self.machine.sensor=False
        self.machine.simulate_single_auto=True
        original=self.machine.rpc
        def request_stop_during_first_dropoff(path,payload=None):
            result=original(path,payload)
            if path=='/printer/gcode/script' and len(self.machine.scripts)==2:
                response=c.stop_cycles(acknowledgement='STOP_AFTER_CURRENT_T0_CYCLE')
                self.assertTrue(response['stop_requested'])
            return result
        with patch.object(c,'_rpc',side_effect=request_stop_during_first_dropoff):
            result=c.repeat_t0_cycles(store=self.store,expected_revision=self.store.rev,
                cycles=10,
                acknowledgement='I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(result['status'],'T0_REPEAT_STOPPED')
        self.assertEqual(result['completed_cycles'],1)
        self.assertEqual(len(self.machine.scripts),2)
        self.assertFalse(self.machine.sensor)
        self.assertFalse(c.cycle_status()['running'])

    def test_repeat_rejects_invalid_counts_and_config_before_any_motion(self):
        for count in (0,-1,21,1.0,'3',True):
            with self.assertRaisesRegex(c.T0Error,'Choose 1 to 20'):
                c.repeat_t0_cycles(store=self.store,expected_revision=self.store.rev,
                    cycles=count,
                    acknowledgement='I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE')
        with self.assertRaisesRegex(c.T0Error,'Confirm the complete'):
            c.repeat_t0_cycles(store=self.store,expected_revision=self.store.rev,
                cycles=2,acknowledgement='INVALID')
        with self.assertRaisesRegex(c.T0Error,'settings changed'):
            c.repeat_t0_cycles(store=self.store,expected_revision='0'*64,
                cycles=2,
                acknowledgement='I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(self.machine.scripts,[])
        self.assertFalse(c.cycle_status()['running'])

    def test_repeat_fails_closed_on_sensor_mismatch_after_dropoff(self):
        self.machine.sensor=True
        original=self.machine.rpc
        def stuck_mounted(path,payload=None):
            result=original(path,payload)
            if path=='/printer/gcode/script':
                self.machine.sensor=True
            return result
        with patch.object(c,'_rpc',side_effect=stuck_mounted):
            with self.assertRaisesRegex(c.T0Error,'presence switch still reports'):
                c.repeat_t0_cycles(store=self.store,expected_revision=self.store.rev,
                    cycles=4,
                    acknowledgement='I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(len(self.machine.scripts),1,
                         'Never proceed to pickup after failing initial dropoff')
        self.assertEqual(c.cycle_status()['completed'],0)
        self.assertFalse(c.cycle_status()['running'])
        self.assertIsNotNone(c.cycle_status()['error'])
        self.assertFalse(c.status(self.store)['automatic']['enabled'])

    def test_repeat_holds_shared_motion_lock_for_whole_test(self):
        self.machine.sensor=False
        self.machine.simulate_single_auto=True
        original=self.machine.rpc
        checked=[False]
        def attempt_parallel_action(path,payload=None):
            if path=='/printer/gcode/script' and not checked[0]:
                checked[0]=True
                with self.assertRaisesRegex(c.T0Error,'Another printer motion'):
                    c.automatic_toolchange(store=self.store,
                        expected_revision=self.store.rev,kind='pickup',
                        acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
            return original(path,payload)
        with patch.object(c,'_rpc',side_effect=attempt_parallel_action):
            result=c.repeat_t0_cycles(store=self.store,expected_revision=self.store.rev,
                cycles=1,
                acknowledgement='I_CONFIRMED_T0_REPEAT_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertTrue(checked[0])
        self.assertEqual(result['completed_cycles'],1)
        self.assertEqual(len(self.machine.scripts),2)

    def test_cxchanger_motion_is_relative_to_each_dock_and_ignores_lineux_legacy_safe_y(self):
        p=c.plan(self.store.read())
        self.assertEqual(p['motion_source'],'CxChanger')
        self.assertAlmostEqual(p['safe_y'],120.0)
        self.store.data['tools'][0]['dock_y']=85.0
        self.assertAlmostEqual(c.plan(self.store.read())['safe_y'],139.12)
        self.store.data['globals']['safe_y']=333.0
        self.assertAlmostEqual(c.plan(self.store.read())['safe_y'],139.12)
        self.store.data['globals']['cxm_shift_x']=-5.0
        self.store.data['globals']['cxm_dodge_y']=16.0
        p=c.plan(self.store.read())
        self.assertEqual(p['dropoff'][1],(293.98,85.0))
        self.assertEqual(p['dropoff'][2],(293.98,101.0))

    def test_legacy_dock_reference_is_not_automatically_authorised(self):
        self.store.data['tools'][0]['dock_reference_accepted']=False
        self.machine.sensor=True
        with self.assertRaisesRegex(c.T0Error,'Re-measure with Lineux'):
            c.automatic_toolchange(store=self.store,expected_revision=self.store.rev,
                kind='dropoff',
                acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(self.machine.scripts,[])

    def test_one_click_dropoff_and_pickup_auto_stage_and_check_sensor(self):
        # No selected sensor, manual recording, or Approach button required.
        self.machine.sensor=True
        self.machine.simulate_single_auto=True
        self.store.data['tools'][0]['dock_x']=302.19
        self.store.data['tools'][0]['dock_y']=65.97
        status=c.status(self.store)
        self.assertTrue(status['automatic']['enabled'])
        self.assertEqual(status['automatic']['signal'],'PRESSED')
        self.assertEqual(status['automatic']['action'],'dropoff')
        result=c.automatic_toolchange(store=self.store,
            expected_revision=self.store.rev,kind='dropoff',
            acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(result['status'],'T0_DROPOFF_SENSOR_CONFIRMED')
        self.assertEqual(result['signal'],'RELEASED')
        self.assertTrue(result['staging_performed'])
        self.assertEqual(len(self.machine.scripts),1,
            'One submitted script contains staging AND all dropoff movements')
        self.assertEqual(self.machine.scripts[0].splitlines(),
            ['G90','G1 Y120.09000 F600','G1 X302.19000 F600','M400',
             'G1 X302.19000 Y65.97000 F240',
             'G1 X297.39000 Y65.97000 F180',
             'G1 X297.39000 Y79.97000 F240',
             'G1 X302.19000 Y79.97000 F240',
             'G1 X302.19000 Y120.09000 F240','M400'])
        self.assertTrue(all(' Z' not in x for x in self.machine.scripts))
        status=c.status(self.store)
        self.assertEqual(status['automatic']['action'],'pickup')
        self.assertTrue(status['automatic']['enabled'])
        result=c.automatic_toolchange(store=self.store,
            expected_revision=self.store.rev,kind='pickup',
            acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(result['signal'],'PRESSED')
        self.assertFalse(result['staging_performed'])
        self.assertEqual(len(self.machine.scripts),2)
        self.assertEqual(self.machine.scripts[1].splitlines(),
            ['G90',
             'G1 X302.19000 Y79.97000 F240',
             'G1 X297.39000 Y79.97000 F240',
             'G1 X297.39000 Y65.97000 F240',
             'G1 X302.19000 Y65.97000 F180',
             'G1 X302.19000 Y120.09000 F240','M400'])
        self.assertEqual(c.status(self.store)['automatic']['action'],'dropoff')
        self.assertEqual(c.SESSION['samples'],{})

    def test_one_click_waits_for_transient_idle_after_complete_sequence(self):
        # Moonraker returns while idle_timeout is transiently Printing.
        # All movements were already sent in one script. Never re-issue it.
        self.machine.sensor=True
        self.machine.simulate_single_auto=True
        self.machine.busy_reads_after_move=3
        result=c.automatic_toolchange(store=self.store,
            expected_revision=self.store.rev,kind='dropoff',
            acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(result['status'],'T0_DROPOFF_SENSOR_CONFIRMED')
        self.assertEqual(len(self.machine.scripts),1)
        self.assertGreaterEqual(self.machine.busy_read_count,3)
        self.assertIn('G1 Y120.00000 F600',self.machine.scripts[0])
        self.assertIn('G1 X298.98000 Y65.88000 F240',self.machine.scripts[0])
        self.assertEqual(c.status(self.store)['automatic']['signal'],'RELEASED')
        self.assertIsNone(c.AUTO_STATE['fault'])

    def test_persistent_klipper_busy_after_complete_sequence_latches_fault(self):
        self.machine.sensor=True
        self.machine.busy_reads_after_move=1000
        clock=itertools.count()
        with patch.object(c.time,'monotonic',side_effect=lambda: next(clock)):
            with patch.object(c.time,'sleep',return_value=None):
                with self.assertRaisesRegex(c.T0Error,'did not return to idle'):
                    c.automatic_toolchange(store=self.store,
                        expected_revision=self.store.rev,kind='dropoff',
                        acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(len(self.machine.scripts),1,
                         'Full ordered sequence submitted once; no extra G-code on idle timeout')
        self.machine.busy_remaining=0
        status=c.status(self.store)
        self.assertFalse(status['automatic']['enabled'])
        self.assertIsNotNone(status['automatic']['fault'])

    def test_final_sensor_mismatch_is_reported_and_latches_test_fault(self):
        # The one script runs fully, then we check the physical switch.
        self.machine.sensor=True
        self.machine.busy_reads_after_move=2
        original=self.machine.rpc
        def frozen_mounted(path,payload=None):
            result=original(path,payload)
            if path=='/printer/gcode/script':
                self.machine.sensor=True
            return result
        with patch.object(c,'_rpc',side_effect=frozen_mounted):
            with self.assertRaisesRegex(c.T0Error,'presence switch still reports'):
                c.automatic_toolchange(store=self.store,
                    expected_revision=self.store.rev,kind='dropoff',
                    acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(len(self.machine.scripts),1)
        self.machine.busy_remaining=0
        self.assertFalse(c.status(self.store)['automatic']['enabled'])

    def test_one_click_action_uses_live_switch_not_session_samples(self):
        self.machine.sensor=True
        self.assertEqual(c.status(self.store)['automatic']['action'],'dropoff')
        self.machine.sensor=False
        self.assertEqual(c.status(self.store)['automatic']['action'],'pickup')
        with self.assertRaisesRegex(c.T0Error,'wrong operation'):
            c.automatic_toolchange(store=self.store,
                expected_revision=self.store.rev,kind='dropoff',
                acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(self.machine.scripts,[])
        self.assertEqual(c.SESSION['samples'],{})

    def test_one_click_requires_homed_safe_power_clear_path_and_actual_switch(self):
        self.machine.sensor=True
        for attr,bad,good in (('axes','xy','xyz'),('enabled',False,True),
                              ('z',19.0,20.0),('y',80.0,170.0)):
            setattr(self.machine,attr,bad)
            with self.assertRaises(c.T0Error):
                c.automatic_toolchange(store=self.store,
                    expected_revision=self.store.rev,kind='dropoff',
                    acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
            setattr(self.machine,attr,good)
        self.machine.sensor=True
        with self.assertRaisesRegex(c.T0Error,'Physically confirm'):
            c.automatic_toolchange(store=self.store,expected_revision=self.store.rev,
                kind='dropoff',acknowledgement='INVALID')
        with self.assertRaisesRegex(c.T0Error,'coordinates changed'):
            c.automatic_toolchange(store=self.store,expected_revision='0'*64,
                kind='dropoff',
                acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(self.machine.scripts,[])

    def test_failed_switch_transition_locks_out_until_physical_inspection(self):
        self.machine.sensor=True
        def frozen(path,payload=None):
            reply=self.machine.rpc(path,payload)
            if path=='/printer/gcode/script':
                self.machine.sensor=True
            return reply
        with patch.object(c,'_rpc',side_effect=frozen):
            with self.assertRaisesRegex(c.T0Error,'presence switch still reports'):
                c.automatic_toolchange(store=self.store,
                    expected_revision=self.store.rev,kind='dropoff',
                    acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(len(self.machine.scripts),1)
        status=c.status(self.store)
        self.assertFalse(status['automatic']['enabled'])
        self.assertIsNotNone(status['automatic']['fault'])
        with self.assertRaisesRegex(c.T0Error,'T0 dropoff interrupted'):
            c.automatic_toolchange(store=self.store,
                expected_revision=self.store.rev,kind='dropoff',
                acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        with self.assertRaisesRegex(c.T0Error,'Physical carriage'):
            c.clear_automatic_fault(store=self.store,
                expected_revision=self.store.rev,acknowledgement='NO')
        result=c.clear_automatic_fault(store=self.store,
            expected_revision=self.store.rev,
            acknowledgement='I_PHYSICALLY_INSPECTED_T0_AND_PATH_AFTER_TEST_FAILURE')
        self.assertEqual(result['status'],'T0_TEST_FAULT_CLEARED_NO_MOVEMENT')
        self.assertEqual(len(self.machine.scripts),1)
        self.assertTrue(c.status(self.store)['automatic']['enabled'])

    def test_one_click_preserves_other_hotends_and_nozzle_z(self):
        self.store.data['globals']['tool_count']=6
        self.store.data['tools'][1]['dock_x']=44.0
        self.store.data['tools'][1]['dock_y']=55.0
        self.store.data['tools'][0]['offset_z']=0.75
        before=self.store.read()['config']['tools'][0].copy()
        self.machine.sensor=True
        self.machine.simulate_single_auto=True
        c.automatic_toolchange(store=self.store,expected_revision=self.store.rev,
            kind='dropoff',acknowledgement='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        self.assertEqual(self.store.read()['config']['tools'][0],before)
        self.assertEqual(self.store.read()['config']['tools'][1]['dock_x'],44.0)
        self.assertTrue(all('X44.00000' not in z for z in self.machine.scripts))
        self.assertTrue(all(' Z' not in z for z in self.machine.scripts))

    def test_t0_ready_after_cxm_service_session_reset(self):
        # Regression: service updates must not force a second G28.
        import cxm_lineux
        cxm_lineux.CXM_HOME_SESSION.update(pid=None,revision=None,at=0.0)
        status=c.status(self.store)
        self.assertTrue(status['ready'],status['blockers'])
        self.assertEqual(status['saved_xy_mm'],{'x':298.98,'y':65.88})
        self.assertEqual(self.machine.scripts,[])

    def test_t0_rejects_missing_homing_or_z20_or_power(self):
        self.machine.axes='xy'
        self.assertFalse(c.status(self.store)['ready'])
        self.machine.axes='xyz'
        self.machine.z=19.9
        self.assertFalse(c.status(self.store)['ready'])
        self.machine.z=20.0
        self.machine.enabled=False
        self.assertFalse(c.status(self.store)['ready'])
        self.machine.enabled=True
        self.assertTrue(c.status(self.store)['ready'])

    def test_saved_xy_and_xy_only_plan(self):
        s=c.status(self.store)
        self.assertTrue(s['ready'],s['blockers'])
        self.assertEqual(s['saved_xy_mm'],{'x':298.98,'y':65.88})
        p=c.plan(self.store.read())
        self.assertEqual(p['pickup'][0],(298.98,79.88))
        self.assertEqual(p['pickup'][-1],(298.98,120.0))
        self.assertEqual(p['dropoff'][-1],(298.98,120.0))

    def test_stage_moves_safe_y_before_x_without_z(self):
        r=c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
                   acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(r['status'],'SUPERVISED_T0_STAGE_COMPLETE')
        self.assertEqual(self.machine.scripts[-1].splitlines(),
            ['G90','G1 Y120.00000 F600','G1 X298.98000 F600','M400'])
        self.assertNotIn(' Z',self.machine.scripts[-1])
        self.assertEqual(c.status(self.store)['stage'],'staged')

    def test_rejects_stale_revision_and_missing_ack_without_motion(self):
        for revision,ack in [('0'*64,'I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH'),
                             (self.store.rev,'bad')]:
            with self.assertRaises(c.T0Error):
                c.motion(store=self.store,expected_revision=revision,kind='stage',
                         acknowledgement=ack)
        self.assertEqual(self.machine.scripts,[])

    def test_sensor_not_wired_blocks_pickup(self):
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        with self.assertRaisesRegex(c.T0Error,'record the carriage'):
            c.motion(store=self.store,expected_revision=self.store.rev,kind='pickup',
                     acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(len(self.machine.scripts),1)

    def test_sensor_dual_state_and_complete_pickup_dropoff(self):
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='empty',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.machine.sensor=True
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.machine.sensor=False
        self.assertTrue(c.status(self.store)['sensor_calibrated'])
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        pick=c.motion(store=self.store,expected_revision=self.store.rev,kind='pickup',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertTrue(pick['sensor_confirmed'])
        drop=c.motion(store=self.store,expected_revision=self.store.rev,kind='dropoff',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertTrue(drop['sensor_confirmed'])
        self.assertEqual(len(self.machine.scripts),3)
        self.assertTrue(all(' Z' not in script for script in self.machine.scripts))

    def test_first_supervised_dropoff_from_initially_mounted_t0(self):
        # Fresh commissioning starts with T0 actually mounted. There is no
        # physically EMPTY carriage to sample until the first dropoff.
        self.machine.sensor=True
        sample=c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.assertEqual(sample['value'],'PRESSED')
        self.assertFalse(sample['both_states_distinct'])
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertTrue(c.status(self.store)['first_dropoff_ready'])
        result=c.motion(store=self.store,expected_revision=self.store.rev,kind='dropoff',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(result['status'],
                         'SUPERVISED_T0_FIRST_DROPOFF_AWAITING_EMPTY_CONFIRMATION')
        self.assertFalse(result['sensor_confirmed'])
        self.assertEqual(self.machine.scripts[-1].splitlines(),
            ['G90','G1 X298.98000 Y65.88000 F240',
             'G1 X295.98000 Y65.88000 F180',
             'G1 X295.98000 Y79.88000 F240',
             'G1 X298.98000 Y79.88000 F240',
             'G1 X298.98000 Y120.00000 F240','M400'])
        status=c.status(self.store)
        self.assertTrue(status['first_dropoff_pending_empty'])
        self.assertFalse(status['sensor_calibrated'])
        with self.assertRaisesRegex(c.T0Error,'Verify carriage sensor EMPTY'):
            c.motion(store=self.store,expected_revision=self.store.rev,kind='pickup',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        recorded=c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='empty',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.assertEqual(recorded['value'],'RELEASED')
        self.assertTrue(recorded['both_states_distinct'])
        status=c.status(self.store)
        self.assertTrue(status['sensor_calibrated'])
        self.assertEqual(status['last_action'],'dropoff')
        self.assertFalse(status['first_dropoff_pending_empty'])
        pick=c.motion(store=self.store,expected_revision=self.store.rev,kind='pickup',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertTrue(pick['sensor_confirmed'])
        self.assertEqual(len(self.machine.scripts),3)

    def test_initial_dropoff_needs_recorded_mounted_and_stage(self):
        self.machine.sensor=True
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
            acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertFalse(c.status(self.store)['first_dropoff_ready'])
        with self.assertRaisesRegex(c.T0Error,'Select and record'):
            c.motion(store=self.store,expected_revision=self.store.rev,kind='dropoff',
                acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(len(self.machine.scripts),1)

    def test_first_dropoff_rejects_unconfirmed_empty_signal(self):
        self.machine.sensor=True
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
            acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        c.motion(store=self.store,expected_revision=self.store.rev,kind='dropoff',
            acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        # A physically false "record mounted again" attempt must not bypass
        # the pending EMPTY verification state.
        with self.assertRaisesRegex(c.T0Error,'awaits physical EMPTY'):
            c.record_sensor(store=self.store,expected_revision=self.store.rev,
                name='gcode_button carriage_t0',condition='mounted',
                acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.machine.sensor=True
        with self.assertRaisesRegex(c.T0Error,'still reports MOUNTED'):
            c.record_sensor(store=self.store,expected_revision=self.store.rev,
                name='gcode_button carriage_t0',condition='empty',
                acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        self.assertTrue(c.status(self.store)['first_dropoff_pending_empty'])
        self.assertFalse(c.status(self.store)['sensor_calibrated'])

    def test_initial_dropoff_stops_if_switch_never_changes(self):
        self.machine.sensor=True
        c.record_sensor(store=self.store,expected_revision=self.store.rev,
            name='gcode_button carriage_t0',condition='mounted',
            acknowledgement='I_CHECKED_THE_PHYSICAL_T0_SENSOR')
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
            acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        # Freeze sensor at the MOUNTED state throughout the dropoff motion.
        def frozen(path,payload=None):
            result=self.machine.rpc(path,payload)
            if path=='/printer/gcode/script':self.machine.sensor=True
            return result
        with patch.object(c,'_rpc',side_effect=frozen):
            with self.assertRaisesRegex(c.T0Error,'did not change sensor'):
                c.motion(store=self.store,expected_revision=self.store.rev,kind='dropoff',
                    acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertIsNone(c.SESSION['stage'])
        self.assertFalse(c.status(self.store)['first_dropoff_ready'])

    def test_no_pickup_from_unpowered_or_unhomed(self):
        for attr,value in [('enabled',False),('axes','xy')]:
            setattr(self.machine,attr,value)
            self.assertFalse(c.status(self.store)['ready'])
            setattr(self.machine,attr,True if attr=='enabled' else 'xyz')
        self.assertFalse(c.status(self.store)['sensor_calibrated'])

    def test_test_paths_reject_unsafe_geometry(self):
        for dx,dy in [(0,14),(-9,14),(-3,40)]:
            with self.assertRaises(c.T0Error):
                c.plan(self.store.read(),shift_x=dx,dodge_y=dy)
        self.store.data['globals']['cxm_safe_clearance_y']=33
        with self.assertRaises(c.T0Error):
            c.plan(self.store.read())

    def test_t0_test_supports_any_configured_tool_count(self):
        # T0's commanded path must not depend on the count of other slots.
        for count in (1,2,6,12):
            self.store.data['globals']['tool_count']=count
            result=c.status(self.store)
            self.assertTrue(result['ready'],result['blockers'])
            self.assertEqual(result['tool'],0)
            self.assertEqual(result['saved_xy_mm'],{'x':298.98,'y':65.88})
            self.assertEqual(c.plan(self.store.read())['stage'],[(298.98,120.0)])
        self.store.data['globals']['tool_count']=6
        outcome=c.motion(store=self.store,expected_revision=self.store.rev,
                 kind='stage',acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(outcome['status'],'SUPERVISED_T0_STAGE_COMPLETE')
        self.assertEqual(self.machine.scripts[-1].splitlines(),
            ['G90','G1 Y120.00000 F600','G1 X298.98000 F600','M400'])

    def test_tool_count_invalid_and_t0_lockout_fail_closed(self):
        for count in (0,13,True,None):
            self.store.data['globals']['tool_count']=count
            result=c.status(self.store)
            self.assertFalse(result['ready'])
            self.assertTrue(any('Invalid configured hotend count' in item
                                for item in result['blockers']))
        self.store.data['globals']['tool_count']=6
        self.store.data['tools'][0]['maintenance_lockout']=True
        self.assertFalse(c.status(self.store)['ready'])

    def test_t0_nonzero_other_tools_never_moved(self):
        self.store.data['globals']['tool_count']=6
        self.store.data['tools'][1]['dock_x']=45.0
        self.store.data['tools'][1]['dock_y']=55.0
        outcome=c.motion(store=self.store,expected_revision=self.store.rev,
                     kind='stage',
                     acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(outcome['source_dock_xy_mm'],[298.98,65.88])
        self.assertNotIn('X45.00000',self.machine.scripts[-1])
        self.assertNotIn('Y55.00000',self.machine.scripts[-1])

    def test_session_invalidated_after_pid_or_revision_changes(self):
        c.motion(store=self.store,expected_revision=self.store.rev,kind='stage',
                 acknowledgement='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH')
        self.assertEqual(c.status(self.store)['stage'],'staged')
        self.machine.pid+=1
        self.assertIsNone(c.status(self.store)['stage'])

if __name__=='__main__': unittest.main()
