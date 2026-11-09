"""Stage 3 Boost: software-only safety regression, no printer motion."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_config import template
from cxm_cxchanger import (
    plan,boost_cycle_script,race_cycle_script,performance_cycle_script,
    faster_cycle_script)
from cxm_rapid import pair_script,stream_script
import cxm_multi as multi

class BoostTests(unittest.TestCase):
    def setUp(self):
        s={'config':template()}
        s['config']['globals']['tool_count']=3
        for n,x,y in [(0,306.79,65.99),(1,267.19,65.68),(2,226.01,65.21)]:
            s['config']['tools'][n].update(dock_x=x,dock_y=y,
                                            dock_reference_accepted=True)
        self.paths={n:plan(s,tool=n) for n in range(3)}
    def test_boost_requested_feeds_same_exact_waypoints(self):
        for n,p in self.paths.items():
            for kind in ('pickup','dropoff'):
                with self.subTest(tool=n,kind=kind):
                    fast=boost_cycle_script(p,kind,at_stage=False)
                    slow=race_cycle_script(p,kind,at_stage=False)
                    self.assertEqual(
                        re.sub(r' F\d+',' F?',fast),
                        re.sub(r' F\d+',' F?',slow),
                        'Speed alone must change, not CxChanger geometry')
                    feeds={int(z.group(1)) for z in
                           re.finditer(r' F(\d+)',fast)}
                    self.assertEqual(feeds,{36000,7200,2400})
                    self.assertTrue(fast.splitlines()[1].startswith('G1 Y'))
                    self.assertTrue(fast.splitlines()[2].startswith('G1 X'))
                    for prohibited in ('G28','G1 Z','G1 E','M104'):
                        self.assertNotIn(prohibited,fast)
    def test_no_other_speed_profile_changes(self):
        p=self.paths[0]
        self.assertIn('F24000',race_cycle_script(p,'pickup',at_stage=False))
        self.assertIn('F4800',performance_cycle_script(p,'pickup',at_stage=False))
        self.assertIn('F1800',faster_cycle_script(p,'pickup',at_stage=False))
        self.assertNotIn('F36000',race_cycle_script(p,'pickup',at_stage=False))
    def test_native_pairs_and_stream_keep_four_independent_sensor_samples(self):
        for n in (0,1,2):
            pair=pair_script(self.paths,n,'boost')
            self.assertEqual(pair.count('CXM_FAST_VERIFY EXPECT=PRESSED'),4)
            self.assertEqual(pair.count('CXM_FAST_VERIFY EXPECT=RELEASED'),6)
            self.assertEqual(pair.count('G4 P150'),2)
            self.assertEqual(pair.count('G4 P80'),6)
        stream=stream_script({k:self.paths[k] for k in (0,1)},[0,1],'boost')
        self.assertIn('F36000',stream)
        self.assertIn('F7200',stream)
        self.assertIn('F2400',stream)
        self.assertEqual(stream.count('CXM_FAST_VERIFY EXPECT=PRESSED'),8)
    def test_no_repeated_boost_runs_before_physical_validation(self):
        with self.assertRaisesRegex(multi.MultiToolError,'exactly one supervised cycle'):
            multi.start(store=None,tools=[0,1],expected_revision='fake',
                        acknowledgement=multi.START_ACK,cycles=2,
                        execution_mode='rapid',travel_profile='boost')
        self.assertFalse(multi.MOVE_LOCK.locked())

if __name__=='__main__': unittest.main()
