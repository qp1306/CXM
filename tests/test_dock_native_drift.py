"""Read-only saved-vs-live T0–T11 Dock XY and loaded legacy guard."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_native

class Store:
    def read(self):
        return {'revision':'r1','config':{'globals':{'tool_count':3},
           'tools':[{'dock_x':325.006,'dock_y':64.9,'dock_reference_accepted':True},
                    {'dock_x':301.25,'dock_y':65.4,'dock_reference_accepted':True},
                    {'dock_x':310.0,'dock_y':66.0,'dock_reference_accepted':False}]}}

class Tests(unittest.TestCase):
    def test_legacy_loaded_source_and_t1_xy_discrepancy(self):
        calls=[]
        def rpc(path,payload=None):
            calls.append((path,payload))
            return {'status':{
              'gcode_macro _CXM_NATIVE':{
                'ready':1,'fault':0,'current_tool':-1,
                't0_x':325.006,'t0_y':64.9,'t0_accepted':1,
                't1_x':300.55,'t1_y':65.4,'t1_accepted':1,
                't2_x':-1,'t2_y':-1,'t2_accepted':0},
              'configfile':{'config':{'gcode_macro _CXM_CLEAR_TRANSFER':{
               'gcode':'{% elif (x-300.55)|abs > 0.02 %}\n'
                    ' {action_raise_error("CXM: T1 synchronized coordinates differ from the proven release point")}'}}}}}
        with patch.object(cxm_native,'_rpc',side_effect=rpc):
            result=cxm_native.dock_sync_diagnostics(Store())
        self.assertTrue(result['read_only'])
        self.assertEqual(result['loaded_transfer'],'older_proven_release_guard')
        self.assertTrue(result['tools'][0]['match'])
        self.assertFalse(result['tools'][1]['match'])
        self.assertEqual(result['tools'][1]['saved']['x'],301.25)
        self.assertEqual(result['tools'][1]['native']['x'],300.55)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1],None,'read-only; never POST to Klipper')
    def test_new_macro_no_stale_guard_and_all_native_values_match(self):
        def rpc(path,payload=None):
            return {'status':{'gcode_macro _CXM_NATIVE':{
              'ready':1,'fault':0,'current_tool':-1,
              't0_x':325.006,'t0_y':64.9,'t0_accepted':1,
              't1_x':301.25,'t1_y':65.4,'t1_accepted':1,
              't2_x':-1,'t2_y':-1,'t2_accepted':0},
              'configfile':{'config':{'gcode_macro _CXM_CLEAR_TRANSFER':{
                'gcode':'CXM_FAST_VERIFY EXPECT={expect}'}}}}}
        with patch.object(cxm_native,'_rpc',side_effect=rpc):
            result=cxm_native.dock_sync_diagnostics(Store())
        self.assertEqual(result['loaded_transfer'],'no_old_release_guard')
        self.assertTrue(result['tools'][0]['match'])
        self.assertTrue(result['tools'][1]['match'])
        self.assertFalse(result['tools'][2]['match'],
           'unsaved tools report no synced datum without claiming success')

if __name__=='__main__':unittest.main()
