"""Isolated no-printer tests for exact-match backed-up jog speed upgrade."""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_jog_upgrade as upgrade

SOURCE=Path(__file__).resolve().parents[1]/'vendor/cxm/cxm_native_toolchange.cfg'

class NativeJogUpgradeTests(unittest.TestCase):
    def make_old(self,root):
        source=SOURCE.read_text('utf8')
        self.assertEqual(source.count(upgrade.NEW_REV),1)
        self.assertEqual(source.count(upgrade.NEW_FEED),1)
        old=source.replace(upgrade.NEW_REV,upgrade.OLD_REV).replace(upgrade.NEW_FEED,upgrade.OLD_FEED)
        path=Path(root)/'cxm_native_toolchange.cfg'
        path.write_text(old,'utf8')
        return path,old

    def test_only_jog_revision_and_feed_change_with_verified_backup(self):
        with TemporaryDirectory() as root:
            path,before=self.make_old(root)
            inspected=upgrade.inspect(path)
            self.assertEqual(inspected['state'],'needs_apply')
            result=upgrade.apply(path,inspected['sha256'])
            self.assertTrue(result['installed'])
            self.assertTrue(result['restart_required'])
            after=path.read_text('utf8')
            expected=before.replace(upgrade.OLD_REV,upgrade.NEW_REV).replace(upgrade.OLD_FEED,upgrade.NEW_FEED)
            self.assertEqual(after,expected)
            backup=path.with_name(result['backup'])
            self.assertEqual(backup.read_text('utf8'),before)
            self.assertEqual(upgrade.inspect(path)['state'],'installed')
            self.assertTrue(upgrade.apply(path,upgrade.inspect(path)['sha256'])['already_installed'])

    def test_rejects_changed_preview_without_writing(self):
        with TemporaryDirectory() as root:
            path,before=self.make_old(root)
            with self.assertRaisesRegex(upgrade.JogUpgradeError,'changed since preview'):
                upgrade.apply(path,'0'*64)
            self.assertEqual(path.read_text('utf8'),before)
            self.assertFalse(list(Path(root).glob('*.bak')))

    def test_rejects_partial_or_unknown_macros(self):
        with TemporaryDirectory() as root:
            path,before=self.make_old(root)
            path.write_text(before.replace(upgrade.OLD_FEED,'{% set feed=777 %}'),'utf8')
            with self.assertRaisesRegex(upgrade.JogUpgradeError,'Unknown or partially'):
                upgrade.inspect(path)

if __name__=='__main__':
    unittest.main()
