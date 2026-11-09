#!/usr/bin/env python3
"""Hardware-free checks for CXM native Klipper toolchange architecture.

Does not connect to Moonraker or generate physical motion.
Jinja2 is needed only to check that every gcode macro is syntactically valid.
"""
import ast
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'server'))

def macro_sections():
    source=(ROOT/'vendor/cxm/cxm_native_toolchange.cfg').read_text('utf8')
    pattern=re.compile(r'(?m)^\[(gcode_macro|delayed_gcode) ([^\]]+)\]\s*$')
    matches=list(pattern.finditer(source))
    if not matches:raise AssertionError('No native Klipper macro definitions')
    return {m.group(2):source[m.end():matches[i+1].start() if i+1<len(matches) else len(source)]
            for i,m in enumerate(matches)}

def check():
    from jinja2 import Environment, TemplateSyntaxError
    blocks=macro_sections()
    required=('CXM_SELECT_TOOL','_CXM_PICKUP_MOTION','_CXM_RELEASE_MOTION',
              '_CXM_VERIFY','CXM_CONFIRM_EMPTY','CXM_TEST_START','CXM_TEST_STOP',
              'CXM_NATIVE_TEST_STEP','CXM_TEST_RESET','CXM_RECOVER')
    for name in required:
        assert name in blocks, 'missing native macro '+name
    env=Environment()
    for name,source in blocks.items():
        assert 'gcode:' in source, name+' has no G-code body'
        body=source.split('gcode:',1)[1]
        try:env.parse(body)
        except TemplateSyntaxError as exc:
            raise AssertionError(name+' Jinja syntax error: '+str(exc)) from exc
    # The original user-supplied toolchange-EN.cfg movement order:
    # Pickup: dodge, X shift, dock entry, X clamp, retract to safe Y.
    # Release: approach fully locked dock XY, withdraw Y+ without X movement.
    from cxm_cxchanger import plan
    tools=[]
    for n in range(12):
        tools.append({'dock_x':150.0+n*3,'dock_y':100.0,
                      'dock_reference_accepted':True})
    saved={'config':{'globals':{'tool_count':12,
                               'cxm_shift_x':-3.0,
                               'cxm_dodge_y':14.0,
                               'cxm_safe_clearance_y':60.0},'tools':tools}}
    for n in range(12):
        p=plan(saved,tool=n)
        x=150.0+n*3;y=100.0
        assert p['pickup']==[(x,y+14),(x-3,y+14),(x-3,y),(x,y),(x,y+60)]
        assert p['dropoff']==[(x,y),(x,y+60)]
    controller=blocks['CXM_SELECT_TOOL']
    assert 'pos.y|float < target_safe - 1.0' in controller
    pickup=blocks['_CXM_PICKUP_MOTION']
    assert '_CXM_CLEAR_TRANSFER X={x} Y={safe} MIN_Y={safe} EXPECT=RELEASED' in pickup
    release=blocks['_CXM_RELEASE_MOTION']
    assert '_CXM_CLEAR_TRANSFER X={x} Y={safe} MIN_Y={safe} EXPECT=PRESSED' in release
    assert 'G1 X{x} Y{y} F{st.approach_feed}' in release
    assert 'G1 X{x} Y{safe} F{st.approach_feed}' in release
    assert 'G1 X{x+shift}' not in release
    calibration=blocks['CXM_CALIBRATION_RELEASE']
    assert 'G1 X{x} Y{safe} F{st.approach_feed}' in calibration
    assert 'G1 X{x+shift}' not in calibration
    assert '_CXM_CLEAR_TRANSFER' in blocks
    clear=blocks['_CXM_CLEAR_TRANSFER']
    assert 'diagonal path would enter dock corridor' in clear
    assert 'G1 X{target_x} Y{target_y} F{st.travel_feed}' in clear
    assert clear.index('SET_VELOCITY_LIMIT ACCEL=9000') < clear.index('G1 X{target_x} Y{target_y}')
    assert clear.index('G1 X{target_x} Y{target_y}') < clear.index('SET_VELOCITY_LIMIT ACCEL=4000')
    assert clear.index('SET_VELOCITY_LIMIT ACCEL=4000') < clear.index('CXM_FAST_VERIFY EXPECT={expect} X={target_x} Y={target_y}')
    assert 'CXM_ACCEL_RESTORE' in blocks
    assert 'SET_VELOCITY_LIMIT ACCEL=4000' in blocks['CXM_ACCEL_RESTORE']
    recover=blocks['CXM_RECOVER']
    assert 'confirmed != "EMPTY"' in recover
    assert 'native.current_tool|int != -1' not in recover
    assert 'state != "RELEASED"' in recover
    assert 'CXM_TEST_RESET' in recover and '_CXM_PREPARE_CLEARANCE EXPECT=RELEASED' in recover
    assert recover.count('CXM_FAST_VERIFY EXPECT=RELEASED') == 4
    assert recover.index('CXM_TEST_RESET') < recover.index('_CXM_PREPARE_CLEARANCE EXPECT=RELEASED')
    assert recover.index('CXM_FAST_VERIFY EXPECT=RELEASED') < recover.index('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE=-1')
    assert recover.index('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE=-1') < recover.index('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=0')
    assert 'SET_VELOCITY_LIMIT ACCEL=4000' in recover
    assert 'UPDATE_DELAYED_GCODE ID=CXM_NATIVE_TEST_STEP DURATION=0' in recover
    assert 'UPDATE_DELAYED_GCODE ID=CXM_ACCEL_RESTORE DURATION=0' in recover
    test_start=blocks['CXM_TEST_START']
    assert '_CXM_STAGE_TEST Y={([y_a,y_b,y_c]|max)}' in test_start
    assert '_CXM_STAGE_TEST' in blocks
    stage=blocks['_CXM_STAGE_TEST']
    assert 'below dock mechanical clearance Y' in stage
    assert 'G1 Y{target} F{st.travel_feed}' in stage
    assert stage.index('G1 Y{target}') < stage.index('CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y={target}')
    assert '_CXM_PREPARE_CLEARANCE EXPECT=RELEASED' in test_start
    assert '_CXM_PREPARE_CLEARANCE EXPECT={' in controller
    assert '_CXM_PREPARE_CLEARANCE' in blocks
    assert 'CXM_DECLARE_CARRIAGE' in blocks
    lift=blocks['_CXM_PREPARE_CLEARANCE']
    assert 'XYZ not homed; automatic clearance lift refused' in lift
    assert 'carriage sensor disagrees' in lift
    assert 'G1 Z25 F600' in lift
    assert lift.index('G1 Z25 F600') < lift.index('CXM_FAST_VERIFY EXPECT={expected}')
    declare=blocks['CXM_DECLARE_CARRIAGE']
    assert declare.count('CXM_FAST_VERIFY EXPECT=RELEASED') == 4
    assert declare.count('CXM_FAST_VERIFY EXPECT=PRESSED') == 4
    assert 'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE={t}' in declare
    assert 'CXM_DECLARE_CARRIAGE TOOL=-1' in blocks['CXM_CONFIRM_EMPTY']
    service=(ROOT/'server/cxm_service.py').read_text('utf8')
    assert "'/v1/native/initialize'" in service
    native=(ROOT/'server/cxm_native.py').read_text('utf8')
    assert 'def initialize(store,expected_revision,carriage_tool):' in native
    verify=blocks['_CXM_VERIFY']
    assert verify.count('CXM_FAST_VERIFY EXPECT={expect}')==2
    assert blocks['CXM_SELECT_TOOL'].count('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=1')==2
    for name in ('cxm_multi.py','cxm_rapid.py'):
        assert not (ROOT/'server'/name).exists(), 'legacy Python motion worker remains: '+name
    for name in ('cxm_native.py','cxm_service.py','cxm_tools.py','cxm_t0.py'):
        ast.parse((ROOT/'server'/name).read_text('utf8'))
    assert 'def automatic_toolchange' not in (ROOT/'server/cxm_t0.py').read_text('utf8')
    assert 'def automatic_toolchange' not in (ROOT/'server/cxm_tools.py').read_text('utf8')
    print('CXM native source checks passed:',len(blocks),'Klipper sections and 12 tool geometries')
if __name__=='__main__':
    check()
