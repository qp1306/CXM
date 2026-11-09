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
