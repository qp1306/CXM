"""Hardware-free native CXM service tests; never commands physical motion."""
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import cxm_native as native

class Store:
    def __init__(self):
        self.revision='rev1'
        self.tools=[]
        for n in range(12):
            self.tools.append({'dock_x':150.0+n*3,'dock_y':100.0,
                               'dock_reference_accepted':n<3,
                               'maintenance_lockout':False})
    def read(self):
        return {'revision':self.revision,'migration_required':False,
                'config':{'globals':{'tool_count':6,'cxm_shift_x':-3.0,
                                     'cxm_dodge_y':14.0,
                                     'cxm_safe_clearance_y':60.0},
                          'tools':self.tools}}

def mock_rpc(path, body=None, **kwargs):
    if path=='/printer/info':
        return {'state':'ready'}
    if path.startswith('/printer/objects/query?'):
        return {'status':{
            'gcode_macro _CXM_NATIVE':{'protocol':1,'ready':1,
                                      'fault':0,'current_tool':-1,
                                      'tool_count':6,'profile':'standard'},
            'gcode_macro _CXM_TEST_STATE':{'running':0,'stop':0,'index':0,'cycles':0,
                                           'completed':0,'tool_a':-1,
                                           'tool_b':-1,'tool_c':-1,'state':'idle'},
            'gcode_button cxm_tool_detect':{'state':'RELEASED'}}}
    if path=='/printer/gcode/script':
        return {'ok':True}
    raise AssertionError('unexpected RPC: '+path)

class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()

    def test_empty_sensor_allows_disk_edit_with_stale_mounted_identity(self):
        scripts=[]
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                state={'ready':0,'fault':1,'current_tool':-2} if scripts else {
                    'ready':1,'fault':0,'current_tool':0}
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,**state},
                    'gcode_macro _CXM_TEST_STATE':{'running':0},
                    'gcode_button cxm_tool_detect':{'state':'RELEASED'}}}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
                return {'ok':True}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc):
            reply=native.invalidate_for_config_edit()
        self.assertTrue(reply['needs_native_sync'])
        self.assertEqual(len(scripts),1)
        self.assertNotIn('G1 ',scripts[0])
        self.assertIn('VARIABLE=current_tool VALUE=-2',scripts[0])

    def test_empty_sensor_edit_rejects_unconfirmed_invalidation(self):
        scripts=[]
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{
                        'protocol':2,'ready':1,'fault':0,'current_tool':0},
                    'gcode_macro _CXM_TEST_STATE':{'running':0},
                    'gcode_button cxm_tool_detect':{'state':'RELEASED'}}}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
                return {'ok':True}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc):
            with self.assertRaisesRegex(native.NativeError,'invalidation not confirmed'):
                native.invalidate_for_config_edit()
        self.assertEqual(len(scripts),1)

    def test_empty_sensor_edit_rejects_running_test(self):
        with patch.object(native,'_native_status',return_value=(
            {'ready':1,'fault':0,'current_tool':0},
            {'running':1},'RELEASED')):
            with self.assertRaisesRegex(native.NativeError,'during native test'):
                native.invalidate_for_config_edit()

    def test_mounted_provisional_save_only_when_native_already_invalidated(self):
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,'ready':0,'fault':1,'current_tool':-2},
                    'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'}}}
            if path=='/printer/gcode/script':
                self.fail('Mounted provisional dock save must not send native Klipper commands')
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc), \
             patch('cxm_manual.status',return_value={'ready':True}) as preflight:
            reply=native.invalidate_for_config_edit(
                permit_mounted_provisional_dock=True,store=self.store,tool=0)
        self.assertTrue(reply['already_invalidated'])
        self.assertTrue(reply['needs_native_sync'])
        preflight.assert_called_once_with(0,self.store)

    def test_ready_mounted_selected_tool_is_invalidated_before_save(self):
        scripts=[]
        states=[
            {'ready':1,'fault':0,'current_tool':0},
            {'ready':0,'fault':1,'current_tool':-2}]
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                st=states[min(len(scripts),1)]
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,**st},
                    'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'}}}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
                return {'ok':True}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc), \
             patch('cxm_manual.status',return_value={'ready':True}):
            result=native.invalidate_for_config_edit(
                permit_mounted_provisional_dock=True,store=self.store,tool=0)
        self.assertTrue(result['previously_ready'])
        self.assertEqual(len(scripts),1)
        self.assertNotIn('G1 ',scripts[0])
        self.assertIn('VARIABLE=ready VALUE=0',scripts[0])
        self.assertIn('VARIABLE=current_tool VALUE=-2',scripts[0])

    def test_mounted_fault_latched_selected_tool_can_save_without_motion(self):
        scripts=[]
        states=[
            {'ready':1,'fault':1,'current_tool':0},
            {'ready':0,'fault':1,'current_tool':-2}]
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                st=states[min(len(scripts),1)]
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,**st},
                    'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'}}}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
                return {'ok':True}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc), \
             patch('cxm_manual.status',return_value={'ready':True}):
            reply=native.invalidate_for_config_edit(
                permit_mounted_provisional_dock=True,store=self.store,tool=0)
        self.assertTrue(reply['invalidated'])
        self.assertEqual(len(scripts),1)
        self.assertNotIn('G1 ',scripts[0])

    def test_simple_unload_initializes_unknown_mounted_tool_then_dispatches(self):
        commands=[]
        native_states=[
            {'ready':0,'fault':1,'current_tool':-2},
            {'ready':1,'fault':0,'current_tool':-1}]
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                st=native_states[min(len(commands),1)]
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,**st},
                    'gcode_macro _CXM_TEST_STATE':{'running':0},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED' if not commands else 'RELEASED'}}}
            if path=='/printer/gcode/script':
                commands.append(body['script'])
                return {}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc), \
             patch.object(native,'initialize',return_value={'ready':True}) as init:
            reply=native.simple_change(self.store,-1,'rev1',mounted_tool=0)
        init.assert_called_once_with(self.store,'rev1',0)
        self.assertEqual(commands,['CXM_SELECT_TOOL TOOL=-1'])
        self.assertTrue(reply['changed'])

    def test_simple_unload_rejects_unknown_mounted_sensor_identity_mismatch(self):
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,'ready':0,'fault':1,'current_tool':-2},
                    'gcode_macro _CXM_TEST_STATE':{'running':0},
                    'gcode_button cxm_tool_detect':{'state':'RELEASED'}}}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc):
            with self.assertRaisesRegex(native.NativeError,'sensor'):
                native.simple_change(self.store,-1,'rev1',mounted_tool=0)

    def test_ready_mounted_invalidation_must_be_confirmed(self):
        scripts=[]
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,'ready':1,'fault':0,'current_tool':0},
                    'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'}}}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
                return {'ok':True}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc), \
             patch('cxm_manual.status',return_value={'ready':True}):
            with self.assertRaisesRegex(native.NativeError,'invalidation not confirmed'):
                native.invalidate_for_config_edit(
                    permit_mounted_provisional_dock=True,store=self.store,tool=0)
        self.assertEqual(len(scripts),1)

    def test_mounted_save_rejects_native_active_or_conflicting_identity(self):
        for ready,fault,identity in ((1,0,1),(0,1,1),(1,1,1)):
            def rpc(path,body=None,**kwargs):
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,'ready':ready,'fault':fault,'current_tool':identity},
                    'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'}}}
            with patch.object(native,'_rpc',side_effect=rpc), \
                 patch('cxm_manual.status',return_value={'ready':True}):
                with self.assertRaises(native.NativeError):
                    native.invalidate_for_config_edit(
                        permit_mounted_provisional_dock=True,store=self.store,tool=0)

    def test_mounted_provisional_save_rejects_failed_manual_preflight(self):
        def rpc(path,body=None,**kwargs):
            return {'status':{
                'gcode_macro _CXM_NATIVE':{'protocol':2,'ready':0,'fault':1,'current_tool':-2},
                'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                'gcode_button cxm_tool_detect':{'state':'PRESSED'}}}
        with patch.object(native,'_rpc',side_effect=rpc), \
             patch('cxm_manual.status',side_effect=ValueError('not homed')):
            with self.assertRaisesRegex(ValueError,'not homed'):
                native.invalidate_for_config_edit(
                    permit_mounted_provisional_dock=True,store=self.store,tool=0)

    def test_calibration_release_dispatches_only_dedicated_macro(self):
        scripts=[]
        self.store.tools[0]['dock_reference_accepted']=True
        def rpc(path,body=None,**kwargs):
            if path=='/printer/info':
                return {'state':'ready'}
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,'ready':1,'fault':0,
                                              'current_tool':0},
                    'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                    'gcode_button cxm_tool_detect':{'state':'PRESSED'}}}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
                return {}
            raise AssertionError(path)
        with patch.object(native,'_rpc',side_effect=rpc):
            result=native.calibration_release(
                self.store,0,'rev1',
                'I_VERIFIED_MOUNTED_TOOL_ENGAGED_IN_CORRECT_DOCK_AND_APPROVE_RELEASE')
        self.assertEqual(result['requested_release'],0)
        self.assertEqual(scripts,['CXM_CALIBRATION_RELEASE TOOL=0 CONFIRM=1'])

    def test_calibration_release_never_moves_if_state_or_approval_wrong(self):
        scripts=[]
        def rpc(path,body=None,**kwargs):
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'gcode_macro _CXM_NATIVE':{'protocol':2,'ready':1,'fault':0,'current_tool':-1},
                    'gcode_macro _CXM_TEST_STATE':{'running':0,'state':'idle'},
                    'gcode_button cxm_tool_detect':{'state':'RELEASED'}}}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
            return {'state':'ready'}
        with patch.object(native,'_rpc',side_effect=rpc):
            with self.assertRaises(native.NativeError):
                native.calibration_release(self.store,0,'rev1','WRONG')
            with self.assertRaises(native.NativeError):
                native.calibration_release(
                    self.store,0,'rev1',
                    'I_VERIFIED_MOUNTED_TOOL_ENGAGED_IN_CORRECT_DOCK_AND_APPROVE_RELEASE')
        self.assertEqual(scripts,[])

    def test_sync_sets_all_tool_datums_and_never_moves(self):
        scripts=[]
        def rpc(path,body=None,**kw):
            if body and path=='/printer/gcode/script':
                scripts.append(body['script'])
            return mock_rpc(path,body,**kw)
        with patch.object(native,'_rpc',side_effect=rpc):
            result=native.sync(self.store,'rev1')
        self.assertTrue(result['synced'])
        self.assertEqual(result['accepted_tools'],[0,1,2])
        self.assertEqual(len(scripts),1)
        script=scripts[0]
        for command in ('VARIABLE=t0_x VALUE=150.0',
                        'VARIABLE=t1_x VALUE=153.0',
                        'VARIABLE=t2_y VALUE=100.0',
                        'VARIABLE=t3_accepted VALUE=0',
                        'VARIABLE=current_tool VALUE=-2',
                        'VARIABLE=ready VALUE=1'):
            self.assertIn(command,script)
        self.assertNotRegex(script,r'(?m)^\s*(G0|G1|G28|M400)\b')

    def test_stale_revision_fails_before_motion(self):
        with patch.object(native,'_rpc',side_effect=AssertionError('RPC must not run')):
            with self.assertRaises(native.NativeError):
                native.select(self.store,1,'stale')

    def test_native_select_sends_only_macro_name(self):
        scripts=[]
        def rpc(path,body=None,**kw):
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
            return mock_rpc(path,body,**kw)
        with patch.object(native,'_rpc',side_effect=rpc):
            native.select(self.store,2,'rev1')
        self.assertEqual(scripts,['CXM_SELECT_TOOL TOOL=2'])

    def test_cycle_uses_profile_and_macros_only(self):
        scripts=[]
        def rpc(path,body=None,**kw):
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
            return mock_rpc(path,body,**kw)
        with patch.object(native,'_rpc',side_effect=rpc):
            native.start(self.store,[0,1,2],'rev1',
                         'I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH',
                         travel_profile='standard',cycles=1)
        self.assertEqual(scripts,['CXM_SET_PROFILE PROFILE=standard\n'
                                  'CXM_TEST_START A=0 B=1 C=2 CYCLES=1'])
        with patch.object(native,'_rpc',side_effect=AssertionError('must fail preflight')):
            with self.assertRaises(native.NativeError):
                native.start(self.store,[0,1],'rev1',
                             'I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH',
                             travel_profile='boost',cycles=2)

    def test_stop_is_native_macro_request_not_gcode_motion(self):
        scripts=[]
        def rpc(path,body=None,**kw):
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
            return mock_rpc(path,body,**kw)
        with patch.object(native,'_rpc',side_effect=rpc):
            native.stop('STOP_AFTER_CURRENT_TOOL_PAIR')
        self.assertEqual(scripts,['CXM_TEST_STOP'])

    def test_macro_gate_and_fault_state_source(self):
        src=(ROOT/'vendor/cxm/cxm_native_toolchange.cfg').read_text()
        self.assertIn('variable_current_tool: -2',src)
        self.assertIn('variable_fault: 1',src)
        self.assertIn('UPDATE_DELAYED_GCODE ID=CXM_NATIVE_TEST_STEP',src)
        self.assertIn('CXM_SELECT_TOOL TOOL={t}',src)
        self.assertIn('CXM_SELECT_TOOL TOOL=-1',src)
        self.assertIn('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=1',src)
        self.assertIn('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=0',src)

if __name__=='__main__':
    unittest.main()
