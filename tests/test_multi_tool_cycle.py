"""Dry-run regressions for the CXM T0/T1/T2 mechanical multi-tool sequence."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_multi as multi
import cxm_t0 as t0
import cxm_tools as tools
from cxm_config import template
from cxm_cxchanger import plan

REV='a'*64
ACK=multi.START_ACK

class Store:
    def __init__(self):
        self.data=template()
        self.data['globals']['tool_count']=3
        for n,x,y in [(0,306.790,65.990),(1,267.190,65.680),(2,226.010,65.210)]:
            t=self.data['tools'][n]
            t.update(dock_x=x,dock_y=y,dock_reference_accepted=True,
                     maintenance_lockout=False,offset_xy_accepted=False,
                     offset_z_accepted=False)
        self.revision=REV
    def read(self):
        return {'revision':self.revision,'migration_required':False,'config':self.data}

class MultiPassTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.signal='RELEASED'
        self.position=[195.,120.,20.]
        self.sent=[]
        self.pid=888
        self.fail_kind=None
        tools._STATE.update(pid=None,revision=None,mounted_tool=None,fault=None,last_success=None)
        t0.AUTO_STATE.update(pid=None,revision=None,fault=None,last_success=None)
        with multi.RUN_LOCK:
            multi.RUN.update(running=False,run_id=None,state='idle',tools=[],total_steps=0,
                requested_cycles=1,completed_cycles=0,current_cycle=None,
                completed_steps=0,current_tool=None,current_action=None,
                last_event='',stop_requested=False,results=[],error=None)
        def context(saved,*,tool=0,**kwargs):
            p=plan(saved,tool=tool)
            return {'pid':self.pid,'revision':saved['revision'],'tool':tool,
                    'x':p['dock_reference_xy']['x'],'y':p['dock_reference_xy']['y'],
                    'safe_y':p['safe_y'],'position':list(self.position),
                    'objects':[t0.AUTO_SENSOR]}
        def rpc(url,data=None):
            self.assertEqual(url,'/printer/gcode/script')
            script=data['script']
            self.assertIn('M400',script)
            self.sent.append(script)
            if self.fail_kind!='stuck':
                self.signal='PRESSED' if self.signal=='RELEASED' else 'RELEASED'
            return {}
        def settle(saved,*,parked,expected_pid,tool):
            self.assertTrue(parked)
            self.assertEqual(expected_pid,self.pid)
            p=plan(saved,tool=tool)
            self.position=[p['dock_reference_xy']['x'],p['safe_y'],20.]
            return context(saved,tool=tool)
        def stable(_name,_objects,wanted,**kwargs):
            if self.signal!=wanted:
                raise tools.ToolError('presence switch did not stabilise at '+wanted)
            return {'signal':wanted,'samples':4,'consecutive':4}
        self.patchers=[
            patch.object(multi,'_safe_context',side_effect=context),
            patch.object(multi,'_rpc',side_effect=rpc),
            patch.object(multi,'_wait_for_idle_after_move',side_effect=settle),
            patch.object(multi,'_sensor_value',side_effect=lambda *_:self.signal),
            patch.object(multi,'_stable_sensor',side_effect=stable)
        ]
        for p in self.patchers:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patchers)])
    def start(self,tools=[0,1,2],ack=ACK,profile='standard',cycles=1):
        return multi.start(store=self.store,tools=tools,expected_revision=self.store.revision,
                           acknowledgement=ack,travel_profile=profile,cycles=cycles)
    def wait(self):
        for _ in range(500):
            if not multi.status(self.store)['running']:
                return multi.status(self.store)
            time.sleep(0.001)
        self.fail('Supervised multi-tool worker did not finish promptly')
    def test_candidates_require_accepted_dock_not_xy_z_offset_commissioning(self):
        c=multi.candidates(self.store)['candidates']
        self.assertEqual([x['tool'] for x in c if x['eligible']],[0,1,2])
        self.assertEqual(c[0]['xy']['x'],306.79)
        self.assertFalse(self.store.data['tools'][0]['offset_xy_accepted'])
        self.store.data['tools'][2]['dock_reference_accepted']=False
        c=multi.candidates(self.store)['candidates']
        self.assertFalse(c[2]['eligible'])
        self.assertIn('Dock XY',c[2]['reason'])
    def test_one_pass_uses_each_real_dock_and_finishes_empty(self):
        result=self.start()
        self.assertTrue(result['started'])
        finished=self.wait()
        self.assertEqual(finished['state'],'complete')
        self.assertEqual(finished['completed_steps'],6)
        self.assertEqual(finished['total_steps'],6)
        self.assertEqual(finished['tools'],[0,1,2])
        self.assertEqual(self.signal,'RELEASED')
        self.assertEqual(len(self.sent),6)
        for n,x in enumerate(['306.79000','267.19000','226.01000']):
            self.assertIn('X'+x,self.sent[2*n])
            self.assertIn('X'+x,self.sent[2*n+1])
        self.assertNotIn('G28',''.join(self.sent))
        self.assertNotIn('G1 Z',''.join(self.sent))
        self.assertNotIn('M104',''.join(self.sent))
        self.assertEqual([x['action'] for x in finished['results'] if 'confirmed' in x['message']],
            ['pickup','dropoff']*3)
        self.assertEqual(t0.AUTO_STATE['last_success'],'T0 dropoff')
        self.assertEqual(tools._STATE['last_success'],'T2 dropoff')
        self.assertIsNone(tools._STATE['mounted_tool'])
    def test_timing_breakdown_reports_all_wait_phases_without_changing_movement(self):
        self.start(cycles=1)
        result=self.wait()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['completed_steps'],6)
        self.assertEqual(len(self.sent),6)
        recorded=[item['message'] for item in result['results']
                  if ' confirmed (' in item['message']]
        self.assertEqual(len(recorded),6)
        for message in recorded:
            self.assertIn('preflight ',message)
            self.assertIn('G-code ',message)
            self.assertIn('idle ',message)
            self.assertIn('sensor ',message)
            self.assertIn('total ',message)
        self.assertEqual(self.signal,'RELEASED')

    def test_separate_preflight_and_idle_time_are_attributed_to_correct_phase(self):
        values=iter([100.,100.2,103.2,103.9,104.4,104.5])
        class Clock:
            def monotonic(self):
                return next(values)
        with patch.object(multi,'time',Clock()):
            result=multi._step(self.store,0,'pickup',self.store.revision,
                               self.pid,{0:plan(self.store.read(),tool=0)})
        measured=result['timing']
        self.assertEqual(measured['preflight_sec'],0.2)
        self.assertEqual(measured['gcode_sec'],3.0)
        self.assertEqual(measured['idle_check_sec'],0.7)
        self.assertEqual(measured['sensor_sec'],0.5)
        self.assertEqual(measured['record_sec'],0.1)
        self.assertEqual(result['total_sec'],4.5)
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.signal,'PRESSED')

    def test_standard_travel_remains_original_baseline(self):
        self.start(profile='standard')
        result=self.wait()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['travel_profile'],'standard')
        self.assertEqual(len(self.sent),6)
        self.assertIn('G1 Y109.99000 F600',self.sent[0])
        self.assertNotIn('F1800',self.sent[0])
        self.assertIn('G1 X306.79000 Y65.99000 F180',self.sent[0])

    def test_opt_in_faster_transfer_uses_correct_t0_t1_t2_and_slow_latch(self):
        self.start(profile='faster')
        result=self.wait()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['travel_profile'],'faster')
        self.assertEqual(result['completed_steps'],6)
        self.assertEqual(self.signal,'RELEASED')
        self.assertEqual(len(self.sent),6)
        for n,x in enumerate(['306.79000','267.19000','226.01000']):
            pickup,dropoff=self.sent[n*2:n*2+2]
            self.assertIn('F1800',pickup)
            self.assertIn('F1800',dropoff)
            self.assertIn('X'+x,pickup)
            self.assertIn('X'+x,dropoff)
            self.assertIn('F180',pickup)
            self.assertIn('F180',dropoff)
            self.assertIn('F240',pickup)
            self.assertIn('F240',dropoff)
            self.assertNotIn('G1 Z',pickup+dropoff)
        complete=[x['message'] for x in result['results'] if 'confirmed' in x['message']]
        self.assertEqual(len(complete),6)
        self.assertTrue(all(' s' in event for event in complete),
                        'Report measured step duration for later speed comparison')

    def test_unknown_speed_is_rejected_without_motion(self):
        for profile in ('turbo','extreme','',None,45):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(multi.MultiToolError,'Invalid travel profile'):
                    self.start(profile=profile)
        self.assertEqual(self.sent,[])


    def test_three_complete_cycles_repeat_every_tool_and_finish_empty(self):
        reply=self.start(cycles=3)
        self.assertEqual(reply['cycles'],3)
        self.assertEqual(reply['total_steps'],18)
        result=self.wait()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['requested_cycles'],3)
        self.assertEqual(result['completed_cycles'],3)
        self.assertEqual(result['current_cycle'],3)
        self.assertEqual(result['completed_steps'],18)
        self.assertEqual(result['total_steps'],18)
        self.assertEqual(len(self.sent),18)
        self.assertEqual(self.signal,'RELEASED')
        for cycle in range(3):
            for n,x in enumerate(('306.79000','267.19000','226.01000')):
                pickup=self.sent[6*cycle+2*n]
                dropoff=self.sent[6*cycle+2*n+1]
                self.assertIn('X'+x,pickup)
                self.assertIn('X'+x,dropoff)
        self.assertTrue(any('Cycle 2/3' in e['message'] for e in result['results']))
        self.assertTrue(any('Cycle 3/3' in e['message'] for e in result['results']))

    def test_repetition_rechecks_empty_klipper_state_before_second_cycle(self):
        original=multi._verify_between_cycles
        checkpoints=[]
        def checked(store,prepared,selected):
            checkpoints.append((self.signal,tuple(self.position),prepared['revision']))
            return original(store,prepared,selected)
        with patch.object(multi,'_verify_between_cycles',side_effect=checked):
            self.start(cycles=3)
            result=self.wait()
        self.assertEqual(result['state'],'complete')
        self.assertEqual(len(checkpoints),2)
        self.assertTrue(all(x[0]=='RELEASED' for x in checkpoints))
        self.assertEqual(result['completed_cycles'],3)

    def test_stop_requested_in_second_cycle_finishes_current_pair_only(self):
        def rpc(url,payload):
            self.sent.append(payload['script'])
            self.signal='PRESSED' if self.signal=='RELEASED' else 'RELEASED'
            if len(self.sent)==9:  # Cycle 2 T1 pickup; complete T1 dropoff
                self.assertTrue(multi.stop(acknowledgement=multi.STOP_ACK)['stop_requested'])
        with patch.object(multi,'_rpc',side_effect=rpc):
            self.start(cycles=5)
            result=self.wait()
        self.assertEqual(result['state'],'stopped')
        self.assertEqual(result['requested_cycles'],5)
        self.assertEqual(result['completed_cycles'],1)
        self.assertEqual(result['current_cycle'],2)
        self.assertEqual(result['completed_steps'],10)
        self.assertEqual(len(self.sent),10)
        self.assertEqual(self.signal,'RELEASED')
        self.assertEqual(result['total_steps'],30)

    def test_stop_after_last_tool_counts_the_finished_cycle(self):
        def rpc(url,payload):
            self.sent.append(payload['script'])
            self.signal='PRESSED' if self.signal=='RELEASED' else 'RELEASED'
            if len(self.sent)==6:
                multi.stop(acknowledgement=multi.STOP_ACK)
        with patch.object(multi,'_rpc',side_effect=rpc):
            self.start(cycles=4)
            result=self.wait()
        self.assertEqual(result['state'],'stopped')
        self.assertEqual(result['completed_cycles'],1)
        self.assertEqual(result['completed_steps'],6)
        self.assertEqual(len(self.sent),6)
        self.assertEqual(self.signal,'RELEASED')

    def test_sensor_failure_in_later_cycle_prevents_all_remaining_motion(self):
        def rpc(url,payload):
            self.sent.append(payload['script'])
            if len(self.sent)!=7:  # T0 pickup, second cycle fails to become PRESSED
                self.signal='PRESSED' if self.signal=='RELEASED' else 'RELEASED'
        with patch.object(multi,'_rpc',side_effect=rpc):
            self.start(cycles=5)
            result=self.wait()
        self.assertEqual(result['state'],'failed')
        self.assertEqual(result['completed_cycles'],1)
        self.assertEqual(result['completed_steps'],6)
        self.assertEqual(len(self.sent),7)
        self.assertIn('T0 pickup result uncertain',t0.AUTO_STATE['fault'])
        self.assertEqual(self.signal,'RELEASED')

    def test_invalid_repeat_counts_and_maximum_total_movement_cap_fail_before_motion(self):
        for count in (0,-1,21,True,False,2.5,'4',None):
            with self.subTest(count=count):
                with self.assertRaisesRegex(multi.MultiToolError,'whole number'):
                    self.start(cycles=count)
        self.store.data['globals']['tool_count']=12
        with self.assertRaisesRegex(multi.MultiToolError,'240-movement'):
            self.start(tools=list(range(12)),cycles=11)
        self.assertEqual(self.sent,[])

    def test_default_one_pass_and_new_manual_run_require_separate_start(self):
        self.start()
        first=self.wait()
        self.assertEqual(first['completed_steps'],6)
        self.assertEqual(first['requested_cycles'],1)
        self.assertEqual(len(self.sent),6)
        # Another pass is not automatic: a new explicit start is required.
        self.assertFalse(first['running'])
        self.start(cycles=2)
        second=self.wait()
        self.assertEqual(second['completed_steps'],12)
        self.assertEqual(second['completed_cycles'],2)
        self.assertEqual(len(self.sent),18)
        self.assertEqual(self.signal,'RELEASED')

    def test_initial_mounted_carriage_is_blocked_before_any_motion(self):
        self.signal='PRESSED'
        with self.assertRaisesRegex(multi.MultiToolError,'FILAMENT PRESENT'):
            self.start()
        self.assertEqual(len(self.sent),0)
        self.assertFalse(multi.status(self.store)['running'])
    def test_uncalibrated_selected_dock_blocks_entire_pass_before_t0(self):
        self.store.data['tools'][2]['dock_reference_accepted']=False
        with self.assertRaisesRegex(multi.MultiToolError,'T2 requires accepted'):
            self.start()
        self.assertEqual(self.sent,[])
    def test_dock_y_spread_over_one_mm_blocks_cross_dock_transfer(self):
        self.store.data['tools'][2]['dock_y']=70.0
        with self.assertRaisesRegex(multi.MultiToolError,'safe-Y staging lines'):
            self.start()
        self.assertEqual(self.sent,[])

    def test_missing_z_or_xy_offset_acceptance_does_not_mislabel_print_ready(self):
        out=multi.status(self.store)
        self.assertIn('not full tool commissioning',out['note'])
        self.assertEqual(len([t for t in out['candidates'] if t['eligible']]),3)
    def test_disallow_bad_selection_duplicate_stale_revision_and_wrong_ack(self):
        for selection in ([0],[1,1],[2,1],[0,3],[0,'1'],[0,1,2,3]):
            with self.subTest(selection=selection):
                with self.assertRaises(multi.MultiToolError):self.start(tools=selection)
        with self.assertRaisesRegex(multi.MultiToolError,'Confirm'):
            self.start(tools=[0,1],ack='WRONG')
        with self.assertRaisesRegex(multi.MultiToolError,'Configuration changed'):
            multi.start(store=self.store,tools=[0,1],expected_revision='b'*64,
                        acknowledgement=ACK)
        self.assertEqual(self.sent,[])
    def test_failed_t0_pickup_never_attempts_dropoff_or_t1(self):
        self.fail_kind='stuck'
        self.start()
        state=self.wait()
        self.assertEqual(state['state'],'failed')
        self.assertEqual(len(self.sent),1)
        self.assertEqual(state['completed_steps'],0)
        self.assertIn('T0 pickup result uncertain: multi-tool pass',t0.AUTO_STATE['fault'])
        self.assertEqual(self.signal,'RELEASED')
        with self.assertRaisesRegex(multi.MultiToolError,'T0 fault'):
            self.start()
    def test_failure_on_t1_pickup_stops_without_t1_dropoff_or_t2(self):
        original=multi._rpc
        def rpc(url,payload):
            # T0 pair succeeds, T1 pickup is dispatched but sensor never flips.
            self.sent.append(payload['script'])
            if len(self.sent)!=3:
                self.signal='PRESSED' if self.signal=='RELEASED' else 'RELEASED'
        with patch.object(multi,'_rpc',side_effect=rpc):
            self.start()
            result=self.wait()
        self.assertEqual(result['state'],'failed')
        self.assertEqual(result['completed_steps'],2)
        self.assertEqual(len(self.sent),3)
        self.assertIn('T1 pickup result uncertain: multi-tool pass',tools._STATE['fault'])
    def test_stop_after_t0_pickup_still_finishes_t0_dropoff(self):
        def rpc(url,payload):
            self.sent.append(payload['script'])
            self.signal='PRESSED' if self.signal=='RELEASED' else 'RELEASED'
            if len(self.sent)==1:
                answer=multi.stop(acknowledgement=multi.STOP_ACK)
                self.assertTrue(answer['stop_requested'])
        with patch.object(multi,'_rpc',side_effect=rpc):
            self.start()
            result=self.wait()
        self.assertEqual(result['state'],'stopped')
        self.assertEqual(result['completed_steps'],2)
        self.assertEqual(len(self.sent),2)
        self.assertEqual(self.signal,'RELEASED')
    def test_shared_motion_lock_blocks_concurrent_start(self):
        self.assertTrue(multi.MOVE_LOCK.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(multi.MultiToolError,'Another CXM'):
                self.start()
            self.assertEqual(self.sent,[])
        finally:
            multi.MOVE_LOCK.release()
    def test_t1_latched_fault_blocks_batch(self):
        tools._STATE.update(pid=self.pid,revision=self.store.revision,
                            mounted_tool=None,fault='T1 requires inspection',
                            last_success=None)
        with self.assertRaisesRegex(multi.MultiToolError,'T1\\+ tool fault'):
            self.start()
        self.assertEqual(self.sent,[])
    def test_stop_when_idle_does_not_move(self):
        self.assertFalse(multi.stop(acknowledgement=multi.STOP_ACK)['stop_requested'])
        with self.assertRaises(multi.MultiToolError):
            multi.stop(acknowledgement='bad')
        self.assertEqual(self.sent,[])

if __name__=='__main__':
    unittest.main()
