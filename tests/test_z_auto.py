import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_z_auto as mod

class Store:
    def read(self):
        return {'revision':'rev1','migration_required':False,
                'config':{'globals':{'tool_count':3,'cxm_safe_clearance_y':100.0},
                          'tools':[{'dock_y':65.6,'dock_reference_accepted':True,
                                    'maintenance_lockout':False} for _ in range(3)]}}

class AutoZTests(unittest.TestCase):
    def test_math_valid_results(self):
        data={'T0':[[0.05,0.06,0.055],[0.057,0.06,0.062]],
              'T1':[[0.15,0.16,0.155],[0.158,0.16,0.162]]}
        result=mod.calculate(data)
        self.assertTrue(result['passed'])
        self.assertAlmostEqual(result['tools']['T1']['relative_to_t0_mm'],0.1)
        self.assertFalse(result['offsets_saved'])
        self.assertFalse(result['offsets_applied'])

    def test_fail_closed_on_redock_drift(self):
        result=mod.calculate({'T0':[[0.05,0.06,0.055],[0.13,0.14,0.15]]})
        self.assertFalse(result['passed'])
        self.assertGreater(result['tools']['T0']['redock_drift_mm'],0.050)

    def test_fail_closed_bad_input(self):
        for bad in ({}, {'T0':[[0.0],[0.0]]},{'T0':[[0.0,0.0,0.0],[float('nan'),0.0,0.0]]}):
            with self.assertRaises(ValueError):mod.calculate(bad)

    def test_gate_disabled_by_default(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertFalse(mod.physical_enabled())
            self.assertEqual(mod.max_commissioned_tool(),0)

    def test_runner_sequence_t0_redock_and_empty(self):
        # A complete simulated T0 sequence, with deliberately mocked hardware.
        device={'tool':0,'reading':0.0,'sample':0}
        commands=[]
        touch=[0.05,0.06,0.055,0.057,0.06,0.062]
        def native():return ({'ready':1,'fault':0,'current_tool':device['tool']},{'running':0},'RELEASED' if device['tool']==-1 else 'PRESSED')
        def obj():return {'toolhead':{'homed_axes':'xyz'},'extruder':{'target':0},'heater_bed':{'target':0},'cartographer':{'touch':{'last_z_result':device['reading']}}}
        def command(script):
            commands.append(script)
            if script=='CXM_SELECT_TOOL TOOL=-1':device['tool']=-1
            elif script=='CXM_SELECT_TOOL TOOL=0':device['tool']=0
            elif script.startswith('CXM_Z_AUTO_TOUCH'):
                device['reading']=touch[device['sample']];device['sample']+=1
        ctl=mod.Controller();ctl.busy=True
        with patch.object(mod,'_native_status',native),patch.object(mod,'_object_status',obj),patch.object(ctl,'_command',command):
            self.assertTrue(mod.MOVE_LOCK.acquire(blocking=False))
            ctl._run(Store(),1,'rev1',mode='verify_redock')
        status=ctl.status()
        self.assertEqual(status['state'],'complete',status['error'])
        self.assertFalse(status['running'])
        self.assertEqual(device['tool'],-1)
        self.assertEqual(sum(x.startswith('CXM_Z_AUTO_TOUCH') for x in commands),6)
        self.assertEqual(commands.count('CXM_SELECT_TOOL TOOL=-1'),2)
        self.assertEqual(commands.count('CXM_SELECT_TOOL TOOL=0'),1)
        self.assertTrue(status['result']['passed'])

    def test_quick_measures_three_once_and_does_not_claim_redock(self):
        device={'tool':-1,'reading':0.0,'sample':0}
        commands=[]
        touch=[0.05,0.06,0.055]
        def native():
            return ({'ready':1,'fault':0,'current_tool':device['tool']},
                    {'running':0}, 'RELEASED' if device['tool']==-1 else 'PRESSED')
        def obj():
            return {'toolhead':{'homed_axes':'xyz'},'extruder':{'target':0},
                    'heater_bed':{'target':0},'cartographer':{'touch':{'last_z_result':device['reading']}}}
        def command(script):
            commands.append(script)
            if script=='CXM_SELECT_TOOL TOOL=-1':device['tool']=-1
            elif script=='CXM_SELECT_TOOL TOOL=0':device['tool']=0
            elif script.startswith('CXM_Z_AUTO_TOUCH'):
                device['reading']=touch[device['sample']];device['sample']+=1
        ctl=mod.Controller();ctl.busy=True
        with patch.object(mod,'_native_status',native),patch.object(mod,'_object_status',obj),patch.object(ctl,'_command',command):
            self.assertTrue(mod.MOVE_LOCK.acquire(blocking=False))
            ctl._run(Store(),[0],'rev1',mode='quick')
        status=ctl.status()
        self.assertEqual(status['state'],'complete',status['error'])
        self.assertEqual(device['tool'],-1)
        self.assertEqual(sum(x.startswith('CXM_Z_AUTO_TOUCH') for x in commands),3)
        self.assertEqual(commands.count('CXM_SELECT_TOOL TOOL=0'),1)
        self.assertEqual(commands.count('CXM_SELECT_TOOL TOOL=-1'),1)
        self.assertFalse(status['result']['redock_verified'])
        self.assertIsNone(status['result']['tools']['T0']['redock_drift_mm'])
        self.assertFalse(status['result']['offsets_applied'])

    def test_noncontiguous_selected_tools(self):
        self.assertEqual(mod.selected_tools([0,5,8]),[0,5,8])
        for invalid in ([5,8],[0,0,5],[0,8,5],[0,12],[True,1],[]):
            with self.assertRaises(ValueError):mod.selected_tools(invalid)
        self.assertEqual(mod.selected_tools(3),[0,1,2])

    def test_quick_range_limit_and_full_drift_limit(self):
        good=mod.calculate({'T0':[[0.010,0.030,0.059]]},mode='quick')
        bad=mod.calculate({'T0':[[0.010,0.030,0.061]]},mode='quick')
        self.assertTrue(good['passed'])
        self.assertFalse(bad['passed'])
        self.assertIsNone(good['tools']['T0']['range_after_mm'])
        self.assertFalse(good['redock_verified'])
        drift=mod.calculate({'T0':[[0.0,0.0,0.0],[0.051,0.051,0.051]]},mode='verify_redock')
        self.assertFalse(drift['passed'])

    def test_fault_prevents_all_motion(self):
        state={'ready':1,'fault':1,'current_tool':0}
        ctl=mod.Controller();ctl.busy=True
        commands=[]
        with (patch.object(mod,'_native_status',lambda:(state,{'running':0},'PRESSED')),
              patch.object(mod,'_object_status',lambda:{'toolhead':{'homed_axes':'xyz'},'extruder':{'target':0},'heater_bed':{'target':0}}),
              patch.object(ctl,'_command',lambda x:commands.append(x))):
            self.assertTrue(mod.MOVE_LOCK.acquire(blocking=False))
            ctl._run(Store(),1,'rev1')
        self.assertEqual(commands,[])
        self.assertEqual(ctl.status()['state'],'stopped_error')

if __name__=='__main__':unittest.main()
