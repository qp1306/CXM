"""Selected-hotend supervised tool motion, identity, and sensor regression."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_tools as tools
import cxm_t0 as t0
from cxm_config import template
from cxm_cxchanger import plan as cx_plan

class Store:
    def __init__(self):
        self.version='a'*64
        self.data=template()
        for n,x,y in [(0,304.42,65.87),(1,267.60,65.94),(2,230.31,66.20)]:
            t=self.data['tools'][n]
            t['dock_x']=x;t['dock_y']=y;t['dock_reference_accepted']=True
    def read(self):
        return {'config':self.data,'revision':self.version,'migration_required':False}

class ToolAwareTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.signal='RELEASED'
        self.motions=[]
        tools._STATE.update(pid=None,revision=None,mounted_tool=None,fault=None,last_success=None)
        t0.AUTO_STATE.update(pid=None,revision=None,fault=None,last_success=None)
        def context(_saved, *,tool=0, require_in_park=False):
            p=cx_plan(self.store.read(),tool=tool)
            return {'pid':123,'revision':self.store.version,'tool':tool,
                    'x':p['dock_reference_xy']['x'],'y':p['dock_reference_xy']['y'],
                    'safe_y':p['safe_y'],'position':[195.,175.,20.],
                    'objects':[t0.AUTO_SENSOR]}
        def sensor(_name,_objects):
            return self.signal
        def rpc(path,payload=None):
            self.assertEqual(path,'/printer/gcode/script')
            self.motions.append(payload['script'])
            self.signal='RELEASED' if self.signal=='PRESSED' else 'PRESSED'
            return {}
        def waited(_saved,*,parked,expected_pid,tool):
            self.assertTrue(parked);self.assertEqual(expected_pid,123)
            self.assertGreater(tool,0)
            p=cx_plan(self.store.read(),tool=tool)
            return {'pid':123,'revision':self.store.version,'tool':tool,
                    'position':[p['dock_reference_xy']['x'],p['safe_y'],20.],
                    'objects':[t0.AUTO_SENSOR]}
        self.patches=[patch.object(tools,'_safe_context',side_effect=context),
                      patch.object(tools,'_sensor_value',side_effect=sensor),
                      patch.object(tools,'_rpc',side_effect=rpc),
                      patch.object(tools,'_wait_for_idle_after_move',side_effect=waited)]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
    def operation(self,tool,kind):
        return tools.automatic_toolchange(store=self.store,tool=tool,
            expected_revision=self.store.version,kind=kind,
            acknowledgement='I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR')
    def test_t1_pickup_and_dropoff_use_t1_datum_not_t0(self):
        self.assertTrue(tools.status(store=self.store,tool=1)['ready'])
        result=self.operation(1,'pickup')
        self.assertEqual(result['tool'],1)
        self.assertEqual(result['status'],'T1_PICKUP_SENSOR_CONFIRMED')
        self.assertEqual(tools.mounted_other_tool(pid=123,revision=self.store.version),1)
        self.assertIn('X267.60000',self.motions[0])
        self.assertNotIn('X304.42000',self.motions[0])
        status=tools.status(store=self.store,tool=1)
        self.assertEqual(status['automatic']['mounted_tool'],1)
        self.assertTrue(status['ready'])
        result=self.operation(1,'dropoff')
        self.assertEqual(result['status'],'T1_DROPOFF_SENSOR_CONFIRMED')
        self.assertEqual(self.signal,'RELEASED')
        self.assertIsNone(tools.mounted_other_tool(pid=123,revision=self.store.version))
        self.assertIn('X267.60000',self.motions[1])
    def test_t2_uses_own_coordinates(self):
        result=self.operation(2,'pickup')
        self.assertEqual(result['tool'],2)
        self.assertIn('X230.31000',self.motions[0])
        self.assertNotIn('X267.60000',self.motions[0])
    def test_selected_t1_with_presence_can_dropoff_without_prior_pickup(self):
        # Filament PRESENT proves occupancy only; operator selects the identity.
        self.signal='PRESSED'
        ready=tools.status(store=self.store,tool=1)
        self.assertTrue(ready['ready'])
        self.assertEqual(ready['automatic']['identity_source'],'operator_selected')
        self.assertEqual(ready['automatic']['action'],'dropoff')
        self.assertEqual(self.motions,[],'status must never move the printer')
        result=self.operation(1,'dropoff')
        self.assertEqual(result['status'],'T1_DROPOFF_SENSOR_CONFIRMED')
        self.assertEqual(result['identity_source'],'operator_selected')
        self.assertEqual(self.signal,'RELEASED')
        self.assertIn('X267.60000',self.motions[0])
        self.assertNotIn('X304.42000',self.motions[0])
        self.assertIsNone(tools.mounted_other_tool(pid=123,revision=self.store.version))

    def test_presence_only_never_bypasses_locked_or_unaccepted_tool(self):
        self.signal='PRESSED'
        self.store.data['tools'][1]['maintenance_lockout']=True
        self.assertFalse(tools.status(store=self.store,tool=1)['ready'])
        with self.assertRaises(tools.ToolError):self.operation(1,'dropoff')
        self.store.data['tools'][1]['maintenance_lockout']=False
        self.store.data['tools'][1]['dock_reference_accepted']=False
        self.assertFalse(tools.status(store=self.store,tool=1)['ready'])
        with self.assertRaises(tools.ToolError):self.operation(1,'dropoff')
        self.assertEqual(self.motions,[])
    def test_wrong_tool_and_cross_tool_dropoff_blocked_after_t1_pickup(self):
        self.operation(1,'pickup')
        self.assertFalse(tools.status(store=self.store,tool=2)['ready'])
        with self.assertRaises(tools.ToolError):
            self.operation(2,'dropoff')
        self.assertEqual(len(self.motions),1)
    def test_unaccepted_dock_and_maintenance_lockout_never_move(self):
        self.store.data['tools'][1]['dock_reference_accepted']=False
        self.assertFalse(tools.status(store=self.store,tool=1)['ready'])
        with self.assertRaises(tools.ToolError):
            self.operation(1,'pickup')
        self.store.data['tools'][1]['dock_reference_accepted']=True
        self.store.data['tools'][1]['maintenance_lockout']=True
        with self.assertRaises(tools.ToolError):
            self.operation(1,'pickup')
        self.assertEqual(self.motions,[])
    def test_t0_fault_blocks_t1_until_inspected(self):
        t0.AUTO_STATE.update(pid=123,revision=self.store.version,fault='Unresolved T0 dropoff',last_success=None)
        state=tools.status(store=self.store,tool=1)
        self.assertFalse(state['ready'])
        self.assertIn('T0 fault',state['automatic']['reason'])
        with self.assertRaisesRegex(tools.ToolError,'T0 fault'):
            self.operation(1,'pickup')
        self.assertEqual(self.motions,[])
    def test_recorded_pickup_identity_expires_on_revision_change(self):
        self.operation(1,'pickup')
        self.store.version='b'*64
        self.assertIsNone(tools.mounted_other_tool(pid=123,revision=self.store.version))
        # Selected tool remains operator-declared identity, not electrically ID'd.
        state=tools.status(store=self.store,tool=1)
        self.assertTrue(state['ready'])
        self.assertEqual(state['automatic']['identity_source'],'operator_selected')
        self.assertEqual(len(self.motions),1)
    def test_t0_path_is_blocked_while_t1_is_attached(self):
        self.operation(1,'pickup')
        ctx={'pid':123,'revision':self.store.version,'x':304.42,'safe_y':109.87,
             'position':[304.42,175.,20.],'objects':[t0.AUTO_SENSOR]}
        with patch.object(t0,'_sensor_value',return_value='PRESSED'):
            auto=t0._auto_snapshot(ctx,self.store.read())
        self.assertFalse(auto['enabled'])
        self.assertIn('T1 is mounted',auto['reason'])
    def test_missing_sensor_transition_latches_fault_and_blocks_repeat(self):
        self.signal='RELEASED'
        with patch.object(tools,'_sensor_value',return_value='RELEASED'):
            with self.assertRaisesRegex(tools.ToolError,'presence switch'):
                self.operation(1,'pickup')
        self.assertEqual(len(self.motions),1)
        self.assertIn('result uncertain',tools._STATE['fault'])
        self.assertFalse(tools.status(store=self.store,tool=1)['ready'])
    def test_config_revision_and_invalid_tool_never_move(self):
        with self.assertRaisesRegex(tools.ToolError,'configuration changed'):
            tools.automatic_toolchange(store=self.store,tool=1,kind='pickup',
                expected_revision='0'*64,
                acknowledgement='I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR')
        with self.assertRaises(tools.ToolError):
            self.operation(0,'pickup')
        self.assertEqual(self.motions,[])

if __name__=='__main__':
    unittest.main()
