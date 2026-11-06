"""CXM homing migration: exact-block patching, safety gates and no auto restart."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
script=Path(__file__).resolve().parents[1]/'scripts/cxm_homing_fix.py'
spec=importlib.util.spec_from_file_location('cxm_homing_fix',script)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

OLD="""# Sample printer hardware
[stepper_x]
step_pin: PA0

[homing_override]
axes: xyz
set_position_z: 0
gcode:
    {% set home_all = 'X' not in params and 'Y' not in params and 'Z' not in params %}
    {% set home_y = home_all or 'Y' in params or 'X' in params %}
    {% set home_x = home_all or 'X' in params %}
    {% set home_z = home_all or 'Z' in params %}
    G90
    G91
    G1 Z10 F300
    G90
    {% if home_y %}
        G28 Y
    {% endif %}
    {% if home_x %}
        G28 X
    {% endif %}
    {% if home_z %}
        G1 X195 Y170 F6000
        G28 Z
        G91
        G1 Z5 F300
        G90
    {% endif %}
    G90

[bed_mesh]
speed: 200
"""

class HomePatch(unittest.TestCase):
    def test_scoped_patch_keeps_full_home_and_untouched_other_sections(self):
        out=module.updated_config(OLD)
        self.assertIn('[homing_override]\naxes: z\nset_position_z: 0',out)
        self.assertIn('G1 Z10 F300',out)
        self.assertIn('G1 Z5 F300',out)
        self.assertIn('G1 X195 Y170 F6000',out)
        self.assertIn('G28 Y',out)
        self.assertIn('G28 X',out)
        self.assertIn('G28 Z',out)
        self.assertIn("('Z' in params and 'y' not in printer.toolhead.homed_axes)",out)
        self.assertIn("('Z' in params and 'x' not in printer.toolhead.homed_axes)",out)
        self.assertEqual(out.split('[homing_override]')[0],OLD.split('[homing_override]')[0])
        self.assertEqual(out.split('[bed_mesh]')[1],OLD.split('[bed_mesh]')[1])
        self.assertNotIn('FIRMWARE_RESTART',module.updated_config.__doc__ or '')
    def test_reject_duplicate_or_unknown_homing(self):
        with self.assertRaisesRegex(ValueError,'exactly one'):
            module.updated_config(OLD+OLD)
        with self.assertRaisesRegex(ValueError,"axes: xyz"):
            module.updated_config(OLD.replace('axes: xyz','axes: z'))
        with self.assertRaisesRegex(ValueError,'Unexpected Y-first'):
            module.updated_config(OLD.replace(module.OLD_Y,'{% set home_y = True %}'))
        with self.assertRaisesRegex(ValueError,'Expected homing command is missing'):
            module.updated_config(OLD.replace('G1 Z10 F300','G1 Z15 F300'))
        with self.assertRaisesRegex(ValueError,'set_position_z'):
            module.updated_config(OLD.replace('set_position_z: 0','set_position_z: 5'))
    def test_idle_gate_never_fabricates_safe_result(self):
        with patch.object(module.urllib.request,'urlopen',side_effect=OSError('offline')):
            self.assertFalse(module.idle_confirmed())
    def test_default_not_apply(self):
        self.assertEqual(module.main.__defaults__,(None,))

if __name__=='__main__':
    unittest.main()
