"""Pure and file-backed native batch macro upgrade safety tests."""
import sys
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_batch_upgrade as mod

LEGACY_VENDOR=Path(__file__).resolve().parents[1]/'tests/fixtures/cxm_native_pre_y105_legacy.cfg'
VENDOR=LEGACY_VENDOR.read_text()

def legacy(source):
    sections=mod.sections(source)
    changes={
      ('gcode_macro','_CXM_TEST_STATE'):(
        'variable_tool_mask: 0\nvariable_tool_count: 0\nvariable_batch_revision: 2\n',''),
      ('gcode_macro','CXM_TEST_START'):(
        'Start native one- to three-tool test',
        'Start native one- to three-tool test'), # changed below via exact replacement
    }
    # Preserve the source's unrelated macros; restore only historical
    # test-controller blocks to the old markers for the upgrade fixture.
    changes.pop(('gcode_macro','CXM_TEST_START'))
    spans=[]
    for name in mod.NAMES:
        start,end,block=sections[name]
        if name==('gcode_macro','_CXM_TEST_STATE'):
            old=block.replace('variable_tool_mask: 0\nvariable_tool_count: 0\nvariable_batch_revision: 2\n','')
        elif name==('gcode_macro','CXM_TEST_START'):
            old=block.replace('Native bounded 1–12 tool test; uses each accepted dock\'s own safe Y',
                              'Start native one- to three-tool test')
            old=old.replace('VARIABLE=tool_mask VALUE={mask}',
                            'VARIABLE=tool_c VALUE={c}')
            old=old.replace('_CXM_STAGE_TEST Y={ns.highest_safe}',
                            '_CXM_STAGE_TEST Y={([y_a,y_b,y_c]|max)}')
            old=old.replace('CXM: invalid tool mask or repeat cycles',
                            'CXM: invalid ordered 1-3 tool cycle parameters')
            old=old.replace('CXM: select 1–12 accepted tools; max 120 movements per run',
                            'CXM: selected dock safe-Y lines differ by more than 1 mm')
        elif name==('gcode_macro','_CXM_TEST_ADVANCE'):
            old=block.replace('set count=st.tool_count|int',
                     'set count=3 if st.tool_c|int >= 0 else 2 if st.tool_b|int >= 0 else 1')
        elif name==('delayed_gcode','CXM_NATIVE_TEST_STEP'):
            old=block.replace('CXM_SELECT_TOOL TOOL={ns.tool}',
                              'CXM_SELECT_TOOL TOOL={t}')
            old=old.replace('{% set dock_y=native["t" ~ ns.tool ~ "_y"]|float %}',
                              '{% set t=st.tool_a|int if st.index|int == 0 else st.tool_b|int if st.index|int == 1 else st.tool_c|int %}')
        else:
            old=block.replace('    SET_GCODE_VARIABLE MACRO=_CXM_TEST_STATE VARIABLE=tool_mask VALUE=0\n','')
            old=old.replace('    SET_GCODE_VARIABLE MACRO=_CXM_TEST_STATE VARIABLE=tool_count VALUE=0\n','')
        spans.append((start,end,old))
    for start,end,block in sorted(spans,reverse=True):
        source=source[:start]+block+source[end:]
    return source

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        # Exercise the one-time migrator against its historical source,
        # never against the proven 15 Nov 2026 active motion macro.
        self.vendor_patch=unittest.mock.patch.object(mod,'VENDOR',LEGACY_VENDOR)
        self.vendor_patch.start()
        self.addCleanup(self.vendor_patch.stop)

    def test_safe_transform_replaces_only_five_controller_macros(self):
        old=legacy(VENDOR)
        result=mod.transform(old,VENDOR)
        self.assertEqual(result,VENDOR)
        self.assertEqual(mod.transform(VENDOR,VENDOR),VENDOR)
        self.assertIn('[gcode_macro _CXM_PICKUP_MOTION]',result)

    def test_unknown_custom_runner_rejected_before_writes(self):
        old=legacy(VENDOR).replace('selected dock safe-Y lines differ by more than 1 mm',
                                  'operator modified staging guard')
        with self.assertRaises(mod.BatchUpgradeError):
            mod.transform(old,VENDOR)

    def test_missing_auto_stage_rejected(self):
        old=legacy(VENDOR).replace('G1 Y{target|round(5)} F6000',
                                  'RESPOND MSG="stage changed"',1)
        with self.assertRaisesRegex(mod.BatchUpgradeError,'staging'):
            mod.transform(old,VENDOR)

    def test_backup_atomic_apply_readback_and_no_rewrite_on_second_attempt(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            old=legacy(VENDOR)
            target.write_text(old)
            before=mod.inspect(target)
            self.assertEqual(before['state'],'needs_apply')
            done=mod.apply(target,before['sha256'])
            self.assertTrue(done['patched'])
            self.assertTrue(done['restart_required'])
            self.assertEqual(target.read_text(),VENDOR)
            self.assertEqual(target.with_name(done['backup']).read_text(),old)
            again=mod.inspect(target)
            self.assertEqual(again['state'],'installed')
            self.assertTrue(mod.apply(target,again['sha256'])['already_installed'])

if __name__=='__main__':unittest.main()
