"""Uninterrupted CXM Klipper stream: safety-critical no-motion tests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_multi as multi
import cxm_rapid as rapid
from cxm_cxchanger import plan
from cxm_config import template
from cxm_t0 import AUTO_STATE
from cxm_tools import _STATE as TOOL_STATE


class Store:
    def __init__(self):
        self.cfg=template()
        self.cfg['globals']['tool_count']=4
        for n,x,y in [(0,306.79,65.99),(1,267.19,65.68),
                      (2,226.01,65.21),(3,186.0,65.0)]:
            self.cfg['tools'][n].update(dock_x=x,dock_y=y,
                                        dock_reference_accepted=True)
        self.revision='f'*64
    def read(self):
        return {'config':self.cfg,'revision':self.revision,
                'migration_required':False}


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.paths={n:plan(self.store.read(),tool=n) for n in range(4)}
        self.prepared={'pid':123,'revision':self.store.revision,
                       'paths':self.paths,'verified_signal':'RELEASED',
                       'validated_objects':('gcode_button cxm_tool_detect',)}
        with multi.RUN_LOCK:
            multi.RUN.update(running=False,execution_mode='legacy',
                             state='idle',stop_requested=False,
                             results=[],error=None,completed_steps=0,
                             completed_cycles=0,tools=[])
        with multi.SESSION_LOCK:
            AUTO_STATE.update(pid=None,revision=None,fault=None)
        with multi.TOOL_STATE_LOCK:
            TOOL_STATE.update(pid=None,revision=None,fault=None,mounted_tool=None)

    def test_concatenated_gcode_retains_every_gate_and_complete_tool_path(self):
        for tools in ([0,1],[0,1,2]):
            with self.subTest(tools=tools):
                paths={n:self.paths[n] for n in tools}
                code=rapid.stream_script(paths,list(tools),'race')
                baseline='\n'.join(rapid.pair_script(paths,n,'race') for n in tools)
                self.assertEqual(code,baseline,
                    'Uninterrupted mode cannot modify validated XY geometry')
                self.assertEqual(code.count('CXM_FAST_VERIFY EXPECT=PRESSED'),4*len(tools))
                self.assertEqual(code.count('CXM_FAST_VERIFY EXPECT=RELEASED'),6*len(tools))
                self.assertEqual(code.count('G4 P80'),6*len(tools))
                self.assertEqual(code.count('G4 P150'),2*len(tools))
                self.assertEqual(code.count('G90'),len(tools))
                self.assertNotIn('G1 Z',code)
                self.assertNotIn('G28',code)
                self.assertNotIn('G1 E',code)
                self.assertNotIn('M104',code)

    def test_stream_rejects_missing_paths_duplicates_unsorted_and_four_tools(self):
        for tools in ([0],[0,1,2,3],[1,0],[0,0],
                      [0,9],[True,1],['0',1]):
            with self.subTest(tools=tools):
                with self.assertRaises(ValueError):
                    rapid.stream_script(self.paths,list(tools),'race')
        with self.assertRaises(ValueError):
            rapid.stream_script({0:self.paths[0]},[0,1])
        with self.assertRaises(ValueError):
            rapid.stream_script({0:self.paths[0],1:self.paths[1]},[0,1],'unsafe')

    def test_native_stream_is_exactly_one_script_request_for_all_tools(self):
        calls=[]
        def rpc(path,payload=None,**kwargs):
            calls.append((path,payload,kwargs))
            if path=='/printer/info':
                self.assertEqual(kwargs,{})
                return {'state':'ready','process_id':123}
            self.assertEqual(path,'/printer/gcode/script')
            self.assertEqual(kwargs,{'timeout_s':multi.STREAM_READ_TIMEOUT_S})
            return {}
        chosen=[0,1,2]
        self.prepared['paths']={n:self.paths[n] for n in chosen}
        with (patch.object(multi,'_rpc',side_effect=rpc),
              patch.object(multi,'_mark_tool') as mark):
            result=multi._stream_run(self.store,chosen,self.prepared,'race')
        self.assertEqual(len(calls),2)
        self.assertEqual([c[0] for c in calls],
                         ['/printer/info','/printer/gcode/script'])
        self.assertEqual(calls[1][1]['script'],
                         rapid.stream_script(self.prepared['paths'],chosen,'race'))
        self.assertEqual(mark.call_count,3)
        self.assertEqual(result['signal'],'RELEASED')

    def test_unexpected_process_change_prevents_dispatch(self):
        with patch.object(multi,'_rpc',return_value={'state':'ready','process_id':124}) as rpc:
            with self.assertRaisesRegex(multi.MultiToolError,'restarted'):
                multi._stream_run(self.store,[0,1],self.prepared,'race')
            rpc.assert_called_once_with('/printer/info')

    def _setup_run(self,selected):
        with multi.RUN_LOCK:
            multi.RUN.update(running=True,execution_mode='stream',
                             state='running',stop_requested=False,
                             requested_cycles=1,completed_cycles=0,
                             current_cycle=None,completed_steps=0,
                             results=[],error=None,tools=list(selected))
        self.assertTrue(multi.MOVE_LOCK.acquire(blocking=False))

    def test_success_marks_steps_only_after_whole_script_returns(self):
        self._setup_run([0,1])
        def running(*args):
            self.assertEqual(multi.RUN['completed_steps'],0)
            return {'duration_sec':4.25,'signal':'RELEASED'}
        with patch.object(multi,'_stream_run',side_effect=running) as done:
            multi._worker(self.store,[0,1],self.prepared,'race',1,'stream')
        self.assertEqual(done.call_count,1)
        self.assertEqual(multi.RUN['completed_steps'],4)
        self.assertEqual(multi.RUN['completed_cycles'],1)
        self.assertEqual(multi.RUN['state'],'complete')
        self.assertFalse(multi.RUN['running'])
        self.assertFalse(multi.MOVE_LOCK.locked())

    def test_failed_stream_latches_global_uncertain_identity_and_no_false_progress(self):
        self._setup_run([0,1,2])
        with patch.object(multi,'_stream_run',
                          side_effect=RuntimeError('Native carriage mismatch')) as done:
            multi._worker(self.store,[0,1,2],self.prepared,'race',1,'stream')
        self.assertEqual(done.call_count,1)
        self.assertEqual(multi.RUN['completed_steps'],0)
        self.assertEqual(multi.RUN['state'],'failed')
        self.assertIn('ALL selected docks',multi.RUN['error'])
        self.assertIn('Uninterrupted',AUTO_STATE['fault'])
        self.assertIn('Uninterrupted',TOOL_STATE['fault'])
        self.assertFalse(multi.MOVE_LOCK.locked())

    def test_stop_api_does_not_falsely_claim_it_can_stop_queued_stream(self):
        with multi.RUN_LOCK:
            multi.RUN.update(running=True,execution_mode='stream',
                             stop_requested=False)
        stop=multi.stop(acknowledgement=multi.STOP_ACK)
        self.assertFalse(stop['stop_requested'])
        self.assertTrue(stop['emergency_stop_required'])
        self.assertFalse(multi.RUN['stop_requested'])

    def test_reject_extra_cycles_or_four_tools_without_touching_motion_lock(self):
        for tools,cycles in [([0,1],2),([0,1,2,3],1)]:
            with self.subTest(tools=tools,cycles=cycles):
                with self.assertRaisesRegex(multi.MultiToolError,
                                            'Uninterrupted stream'):
                    multi.start(store=self.store,tools=tools,
                                expected_revision=self.store.revision,
                                acknowledgement=multi.START_ACK,
                                execution_mode='stream',travel_profile='race',
                                cycles=cycles)
                self.assertFalse(multi.MOVE_LOCK.locked())

if __name__=='__main__':unittest.main()
