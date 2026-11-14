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

def with_stale_t1(source, indent='    ', newline='\n'):
    # Reproduce exactly the stale X264.70/Y65.60 branch observed in Klipper.
    target='    {% elif pos.y < safe-0.001 or safe > ymax or x+4.4 > xmax or pos.x < 5 or pos.x > 334 %}'
    if source.count(target)!=1:
        target=target.replace('pos.x > 334','pos.x > 325')
    assert source.count(target)==1
    old=(indent + x334.LEGACY_T1_CONDITION + newline +
         indent + '  ' + x334.LEGACY_T1_ACTION + newline)
    return source.replace(target,old+target,1)

def old_stage_source(source):
    # Files predating X334 also contain this staging block with X325.
    new_clear=x334.NEW_STAGE_CLEARANCE
    old_clear=x334.OLD_STAGE_CLEARANCE
    if new_clear not in source:
        new_clear=new_clear.replace('334.0','325.0')
        old_clear=old_clear.replace('334.0','325.0')
    assert source.count(new_clear)==1
    assert source.count(x334.NEW_STAGE_START)==1
    return (source.replace(new_clear,old_clear,1)
                  .replace(x334.NEW_STAGE_START,x334.OLD_STAGE_START,1))

class NativeX334Tests(unittest.TestCase):
    def test_exact_old_guard_fixed_and_every_other_byte_preserved(self):
        before=old_source()
        after=x334._transform(before)
        self.assertEqual(after,SOURCE.read_text())
        self.assertIn('CXM_FAST_VERIFY EXPECT=PRESSED',after)
        self.assertIn('CXM_FAST_VERIFY EXPECT=RELEASED',after)
        self.assertIn('G1 X{mounted|round(5)}',after)
    def test_actual_old_T1_release_point_only_is_removed(self):
        current=SOURCE.read_text()
        old=with_stale_t1(current)
        self.assertEqual(x334._transform(old),current)
        self.assertEqual(x334._transform(x334._transform(old)),current)

    def test_loaded_T1_guard_with_no_indentation_and_crlf(self):
        current=SOURCE.read_text()
        old=with_stale_t1(current,indent='',newline='\r\n')
        self.assertEqual(x334._transform(old),current)

    def test_known_old_T1_check_and_old_X325_bounds_are_removed_together(self):
        current=SOURCE.read_text()
        old=with_stale_t1(old_source())
        self.assertEqual(x334._transform(old),current)

    def test_one_time_T1_patch_backed_up_and_verified(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            old=with_stale_t1(SOURCE.read_text())
            target.write_text(old)
            preview=x334.inspect(target)
            self.assertEqual(preview['state'],'needs_apply')
            applied=x334.apply(target,preview['sha256'])
            self.assertTrue(applied['patched'])
            self.assertTrue(applied['restart_required'])
            self.assertEqual(target.read_text(),SOURCE.read_text())
            self.assertEqual(target.with_name(applied['backup']).read_text(),old)
            again=x334.inspect(target)
            self.assertEqual(again['state'],'installed')

    def test_unknown_T1_datum_or_duplicate_check_is_refused(self):
        old=with_stale_t1(SOURCE.read_text())
        variants=[
            old.replace('x-264.70','x-270.00'),
            old.replace(x334.LEGACY_T1_ACTION,x334.LEGACY_T1_ACTION+'\n      '+x334.LEGACY_T1_ACTION),
            old.replace(x334.LEGACY_T1_CONDITION,'{% elif t==1 and x > 264.70 %}')
        ]
        for source in variants:
            with self.subTest(source=source[-50:]):
                with self.assertRaisesRegex(x334.NativeX334Error,'Unexpected T1 release guard'):
                    x334._transform(source)

    def test_old_batch_stage_is_repaired_without_replacing_pickup_macro(self):
        current=SOURCE.read_text()
        obsolete=old_stage_source(current)
        self.assertIn('start on or above the clear staging line',obsolete)
        updated=x334._transform(obsolete)
        self.assertEqual(updated,current)
        self.assertIn('G1 Y{target|round(5)} F6000',updated)
        self.assertNotIn('start on or above the clear staging line',updated)
        self.assertIn('CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y={target}',updated)
        self.assertEqual(x334._transform(updated),current)

    def test_old_batch_stage_and_old_x325_and_old_t1_all_patch_together(self):
        current=SOURCE.read_text()
        obsolete=old_stage_source(with_stale_t1(old_source()))
        self.assertEqual(x334._transform(obsolete),current)

    def test_unknown_batch_staging_guard_cannot_be_overwritten(self):
        obsolete=old_stage_source(SOURCE.read_text())
        unexpected=obsolete.replace(
            'start on or above the clear staging line',
            'new staging error typed by operator')
        with self.assertRaisesRegex(x334.NativeX334Error,'Unknown or duplicated Dock Batch staging'):
            x334._transform(unexpected)

    def test_disk_batch_stage_patch_keeps_backup_and_all_other_bytes(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            old=old_stage_source(SOURCE.read_text())
            target.write_text(old)
            before=x334.inspect(target)
            self.assertEqual(before['state'],'needs_apply')
            done=x334.apply(target,before['sha256'])
            self.assertTrue(done['patched'])
            self.assertTrue(done['restart_required'])
            self.assertEqual(target.read_text(),SOURCE.read_text())
            self.assertEqual(target.with_name(done['backup']).read_text(),old)

    def test_only_old_t1_guard_patched_when_live_native_contains_custom_sections(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            current=SOURCE.read_text()
            # Reproduce user's installed custom macro divergence: another
            # checked guard has been modified, but the exact old T1 check remains.
            old=with_stale_t1(current).replace('pos.x|float > 334.0',
                                                'pos.x|float > 330.0',1)
            target.write_text(old)
            with self.assertRaises(x334.NativeX334Error):
                x334.inspect(target)
            state=x334.inspect_compat(target)
            self.assertEqual(state['mode'],'t1_only')
            self.assertEqual(state['state'],'needs_apply')
            done=x334.apply_compat(target,state['sha256'])
            self.assertEqual(done['mode'],'t1_only')
            self.assertTrue(done['patched'])
            expected=old.replace(x334.LEGACY_T1_CONDITION+'\\n','')
            # Compare with direct exact T1-only transformer, never vendor file.
            self.assertEqual(target.read_text(),
                             x334._transform_stale_t1_only(old))
            self.assertEqual(target.with_name(done['backup']).read_text(),old)
            verified=x334.inspect_compat(target)
            self.assertEqual(verified['state'],'installed')
            self.assertEqual(verified['mode'],'t1_only_cleared')

    def test_unknown_t1_condition_in_custom_macro_is_never_rewritten(self):
        with TemporaryDirectory() as folder:
            target=Path(folder)/'cxm_native_toolchange.cfg'
            old=with_stale_t1(SOURCE.read_text())
            old=old.replace('x-264.70','x-280.00')
            old=old.replace('pos.x|float > 334.0','pos.x|float > 330.0',1)
            target.write_text(old)
            with self.assertRaises(x334.NativeX334Error):
                x334.inspect_compat(target)
            self.assertEqual(target.read_text(),old)

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
    def test_loaded_t1_guard_status_requires_actual_Klipper_source(self):
        def mock(source):
            return lambda path:{'status':{'configfile':{'config':{
                'gcode_macro _CXM_CLEAR_TRANSFER':{'gcode':source}}}}}
        old=with_stale_t1(SOURCE.read_text())
        self.assertEqual(x334.loaded_t1_release_guard(mock(old)),'obsolete_t1')
        self.assertEqual(x334.loaded_t1_release_guard(mock(SOURCE.read_text())),'clear')
        self.assertEqual(x334.loaded_t1_release_guard(mock('')),'unknown')

    def test_loaded_old_and_new_are_reported_not_inferred(self):
        def mock(source):
            return lambda path:{'status':{'configfile':{'config':{
               'gcode_macro _CXM_CHECK_TOOL':{'gcode':source}}}}}
        self.assertEqual(x334.live_status(mock('x+st.shift_x|float>325')),'x325')
        self.assertEqual(x334.live_status(mock('x+st.shift_x|float>334')),'x334')
        self.assertEqual(x334.live_status(mock('')), 'unknown')
if __name__=='__main__':
    unittest.main()
