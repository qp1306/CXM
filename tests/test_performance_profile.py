"""CXM performance corridor speed profile: no dock/lock geometry changes."""
import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))

from cxm_config import template
from cxm_cxchanger import (plan,automatic_script,faster_cycle_script,
                            performance_cycle_script)
from cxm_rapid import pair_script

class PerformanceProfileTests(unittest.TestCase):
    def setUp(self):
        self.saved={'config':template()}
        self.saved['config']['globals']['tool_count']=3
        for tool,x,y in [(0,306.79,65.99),(1,267.19,65.68),(2,226.01,65.21)]:
            self.saved['config']['tools'][tool].update(
                dock_x=x,dock_y=y,dock_reference_accepted=True)
        self.paths={n:plan(self.saved,tool=n) for n in range(3)}

    def test_existing_standard_and_faster_scripts_not_modified(self):
        p=self.paths[0]
        standard=automatic_script(p,'pickup',at_stage=False)
        faster=faster_cycle_script(p,'pickup',at_stage=False)
        self.assertIn('G1 Y109.99000 F600',standard)
        self.assertIn('G1 X306.79000 Y65.99000 F180',standard)
        self.assertIn('G1 Y109.99000 F1800',faster)
        self.assertIn('G1 X306.79000 Y89.99000 F1800',faster)
        self.assertNotIn('F4800',standard)
        self.assertNotIn('F4800',faster)

    def test_fast_clearance_slow_approach_and_original_latch(self):
        for n,p in self.paths.items():
            with self.subTest(tool=n):
                y=p['dock_reference_xy']['y']
                x=p['dock_reference_xy']['x']
                near=y+p['dodge_y']+15
                for kind in ('pickup','dropoff'):
                    lines=performance_cycle_script(p,kind,at_stage=False).splitlines()
                    self.assertEqual(lines[0],'G90')
                    self.assertEqual(lines[-1],'M400')
                    self.assertEqual(lines[1],f'G1 Y{p["safe_y"]:.5f} F4800')
                    self.assertEqual(lines[2],f'G1 X{x:.5f} F4800')
                    self.assertIn(f'G1 X{x:.5f} Y{near:.5f} F4800',lines)
                    self.assertIn(f'G1 X{x:.5f} Y{near:.5f} F480',lines)
                    self.assertIn(f'G1 X{x:.5f} Y{p["safe_y"]:.5f} F4800',lines)
                    self.assertIn(f'G1 X{x+p["shift_x"]:.5f} Y{y if kind=="dropoff" else y+p["dodge_y"]:.5f} F{180 if kind=="dropoff" else 480}',lines)
                    for line in lines:
                        self.assertNotRegex(line,r'(?<!\w)(?:G28|M104|G1 Z|G1 E)')
                        if line.startswith('G1 '):
                            feed=float(re.search(r' F([0-9.]+)$',line).group(1))
                            self.assertIn(feed,(180,480,4800))

    def test_native_rapid_pair_uses_exact_same_performance_geometry_and_safety_gates(self):
        for tool,p in self.paths.items():
            with self.subTest(tool=tool):
                rapid=pair_script(self.paths,tool,'performance')
                self.assertIn(f'G1 X{p["dock_reference_xy"]["x"]:.5f} F4800',rapid)
                self.assertEqual(rapid.count('CXM_FAST_VERIFY EXPECT=PRESSED'),4)
                self.assertEqual(rapid.count('CXM_FAST_VERIFY EXPECT=RELEASED'),6)
                self.assertEqual(rapid.count('G4 P80'),6)
                self.assertEqual(rapid.count('G4 P150'),2)
                self.assertIn('F4800',rapid)
                self.assertIn('F480',rapid)
                self.assertIn('F180',rapid)
                self.assertNotIn('G1 Z',rapid)
                self.assertNotIn('G28',rapid)

    def test_old_faster_limit_remains_and_unsafe_geometry_is_rejected(self):
        p=self.paths[0]
        with self.assertRaises(ValueError):
            faster_cycle_script(p,'pickup',at_stage=True,travel_feed=4800)
        with self.assertRaises(ValueError):
            faster_cycle_script(p,'pickup',at_stage=True,test_feed=480)
        bad=dict(p)
        bad['safe_y']=p['dock_reference_xy']['y']+p['dodge_y']+17
        with self.assertRaisesRegex(ValueError,'clear'):
            performance_cycle_script(bad,'pickup',at_stage=True)

if __name__=='__main__':unittest.main()
