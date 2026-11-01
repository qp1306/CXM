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
    def test_all_axis_dock_endpoint_and_validation(self):
        current=self.call('/v1/config')
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}',
                 'X-Requested-With':'CXM'}
        body={'tool':0,'xyz':{'x':172.5,'y':175.0,'z':291.5},
              'expected_revision':current['revision']}
        with patch('cxm_service.printer_safe',return_value=True):
            saved=self.call('/v1/dock',body,headers)
        self.assertTrue(saved['saved'])
        self.assertFalse(saved['verified_pickup'])
        self.assertFalse(saved['active_in_klipper'])
        self.assertEqual(len(self.store.history()),1)
        self.assertEqual(self.call('/v1/config')['config']['tools'][0]['dock_y'],175)
        with patch('cxm_service.printer_safe',return_value=True):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/v1/dock',body,headers)
        self.assertEqual(error.exception.code,409)
        with patch('cxm_service.printer_safe',return_value=False):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.call('/v1/dock',{'tool':0,'xyz':{'x':1,'y':2,'z':3},
                                      'expected_revision':saved['revision']},headers)
        self.assertEqual(error.exception.code,409)

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

