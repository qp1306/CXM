import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_config import Store
from cxm_service import Handler, printer_safe

class TestAPI(unittest.TestCase):
    def setUp(self):
        # Disk/API tests isolate the not-yet-installed Klipper macro controller.
        self.native_patcher=patch('cxm_service.native_invalidate',return_value={'invalidated':False})
        self.native_patcher.start()
        self.dir=tempfile.TemporaryDirectory()
        self.store=Store(self.dir.name)
        self.store.initialize()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.store=self.store
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.dir.cleanup()
        self.native_patcher.stop()
    def call(self,path,body=None,headers=None):
        payload=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(f'http://127.0.0.1:{self.port}{path}',data=payload,headers=headers or {})
        with urllib.request.urlopen(req,timeout=5) as response:
            return json.load(response)
    def test_read_and_guarded_autosave(self):
        current=self.call('/v1/config')
        body={'tool':0,'key':'dock_x','value':172.55,'expected_revision':current['revision']}
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.call('/v1/setting',body,headers={'Content-Type':'application/json'})
        self.assertEqual(err.exception.code,403)
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}',
                 'X-Requested-With':'CXM'}
        with patch('cxm_service.printer_safe',return_value=True):
            updated=self.call('/v1/setting',body,headers)
        self.assertTrue(updated['saved'])
        self.assertNotEqual(current['revision'],updated['revision'])
        self.assertFalse(updated['active_in_klipper'])
        self.assertEqual(self.call('/v1/config')['config']['tools'][0]['dock_x'],172.55)
    def test_gantry_xy_dock_endpoint_and_validation(self):
        current=self.call('/v1/config')
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}',
                 'X-Requested-With':'CXM'}
        body={'tool':0,'xy':{'x':172.5,'y':175.0},
              'expected_revision':current['revision']}
        with patch('cxm_service.printer_safe',return_value=True):
            saved=self.call('/v1/dock',body,headers)
        self.assertTrue(saved['saved'])
        self.assertFalse(saved['verified_pickup'])
        self.assertFalse(saved['active_in_klipper'])
        self.assertEqual(len(self.store.history()),1)
        self.assertEqual(self.call('/v1/config')['config']['tools'][0]['dock_y'],175)
        self.assertIsNone(self.call('/v1/config')['config']['tools'][0]['dock_z'])
        with patch('cxm_service.printer_safe',return_value=True):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/v1/dock',body,headers)
        self.assertEqual(error.exception.code,409)
        with patch('cxm_service.printer_safe',return_value=False):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/v1/dock',{'tool':0,'xy':{'x':1,'y':2},
                                      'expected_revision':saved['revision']},headers)
        self.assertEqual(error.exception.code,409)

    def test_fine_adjust_x_preserves_y_and_rejects_replay(self):
        headers = {'Content-Type':'application/json', 'X-Requested-With':'CXM',
                   'Origin':f'http://127.0.0.1:{self.port}'}
        with patch('cxm_service.printer_safe', return_value=True):
            rev = self.store.read()['revision']
            rev = self.store.set_value('global','cxm_shift_x',4.4,rev)['revision']
            saved = self.store.save_dock(2, {'x':222.01,'y':65.6}, rev)
            body = {'tool':2, 'hundredths':-10, 'expected_revision':saved['revision']}
            reply = self.call('/v1/dock/fine-x', body, headers)
            self.assertTrue(reply['backup'])
            entry = self.store.read()['config']['tools'][2]
            self.assertEqual((entry['dock_x'],entry['dock_y']), (221.91,65.6))
            for rejected in (body, dict(body, tool=1, expected_revision=reply['revision']),
                             dict(body, hundredths=101, expected_revision=reply['revision'])):
                with self.assertRaises(urllib.error.HTTPError):
                    self.call('/v1/dock/fine-x', rejected, headers)
            self.assertEqual(self.store.read()['revision'], reply['revision'])

    def test_reject_legacy_xyz_without_touching_config(self):
        current=self.call('/v1/config')
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}',
                 'X-Requested-With':'CXM'}
        with patch('cxm_service.printer_safe',return_value=True):
            with self.assertRaises(urllib.error.HTTPError) as err:
                self.call('/v1/dock',{'tool':0,'xyz':{'x':298,'y':66,'z':20},
                    'expected_revision':current['revision']},headers)
        self.assertEqual(err.exception.code,400)
        self.assertEqual(self.call('/v1/config')['revision'],current['revision'])

    def test_atomic_xy_and_z_offset_endpoint(self):
        current=self.call('/v1/config')
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}',
                 'X-Requested-With':'CXM'}
        with patch('cxm_service.printer_safe',return_value=True):
            xy=self.call('/v1/offset',{'tool':1,'axes':'xy',
                'values':{'x':0.12,'y':-0.08},
                'expected_revision':current['revision']},headers)
            z=self.call('/v1/offset',{'tool':1,'axes':'z',
                'values':{'z':0.045},
                'expected_revision':xy['revision']},headers)
            self.assertTrue(xy['saved'])
            self.assertTrue(z['saved'])
            self.assertFalse(z['physically_verified'])
            tool=self.call('/v1/config')['config']['tools'][1]
            self.assertEqual([tool['offset_x'],tool['offset_y'],tool['offset_z']],
                             [0.12,-0.08,0.045])
            self.assertFalse(tool['commissioned'])
            with self.assertRaises(urllib.error.HTTPError) as exc:
                self.call('/v1/offset',{'tool':1,'axes':'xy',
                    'values':{'x':0.1},'expected_revision':z['revision']},headers)
            self.assertEqual(exc.exception.code,400)

    def test_only_expected_primary_mcu_error_is_dev_safe(self):
        import io
        def response(state, message):
            result={'result':{'state':state,'state_message':message}}
            return io.BytesIO(json.dumps(result).encode())
        with patch('cxm_service.urllib.request.urlopen',return_value=response(
            'error',"mcu 'mcu': Unable to connect\nError configuring printer")):
            self.assertTrue(printer_safe())
        with patch('cxm_service.urllib.request.urlopen',return_value=response(
            'error',"Option 'serial' in section 'mcu' must be specified")):
            self.assertTrue(printer_safe())
        for state, msg in [('error',"mcu 'toolboard1': Unable to connect"),
                           ('shutdown',"mcu 'mcu': Unable to connect"),
                           ('error','MCU lost steps'),('startup','printer starting')]:
            with patch('cxm_service.urllib.request.urlopen',return_value=response(state,msg)):
                self.assertFalse(printer_safe())
    def test_schema2_migration_endpoint_and_readonly_legacy(self):
        import cxm_config
        config=self.store.read()['config']
        old_tools=[]
        for i,t in enumerate(config['tools']):
            item={key:t[key] for key in cxm_config.LEGACY_FIELDS if key!='enabled'}
            item['enabled']=i<6
            old_tools.append(item)
        raw=['[gcode_macro _CXM_VARIABLES]','variable_schema_version: 1',
             'variable_globals: '+repr({k:config['globals'][k] for k in cxm_config.V2_GLOBAL_FIELDS})]
        raw += ['variable_t%d: %s'%(i,repr(t)) for i,t in enumerate(old_tools)]
        raw += ['gcode:','  {% set cxm_values_loaded = 1 %}','']
        self.store.path.write_text('\n'.join(raw))
        current=self.call('/v1/config')
        self.assertTrue(current['migration_required'])
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}',
                 'X-Requested-With':'CXM'}
        with patch('cxm_service.printer_safe',return_value=True):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/v1/setting',{'tool':0,'key':'dock_x','value':12,
                                         'expected_revision':current['revision']},headers)
            self.assertEqual(error.exception.code,409)
            migrated=self.call('/v1/migrate',{'expected_revision':current['revision']},headers)
        self.assertTrue(migrated['saved'])
        self.assertFalse(self.call('/v1/config')['migration_required'])
        self.assertEqual(self.call('/v1/config')['config']['schema'],3)
        self.assertEqual(len(self.store.history()),1)
        with patch('cxm_service.printer_safe',return_value=True):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/v1/setting',{'tool':0,'key':'commissioned','value':True,
                                         'expected_revision':migrated['revision']},headers)
        self.assertEqual(error.exception.code,400)

    def test_unknown_printer_state_blocks(self):
        current=self.call('/v1/config')
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}',
                 'X-Requested-With':'CXM'}
        with patch('cxm_service.printer_safe',return_value=False):
            with self.assertRaises(urllib.error.HTTPError) as err:
                self.call('/v1/setting',{'tool':0,'key':'dock_x','value':172.55,
                    'expected_revision':current['revision']},headers)
        self.assertEqual(err.exception.code,409)
if __name__=='__main__':unittest.main()

