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
        tools._STATE.update(pid=None,revision=None,mounted_tool=None,identity_source=None,fault=None,last_success=None)
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
            acknowledgement='I_CONFIRMED_SELECTED_TOOL_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
    def confirm(self,tool=1,acknowledgement='I_IDENTIFIED_SELECTED_HOTEND_MOUNTED_EMPTY_DOCK_HOMED_XY_NOT_HAND_MOVED'):
        return tools.confirm_mounted_for_first_dropoff(
            store=self.store,tool=tool,expected_revision=self.store.version,
            acknowledgement=acknowledgement)

    def test_initial_t1_mount_can_be_operator_confirmed_without_motion(self):
        self.signal='PRESSED'
        before=tools.status(store=self.store,tool=1)
        self.assertFalse(before['ready'])
        self.assertTrue(before['automatic']['can_confirm_mounted'])
        self.assertIsNone(before['automatic']['mounted_tool'])
        with self.assertRaisesRegex(tools.ToolError,'not verified'):
            self.operation(1,'dropoff')
        result=self.confirm(1)
        self.assertEqual(result['status'],'T1_MOUNTED_OPERATOR_CONFIRMED_NO_MOVEMENT')
        self.assertEqual(self.motions,[],'Identity confirmation MUST issue no G-code')
        state=tools.status(store=self.store,tool=1)
        self.assertTrue(state['ready'])
        self.assertEqual(state['automatic']['mounted_tool'],1)
        self.assertEqual(state['automatic']['identity_source'],'operator_confirmed')
        result=self.operation(1,'dropoff')
        self.assertEqual(result['status'],'T1_DROPOFF_SENSOR_CONFIRMED')
        self.assertEqual(result['signal'],'RELEASED')
        self.assertEqual(len(self.motions),1)
        self.assertIn('X267.60000',self.motions[0])
        self.assertNotIn('X304.42000',self.motions[0])
        self.assertIsNone(tools.mounted_other_tool(pid=123,revision=self.store.version))

    def test_initial_confirmation_fails_closed_on_wrong_ack_revision_or_signal(self):
        self.signal='PRESSED'
        with self.assertRaisesRegex(tools.ToolError,'Physically identify'):
            self.confirm(1,acknowledgement='INVALID')
        with self.assertRaisesRegex(tools.ToolError,'configuration changed'):
            tools.confirm_mounted_for_first_dropoff(store=self.store,tool=1,
                expected_revision='0'*64,
                acknowledgement='I_IDENTIFIED_SELECTED_HOTEND_MOUNTED_EMPTY_DOCK_HOMED_XY_NOT_HAND_MOVED')
        self.signal='RELEASED'
        with self.assertRaisesRegex(tools.ToolError,'Cannot confirm'):
            self.confirm(1)
        self.assertIsNone(tools.mounted_other_tool(pid=123,revision=self.store.version))
        self.assertEqual(self.motions,[])

    def test_initial_confirmation_rejects_prior_t0_fault_or_wrong_selected_tool(self):
        self.signal='PRESSED'
        t0.AUTO_STATE.update(pid=123,revision=self.store.version,
                             fault='T0 dropoff failed',last_success=None)
        self.assertFalse(tools.status(store=self.store,tool=1)['automatic']['can_confirm_mounted'])
        with self.assertRaisesRegex(tools.ToolError,'T0 fault'):
            self.confirm(1)
        t0.AUTO_STATE['fault']=None
        self.confirm(1)
        with self.assertRaisesRegex(tools.ToolError,'T1 is still recorded as mounted'):
            self.confirm(2)
        self.assertEqual(self.motions,[])

    def test_operator_identity_expires_after_config_revision_change(self):
        self.signal='PRESSED'
        self.confirm(1)
        self.store.version='b'*64
        state=tools.status(store=self.store,tool=1)
        self.assertFalse(state['ready'])
        self.assertTrue(state['automatic']['can_confirm_mounted'])
        self.assertIsNone(state['automatic']['identity_source'])
        self.assertEqual(self.motions,[])

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
    def test_unknown_pressed_identity_blocks_all_other_docks(self):
        self.signal='PRESSED'
        for tool in (1,2):
            self.assertFalse(tools.status(store=self.store,tool=tool)['ready'])
            with self.assertRaisesRegex(tools.ToolError,'not verified'):
                self.operation(tool,'dropoff')
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
    def test_mount_identity_invalidates_on_revision_change(self):
        self.operation(1,'pickup')
        self.store.version='b'*64
        self.assertIsNone(tools.mounted_other_tool(pid=123,revision=self.store.version))
        self.assertFalse(tools.status(store=self.store,tool=1)['ready'])
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
                acknowledgement='I_CONFIRMED_SELECTED_TOOL_XY_PATH_CLEAR_AND_WILL_SUPERVISE')
        with self.assertRaises(tools.ToolError):
            self.operation(0,'pickup')
        self.assertEqual(self.motions,[])

if __name__=='__main__':
    unittest.main()
