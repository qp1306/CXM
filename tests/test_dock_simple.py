"""Simple Dock XY commissioning, tested without hardware or filament sensor."""
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_dock_simple as m

class Store:
    def __init__(self):
        self.rev='a'*64
        self.xyz=[299.5,65.5,15.0]
        self.homed=True
        self.ready=True
        self.native={'ready':1,'fault':0,'current_tool':0}
        self.commands=[]
        self.saved=[]
        self.config={'globals':{'tool_count':5,'cxm_shift_x':4.4,'cxm_safe_clearance_y':100.0},
                     'tools':[{'dock_x':None,'dock_y':None,'dock_reference_accepted':False} for _ in range(12)]}
    def read(self):
        return {'revision':self.rev,'config':self.config}
    def save_dock(self,tool,xy,revision):
        assert revision==self.rev
        t=self.config['tools'][tool]
        t.update(dock_x=xy['x'],dock_y=xy['y'],dock_reference_accepted=True)
        self.saved.append((tool,dict(xy)))
        self.rev='b'*64
        return {'saved':True,'backup':'dock-backup.cfg'}
    def rpc(self,path,payload=None):
        if path.startswith('/printer/objects/query?'):
            if 'toolhead=' in path:
                return {'status':{
                    'webhooks':{'state':'ready' if self.ready else 'error'},
                    'toolhead':{'homed_axes':'xyz' if self.homed else '',
                        'position':list(self.xyz),'axis_minimum':[29.0,54.0,0.0],
                        'axis_maximum':[334.0,362.0,330.0]},
                    'idle_timeout':{'state':'Idle'},
                    'print_stats':{'state':'standby'},
                    'gcode_macro _CXM_TEST_STATE':{'running':0}}}
            return {'status':{'gcode_macro _CXM_NATIVE':dict(self.native),
                              'gcode_macro _CXM_TEST_STATE':{'running':0}}}
        if path=='/printer/gcode/script':
            script=payload['script']
            self.commands.append(script)
            if script=='G28':
                self.homed=True
            for line in script.splitlines():
                if line.startswith('G1 '):
                    for match in re.finditer(r'(X|Y|Z)(-?[0-9]+(?:\.[0-9]+)?)',line):
                        self.xyz['XYZ'.index(match[1])]=float(match[2])
                if line.startswith('SET_GCODE_VARIABLE'):
                    match=re.search(r'VARIABLE=(\w+) VALUE=(-?\d+)',line)
                    if match:self.native[match[1]]=int(match[2])
            return {}
        raise AssertionError('Unexpected Moonraker route: '+path)

class DockSimpleTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.patcher=patch.object(m,'_rpc',side_effect=self.store.rpc)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
    def kw(self):
        return dict(store=self.store,tool=0,expected_revision=self.store.rev)
    def test_home_then_enable_exact_z22_and_no_sensor(self):
        self.store.homed=False
        m.home(**self.kw())
        self.assertEqual(self.store.commands,['G28'])
        after=m.enable(**self.kw())
        self.assertEqual(after['xyz']['z'],22)
        self.assertIn('SAVE_GCODE_STATE NAME=CXM_SIMPLE_DOCK',self.store.commands[1])
        self.assertIn('G90\nG1 Z22 F1500',self.store.commands[1])
        self.assertIn('RESTORE_GCODE_STATE NAME=CXM_SIMPLE_DOCK MOVE=0',self.store.commands[1])
        self.assertEqual(len(self.store.commands),2)
    def test_jog_at_50mm_per_second(self):
        m.enable(**self.kw())
        d=m.jog(axis='x',distance=.1,**self.kw())
        self.assertAlmostEqual(d['xyz']['x'],299.6)
        self.assertIn('G1 X299.60000 F3000',self.store.commands[-1])
        self.assertNotIn('cxm_tool_detect',Path(m.__file__).read_text())
    def test_proven_pickup_and_release_path_returns_dock_datum(self):
        m.enable(**self.kw())
        result=m.test(**self.kw())
        self.assertTrue(result['tested'])
        moves=[x.strip() for x in self.store.commands[-1].splitlines() if x.startswith('G1')]
        self.assertEqual(moves,[
            'G1 Y165.50000 F6000',
            'G1 Y65.50000 F6000',
            'G1 X303.90000 F6000',
            'G1 Y165.50000 F6000',
            'G1 Y65.50000 F6000',
            'G1 X299.50000 F6000',
            'G1 Y165.50000 F6000',
            'G1 Y65.50000 F6000'])
        self.assertEqual(self.store.xyz,[299.5,65.5,22])
    def test_no_legacy_x325_limit(self):
        self.store.xyz=[328,65.5,22]
        self.assertTrue(m.test(**self.kw())['tested'])
        self.assertEqual(self.store.xyz[0],328)
    def test_physical_limits_still_enforced_by_klipper(self):
        self.store.xyz=[331,65.5,22]
        with self.assertRaisesRegex(m.DockSimpleError,'X move exceeds'):
            m.test(**self.kw())
        self.assertEqual(self.store.commands,[])
    def test_adjust_and_save_without_filament_or_retest_gates(self):
        m.enable(**self.kw())
        m.jog(axis='x',distance=.1,**self.kw())
        d=m.save(**self.kw())
        self.assertTrue(d['saved'])
        self.assertEqual(d['xy'],{'x':299.6,'y':65.5})
        self.assertEqual(self.store.saved[0][0],0)
        self.assertTrue(self.store.read()['config']['tools'][0]['dock_reference_accepted'])
        self.assertEqual(self.store.native,{'ready':0,'fault':1,'current_tool':-2})
    def test_only_one_normal_source_update_no_macro_installer(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'web/index.html').read_text()
        script=(root/'web/cxm-dock-simple.js').read_text()
        self.assertIn('cxm-dock-simple.js',html)
        self.assertNotIn('cxm-dock-verify-update.js',html)
        self.assertNotIn('FILAMENT',script)
        self.assertNotIn('sensor',script.lower())
        for label in ('Home printer','Select hotend','Enable jogging','Jog carriage into position',
                      'Test docking / undocking','Adjust X/Y if needed','Save coordinates','Next hotend'):
            self.assertIn(label,script)
if __name__=='__main__':
    unittest.main()
