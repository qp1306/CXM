"""Regression for the targeted live Klipper X334 compatibility correction."""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_x334_live as x334
SOURCE=Path(__file__).resolve().parents[1]/'vendor/cxm/cxm_native_toolchange.cfg'

def old_source():
    fresh=SOURCE.read_text()
    old=fresh
    for pairs in x334.RULES.values():
        for left,right in pairs:
            assert old.count(right)==1,(left,right)
            old=old.replace(right,left)
    assert old!=fresh
    return old

class NativeX334Tests(unittest.TestCase):
    def test_exact_old_guard_fixed_and_every_other_byte_preserved(self):
        before=old_source()
        after=x334._transform(before)
        self.assertEqual(after,SOURCE.read_text())
        self.assertIn('CXM_FAST_VERIFY EXPECT=PRESSED',after)
        self.assertIn('CXM_FAST_VERIFY EXPECT=RELEASED',after)
        self.assertIn('G1 X{mounted|round(5)}',after)
    def test_existing_new_file_is_idempotent(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            target.write_text(SOURCE.read_text())
            d=x334.inspect(target)
            self.assertEqual(d['state'],'installed')
            result=x334.apply(target,d['sha256'])
            self.assertFalse(result['restart_required'])
            self.assertFalse(list(target.parent.glob('*.bak')))
    def test_backup_atomic_apply_and_exact_byte_readback(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            source=old_source()
            target.write_text(source)
            d=x334.inspect(target)
            self.assertEqual(d['state'],'needs_apply')
            result=x334.apply(target,d['sha256'])
            self.assertTrue(result['patched'])
            self.assertTrue(result['restart_required'])
            self.assertEqual(target.read_text(),SOURCE.read_text())
            self.assertEqual(target.with_name(result['backup']).read_text(),source)
    def test_user_custom_motion_outside_guards_untouched(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            source=old_source().replace('G1 X{mounted|round(5)}',
              'G1 X{mounted|round(5)}  ; proven live adjustment')
            target.write_text(source)
            d=x334.inspect(target)
            x334.apply(target,d['sha256'])
            self.assertEqual(target.read_text(),
                             source.replace('pos.x|float > 325.0','pos.x|float > 334.0')
                                   .replace('x>325 or y<10','x>334 or y<10')
                                   .replace('x+st.shift_x|float>325','x+st.shift_x|float>334')
                                   .replace('pos.x > 325','pos.x > 334'))
    def test_malformed_or_duplicated_guard_is_refused(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            original=old_source().replace(
                'x+st.shift_x|float>325','x+st.shift_x|float>500')
            target.write_text(original)
            with self.assertRaisesRegex(x334.NativeX334Error,'unknown or duplicated'):
                x334.inspect(target)
            self.assertEqual(target.read_text(),original)
    def test_stale_sha_fails_without_backup_or_file_change(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            original=old_source()
            target.write_text(original)
            with self.assertRaisesRegex(x334.NativeX334Error,'changed'):
                x334.apply(target,'0'*64)
            self.assertEqual(target.read_text(),original)
            self.assertFalse(list(target.parent.glob('*.bak')))
    def test_loaded_old_and_new_are_reported_not_inferred(self):
        def mock(source):
            return lambda path:{'status':{'configfile':{'config':{
               'gcode_macro _CXM_CHECK_TOOL':{'gcode':source}}}}}
        self.assertEqual(x334.live_status(mock('x+st.shift_x|float>325')),'x325')
        self.assertEqual(x334.live_status(mock('x+st.shift_x|float>334')),'x334')
        self.assertEqual(x334.live_status(mock('')), 'unknown')
if __name__=='__main__':
    unittest.main()
