"""Hardware-free tests for supervised dock verification and sensor telemetry."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import cxm_dock_verify as m

class Store:
    def __init__(self):
        self.native={'current_tool':-2,'jog_revision':2}
        self.sensor='RELEASED'
        self.xy=[309.0,66.0,21.0]
        self.saved=False
        self.rev='a'*64
        self.commands=[]
    def read(self):
        return {'revision':self.rev,'migration_required':False,
                'config':{'globals':{'tool_count':3},
                'tools':[{'maintenance_lockout':False} for _ in range(3)]}}
    def save_dock(self,tool,xy,expected_revision):
        self.saved=True;self.saved_tool=tool;self.saved_xy=xy
        return {'backup':'before.cfg'}

class Tests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        def rpc(path,payload=None):
            if path.startswith('/printer/objects/query?gcode_macro%20CXM_DOCK_VERIFY_MOVE=version'):
                return {'status':{'gcode_macro CXM_DOCK_VERIFY_MOVE':{'version':2}}}
            if path.startswith('/printer/objects/query?'):
                return {'status':{
                    'webhooks':{'state':'ready'},
                    'toolhead':{'homed_axes':'xyz','position':list(self.store.xy),
                                'axis_minimum':[0,0,0],'axis_maximum':[335,362,350]},
                    'idle_timeout':{'state':'Idle'},
                    'print_stats':{'state':'standby'},
                    'stepper_enable':{'steppers':{n:True for n in (
                        'stepper_x','stepper_y','stepper_z','stepper_z1','stepper_z2','stepper_z3')}},
                    'gcode_button cxm_tool_detect':{'state':self.store.sensor},
                    'gcode_macro _CXM_NATIVE':self.store.native,
                    'gcode_macro _CXM_TEST_STATE':{'running':0}
                }}
            if path=='/printer/gcode/script':
                script=payload['script'];self.store.commands.append(script)
                if script.startswith('CXM_DOCK_VERIFY_MOVE '):
                    fields=dict(p.split('=',1) for p in script.split()[1:])
                    self.store.xy['XYZ'.index(fields['AXIS'])]+=float(fields['DIST'])
                return {}
            raise AssertionError('Unexpected Moonraker action '+path)
        self.patcher=patch.object(m,'_rpc',side_effect=rpc)
        self.patcher.start();self.addCleanup(self.patcher.stop)
        import cxm_manual
        second=patch.object(cxm_manual,'_rpc',side_effect=rpc)
        second.start();self.addCleanup(second.stop)
    def args(self):
        return dict(tool=0,expected_revision=self.store.rev,
            acknowledgement=m.ACK,store=self.store)
    def test_exact_two_moves_and_endpoint_verified(self):
        d=m.roundtrip(**self.args())
        self.assertTrue(d['verified'])
        self.assertEqual(d['sensor'],'RELEASED')
        self.assertEqual([round(v,2) for v in self.store.xy],[309,66,21])
        self.assertEqual(len(self.store.commands),2)
        self.assertIn('DIST=100.0000',self.store.commands[0])
        self.assertIn('DIST=-100.0000',self.store.commands[1])
        self.assertTrue(m.status(0,self.store)['travel_verified'])
    def test_pressed_sensor_is_observed_but_does_not_block_supervised_test(self):
        self.store.sensor='PRESSED'
        result=m.roundtrip(**self.args())
        self.assertTrue(result['verified'])
        self.assertEqual(result['sensor'],'PRESSED')
        self.assertEqual(len(self.store.commands),2)
    def test_sensor_transition_during_outward_leg_is_observed_and_return_permitted(self):
        original=m._rpc.side_effect
        def sensor_transition(path,payload=None):
            response=original(path,payload)
            if path=='/printer/gcode/script' and payload['script'].startswith('CXM_DOCK_VERIFY_MOVE '):
                self.store.sensor='PRESSED'
            return response
        with patch.object(m,'_rpc',side_effect=sensor_transition):
            result=m.roundtrip(**self.args())
        self.assertEqual(len(self.store.commands),2)
        self.assertEqual(result['sensor'],'PRESSED')
        self.assertTrue(result['verified'])

    def test_unhomed_axis_blocks_motion_even_with_sensor_observe_only(self):
        original=m._rpc.side_effect
        def unhomed(path,payload=None):
            response=original(path,payload)
            if path.startswith('/printer/objects/query?') and 'toolhead' in response.get('status',{}):
                response['status']['toolhead']['homed_axes']='xy'
            return response
        with patch.object(m,'_rpc',side_effect=unhomed):
            with self.assertRaisesRegex(m.ManualDockError,'Home XYZ'):
                m.roundtrip(**self.args())
        self.assertEqual(self.store.commands,[])

    def test_adjustment_requires_retest(self):
        self.assertTrue(m.roundtrip(**self.args())['verified'])
        d=m.adjust(tool=0,axis='x',distance=.1,**{k:v for k,v in self.args().items() if k!='tool'})
        self.assertTrue(d['repeat_test_required'])
        self.assertFalse(m.status(0,self.store)['travel_verified'])
        with self.assertRaisesRegex(m.ManualDockError,'Pass \\+100/-100'):
            m.save(**self.args())
    def test_save_requires_test_and_preserves_dock_position(self):
        with self.assertRaisesRegex(m.ManualDockError,'Pass \\+100/-100'):
            m.save(**self.args())
        m.roundtrip(**self.args())
        with patch('cxm_native.invalidate_for_config_edit',side_effect=lambda **kw:self.store.native.update(current_tool=-2)):
            # Implement disk persistence only in a test backing store.
            self.store.config={'tools':[{'dock_x':None,'dock_y':None,
                                          'dock_reference_accepted':False} for _ in range(3)]}
            original_read=self.store.read
            def read():
                result=original_read()
                if self.store.saved:
                    result['config']['tools'][0].update(dock_x=self.store.saved_xy['x'],
                        dock_y=self.store.saved_xy['y'],dock_reference_accepted=True)
                return result
            with patch.object(self.store,'read',side_effect=read):
                result=m.save(**self.args())
        self.assertTrue(result['verified'])
        self.assertEqual(self.store.saved_xy,{'x':309.0,'y':66.0})

if __name__=='__main__':
    unittest.main()
