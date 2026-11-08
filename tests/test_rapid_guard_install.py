"""No-hardware CXM rapid guard installer regression tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"cxm_fast_guard_install.py"
spec=importlib.util.spec_from_file_location("cxm_fast_guard_install",SCRIPT)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SRC=Path(__file__).resolve().parents[1]/"vendor"/"cxm"/"cxm_fast_guard.cfg"

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.repo=self.root/"repo"
        (self.repo/"vendor"/"cxm").mkdir(parents=True)
        (self.repo/"vendor"/"cxm"/"cxm_fast_guard.cfg").write_bytes(SRC.read_bytes())
        self.printer=self.root/"printer_data"/"config"/"printer.cfg"
        self.printer.parent.mkdir(parents=True)
        self.printer.write_text(
            "[printer]\nkinematics: corexy\n\n"
            "#*# <---------------------- SAVE_CONFIG ---------------------->\n"
            "#*# [extruder]\n#*# control = pid\n",encoding="utf-8")
    def test_preflight_prepares_include_before_save_config_without_writing(self):
        prior=self.printer.read_bytes()
        source,dest,raw,updated,included=m.plan(self.repo,self.printer)
        self.assertFalse(included)
        self.assertEqual(self.printer.read_bytes(),prior)
        self.assertFalse(dest.exists())
        self.assertEqual(raw,SRC.read_bytes())
        self.assertIn(m.INCLUDE,updated)
        self.assertLess(updated.index(m.INCLUDE),updated.index("#*# <---"))
        self.assertNotIn("#*# "+m.INCLUDE,updated)

    def test_apply_idempotency_content_integrity_and_conflict_refusal(self):
        _,dest,data,updated,_=m.plan(self.repo,self.printer)
        m.atomic_bytes(dest,data)
        m.atomic_bytes(self.printer,updated.encode('utf-8'))
        _,_,_,same,included=m.plan(self.repo,self.printer)
        self.assertTrue(included)
        self.assertEqual(same,updated)
        dest.write_bytes(b'other custom macro')
        with self.assertRaisesRegex(RuntimeError,'differs'):
            m.plan(self.repo,self.printer)

    def test_duplicate_or_conflicting_macro_blocks_before_any_edit(self):
        raw=self.printer.read_text("utf-8")
        self.printer.write_text(raw+"\n"+m.INCLUDE+"\n"+m.INCLUDE+"\n")
        with self.assertRaisesRegex(RuntimeError,'Duplicate'):
            m.plan(self.repo,self.printer)
        self.printer.write_text(raw+"\n[gcode_macro CXM_FAST_VERIFY]\ngcode:\n  M117 wrong\n")
        with self.assertRaisesRegex(RuntimeError,'already defined'):
            m.plan(self.repo,self.printer)

    def test_macro_protocol_and_four_runtime_safety_checks_exist(self):
        raw=SRC.read_text("utf-8")
        for signal in ("PRESSED","RELEASED"):
            self.assertIn(signal,raw)
        for check in ("homed_axes","stepper_enable.steppers","virtual_sdcard",
                      "pause_resume","gcode_button cxm_tool_detect",
                      "position[2]","MIN_Y","cxm_rapid_protocol: 1"):
            self.assertIn(check,raw)
        self.assertEqual(raw.count("[gcode_macro CXM_FAST_VERIFY]"),1)

if __name__=='__main__':unittest.main()
