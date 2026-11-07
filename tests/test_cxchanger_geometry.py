"""Source-level regression for CxChanger motion independent of Lineux."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_config import template
from cxm_cxchanger import plan,automatic_script

class CxChangerMotion(unittest.TestCase):
    def setUp(self):
        self.saved={'config':template()}
        t=self.saved['config']['tools'][0]
        t.update(dock_x=301.38,dock_y=65.99,dock_reference_accepted=True)
    def test_upstream_cxchanger_dropoff_path_and_relative_safe_y(self):
        p=plan(self.saved)
        self.assertEqual(p['stage'],[(301.38,109.99)])
        self.assertEqual(p['dropoff'],[
            (301.38,65.99),(296.58,65.99),(296.58,79.99),
            (301.38,79.99),(301.38,109.99)])
        self.assertEqual(p['pickup'],[
            (301.38,79.99),(296.58,79.99),(296.58,65.99),
            (301.38,65.99),(301.38,109.99)])
        self.assertEqual(p['motion_source'],'CxChanger')
        self.assertEqual(p['measurement_source'],'Lineux (separate)')
    def test_legacy_absolute_safe_y_never_affects_cxchanger(self):
        self.saved['config']['globals']['safe_y']=340
        self.assertEqual(plan(self.saved)['safe_y'],109.99)
        self.saved['config']['tools'][0]['dock_y']=80
        self.assertEqual(plan(self.saved)['safe_y'],124.0)
    def test_each_dock_has_independent_datum(self):
        self.saved['config']['globals']['tool_count']=2
        self.saved['config']['tools'][1].update(
            dock_x=271.38,dock_y=66.5,dock_reference_accepted=True)
        self.assertEqual(plan(self.saved,tool=1)['stage'],[(271.38,110.5)])
        self.assertEqual(plan(self.saved,tool=0)['stage'],[(301.38,109.99)])
    def test_missing_or_old_unaccepted_datum_fails_closed(self):
        self.saved['config']['tools'][0]['dock_reference_accepted']=False
        with self.assertRaisesRegex(ValueError,'Re-measure with Lineux'):
            plan(self.saved)
        self.saved['config']['tools'][0]['dock_reference_accepted']=True
        self.saved['config']['tools'][0]['dock_x']=None
        with self.assertRaisesRegex(ValueError,'Save CxChanger'):
            plan(self.saved)
    def test_geometry_validation_never_skips_clearance_or_limits(self):
        g=self.saved['config']['globals']
        g['cxm_safe_clearance_y']=35
        g['cxm_dodge_y']=25
        with self.assertRaisesRegex(ValueError,'at least 20'):
            plan(self.saved)
        g['cxm_safe_clearance_y']=44
        g['cxm_dodge_y']=14
        self.saved['config']['tools'][0]['dock_y']=319
        with self.assertRaisesRegex(ValueError,'guarded X/Y'):
            plan(self.saved)
    def test_one_script_has_stage_barrier_and_only_xy_motion(self):
        code=automatic_script(plan(self.saved),'dropoff',at_stage=False)
        lines=code.splitlines()
        self.assertEqual(lines[:4],
            ['G90','G1 Y109.99000 F600','G1 X301.38000 F600','M400'])
        self.assertEqual(lines[-1],'M400')
        self.assertEqual(lines.count('M400'),2)
        self.assertIn('G1 X296.58000 Y65.99000 F180',lines)
        self.assertTrue(all(' Z' not in line and ' E' not in line for line in lines))
        pickup=automatic_script(plan(self.saved),'pickup',at_stage=True)
        self.assertEqual(pickup.splitlines().count('M400'),1)

if __name__=='__main__':
    unittest.main()
