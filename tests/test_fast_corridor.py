"""Opt-in fast corridor travel must preserve original CxChanger contact motion."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_config import template
from cxm_cxchanger import plan, automatic_script, faster_cycle_script

class FasterClearCorridor(unittest.TestCase):
    def setUp(self):
        self.saved={'config':template()}
        self.saved['config']['tools'][0].update(
            dock_x=301.38,dock_y=65.99,dock_reference_accepted=True)
        self.path=plan(self.saved)

    def test_original_tested_single_tool_script_remains_untouched(self):
        code=automatic_script(self.path,'pickup',at_stage=False)
        self.assertIn('G1 Y109.99000 F600',code)
        self.assertIn('G1 X301.38000 Y65.99000 F180',code)
        self.assertNotIn('F1800',code)

    def test_pickup_faster_only_before_entry_and_after_clearance(self):
        code=faster_cycle_script(self.path,'pickup',at_stage=False)
        lines=code.splitlines()
        self.assertEqual(lines[:4],[
            'G90','G1 Y109.99000 F1800','G1 X301.38000 F1800','M400'])
        self.assertEqual(lines[4:],[
            'G1 X301.38000 Y89.99000 F1800',
            'G1 X301.38000 Y79.99000 F240',
            'G1 X296.58000 Y79.99000 F240',
            'G1 X296.58000 Y65.99000 F240',
            'G1 X301.38000 Y65.99000 F180',
            'G1 X301.38000 Y89.99000 F240',
            'G1 X301.38000 Y109.99000 F1800',
            'M400'])
        self.assertEqual(lines.count('M400'),2)
        self.assertTrue(all(' Z' not in line and ' E' not in line for line in lines))
        self.assertFalse(any('G28' in x or 'M104' in x for x in lines))

    def test_dropoff_final_contact_and_latch_are_original_speeds(self):
        lines=faster_cycle_script(self.path,'dropoff',at_stage=True).splitlines()
        self.assertEqual(lines,[
            'G90',
            'G1 X301.38000 Y89.99000 F1800',
            'G1 X301.38000 Y65.99000 F240',
            'G1 X296.58000 Y65.99000 F180',
            'G1 X296.58000 Y79.99000 F240',
            'G1 X301.38000 Y79.99000 F240',
            'G1 X301.38000 Y89.99000 F240',
            'G1 X301.38000 Y109.99000 F1800',
            'M400'])
        self.assertNotIn('G1 Y109.99000 F1800',lines,
                         'Already staged: no redundant Y/X staging')

    def test_no_contact_or_latch_point_has_faster_feed(self):
        for kind in ('pickup','dropoff'):
            script=faster_cycle_script(self.path,kind,at_stage=False)
            for line in script.splitlines():
                if not line.startswith('G1 '):continue
                feed=float(re.search(r' F([0-9.]+)$',line).group(1))
                self.assertLessEqual(feed,1800)
                if 'Y65.99000 ' in line or 'Y79.99000 ' in line:
                    self.assertLessEqual(feed,240,
                                         'Contact/dodge point must never use fast travel feed')

    def test_reject_unsafe_feed_or_geometry(self):
        for speed in (1801,5000,0,-1,float('nan')):
            with self.subTest(speed=speed):
                with self.assertRaises(ValueError):
                    faster_cycle_script(self.path,'pickup',at_stage=True,
                                        travel_feed=speed)
        with self.assertRaises(ValueError):
            faster_cycle_script(self.path,'pickup',at_stage=True,margin_y=1)
        with self.assertRaises(ValueError):
            faster_cycle_script(self.path,'stage',at_stage=True)
        unsafe=dict(self.path)
        unsafe['safe_y']=85
        with self.assertRaisesRegex(ValueError,'clear'):
            faster_cycle_script(unsafe,'dropoff',at_stage=True)

if __name__=='__main__':
    unittest.main()
