import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_config import Store, template, render, parse

class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name)
        self.store.initialize()
    def tearDown(self):
        self.tmp.cleanup()
    def test_roundtrip_all_12(self):
        x=template()
        self.assertEqual(parse(render(x)),x)
        self.assertEqual(len(self.store.read()['config']['tools']),12)
    def test_save_and_persistence(self):
        state=self.store.read()
        saved=self.store.set_value(0,'dock_x',279.422,state['revision'])
        self.assertTrue(saved['saved'])
        self.assertFalse(saved['active_in_klipper'])
        self.assertEqual(self.store.read()['config']['tools'][0]['dock_x'],279.422)
        self.assertEqual(Store(self.tmp.name).read()['config']['tools'][0]['dock_x'],279.422)
        self.assertEqual(len(self.store.history()),1)
    def test_rollback(self):
        initial=self.store.read()
        updated=self.store.set_value(1,'offset_z',0.123,initial['revision'])
        rolled=self.store.rollback(updated['backup'],updated['revision'])
        self.assertEqual(self.store.read()['config'],initial['config'])
        self.assertEqual(len(self.store.history()),2)
        self.assertNotEqual(updated['revision'],rolled['revision'])
    def test_stale_revision_fails(self):
        old=self.store.read()['revision']
        self.store.set_value('global','safe_y',125,old)
        with self.assertRaises(RuntimeError):
            self.store.set_value(1,'dock_x',200,old)
        self.assertEqual(len(self.store.history()),1)
    def test_no_nan_or_out_of_range(self):
        rev=self.store.read()['revision']
        for field,value in [('dock_x',float('nan')),('dock_x',float('inf')),('dock_x',1000),('offset_z',100),('enabled',1)]:
            with self.assertRaises(ValueError):
                self.store.set_value(0,field,value,rev)
        self.assertEqual(self.store.read()['revision'],rev)
        self.assertEqual(len(self.store.history()),0)
    def test_malformed_file_is_rejected_not_overwritten(self):
        self.store.path.write_text('[gcode_macro bad]\ngcode:\n  G28\n')
        with self.assertRaises(ValueError):self.store.initialize()
    def test_atomic_failure_leaves_original(self):
        state=self.store.read()
        original=self.store.path.read_bytes()
        with mock.patch('cxm_config.os.replace',side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                self.store.set_value(0,'dock_y',188,state['revision'])
        self.assertEqual(self.store.path.read_bytes(),original)
    def test_concurrent_edit_conflict(self):
        revision=self.store.read()['revision']
        errors=[]
        def edit(n):
            try:self.store.set_value(n,'dock_x',n+100,revision)
            except RuntimeError as e: errors.append(str(e))
        t1=threading.Thread(target=edit,args=(0,));t2=threading.Thread(target=edit,args=(1,))
        t1.start();t2.start();t1.join();t2.join()
        self.assertEqual(len(errors),1)
        self.assertEqual(len(self.store.history()),1)

if __name__=='__main__':unittest.main()
