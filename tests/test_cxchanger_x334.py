"""CXM X334 limit: reject only paths exceeding the actual configured X endstop."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from cxm_cxchanger import plan
from cxm_config import template

class X334Tests(unittest.TestCase):
    def setUp(self):
        self.config=template()
        self.config['globals']['tool_count']=5
        self.config['tools'][0].update(
            dock_x=325.006,dock_y=65.55,dock_reference_accepted=True)
    def test_T0_at_325_006_is_allowed_when_full_latch_path_fits(self):
        result=plan({'config':self.config})
        self.assertAlmostEqual(result['dock_reference_xy']['x'],325.006)
        self.assertAlmostEqual(result['pickup'][1][0],329.406)
        self.assertLess(result['pickup'][1][0],334.0)
    def test_exact_x334_latch_endpoint_allowed(self):
        self.config['tools'][0]['dock_x']=329.6
        result=plan({'config':self.config})
        self.assertAlmostEqual(result['pickup'][1][0],334.0,places=4)
    def test_x_latch_above_334_still_rejected(self):
        self.config['tools'][0]['dock_x']=330.0
        with self.assertRaisesRegex(ValueError,'docking path exceeds'):
            plan({'config':self.config})
    def test_native_guards_match_python_validator(self):
        source=(ROOT/'vendor/cxm/cxm_native_toolchange.cfg').read_text()
        self.assertIn('x+st.shift_x|float>334',source)
        self.assertIn('pos.x > 334',source)
        self.assertNotIn('x+st.shift_x|float>325',source)
        self.assertNotIn('pos.x > 325',source)
        self.assertNotIn('pos.x|float > 325.0',source)
if __name__=='__main__':
    unittest.main()
