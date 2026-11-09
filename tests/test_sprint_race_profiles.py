"""CXM graduated high-speed XY toolchange motion, no hardware or motion."""
import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from cxm_config import template
from cxm_cxchanger import (
    plan, performance_cycle_script, faster_cycle_script,
    sprint_cycle_script, race_cycle_script)
from cxm_rapid import pair_script
import cxm_multi as multi


class SprintRaceTests(unittest.TestCase):
    def setUp(self):
        self.saved={'config':template()}
        self.saved['config']['globals']['tool_count']=3
        for n,x,y in ((0,306.79,65.99),(1,267.19,65.68),(2,226.01,65.21)):
            self.saved['config']['tools'][n].update(
                dock_x=x,dock_y=y,dock_reference_accepted=True)
        self.paths={n:plan(self.saved,tool=n) for n in range(3)}

    def test_stage_feeds_and_same_proven_geometry(self):
        variants=[('sprint',sprint_cycle_script,{12000,2400,600}),
                  ('race',race_cycle_script,{24000,4800,1200})]
        for mode,make,allowed in variants:
            for n,p in self.paths.items():
                for kind in ('pickup','dropoff'):
                    with self.subTest(mode=mode,tool=n,kind=kind):
                        lines=make(p,kind,at_stage=False).splitlines()
                        self.assertEqual(lines[0],'G90')
                        self.assertEqual(lines[-1],'M400')
                        self.assertEqual(lines[1],
                                         'G1 Y%.5f F%d'%(p['safe_y'],max(allowed)))
                        self.assertEqual(lines[2],
                                         'G1 X%.5f F%d'%(p['dock_reference_xy']['x'],
                                                        max(allowed)))
                        self.assertEqual(len(lines),12)
                        self.assertEqual(lines[3],'M400')
                        for line in lines:
                            self.assertNotIn('G28',line)
                            self.assertNotIn('G1 Z',line)
                            self.assertNotIn('G1 E',line)
                            self.assertNotIn('M104',line)
                        feeds={int(re.search(r' F(\d+)$',x).group(1))
                               for x in lines if x.startswith('G1 ')}
                        self.assertEqual(feeds,allowed)
                        # A higher feed must not alter CxChanger point
                        # geometry: compare identical 15mm-margin route.
                        baseline=performance_cycle_script(p,kind,at_stage=False)
                        strip=lambda raw:re.sub(r' F\d+', ' F?',raw)
                        self.assertEqual(strip('\n'.join(lines)),
                                         strip(baseline),
                                         'Every XY waypoint must remain identical')

    def test_rapid_native_gates_remain_four_each_and_xy_is_unchanged(self):
        for mode in ('sprint','race'):
            for n,p in self.paths.items():
                with self.subTest(mode=mode,tool=n):
                    script=pair_script(self.paths,n,mode)
                    self.assertEqual(script.count('CXM_FAST_VERIFY EXPECT=PRESSED'),4)
                    self.assertEqual(script.count('CXM_FAST_VERIFY EXPECT=RELEASED'),6)
                    self.assertEqual(script.count('G4 P80'),6)
                    self.assertEqual(script.count('G4 P150'),2)
                    self.assertEqual(script.splitlines()[0],'G90')
                    self.assertTrue(script.splitlines()[1].startswith(
                        'CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y='))
                    self.assertNotIn('G28',script)
                    self.assertNotIn('G1 Z',script)
                    self.assertNotIn('G1 E',script)
                    self.assertNotIn('M104',script)

    def test_existing_performance_faster_speed_caps_stay_unchanged(self):
        p=self.paths[0]
        performance=performance_cycle_script(p,'pickup',at_stage=True)
        faster=faster_cycle_script(p,'pickup',at_stage=True)
        self.assertNotIn('F12000',performance)
        self.assertNotIn('F24000',performance)
        self.assertIn('F4800',performance)
        self.assertIn('F1800',faster)
        self.assertNotIn('F2400',faster)
        with self.assertRaises(ValueError):
            faster_cycle_script(p,'pickup',at_stage=True,travel_feed=24000)
        with self.assertRaises(ValueError):
            faster_cycle_script(p,'pickup',at_stage=True,latch_feed=1200)

    def test_sprint_race_reject_repeat_before_sending_motion(self):
        for mode in ('sprint','race'):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(multi.MultiToolError,'exactly one supervised cycle'):
                    multi.start(store=None,tools=[0,1],expected_revision='bad',
                                acknowledgement=multi.START_ACK,travel_profile=mode,
                                cycles=2)
        self.assertFalse(multi.MOVE_LOCK.locked())

    def test_nonfinite_unsafe_geometry_fails_closed(self):
        bad=dict(self.paths[0])
        bad['safe_y']=bad['dock_reference_xy']['y']+bad['dodge_y']+17
        for make in (sprint_cycle_script,race_cycle_script):
            with self.subTest(make=make):
                with self.assertRaisesRegex(ValueError,'clear'):
                    make(bad,'pickup',at_stage=False)

if __name__=='__main__': unittest.main()
