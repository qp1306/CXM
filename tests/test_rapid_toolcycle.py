"""Regression tests for opt-in CXM rapid Klipper-local mechanical mode."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))

import cxm_rapid as rapid
import cxm_multi as multi
from cxm_cxchanger import plan
from cxm_config import template

class Store:
    def __init__(self):
        self.config=template()
        self.config['globals']['tool_count']=3
        for n,x,y in [(0,306.79,65.99),(1,267.19,65.68),(2,226.01,65.21)]:
            self.config['tools'][n].update(
                dock_x=x,dock_y=y,dock_reference_accepted=True,
                maintenance_lockout=False)
        self.revision='f'*64
    def read(self):
        return {'config':self.config,'revision':self.revision,
                'migration_required':False}

class RapidPairTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        saved=self.store.read()
        self.paths={n:plan(saved,tool=n) for n in range(3)}

    def test_each_tool_pair_is_native_and_exact_known_dock_geometry(self):
        for tool,dx in [(0,'306.79000'),(1,'267.19000'),(2,'226.01000')]:
            with self.subTest(tool=tool):
                script=rapid.pair_script(self.paths,tool,'standard')
                lines=script.splitlines()
                self.assertEqual(lines[0],'G90')
                self.assertIn('CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y=',lines[1])
                self.assertTrue(lines[2].startswith('G1 Y'))
                self.assertEqual(lines[3],'G1 X'+dx+' F600')
                self.assertNotIn('G28',script)
                self.assertNotIn('G1 Z',script)
                self.assertNotIn('M104',script)
                self.assertNotIn('G1 E',script)
                self.assertIn('X'+dx,script)
                self.assertIn('G1 X'+dx+' Y65.',script) if tool==0 else None
                self.assertEqual(sum(x.startswith('CXM_FAST_VERIFY EXPECT=PRESSED')
                                     for x in lines),4)
                # 1 before stage, 1 after stage, 4 after release
                self.assertEqual(sum(x.startswith('CXM_FAST_VERIFY EXPECT=RELEASED')
                                     for x in lines),6)
                self.assertEqual(lines[-1],rapid._verify(
                    'RELEASED',x=self.paths[tool]['dock_reference_xy']['x'],
                    y=self.paths[tool]['safe_y']))

    def test_four_samples_are_separated_by_executed_dwell_not_queued_dwell(self):
        lines=rapid.pair_script(self.paths,1).splitlines()
        for state in ('PRESSED','RELEASED'):
            indices=[i for i,x in enumerate(lines)
                     if x.startswith('CXM_FAST_VERIFY EXPECT='+state)]
            if state=='PRESSED':self.assertEqual(len(indices),4)
            else:indices=indices[-4:]
            self.assertEqual(len(indices),4)
            for i in indices[1:]:
                self.assertEqual(lines[i-1],'M400')
                self.assertEqual(lines[i-2],'G4 P80')
        # Both pre-verification settle periods include a mandatory M400.
        self.assertEqual(lines.count('G4 P150'),2)
        self.assertEqual(lines.count('G4 P80'),6)

    def test_faster_only_uses_original_clearance_profile_and_slow_latch(self):
        s=rapid.pair_script(self.paths,2,'faster')
        self.assertIn('F1800',s)
        self.assertIn('F240',s)
        self.assertIn('F180',s)
        self.assertEqual(s.count('CXM_FAST_VERIFY EXPECT=PRESSED'),4)
        self.assertEqual(s.count('CXM_FAST_VERIFY EXPECT=RELEASED'),6)
        self.assertNotIn('G28',s)
        self.assertNotIn('G1 Z',s)

    def test_reject_bad_inputs_without_any_motion(self):
        for tool in (-1,3,True,0.3,'T0'):
            with self.subTest(tool=tool):
                with self.assertRaises(ValueError):rapid.pair_script(self.paths,tool)
        with self.assertRaises(ValueError):rapid.pair_script(self.paths,0,'turbo')
        with self.assertRaises(ValueError):rapid.pair_script({0:self.paths[0]},0)

    def test_backend_refuses_uninstalled_and_wrong_protocol_before_motion(self):
        # Unit mock exercises the guarded preflight; all independent
        # conventional mandatory safety checks still execute.
        ctx={'pid':123,'objects':['gcode_button cxm_tool_detect'],
             'position':[195,120,20]}
        with (patch.object(multi,'_validate_selection',return_value=self.paths),
              patch.object(multi,'_safe_context',return_value=ctx),
              patch.object(multi,'_check_no_pending_fault'),
              patch.object(multi,'_sensor_value',return_value='RELEASED'),
              patch.object(multi,'_stable_sensor',return_value={'signal':'RELEASED'})):
            with self.assertRaisesRegex(multi.MultiToolError,'install the native'):
                multi._prepare(self.store,[0,1,2],self.store.revision,'rapid')
            ctx['objects'].append('gcode_macro CXM_FAST_VERIFY')
            with patch.object(multi,'_rpc',return_value={
                    'status':{'gcode_macro CXM_FAST_VERIFY':{
                        'cxm_rapid_protocol':2}}}):
                with self.assertRaisesRegex(multi.MultiToolError,'version mismatch'):
                    multi._prepare(self.store,[0,1,2],self.store.revision,'rapid')

    def test_pair_rechecks_process_sends_single_script_and_no_extra_sensor_rpc(self):
        sent=[]
        def rpc(path,payload=None):
            if path=='/printer/info':return {'state':'ready','process_id':123}
            self.assertEqual(path,'/printer/gcode/script')
            self.assertIsNotNone(payload)
            sent.append(payload['script'])
            return {}
        with (patch.object(multi,'_rpc',side_effect=rpc),
              patch.object(multi,'_mark_tool') as marker):
            result=multi._rapid_pair(self.store,1,self.store.revision,123,
                                     self.paths,'standard')
        self.assertEqual(result['signal'],'RELEASED')
        self.assertEqual(len(sent),1)
        self.assertIn('CXM_FAST_VERIFY',sent[0])
        marker.assert_called_once()

    def test_failed_or_ambiguous_native_script_never_marks_docked_or_retries(self):
        sent=[]
        def rpc(path,payload=None):
            if path=='/printer/info':return {'state':'ready','process_id':123}
            sent.append(payload['script'])
            raise RuntimeError('Klipper sensor gate failed')
        with (patch.object(multi,'_rpc',side_effect=rpc),
              patch.object(multi,'_mark_tool') as marker):
            with self.assertRaisesRegex(RuntimeError,'sensor gate failed'):
                multi._rapid_pair(self.store,1,self.store.revision,123,
                                  self.paths,'standard')
        self.assertEqual(len(sent),1)
        marker.assert_not_called()

    def test_not_active_klipper_process_rejected_before_script(self):
        with patch.object(multi,'_rpc',return_value={'state':'ready',
                                                    'process_id':999}) as rpc:
            with self.assertRaisesRegex(multi.MultiToolError,'restarted'):
                multi._rapid_pair(self.store,0,self.store.revision,123,
                                  self.paths,'standard')
            rpc.assert_called_once_with('/printer/info')

if __name__=='__main__': unittest.main()
