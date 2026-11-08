"""Non-moving regression tests for safe Klipper object registry reuse."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_t0 as t0
from cxm_config import template
from cxm_cxchanger import plan


class KlipperRegistryCacheTests(unittest.TestCase):
    def setUp(self):
        self.saved={'config':template(),'revision':'a'*64,'migration_required':False}
        self.saved['config']['tools'][0].update(
            dock_x=306.79,dock_y=65.99,dock_reference_accepted=True)
        self.path=plan(self.saved,tool=0)
        self.objects=['toolhead','stepper_enable','idle_timeout','print_stats',
                      'virtual_sdcard','pause_resume',t0.AUTO_SENSOR]
        self.pid=12345
        self.state='ready'
        self.status={
            'toolhead':{'homed_axes':'xyz','position':[306.79,self.path['safe_y'],20.0]},
            'stepper_enable':{'steppers':{name:True for name in t0.MOTORS}},
            'idle_timeout':{'state':'Idle'},
            'print_stats':{'state':'standby'},
            'virtual_sdcard':{'is_active':False},
            'pause_resume':{'is_paused':False},
            t0.AUTO_SENSOR:{'state':'RELEASED'}}
        self.calls=[]
        def rpc(url,data=None):
            self.assertIsNone(data,'Registry verification may not issue G-code')
            self.calls.append(url)
            if url=='/printer/info':
                return {'state':self.state,'process_id':self.pid}
            if url=='/printer/objects/list':
                return {'objects':self.objects[:]}
            if url.startswith('/printer/objects/query?'):
                keys=parse_qs(urlsplit(url).query).keys()
                return {'status':{name:copy.deepcopy(self.status[name])
                                  for name in keys if name in self.status}}
            raise AssertionError('Unexpected Moonraker API '+url)
        patcher=patch.object(t0,'_rpc',side_effect=rpc)
        patcher.start()
        self.addCleanup(patcher.stop)
    def check_cached(self,known):
        return t0._safe_context(self.saved,tool=0,
                                validated_objects=known,
                                expected_pid=12345)

    def test_first_preflight_discovers_registry_and_later_preflight_uses_two_live_queries(self):
        initial=t0._safe_context(self.saved,tool=0)
        self.assertEqual(len(self.calls),3)
        self.assertEqual(self.calls[0],'/printer/info')
        self.assertEqual(self.calls[1],'/printer/objects/list')
        self.assertTrue(self.calls[2].startswith('/printer/objects/query?'))
        self.calls.clear()
        cached=self.check_cached(tuple(initial['objects']))
        self.assertEqual(cached['pid'],initial['pid'])
        self.assertEqual(cached['objects'],initial['objects'])
        self.assertEqual(cached['position'],initial['position'])
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[0],'/printer/info')
        self.assertTrue(self.calls[1].startswith('/printer/objects/query?'))
        self.assertNotIn('/printer/objects/list',self.calls)


    def test_combined_sensor_snapshot_in_same_query_as_safety_readings(self):
        self.calls.clear()
        ctx=t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(self.objects),expected_pid=self.pid,
                             sensor_name=t0.AUTO_SENSOR)
        self.assertEqual(ctx['sensor_signal'],'RELEASED')
        self.assertEqual(len(self.calls),2,'Info and one combined status; no separate sensor query')
        self.assertIn('gcode_button+cxm_tool_detect=state',self.calls[1])
        self.assertIn('toolhead=homed_axes%2Cposition',self.calls[1])
        self.assertIn('stepper_enable=steppers',self.calls[1])
        self.assertIn('idle_timeout=state',self.calls[1])
        self.status[t0.AUTO_SENSOR]['state']='PRESSED'
        ctx=t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(self.objects),expected_pid=self.pid,
                             sensor_name=t0.AUTO_SENSOR)
        self.assertEqual(ctx['sensor_signal'],'PRESSED')

    def test_combined_sensor_fails_closed_if_missing_invalid_or_unregistered(self):
        for value in (None,'UNKNOWN','',True):
            with self.subTest(value=value):
                self.status[t0.AUTO_SENSOR]={'state':value}
                with self.assertRaisesRegex(t0.T0Error,'live state unavailable'):
                    t0._safe_context(self.saved,tool=0,
                                     validated_objects=tuple(self.objects),
                                     expected_pid=self.pid,sensor_name=t0.AUTO_SENSOR)
        self.status.pop(t0.AUTO_SENSOR)
        with self.assertRaisesRegex(t0.T0Error,'live state unavailable'):
            t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(self.objects),
                             expected_pid=self.pid,sensor_name=t0.AUTO_SENSOR)
        with self.assertRaisesRegex(t0.T0Error,'presence switch unavailable'):
            t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(x for x in self.objects
                                                     if x != t0.AUTO_SENSOR),
                             expected_pid=self.pid,sensor_name=t0.AUTO_SENSOR)
        with self.assertRaisesRegex(t0.T0Error,'presence switch unavailable'):
            t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(self.objects),expected_pid=self.pid,
                             sensor_name='gcode_button wrong_sensor')

    def test_combined_sensor_still_rejects_unhomed_motors_off_and_printing(self):
        self.status[t0.AUTO_SENSOR]['state']='RELEASED'
        self.status['toolhead']['homed_axes']=''
        with self.assertRaisesRegex(t0.T0Error,'Home XYZ'):
            t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(self.objects),
                             expected_pid=self.pid,sensor_name=t0.AUTO_SENSOR)
        self.status['toolhead']['homed_axes']='xyz'
        self.status['stepper_enable']['steppers']['stepper_z3']=False
        with self.assertRaisesRegex(t0.T0Error,'four Z steppers'):
            t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(self.objects),
                             expected_pid=self.pid,sensor_name=t0.AUTO_SENSOR)
        self.status['stepper_enable']['steppers']['stepper_z3']=True
        self.status['idle_timeout']['state']='Printing'
        with self.assertRaisesRegex(t0.T0Error,'Klipper is not idle'):
            t0._safe_context(self.saved,tool=0,
                             validated_objects=tuple(self.objects),
                             expected_pid=self.pid,sensor_name=t0.AUTO_SENSOR)

    def test_cached_registry_never_used_without_matching_process_identity(self):
        with self.assertRaisesRegex(t0.T0Error,'verified process ID'):
            t0._safe_context(self.saved,validated_objects=tuple(self.objects))
        self.calls.clear()
        self.pid=54321
        with self.assertRaisesRegex(t0.T0Error,'Klipper process changed'):
            self.check_cached(tuple(self.objects))
        self.assertEqual(self.calls,['/printer/info'],
                         'Refuse stale registry before any state query')
        self.calls.clear()
        self.state='shutdown'
        with self.assertRaisesRegex(t0.T0Error,'Klipper not ready'):
            self.check_cached(tuple(self.objects))
        self.assertEqual(self.calls,['/printer/info'])

    def test_live_print_homing_z_motor_and_pause_blocks_remain_enforced(self):
        failures=[
            ('print_stats',{'state':'printing'},'active'),
            ('idle_timeout',{'state':'Printing'},'not idle'),
            ('toolhead',{'homed_axes':'xy','position':[306.79,109.99,20.0]},'Home XYZ'),
            ('toolhead',{'homed_axes':'xyz','position':[306.79,109.99,18.0]},'Home XYZ'),
            ('pause_resume',{'is_paused':True},'paused'),
            ('virtual_sdcard',{'is_active':True},'print active')]
        for name,value,expected in failures:
            with self.subTest(name=name,value=value):
                old=self.status[name]
                self.status[name]=value
                self.calls.clear()
                try:
                    with self.assertRaisesRegex(t0.T0Error,expected):
                        self.check_cached(tuple(self.objects))
                    self.assertEqual(len(self.calls),2)
                finally:
                    self.status[name]=old
        self.status['stepper_enable']['steppers']['stepper_z2']=False
        with self.assertRaisesRegex(t0.T0Error,'four Z steppers'):
            self.check_cached(tuple(self.objects))

    def test_registered_print_stats_missing_from_response_fails_closed(self):
        self.status.pop('print_stats')
        with self.assertRaisesRegex(t0.T0Error,'unknown state'):
            self.check_cached(tuple(self.objects))
        self.assertNotIn('/printer/objects/list',self.calls)

    def test_cached_registry_refuses_incomplete_or_malformed_object_list(self):
        for known in ((),('toolhead','idle_timeout'),['toolhead',False],{'toolhead':1}):
            with self.subTest(known=known):
                with self.assertRaises(t0.T0Error):
                    self.check_cached(known)

    def test_cached_post_move_idle_verification_checks_parked_position_without_discovery(self):
        self.calls.clear()
        ctx=t0._wait_for_idle_after_move(
            self.saved,parked=True,expected_pid=12345,
            tool=0,validated_objects=tuple(self.objects))
        self.assertEqual(ctx['position'][1],self.path['safe_y'])
        self.assertEqual(self.calls[0],'/printer/info')
        self.assertEqual(len(self.calls),2)
        self.assertNotIn('/printer/objects/list',self.calls)
        self.status['toolhead']['position'][0]+=1.0
        with self.assertRaisesRegex(t0.T0Error,'verified staging'):
            t0._wait_for_idle_after_move(
                self.saved,parked=True,expected_pid=12345,
                tool=0,validated_objects=tuple(self.objects))

    def test_individual_t0_path_without_cached_objects_keeps_original_live_discovery(self):
        self.calls.clear()
        ctx=t0._wait_for_idle_after_move(
            self.saved,parked=True,expected_pid=12345,tool=0)
        self.assertEqual(ctx['pid'],12345)
        self.assertEqual(len(self.calls),3)
        self.assertIn('/printer/objects/list',self.calls)


if __name__=='__main__':
    unittest.main()
