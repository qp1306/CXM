"""CXM V0.9.3: Y-before-X cannot regress; Z lifts stay out of XY-only homing."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

script=Path(__file__).resolve().parents[1]/'scripts/cxm_homing_fix.py'
spec=importlib.util.spec_from_file_location('cxm_homing_fix',script)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

OLD="""# Actual homing structure
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

def sections(text):
    pattern=re.compile(r"(?m)^\[([^\]]+)\][ \t]*(?:\r?\n)")
    matches=list(pattern.finditer(text))
    return {m.group(1):text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
            for i,m in enumerate(matches)}

try:
    import jinja2
except ImportError:
    jinja2=None

@unittest.skipUnless(jinja2,'Jinja2 required: installed explicitly in CI')
class ActualKlipperTemplateTests(unittest.TestCase):
    def setUp(self):
        self.config=sections(module.updated_config(OLD))
        self.wrapper=self.config['gcode_macro G28'].split('gcode:',1)[1]
        self.override=self.config['homing_override'].split('gcode:',1)[1]

    def render(self,template,axes=(),homed='xyz'):
        from types import SimpleNamespace
        params={k:'0' for k in axes}
        printer=SimpleNamespace(toolhead=SimpleNamespace(homed_axes=homed))
        return [line.strip() for line in jinja2.Template(template).render(
            params=params,printer=printer).splitlines()
            if line.strip() and not line.strip().startswith('#')]

    def test_public_G28_X_always_Y_first_never_Z(self):
        for homed in ('','x','y','xy','xyz'):
            self.assertEqual(self.render(self.wrapper,('X',),homed),
                             ['G28.1 Y','G28.1 X'])

    def test_XY_and_Y_only_never_lift_Z(self):
        self.assertEqual(self.render(self.wrapper,('X','Y')),['G28.1 Y','G28.1 X'])
        self.assertEqual(self.render(self.wrapper,('Y',)),['G28.1 Y'])

    def test_full_home_preserves_original_lift_and_cartographer(self):
        self.assertEqual(self.render(self.wrapper),['G28.1'])
        cmds=self.render(self.override,homed='')
        self.assertLess(cmds.index('G28.1 Y'),cmds.index('G28.1 X'))
        self.assertLess(cmds.index('G28.1 X'),cmds.index('G28.1 Z'))
        self.assertLess(cmds.index('G1 Z10 F300'),cmds.index('G28.1 Y'))
        self.assertIn('G1 X195 Y170 F6000',cmds)
        self.assertIn('G1 Z5 F300',cmds)

    def test_Z_only_will_home_missing_XY_before_Z(self):
        self.assertEqual(self.render(self.wrapper,('Z',)),['G28.1 Z'])
        cmds=self.render(self.override,('Z',),homed='')
        self.assertLess(cmds.index('G28.1 Y'),cmds.index('G28.1 X'))
        self.assertLess(cmds.index('G28.1 X'),cmds.index('G28.1 Z'))
        cmds=self.render(self.override,('Z',),homed='xyz')
        self.assertNotIn('G28.1 Y',cmds)
        self.assertNotIn('G28.1 X',cmds)
        self.assertIn('G28.1 Z',cmds)

    def test_mixed_XZ_and_YZ_routed_via_full_homing(self):
        self.assertEqual(self.render(self.wrapper,('X','Z')),['G28.1'])
        self.assertEqual(self.render(self.wrapper,('Y','Z')),['G28.1'])
        self.assertEqual(self.render(self.wrapper,('X','Y','Z')),['G28.1'])

class ConfigSafetyTests(unittest.TestCase):
    def test_original_config_uses_Z_only_override_and_one_public_G28(self):
        out=module.updated_config(OLD)
        ss=sections(out)
        self.assertIn('axes: z',ss['homing_override'])
        self.assertIn('set_position_z: 0',ss['homing_override'])
        self.assertIn('rename_existing: G28.1',ss['gcode_macro G28'])
        self.assertIn('G28.1 Y',ss['homing_override'])
        self.assertIn('G28.1 X',ss['homing_override'])
        self.assertIn('G28.1 Z',ss['homing_override'])
        self.assertNotRegex(ss['homing_override'],r"(?m)^\s+G28 [XYZ]\s*$")
        self.assertEqual(out.split('[homing_override]')[0],
                         OLD.split('[homing_override]')[0])
        self.assertIn('[bed_mesh]\nspeed: 200',out)
        self.assertEqual(out.count('[gcode_macro G28]'),1)
        self.assertEqual(out.count('[homing_override]'),1)

    def test_upgrades_previous_Z_only_patch(self):
        previous=OLD.replace('axes: xyz','axes: z').replace(module.OLD_Y,module.NEW_Y).replace(
            module.OLD_X,module.NEW_X)
        out=module.updated_config(previous)
        self.assertIn('rename_existing: G28.1',out)
        self.assertEqual(out.count('G28.1 Y'),2) # one in override, one in wrapper
        self.assertEqual(out.count('[gcode_macro G28]'),1)

    def test_rejects_conflicting_macro_and_unknown_homing(self):
        with self.assertRaisesRegex(ValueError,'G28 macro already defined'):
            module.updated_config(module.updated_config(OLD))
        with self.assertRaisesRegex(ValueError,'exactly one'):
            module.updated_config(OLD+OLD)
        with self.assertRaisesRegex(ValueError,'Unknown homing override'):
            module.updated_config(OLD.replace('axes: xyz','axes: xy'))
        with self.assertRaisesRegex(ValueError,'Unknown homing override'):
            module.updated_config(OLD.replace(module.OLD_Y,'{% set home_y = True %}'))
        with self.assertRaisesRegex(ValueError,'Expected precisely one inner G28'):
            module.updated_config(OLD.replace('G28 X','G28 Q'))
        with self.assertRaisesRegex(ValueError,'Required Cartographer'):
            module.updated_config(OLD.replace('G1 Z10 F300','G1 Z25 F300'))

    def test_no_unattended_motion_or_restart(self):
        src=script.read_text()
        self.assertNotIn('subprocess',src)
        self.assertNotIn('os.system',src)
        self.assertNotIn('/printer/gcode/script',src)
        self.assertIn('if not args.apply:',src)
        self.assertIn('if not idle_confirmed():',src)
        self.assertIn('shutil.copy2(path, backup)',src)
        self.assertIn('os.replace(tmp, path)',src)

    def test_idle_gate_fails_closed(self):
        with patch.object(module.urllib.request,'urlopen',side_effect=OSError('offline')):
            self.assertFalse(module.idle_confirmed())

if __name__=='__main__':
    unittest.main()
