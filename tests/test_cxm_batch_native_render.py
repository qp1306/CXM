"""Hardware-free Jinja simulation of 1–12-tool native batch controller."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from validate_cxm_native import macro_sections
from jinja2 import Environment

B=macro_sections()
E=Environment()
def fail(message):
    raise ValueError(message)

class Tests(unittest.TestCase):
    def native(self,count):
        n={'tool_count':count,'ready':1,'fault':0,'current_tool':-1,
           'clearance_y':100.0}
        for t in range(count):
            n[f't{t}_x']=324.9-45.0*t
            n[f't{t}_y']=64.9 + (1.0 if t==3 else -1.9 if t==5 else -0.7 if t in (1,2) else 0)
            n[f't{t}_accepted']=1
        return n

    def render(self,macro,**kwargs):
        source=B[macro].split('gcode:',1)[1]
        return E.from_string(source).render(
          action_raise_error=fail,**kwargs)

    def test_six_tools_stage_highest_y_even_when_docks_differ_by_more_than_one_mm(self):
        native=self.native(6)
        state={'running':0,'tool_mask':0,'tool_count':0}
        output=self.render('CXM_TEST_START',params={'MASK':'63','CYCLES':'1'},
               printer={'gcode_macro _CXM_NATIVE':native,
                        'gcode_macro _CXM_TEST_STATE':state})
        self.assertIn('VARIABLE=tool_mask VALUE=63',output)
        self.assertIn('VARIABLE=tool_count VALUE=6',output)
        self.assertIn('_CXM_STAGE_TEST Y=165.9',output)
        for t in range(6):
            self.assertIn(f'_CXM_CHECK_TOOL TOOL={t}',output)
        self.assertNotIn('selected dock safe-Y lines differ',output)

    def test_each_pair_stages_to_its_own_measured_dock_y(self):
        native=self.native(6)
        for index in range(6):
            state={'running':1,'stop':0,'completed':0,'cycles':1,
                   'index':index,'tool_mask':63,'tool_count':6}
            result=self.render('CXM_NATIVE_TEST_STEP',
                printer={'gcode_macro _CXM_NATIVE':native,
                         'gcode_macro _CXM_TEST_STATE':state})
            y=native[f't{index}_y']
            self.assertIn(f'_CXM_STAGE_TEST Y={y+100.0} DOCK_Y={y}',result)
            self.assertIn(f'CXM_SELECT_TOOL TOOL={index}',result)
            self.assertIn('CXM_SELECT_TOOL TOOL=-1',result)
            self.assertIn('_CXM_TEST_ADVANCE',result)

    def test_noncontiguous_and_twelve_tool_selection(self):
        native=self.native(12)
        mask=2**0+2**5+2**11
        output=self.render('CXM_TEST_START',params={'MASK':str(mask),'CYCLES':'5'},
            printer={'gcode_macro _CXM_NATIVE':native,
                     'gcode_macro _CXM_TEST_STATE':{'running':0}})
        self.assertIn(f'VARIABLE=tool_mask VALUE={mask}',output)
        self.assertIn('VARIABLE=tool_count VALUE=3',output)
        for index,t in enumerate((0,5,11)):
            state={'running':1,'stop':0,'completed':0,'cycles':5,
                   'index':index,'tool_mask':mask,'tool_count':3}
            code=self.render('CXM_NATIVE_TEST_STEP',
                  printer={'gcode_macro _CXM_NATIVE':native,
                           'gcode_macro _CXM_TEST_STATE':state})
            self.assertIn(f'CXM_SELECT_TOOL TOOL={t}',code)

    def test_invalid_masks_and_excess_movements_fail_closed(self):
        native=self.native(6)
        for mask,cycles in ((0,1),(64,1),(63,11)):
            with self.subTest(mask=mask,cycles=cycles),self.assertRaises(ValueError):
                self.render('CXM_TEST_START',params={'MASK':str(mask),'CYCLES':str(cycles)},
                  printer={'gcode_macro _CXM_NATIVE':native,
                           'gcode_macro _CXM_TEST_STATE':{'running':0}})

    def test_advancing_sixth_tool_counts_completed_cycle(self):
        result=self.render('_CXM_TEST_ADVANCE',
            printer={'gcode_macro _CXM_NATIVE':{'current_tool':-1},
                     'gcode_macro _CXM_TEST_STATE':{'tool_count':6,'index':5,'completed':0}})
        self.assertIn('VARIABLE=index VALUE=0',result)
        self.assertIn('VARIABLE=completed VALUE=1',result)

if __name__=='__main__':unittest.main()
