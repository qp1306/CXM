from collections import namedtuple
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
import sys

import jinja2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'server'))
import cxm_native

Point = namedtuple('Point', 'x y z')
source = (ROOT/'vendor/cxm/cxm_native_toolchange.cfg').read_text()
# Isolate CAMERA's gcode section; another independent macro can follow it.
body = source.split('[gcode_macro CXM_CAMERA]', 1)[1].split('gcode:\n', 1)[1].split('\n[gcode_macro ', 1)[0]
template = jinja2.Environment('{%', '%}', '{', '}').from_string(body)


class CameraTests(TestCase):
    def render(self, action, mounted=0, token=7, pos=Point(200, 230, 32)):
        st = dict(camera_reference=[7, 200, 230, 32],ready=1,fault=0,current_tool=mounted,
                  tool_count=2,t0_accepted=1,t1_accepted=1,t0_x=324.9,t1_x=284.0,t0_y=65,t1_y=66,shift_x=-4.4,transfer_y=105,clearance_y=100)
        printer = {'gcode_macro _CXM_NATIVE':st,'gcode_macro _CXM_TEST_STATE':{'running':0},
                   'toolhead':dict(position=pos,axis_minimum=Point(0,0,0),axis_maximum=Point(350,350,350)),
                   'gcode_move':dict(gcode_position=pos)}
        def fail(message):
            raise ValueError(message)
        return template.render(printer=printer,params=dict(ACTION=action,TOOL=0 if action=='REFERENCE' else 1,
                               MOUNTED=mounted,TOKEN=token),action_raise_error=fail)

    def test_capture_has_no_motion_and_uses_machine_xyz(self):
        cmd = self.render('REFERENCE')
        self.assertIn('VALUE=[7,200,230,32]',cmd)
        self.assertNotIn('G1 ',cmd)

    def test_lift_before_dock_then_verify_tool_before_return(self):
        change = self.render('CHANGE')
        self.assertLess(change.index('G1 Z37'),change.index('CXM_SELECT_TOOL TOOL=1'))
        self.assertLess(change.index('CXM_SELECT_TOOL TOOL=1'),change.index('CXM_CAMERA_RETURN TOOL=1'))
        with self.assertRaisesRegex(ValueError,'unexpected fitted'):
            self.render('RETURN',mounted=0)
        cmd = self.render('RETURN',mounted=1,pos=Point(264,166,37))
        self.assertLess(cmd.index('G1 Y230 F3000'),cmd.index('G1 X200 F3000'))
        self.assertLess(cmd.index('G1 X200 F3000'),cmd.index('G1 Z32 F60'))

    def test_stale_or_obstructed_reference_blocks_motion(self):
        for action,opts in [('CHANGE',dict(token=4)),('REFERENCE',dict(pos=Point(-1,65,32))),
                            ('REFERENCE',dict(pos=Point(200,230,348))),('RETURN',dict(mounted=1))]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.render(action,**opts)

    def test_verify_uses_saved_xy_and_capture_overwrites_total_offset(self):
        store = Mock()
        tools = [dict(dock_reference_accepted=True, maintenance_lockout=False,
                      offset_x=0.0, offset_y=0.0),
                 dict(dock_reference_accepted=True, maintenance_lockout=False,
                      offset_x=-1.04, offset_y=0.30, offset_xy_accepted=False)]
        store.read.return_value = dict(revision='r', migration_required=False,
                                       config=dict(globals=dict(tool_count=2), tools=tools))
        start = dict(camera_reference=[7,200,230,32], ready=1, fault=0, current_tool=0)
        after = dict(start, current_tool=1)
        live = dict(xy=dict(x=198.96,y=230.30),z=32.0,
                    native_tool_identity=1,revision='r')
        with patch.object(cxm_native, '_native_status', side_effect=[(start,{},'PRESSED'),(after,{},'PRESSED')]), \
             patch.object(cxm_native, '_rpc') as rpc, \
             patch('cxm_manual._check_after_own_command', return_value=live):
            result = cxm_native.camera_action(store,'verify',1,0,'r',7)
        self.assertIn('ACTION=VERIFY TOOL=1 MOUNTED=0 TOKEN=7 DX=-1.040000 DY=0.300000',
                      rpc.call_args.args[1]['script'])
        self.assertEqual(result['verification_offset'], {'x':-1.04,'y':0.3})
        store.save_offsets.assert_not_called()

        # Save after a slight jog must overwrite the complete T0-relative offset.
        start = dict(after)
        live['xy'] = dict(x=198.94,y=230.31)
        with patch.object(cxm_native, '_native_status', side_effect=[(start,{},'PRESSED'),(start,{},'PRESSED')]), \
             patch.object(cxm_native, '_rpc'), \
             patch('cxm_manual._check_after_own_command', return_value=live):
            store.save_offsets.return_value = {'saved': True}
            store.read.side_effect = [store.read.return_value, dict(store.read.return_value, config=dict(globals=dict(tool_count=2),tools=[tools[0],dict(tools[1], offset_x=-1.06,offset_y=0.31)]))]
            cxm_native.camera_action(store,'capture',1,1,'r',7)
        store.save_offsets.assert_called_once_with(1,'xy', {'x':-1.06,'y':0.31},'r')

    def test_offset_is_measured_carriage_minus_t0_and_only_xy_is_written(self):
        store=Mock()
        store.read.return_value=dict(revision='r',migration_required=False,config=dict(
            globals=dict(tool_count=2),tools=[dict(dock_reference_accepted=True,maintenance_lockout=False),
            dict(dock_reference_accepted=True,maintenance_lockout=False,offset_x=0.2,offset_y=-0.15)]))
        state=dict(camera_reference=[7,200,230,32],ready=1,fault=0,current_tool=1)
        live=dict(xy=dict(x=200.2,y=229.85),z=32.4,native_tool_identity=1,revision='r')
        store.save_offsets.return_value={'saved':True}
        with patch.object(cxm_native,'_native_status',return_value=(state,{},'PRESSED')), \
             patch.object(cxm_native,'_rpc'), patch('cxm_manual._check_after_own_command',return_value=live):
            cxm_native.camera_action(store,'capture',1,1,'r',7)
            store.save_offsets.assert_called_once_with(1,'xy',{'x':0.2,'y':-0.15},'r')
