"""No-hardware tests: append-only locked-dock native macro installer."""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_dock_verify_install as m

SOURCE=Path(__file__).resolve().parents[1]/'vendor/cxm/cxm_native_toolchange.cfg'

class Tests(unittest.TestCase):
    def make_old(self,folder):
        source=SOURCE.read_text('utf8')
        self.assertEqual(source.count(m.MARKER),1)
        old=source[:source.index(m.MARKER)].rstrip()+'\n'
        target=Path(folder)/'cxm_native_toolchange.cfg'
        target.write_text(old,'utf8')
        return target,old
    def test_appends_only_approved_macro_and_preserves_prior_code(self):
        with TemporaryDirectory() as folder:
            target,old=self.make_old(folder)
            preview=m.inspect(target)
            self.assertEqual(preview['state'],'needs_apply')
            result=m.apply(target,preview['sha256'])
            self.assertTrue(result['restart_required'])
            updated=target.read_text('utf8')
            self.assertTrue(updated.startswith(old.rstrip()))
            self.assertEqual(updated.count(m.MARKER),1)
            self.assertEqual(m.inspect(target)['state'],'installed')
            self.assertEqual(target.with_name(result['backup']).read_text('utf8'),old)
    def test_stale_sha_refused_without_writing(self):
        with TemporaryDirectory() as folder:
            target,old=self.make_old(folder)
            with self.assertRaisesRegex(m.DockVerifyInstallError,'changed since preview'):
                m.apply(target,'0'*64)
            self.assertEqual(target.read_text('utf8'),old)
            self.assertFalse(list(Path(folder).glob('*.bak')))
    def test_unknown_existing_macro_refused(self):
        with TemporaryDirectory() as folder:
            target,old=self.make_old(folder)
            target.write_text(old+'\n'+m.MARKER+'\ngcode:\n    G1 X1 F3000\n','utf8')
            with self.assertRaisesRegex(m.DockVerifyInstallError,'differs'):
                m.inspect(target)
if __name__=='__main__':
 unittest.main()
