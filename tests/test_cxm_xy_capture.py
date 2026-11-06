"""Run: python3 -m unittest discover -s tests -p 'test_cxm_xy_capture.py' -v"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cxm_xy_capture import (CaptureError,parse_mcu,extract_marked_snapshot,
                            motor_delta,verify_z_unchanged,reconstruct_known_xy,validate_preflight,Moonraker)
from cxm_xy_measure import CoreXYTransform

class CaptureTests(unittest.TestCase):
    def test_parse_mcu(self):
        self.assertEqual(parse_mcu('// mcu: stepper_x:-50 stepper_y:120 stepper_z:4 stepper_z1:5'),
                         {'stepper_x':-50,'stepper_y':120,'stepper_z':4,'stepper_z1':5})
        with self.assertRaises(CaptureError):
            parse_mcu('// mcu: stepper_x:5 stepper_x:6')

    def test_markers(self):
        token='A1B2'
        es=[{'type':'response','message':'// CXMXY_A1B2_START'},
            {'type':'response','message':'// mcu: stepper_x:10 stepper_y:-20 stepper_z:30'},
            {'type':'response','message':'// CXMXY_A1B2_END'}]
        self.assertEqual(extract_marked_snapshot(es,token)['stepper_y'],-20)
        es.insert(1,{'type':'command','message':'G1 X100'})
        with self.assertRaises(CaptureError):
            extract_marked_snapshot(es,token)

    def test_reconstruction(self):
        m=CoreXYTransform.calibrate(10,(800,800),10,(800,-800))
        # Known starting point 180,172; endstop 335,362
        known=(180,172); ending=(335,362)
        a,b=(800*(155+190)/10,800*(155-190)/10)
        data=reconstruct_known_xy(matrix=m,before={'stepper_x':0,'stepper_y':0},
                                  after={'stepper_x':int(a),'stepper_y':int(b)},
                                  end_xy=ending,known_xy=known)
        self.assertTrue(data['passed'])
        self.assertEqual(data['inferred_start_xy_mm'],[180.0,172.0])

    def test_z_guard(self):
        before={'stepper_x':1,'stepper_y':2,'stepper_z':9,'stepper_z1':10}
        after={'stepper_x':100,'stepper_y':150,'stepper_z':9,'stepper_z1':10}
        verify_z_unchanged(before,after)
        after['stepper_z1']=11
        with self.assertRaises(CaptureError):
            verify_z_unchanged(before,after)

    def test_read_only_preflight(self):
        config={'toolhead':{'homed_axes':'xyz','position':[140.0,165.0,12.0]},
                'print_stats':{'state':'standby'},
                'idle_timeout':{'state':'Ready'},
                'virtual_sdcard':{'is_active':False},
                'pause_resume':{'is_paused':False},
                'configfile':{'settings':{
                    'stepper_x':{'position_min':0,'position_max':335,'position_endstop':335},
                    'stepper_y':{'position_min':0,'position_max':362,'position_endstop':362},
                    'homing_override':{'axes':'xyz'}}}}
        self.assertEqual(validate_preflight(config)['bounds']['x']['endstop_mm'],335.0)
        config['toolhead']['position'][2]=5
        with self.assertRaises(CaptureError):
            validate_preflight(config)
        config['toolhead']['position'][2]=12
        config['print_stats']['state']='printing'
        with self.assertRaises(CaptureError):
            validate_preflight(config)
        config['print_stats']['state']=None
        self.assertEqual(validate_preflight(config)['print_state'],None)
        config['virtual_sdcard']['is_active']=True
        with self.assertRaises(CaptureError):
            validate_preflight(config)
        config['virtual_sdcard']['is_active']=False
        config['pause_resume']['is_paused']=True
        with self.assertRaises(CaptureError):
            validate_preflight(config)
        config['pause_resume']['is_paused']=False
        config['idle_timeout']['state']='Printing'
        with self.assertRaises(CaptureError):
            validate_preflight(config)
        config['idle_timeout']['state']='Idle'
        del config['virtual_sdcard']
        self.assertEqual(validate_preflight(config)['idle_timeout_state'],'Idle')
        config['idle_timeout']['state']='Ready'
        with self.assertRaises(CaptureError):
            validate_preflight(config)

    def test_optional_status_object_discovery(self):
        class FakeMoonraker(Moonraker):
            def __init__(self):
                self.queries=[]
            def request(self,path,payload=None):
                self.queries.append(path)
                if path == '/printer/objects/list':
                    return {'objects':['toolhead','configfile','idle_timeout',
                                       'print_stats','virtual_sdcard']}
                return {'status':{'idle_timeout':{'state':'Ready'},
                                  'print_stats':{'state':None},
                                  'virtual_sdcard':{'is_active':False}}}
        api=FakeMoonraker()
        data=api.status()
        self.assertIsNone(data['print_stats']['state'])
        self.assertIn('idle_timeout=state',api.queries[1])
        self.assertIn('virtual_sdcard=is_active',api.queries[1])
        self.assertNotIn('pause_resume',api.queries[1])

    def test_mcu_counter_session_change(self):
        with self.assertRaises(CaptureError):
            motor_delta({'stepper_x':0,'stepper_y':0,'stepper_z':0},
                        {'stepper_x':1,'stepper_y':2})

if __name__=='__main__': unittest.main()