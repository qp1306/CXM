import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from cxm_config import (Store, template, render, parse, LEGACY_FIELDS,
                        V2_GLOBAL_FIELDS, V2_FIELDS, SCHEMA)

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
    def test_gantry_dock_xy_save_single_commit_and_rollback(self):
        rev=self.store.read()['revision']
        old=self.store.read()['config']['tools'][0].copy()
        saved=self.store.save_dock(0, {'x':172.00625,'y':175.00625}, rev)
        self.assertTrue(saved['saved'])
        self.assertFalse(saved['verified_pickup'])
        self.assertFalse(saved['active_in_klipper'])
        tool=self.store.read()['config']['tools'][0]
        self.assertEqual([tool[k] for k in ('dock_x','dock_y','dock_z')],[172.00625,175.00625,None])
        self.assertEqual(len(self.store.history()),1)
        self.store.rollback(saved['backup'],saved['revision'])
        self.assertEqual(self.store.read()['config']['tools'][0],old)
    def test_dock_validation_does_not_change_disk(self):
        rev=self.store.read()['revision']
        for xy in ({'x':25}, {'x':25,'y':25,'z':None},
                    {'x':25,'y':float('nan')}, {'x':700,'y':25},
                    {'x':25,'y':25,'extra':10}):
            with self.assertRaises(ValueError):
                self.store.save_dock(0,xy,rev)
        self.assertEqual(len(self.store.history()),0)
        self.assertEqual(self.store.read()['revision'],rev)
        self.store.set_value('global','tool_count',3,rev)
        rev=self.store.read()['revision']
        with self.assertRaises(ValueError):
            self.store.save_dock(4,{'x':3,'y':4},rev)
        with self.assertRaises(RuntimeError):
            self.store.save_dock(0,{'x':3,'y':4},'0'*64)
        self.assertEqual(len(self.store.history()),1)
    def test_xy_save_clears_legacy_dock_z_but_not_nozzle_offset(self):
        data=self.store.read()['config']
        data['tools'][0]['dock_z']=291.5
        data['tools'][0]['offset_z']=0.375
        self.store._atomic(self.store.path,render(data))
        revision=self.store.read()['revision']
        result=self.store.save_dock(0,{'x':298.62,'y':65.57},revision)
        tool=self.store.read()['config']['tools'][0]
        self.assertTrue(result['saved'])
        self.assertEqual(tool['dock_x'],298.62)
        self.assertEqual(tool['dock_y'],65.57)
        self.assertIsNone(tool['dock_z'])
        self.assertEqual(tool['offset_z'],0.375)
        self.assertEqual(len(self.store.history()),1)

    def test_xy_dock_save_does_not_need_z(self):
        revision=self.store.read()['revision']
        result=self.store.save_dock(0,{'x':298.62,'y':65.57},revision)
        self.assertTrue(result['saved'])
        self.assertEqual(self.store.read()['config']['tools'][0]['dock_z'],None)
        unchanged=self.store.save_dock(0,{'x':298.62,'y':65.57},result['revision'])
        self.assertTrue(unchanged['unchanged'])
        self.assertEqual(len(self.store.history()),1)

    def test_save_xy_offsets_atomically_and_rollback(self):
        original=self.store.read()
        before=original['config']['tools'][1].copy()
        result=self.store.save_offsets(1,'xy',{'x':0.12,'y':-0.08},original['revision'])
        self.assertTrue(result['saved'])
        self.assertFalse(result['active_in_klipper'])
        self.assertFalse(result['physically_verified'])
        saved=self.store.read()['config']['tools'][1]
        self.assertEqual((saved['offset_x'],saved['offset_y']),(0.12,-0.08))
        self.assertFalse(saved['offset_xy_accepted'])
        self.assertEqual(len(self.store.history()),1)
        self.store.rollback(result['backup'],result['revision'])
        self.assertEqual(self.store.read()['config']['tools'][1],before)

    def test_save_z_offset_only_preserves_xy(self):
        revision=self.store.read()['revision']
        first=self.store.save_offsets(1,'xy',{'x':0.15,'y':-0.2},revision)
        saved=self.store.save_offsets(1,'z',{'z':0.06},first['revision'])
        tool=self.store.read()['config']['tools'][1]
        self.assertEqual([tool['offset_x'],tool['offset_y'],tool['offset_z']],[0.15,-0.2,0.06])
        self.assertFalse(tool['offset_z_accepted'])
        self.assertFalse(saved['physically_verified'])
        unchanged=self.store.save_offsets(1,'z',{'z':0.06},saved['revision'])
        self.assertTrue(unchanged['unchanged'])
        self.assertEqual(len(self.store.history()),2)

    def test_t0_relative_offset_stays_zero(self):
        original=self.store.read()
        for axes,values in [('xy',{'x':0.01,'y':0}),('z',{'z':0.01})]:
            with self.assertRaises(ValueError):
                self.store.save_offsets(0,axes,values,original['revision'])
        self.assertEqual(self.store.read()['revision'],original['revision'])
        same=self.store.save_offsets(0,'xy',{'x':0,'y':0},original['revision'])
        self.assertTrue(same['unchanged'])

    def test_offsets_reject_invalid_and_stale_requests(self):
        revision=self.store.read()['revision']
        cases=[('xy',{'x':0.1}),('xy',{'x':0,'y':float('nan')}),
               ('xy',{'x':25,'y':0}),('z',{'z':11}),('z',{'x':0,'z':0})]
        for axes,values in cases:
            with self.assertRaises(ValueError):
                self.store.save_offsets(1,axes,values,revision)
        with self.assertRaises(RuntimeError):
            self.store.save_offsets(1,'xy',{'x':0,'y':0},'0'*64)
        self.assertEqual(len(self.store.history()),0)

    def test_dock_partial_write_failure_is_not_accepted(self):
        initial=self.store.read()
        with mock.patch('cxm_config.os.replace',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.store.save_dock(0,{'x':3,'y':4},initial['revision'])
        self.assertEqual(initial,self.store.read())

    def test_schema_three_default_never_ready_and_verification_protected(self):
        data=self.store.read()
        self.assertEqual(data['config']['schema'],3)
        self.assertFalse(data['migration_required'])
        self.assertFalse(data['config']['tools'][10]['maintenance_lockout'])
        for t in data['config']['tools']:
            self.assertFalse(t['commissioned'])
            self.assertFalse(t['dock_verified'])
            self.assertFalse(t['offset_xy_accepted'])
        rev=data['revision']
        for key in ('commissioned','pickup_verified','dock_verified',
                    'offset_xy_accepted','offset_z_accepted'):
            with self.assertRaises(ValueError):
                self.store.set_value(0,key,True,rev)
        self.assertEqual(self.store.read()['revision'],rev)

    def test_legacy_read_only_projection_and_explicit_atomic_migration(self):
        original=self.store.read()['config']
        legacy={'schema':1,'globals':{k:original['globals'][k] for k in V2_GLOBAL_FIELDS},
                'tools':[{k:tool[k] for k in LEGACY_FIELDS if k!='enabled'}
                         |{'enabled':n<6} for n,tool in enumerate(original['tools'])]}
        legacy['globals']['tool_count']=12
        legacy['tools'][2]['enabled']=False   # possible manual disable
        legacy['tools'][10]['dock_x']=279.25
        legacy['tools'][10]['offset_y']=0.123
        lines=['[gcode_macro _CXM_VARIABLES]','variable_schema_version: 1',
               'variable_globals: '+repr(legacy['globals'])]
        lines += ['variable_t%d: %s'%(n,repr(t)) for n,t in enumerate(legacy['tools'])]
        lines += ['gcode:', '  {% set cxm_values_loaded = 1 %}', '']
        old='\n'.join(lines)
        self.store.path.write_text(old)
        before=self.store.read()
        self.assertTrue(before['migration_required'])
        self.assertEqual(before['config']['tools'][10]['dock_x'],279.25)
        self.assertFalse(before['config']['tools'][10]['maintenance_lockout'])
        self.assertTrue(before['config']['tools'][2]['maintenance_lockout'])
        self.assertFalse(before['config']['tools'][10]['commissioned'])
        with self.assertRaises(RuntimeError):
            self.store.set_value(10,'offset_y',0.77,before['revision'])
        with self.assertRaises(RuntimeError):
            self.store.save_dock(10,{'x':2,'y':3},before['revision'])
        self.assertEqual(self.store.path.read_text(),old)
        self.assertEqual(self.store.history(),[])
        with self.assertRaises(RuntimeError):
            self.store.migrate('0'*64)
        migration=self.store.migrate(before['revision'])
        self.assertTrue(migration['saved'])
        self.assertFalse(self.store.read()['migration_required'])
        self.assertEqual(self.store.read()['config']['schema'],SCHEMA)
        self.assertEqual(len(self.store.history()),1)
        self.assertEqual((self.store.backups/migration['backup']).read_text(),old)
        self.assertEqual(self.store.read()['config']['tools'][10]['offset_y'],0.123)
        self.assertFalse(self.store.read()['config']['tools'][10]['commissioned'])
        restored=self.store.rollback(migration['backup'],migration['revision'])
        self.assertEqual(self.store.read()['config']['schema'],3)
        self.assertFalse(self.store.read()['migration_required'])
        self.assertEqual(self.store.read()['config']['tools'][10]['dock_x'],279.25)
        self.assertTrue(restored['saved'])

    def test_legacy_migration_atomic_failure_keeps_source(self):
        config=self.store.read()['config']
        values=[dict(t,enabled=i<6) for i,t in enumerate(config['tools'])]
        for tool in values:
            for key in list(tool):
                if key not in LEGACY_FIELDS:
                    del tool[key]
        old='[gcode_macro _CXM_VARIABLES]\nvariable_schema_version: 1\nvariable_globals: '+repr({k:config['globals'][k] for k in V2_GLOBAL_FIELDS})+'\n'
        old+=''.join('variable_t%d: %s\n'%(i,repr(t)) for i,t in enumerate(values))
        old+='gcode:\n  {% set cxm_values_loaded = 1 %}\n'
        self.store.path.write_text(old)
        rev=self.store.read()['revision']
        with mock.patch('cxm_config.os.replace',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.store.migrate(rev)
        self.assertEqual(self.store.path.read_text(),old)
        self.assertTrue(self.store.read()['migration_required'])

    def test_schema2_migration_preserves_coordinates_but_requires_new_cxchanger_datum(self):
        config=self.store.read()['config']
        old_cfg={'schema':2,
            'globals':{k:config['globals'][k] for k in V2_GLOBAL_FIELDS},
            'tools':[{k:t[k] for k in V2_FIELDS} for t in config['tools']]}
        old_cfg['tools'][0]['dock_x']=301.38
        old_cfg['tools'][0]['dock_y']=65.99
        lines=['[gcode_macro _CXM_VARIABLES]', 'variable_schema_version: 2',
               'variable_globals: '+repr(old_cfg['globals'])]
        lines += ['variable_t%d: %r'%(i,t) for i,t in enumerate(old_cfg['tools'])]
        lines+=['gcode:', '']
        old='\n'.join(lines)
        self.store.path.write_text(old)
        state=self.store.read()
        self.assertTrue(state['migration_required'])
        self.assertEqual(state['config']['tools'][0]['dock_x'],301.38)
        self.assertFalse(state['config']['tools'][0]['dock_reference_accepted'])
        with self.assertRaises(RuntimeError):
            self.store.save_dock(0,{'x':301.38,'y':65.99},state['revision'])
        result=self.store.migrate(state['revision'])
        self.assertEqual(self.store.read()['config']['schema'],3)
        self.assertFalse(self.store.read()['migration_required'])
        self.assertFalse(self.store.read()['config']['tools'][0]['dock_reference_accepted'])
        self.assertEqual((self.store.backups/result['backup']).read_text(),old)

    def test_save_lineux_raw_and_cxchanger_datum_as_two_values_with_verified_conversion(self):
        state=self.store.read()
        raw={'x':299.0,'y':66.0}
        actual={'x':299.0,'y':66.0}
        with self.assertRaisesRegex(ValueError,'must equal Lineux'):
            self.store.save_dock(0,{'x':302.0,'y':66.0},state['revision'],raw_xy=raw)
        res=self.store.save_dock(0,actual,state['revision'],raw_xy=raw)
        t=self.store.read()['config']['tools'][0]
        self.assertEqual([t['lineux_raw_x'],t['lineux_raw_y']],[299.0,66.0])
        self.assertTrue(t['dock_reference_accepted'])
        self.assertEqual([t['dock_x'],t['dock_y']],[299.0,66.0])
        self.assertEqual(len(self.store.history()),1)
        updated=self.store.set_value('global','x_docking_adjust',3,res['revision'])
        self.assertFalse(self.store.read()['config']['tools'][0]['dock_reference_accepted'])
        self.assertTrue(updated['saved'])

    def test_maintenance_and_speed_invalidate_previous_verification(self):
        data=self.store.read()['config']
        t=data['tools'][0]
        for key in ('dock_verified','pickup_verified','dropoff_verified','commissioned',
                    'offset_xy_accepted','offset_xy_verified','offset_z_accepted','offset_z_verified'):
            t[key]=True
        t.update({'dock_x':22.0,'dock_y':23.0,'dock_z':24.0})
        self.store._atomic(self.store.path,render(data)) # simulate previously verified records
        rev=self.store.read()['revision']
        self.store.set_value(0,'offset_x',0.12,rev)
        t=self.store.read()['config']['tools'][0]
        self.assertFalse(t['offset_xy_accepted'])
        self.assertFalse(t['offset_xy_verified'])
        self.assertFalse(t['commissioned'])
        rev=self.store.read()['revision']
        self.store.set_value(0,'dock_speed',900,rev)
        t=self.store.read()['config']['tools'][0]
        self.assertFalse(t['pickup_verified'])
        self.assertFalse(t['dropoff_verified'])
        rev=self.store.read()['revision']
        self.store.set_value('global','x_docking_adjust',4,rev)
        self.assertFalse(self.store.read()['config']['tools'][0]['dock_verified'])

    def test_no_nan_or_out_of_range(self):
        rev=self.store.read()['revision']
        for field,value in [('dock_x',float('nan')),('dock_x',float('inf')),('dock_x',1000),('offset_z',100),('maintenance_lockout',1)]:
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
