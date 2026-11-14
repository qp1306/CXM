"""Disk-only tests of verified T0 motion baseline. No printer connection."""
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from cxm_config import Store

class ProvenT0BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name)
        self.store.initialize()

    def accept_t0(self, x=304.60625, y=65.6):
        revision=self.store.read()['revision']
        self.store.save_dock(0,{'x':x,'y':y},revision)

    def test_save_preserves_exact_measured_dock_and_creates_backup(self):
        self.accept_t0()
        current=self.store.read()
        # Simulate existing pre-upgrade legacy motion variables.
        self.store.set_value('global','cxm_shift_x',-4.8,current['revision'])
        rev=self.store.read()['revision']
        self.store.set_value('global','cxm_safe_clearance_y',44.0,rev)
        before=self.store.read()
        old_t0=before['config']['tools'][0].copy()
        result=self.store.apply_verified_t0_motion(before['revision'])
        self.assertTrue(result['saved'])
        self.assertTrue(result['backup'])
        after=self.store.read()
        self.assertEqual(after['config']['globals']['cxm_shift_x'],4.4)
        self.assertEqual(after['config']['globals']['cxm_safe_clearance_y'],100.0)
        self.assertEqual(after['config']['tools'][0]['dock_x'],304.60625)
        self.assertEqual(after['config']['tools'][0]['dock_y'],65.6)
        self.assertTrue(after['config']['tools'][0]['dock_reference_accepted'])
        self.assertEqual(after['config']['tools'][0]['dock_z'],old_t0['dock_z'])
        self.assertTrue((self.store.backups/result['backup']).is_file())
        unchanged=self.store.apply_verified_t0_motion(after['revision'])
        self.assertTrue(unchanged['unchanged'])
        self.assertEqual(after['revision'],self.store.read()['revision'])

    def test_accept_relocated_t0_without_overwriting_measured_dock(self):
        self.accept_t0(305.50,66.10)
        before=self.store.read()
        result=self.store.apply_verified_t0_motion(before['revision'])
        self.assertTrue(result['saved'])
        self.assertEqual(self.store.read()['config']['tools'][0]['dock_x'],305.50)
        self.assertEqual(self.store.read()['config']['tools'][0]['dock_y'],66.10)
        self.assertTrue(self.store.read()['config']['tools'][0]['dock_reference_accepted'])

    def test_refuse_out_of_bounds_dock_without_overwriting(self):
        self.accept_t0(330.0,65.6)
        rev=self.store.read()['revision']
        with self.assertRaisesRegex(ValueError,'guarded motion region'):
            self.store.apply_verified_t0_motion(rev)
        self.assertEqual(self.store.read()['revision'],rev)

    def test_refuse_stale_revision(self):
        self.accept_t0()
        with self.assertRaisesRegex(RuntimeError,'Configuration changed'):
            self.store.apply_verified_t0_motion('0'*64)

    def test_refuse_missing_dock(self):
        rev=self.store.read()['revision']
        with self.assertRaisesRegex(ValueError,'newly measured accepted dock'):
            self.store.apply_verified_t0_motion(rev)

if __name__=='__main__':
    unittest.main()
