"""Clean-room CXM installation test: never touches the user's Pi or printer.

Verifies the macro installers against a fresh isolated printer_data/config,
then first-save T0..T11, native geometry sync and the absence of old state.
Does NOT simulate motors, sensors, Klipper parsing or physical collisions.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from cxm_config import Store
from cxm_cxchanger import plan
import cxm_native as native


class CleanRoomInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='cxm-clean-')
        self.addCleanup(self.tmp.cleanup)
        self.config=Path(self.tmp.name)/'printer_data'/'config'
        self.config.mkdir(parents=True)
        self.printer=self.config/'printer.cfg'
        self.baseline=('[printer]\nkinematics: corexy\nmax_velocity: 800\n'
                       '# PROTECT existing printer/homing/MCU/Z settings\n'
                       '[stepper_z3]\nstep_pin: untouched-pin\n')
        self.printer.write_text(self.baseline,encoding='utf8')
        self.store=Store(self.config)

    def installer(self, name, apply=False, printer=None):
        cmd=[sys.executable,str(ROOT/'scripts'/name),'--repo',str(ROOT),
             '--printer-config',str(printer or self.printer)]
        if apply:
            cmd.append('--apply')
        return subprocess.run(cmd,text=True,capture_output=True,timeout=20)

    def test_clean_macro_install_is_dry_run_first_backup_and_idempotent(self):
        self.assertFalse((self.config/'CXM_variables.cfg').exists())
        self.assertFalse((self.config/'cxm_fast_guard.cfg').exists())
        self.assertFalse((self.config/'cxm_native_toolchange.cfg').exists())
        for name in ('cxm_fast_guard_install.py','cxm_native_install.py'):
            # Native requires fast-guard include; its first preflight must
            # reject that missing prerequisite, without modifying files.
            result=self.installer(name)
            if name=='cxm_native_install.py':
                self.assertNotEqual(result.returncode,0)
            else:
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(self.printer.read_text('utf8'),self.baseline)
        for name in ('cxm_fast_guard_install.py','cxm_native_install.py'):
            before=self.printer.read_bytes()
            first=self.installer(name)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            self.assertEqual(self.printer.read_bytes(),before,'dry-run changed printer.cfg')
            applied=self.installer(name,apply=True)
            self.assertEqual(applied.returncode,0,applied.stdout+applied.stderr)
            reapply=self.installer(name,apply=True)
            self.assertEqual(reapply.returncode,0,reapply.stdout+reapply.stderr)
        printer=self.printer.read_text('utf8')
        self.assertIn(self.baseline,printer)
        for component in ('cxm_fast_guard.cfg','cxm_native_toolchange.cfg'):
            self.assertEqual(len(re.findall(
                r'(?m)^\[include '+re.escape(component)+r'\]$',printer)),1)
            self.assertEqual((self.config/component).read_bytes(),
                (ROOT/'vendor/cxm'/component).read_bytes())
        self.assertIn('[gcode_macro CXM_MANUAL_DOCK_JOG]',
            (self.config/'cxm_native_toolchange.cfg').read_text('utf8'))
        self.assertNotIn('dock_locate_calibrate.cfg',printer)
        self.assertNotIn('toolchange-EN.cfg',printer)
        self.assertTrue(list((self.config/'cxm_backups').iterdir()),
                        'First install did not create backups')

    def test_first_capture_save_all_twelve_tools_and_sync_paths(self):
        self.assertTrue(self.store.initialize()['created'])
        default=self.store.read()
        self.assertEqual(default['config']['globals']['cxm_shift_x'],4.4)
        self.assertEqual(default['config']['globals']['cxm_safe_clearance_y'],100)
        self.assertFalse(any(t['dock_reference_accepted'] for t in
                             default['config']['tools']))
        self.store.set_value('global','tool_count',12,default['revision'])
        for t in range(12):
            before=self.store.read()
            x=304.60625-12*t
            y=65.6
            result=self.store.save_dock(t,{'x':x,'y':y},before['revision'])
            self.assertTrue(result['saved'])
            saved=self.store.read()
            entry=saved['config']['tools'][t]
            self.assertEqual((entry['dock_x'],entry['dock_y']),(x,y))
            self.assertTrue(entry['dock_reference_accepted'])
            path=plan(saved,tool=t)
            self.assertEqual(path['pickup'],[(x,y),(x+4.4,y),(x+4.4,y+100)])
            self.assertEqual(path['dropoff'],[(x+4.4,y),(x,y),(x,y+100)])
        self.assertTrue(list((self.config/'cxm_backups').iterdir()))
        scripts=[]
        def rpc(path,body=None,**kw):
            if path=='/printer/info':
                return {'state':'ready'}
            if path=='/printer/gcode/script':
                scripts.append(body['script'])
                return {}
            raise AssertionError('Unexpected hardware access: '+path)
        current=self.store.read()
        with patch.object(native,'_native_status',return_value=(
                {'protocol':2,'current_tool':-2,'fault':1,'ready':0},
                {'running':0},'RELEASED')),patch.object(native,'_rpc',side_effect=rpc):
            result=native.sync(self.store,current['revision'],declared_tool=-1)
        self.assertTrue(result['synced'])
        self.assertEqual(result['accepted_tools'],list(range(12)))
        self.assertEqual(len(scripts),1)
        self.assertNotRegex(scripts[0],r'(?m)^\s*(G0|G1|G28)\b')
        self.assertIn('VARIABLE=t0_x VALUE=304.60625',scripts[0])
        self.assertIn('VARIABLE=t11_accepted VALUE=1',scripts[0])
        self.assertIn('VARIABLE=shift_x VALUE=4.4',scripts[0])
        self.assertIn('VARIABLE=clearance_y VALUE=100.0',scripts[0])

    def test_collision_fails_closed_before_installing_native_file(self):
        self.installer('cxm_fast_guard_install.py',apply=True)
        with self.printer.open('a') as f:
            f.write('\n[gcode_macro CXM_SELECT_TOOL]\ngcode:\n    M400\n')
        before=self.printer.read_bytes()
        result=self.installer('cxm_native_install.py',apply=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('collide',result.stdout.lower()+result.stderr.lower())
        self.assertEqual(self.printer.read_bytes(),before)
        self.assertFalse((self.config/'cxm_native_toolchange.cfg').exists())

    def test_clean_store_is_idempotent_and_does_not_seed_old_coordinates(self):
        self.assertTrue(self.store.initialize()['created'])
        unchanged=self.store.read()
        self.assertFalse(self.store.initialize()['created'])
        self.assertEqual(self.store.read()['revision'],unchanged['revision'])
        self.assertTrue(all(t['dock_x'] is None and t['dock_y'] is None
                            for t in unchanged['config']['tools']))


if __name__=='__main__':
    unittest.main()
