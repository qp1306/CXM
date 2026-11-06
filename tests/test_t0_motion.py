"""T0 XY-only commissioning protections: no physical hardware required."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_t0 as c
from cxm_config import template

class Store:
    def __init__(self):
        self.data=template()
        self.data['globals']['tool_count']=1
        self.data['globals']['safe_y']=120.0
        self.data['tools'][0]['dock_x']=298.98
        self.data['tools'][0]['dock_y']=65.88
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
        self.scripts=[]
        self.axes='xyz'
        self.enabled=True
    def rpc(self,path,payload=None):
        if path=='/printer/info':
            return {'state':'ready','process_id':self.pid}
        if path=='/printer/objects/list':
            return {'objects':['idle_timeout','toolhead','stepper_enable',
                               'gcode_button carriage_t0']}
        if path.startswith('/printer/objects/query?'):
            if 'gcode_button' in path:
                return {'status':{'gcode_button carriage_t0':
                                   {'state':'PRESSED' if self.sensor else 'RELEASED'}}}
            return {'status':{
                'idle_timeout':{'state':'Ready'},
                'toolhead':{'homed_axes':self.axes,'position':[self.x,self.y,self.z,0]},
                'stepper_enable':{'steppers':{v:self.enabled for v in c.MOTORS}},
            }}
        if path=='/printer/gcode/script':
            script=payload['script']
            self.scripts.append(script)
            for line in script.splitlines():
                if line.startswith('G1'):
                    for term in line.split()[1:]:
                        if term.startswith('X'):self.x=float(term[1:])
                        if term.startswith('Y'):self.y=float(term[1:])
            if len(self.scripts)>=2:
                self.sensor=not self.sensor
            return {}
        raise AssertionError('Unexpected request '+path)

class T0Test(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.machine=Machine()
        c.SESSION.update(pid=None,revision=None,stage=None,sensor=None,
                         samples={},last_action=None,xy=None,path=None)
        self.patch=patch.object(c,'_rpc',side_effect=self.machine.rpc)
        self.patch.start()
        self.addCleanup(self.patch.stop)

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
        with self.assertRaisesRegex(c.T0Error,'Carriage switch'):
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
        self.store.data['globals']['safe_y']=85
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
