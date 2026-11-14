"""Fresh commissioning reset: isolated disk Store + mocked Moonraker, never hardware."""
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import cxm_config as config
import cxm_native as native

ACK=native.RESET_COMMISSIONING_ACK

class FreshCommissioningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cxm-fresh-')
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.store=config.Store(self.folder)
        self.store.initialize()
        raw=config.template()
        raw['globals']['tool_count']=5
        raw['tools'][0].update(dock_x=304.60625,dock_y=65.6,dock_reference_accepted=True,
                              offset_x=0.0,offset_xy_accepted=True,commissioned=True)
        raw['tools'][1].update(dock_x=264.7,dock_y=65.6,dock_reference_accepted=True,
                              offset_x=1.5,offset_z=0.12,offset_xy_accepted=True)
        raw['tools'][3].update(dock_x=184.0,dock_y=65.0,dock_reference_accepted=True,
                              offset_z=0.33,offset_z_accepted=True)
        self.store._atomic(self.store.path,config.render(raw))
        self.previous=self.store.read()
        self.printer=self.folder/'printer.cfg'
        self.printer.write_text('LEAVE ALL PRINTER SETTINGS UNTOUCHED\n')

    def test_reset_keeps_backup_and_clears_every_tool(self):
        before=self.store.path.read_bytes()
        output=self.store.reset_commissioning(self.previous['revision'])
        after=self.store.read()
        self.assertTrue(output['reset_commissioning'])
        self.assertEqual(output['cleared_tools'],12)
        self.assertEqual(after['config']['globals']['tool_count'],1)
        for tool in after['config']['tools']:
            for key in ('dock_x','dock_y','dock_z','lineux_raw_x','lineux_raw_y'):
                self.assertIsNone(tool[key])
            for key in ('dock_reference_accepted','offset_xy_accepted','offset_z_accepted',
                        'dock_verified','offset_xy_verified','offset_z_verified',
                        'pickup_verified','dropoff_verified','commissioned'):
                self.assertFalse(tool[key])
            for key in ('offset_x','offset_y','offset_z'):
                self.assertEqual(tool[key],0.0)
        self.assertEqual((self.store.backups/output['backup']).read_bytes(),before)
        self.assertEqual(self.printer.read_text(),'LEAVE ALL PRINTER SETTINGS UNTOUCHED\n')

    def test_revision_conflict_does_not_edit_disk(self):
        before=self.store.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.store.reset_commissioning('0'*64)
        self.assertEqual(self.store.path.read_bytes(),before)

    def test_native_reset_fails_when_sensor_mounted(self):
        with patch.object(native,'_native_status',
            return_value=({'protocol':2,'ready':1},{'running':0},'PRESSED')), \
            patch.object(native,'_rpc') as rpc:
            with self.assertRaisesRegex(native.NativeError,'sensor must be RELEASED'):
                native.reset_commissioning(self.store,self.previous['revision'],ACK)
            rpc.assert_not_called()
        self.assertEqual(self.store.read()['revision'],self.previous['revision'])

    def test_native_invalidates_all_twelve_before_backed_up_disk_reset(self):
        old=({'protocol':2,'ready':1,'current_tool':-1,'fault':0},
             {'running':0},'RELEASED')
        live={'ready':0,'fault':1,'current_tool':-2,'tool_count':1,
              'camera_reference':[0,0,0,0],'profile':'standard'}
        for n in range(12):
            live[f't{n}_accepted']=0
            live[f't{n}_x']=-1.0
            live[f't{n}_y']=-1.0
        readback={'status':{
            'gcode_macro _CXM_NATIVE':live,
            'gcode_macro _CXM_TEST_STATE':{'running':0,'stop':0,'state':'idle'},
            'gcode_button cxm_tool_detect':{'state':'RELEASED'}}}
        dispatched=[]
        def rpc(path,payload=None):
            dispatched.append((path,payload))
            if path=='/printer/info':return {'state':'ready'}
            if path=='/printer/gcode/script':return {}
            if path.startswith('/printer/objects/query?'):return readback
            raise AssertionError(path)
        with patch.object(native,'_native_status',return_value=old), \
             patch.object(native,'_rpc',side_effect=rpc), \
             patch('cxm_z_auto.CONTROLLER.reset_idle_history') as zreset, \
             patch.object(native,'MOVE_LOCK') as lock:
            lock.acquire.return_value=True
            result=native.reset_commissioning(self.store,self.previous['revision'],ACK)
            lock.release.assert_called_once()
            zreset.assert_called_once()
        self.assertTrue(result['native_inhibited'])
        self.assertTrue(result['z_session_cleared'])
        sent=dispatched[1][1]['script']
        self.assertIn('UPDATE_DELAYED_GCODE ID=CXM_NATIVE_TEST_STEP DURATION=0',sent)
        self.assertIn('VARIABLE=ready VALUE=0',sent)
        self.assertIn('VARIABLE=current_tool VALUE=-2',sent)
        self.assertIn('VARIABLE=t11_accepted VALUE=0',sent)
        self.assertIn('VARIABLE=t0_x VALUE=-1.0',sent)
        self.assertNotRegex(sent,r'(?m)^\\s*(?:G0|G1|G28)\\s')
        self.assertEqual(self.store.read()['config']['globals']['tool_count'],1)

if __name__=='__main__':
    unittest.main()
