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
    required=('CXM_MANUAL_DOCK_JOG','CXM_SELECT_TOOL','_CXM_PICKUP_MOTION','_CXM_RELEASE_MOTION',
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
    # Verified manual T0 baseline: release X304.60 Y65.60,
    # mounted X309.00, retreat Y165.60; both operations F6000.
    from cxm_cxchanger import plan
    tools=[]
    for n in range(12):
        tools.append({'dock_x':150.0+n*3,'dock_y':100.0,
                      'dock_reference_accepted':True})
    saved={'config':{'globals':{'tool_count':12,
                               'cxm_shift_x':4.4,
                               'cxm_dodge_y':14.0,
                               'cxm_safe_clearance_y':100.0},'tools':tools}}
    for n in range(12):
        p=plan(saved,tool=n)
        x=150.0+n*3;y=100.0
        assert p['pickup']==[(x,y),(x+4.4,y),(x+4.4,y+100)]
        assert p['dropoff']==[(x+4.4,y),(x,y),(x,y+100)]
    t0={'config':{'globals':saved['config']['globals'],
                 'tools':[{'dock_x':304.60,'dock_y':65.60,
                           'dock_reference_accepted':True}]}}
    t0['config']['globals']=dict(t0['config']['globals'],tool_count=1)
    path=plan(t0)
    assert path['pickup']==[(304.60,65.60),(309.0,65.60),(309.0,165.6)]
    assert path['dropoff']==[(309.0,65.60),(304.60,65.60),(304.60,165.6)]

    # Validate the published Y105 transfer geometry against the ACTUAL Jinja
    # macros. This never connects to a printer or commands physical motion.
    fake_native={'t0_x':304.60625,'t0_y':65.6,'shift_x':4.4,
                 'transfer_y':105.0,'clearance_y':100.0,'travel_feed':6000,
                 'approach_feed':6000,'latch_feed':6000}
    printer={'gcode_macro _CXM_NATIVE':fake_native,
             'gcode_macro _CXM_TEST_STATE':{'running':0},
             'toolhead':{'position':{'y':105.0}}}
    def actual_g1(name):
        # Klipper template expressions have {expr}, not Jinja {{expr}}.
        body=blocks[name].split('gcode:',1)[1]
        jinja_body=re.sub(r'(?<![{%])\{([^{}%#\n]+)\}(?!})',
                          lambda m:'{{'+m.group(1)+'}}',body)
        rendered=env.from_string(jinja_body).render(
            printer=printer,params={'TOOL':0})
        return [line.strip() for line in rendered.splitlines()
                if line.strip().startswith('G1 ')]
    assert actual_g1('_CXM_PICKUP_MOTION')==[
        'G1 X304.60625 F6000', 'G1 Y105.0 F6000',
        'G1 Y65.6 F6000', 'G1 X309.00625 F6000',
        'G1 Y105.0 F6000']
    assert actual_g1('_CXM_RELEASE_MOTION')==[
        'G1 X309.00625 F6000', 'G1 Y105.0 F6000',
        'G1 Y65.6 F6000', 'G1 X304.60625 F6000',
        'G1 Y105.0 F6000']

    # Preserve sequencing, sensor checks, travel bounds, and state discipline.
    controller=blocks['CXM_SELECT_TOOL']
    assert '_CXM_PREPARE_CLEARANCE EXPECT={' in controller
    assert '_CXM_CHECK_TOOL TOOL={old}' in controller
    assert '_CXM_CHECK_TOOL TOOL={target}' in controller
    assert '_CXM_RELEASE_MOTION TOOL={old}' in controller
    assert '_CXM_PICKUP_MOTION TOOL={target}' in controller
    assert controller.index('_CXM_RELEASE_MOTION TOOL={old}') < controller.index('_CXM_PICKUP_MOTION TOOL={target}')
    for name,expected in (('_CXM_PICKUP_MOTION','RELEASED'),('_CXM_RELEASE_MOTION','PRESSED')):
        block=blocks[name]
        assert block.index('_CXM_CLEAR_TRANSFER TOOL={t} EXPECT='+expected) < block.index('G1 ')
        assert 'RESTORE_GCODE_STATE' in block and 'MOVE=0' in block
        assert 'st.transfer_y|float' in block
        assert 'M400' in block
    verify=blocks['_CXM_VERIFY']
    assert 'final_x=(x+st.shift_x|float)|round(5) if expect == "PRESSED" else x' in verify
    assert verify.count('X={final_x} Y={y}')==2
    assert verify.count('CXM_FAST_VERIFY EXPECT={expect}')==2
    commit=blocks['_CXM_COMMIT_STATE']
    assert 'Y={st.transfer_y|float}' in commit
    assert 'CXM_FAST_VERIFY EXPECT=PRESSED' in commit
    assert 'CXM_FAST_VERIFY EXPECT=RELEASED' in commit
    assert commit.index('CXM_FAST_VERIFY EXPECT=PRESSED') < commit.index('VARIABLE=current_tool')
    check_tool=blocks['_CXM_CHECK_TOOL']
    assert 'st.ready|int != 1 or st.fault|int != 0' in check_tool
    assert 'st["t" ~ t ~ "_accepted"]|int != 1' in check_tool
    for bound in ('h.axis_minimum.x','h.axis_maximum.x',
                  'h.axis_minimum.y','h.axis_maximum.y'):
        assert bound in check_tool
    assert 'st.transfer_y|float' in check_tool
    calibration=blocks['CXM_CALIBRATION_RELEASE']
    assert 'action_raise_error' in calibration and 'G1 ' not in calibration
    clear=blocks['_CXM_CLEAR_TRANSFER']
    assert 'CXM_FAST_VERIFY EXPECT={expect}' in clear and 'G1 ' not in clear
    assert 'CXM_ACCEL_RESTORE' in blocks
    assert 'SET_VELOCITY_LIMIT ACCEL=4000' in blocks['CXM_ACCEL_RESTORE']

    recover=blocks['CXM_RECOVER']
    assert 'confirmed != "EMPTY"' in recover
    assert 'state != "RELEASED"' in recover
    assert 'CXM_TEST_RESET' in recover
    assert '_CXM_PREPARE_CLEARANCE EXPECT=RELEASED' in recover
    assert recover.count('CXM_FAST_VERIFY EXPECT=RELEASED')==4
    assert recover.index('CXM_TEST_RESET') < recover.index('_CXM_PREPARE_CLEARANCE EXPECT=RELEASED')
    assert recover.index('CXM_FAST_VERIFY EXPECT=RELEASED') < recover.index('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE=-1')
    assert recover.index('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE=-1') < recover.index('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=0')
    assert 'UPDATE_DELAYED_GCODE ID=CXM_NATIVE_TEST_STEP DURATION=0' in recover
    assert 'UPDATE_DELAYED_GCODE ID=CXM_ACCEL_RESTORE DURATION=0' in recover

    test_start=blocks['CXM_TEST_START']
    assert '_CXM_STAGE_TEST Y={native.transfer_y|float}' in test_start
    assert 'selected dock safe-Y lines differ' not in test_start
    assert 'VARIABLE=tool_mask VALUE={mask}' in test_start
    assert 'ns.count*n*2>120' in test_start
    assert 'MASK' in test_start
    assert 'variable_batch_revision: 2' in blocks['_CXM_TEST_STATE']
    assert 'variable_tool_mask: 0' in blocks['_CXM_TEST_STATE']
    assert 'st.tool_mask|int' in blocks['CXM_NATIVE_TEST_STEP']
    assert '_CXM_STAGE_TEST Y={native.transfer_y|float}' in blocks['CXM_NATIVE_TEST_STEP']
    assert 'st.tool_count|int' in blocks['_CXM_TEST_ADVANCE']
    stage=blocks['_CXM_STAGE_TEST']
    assert 'G1 Y{target|round(5)} F6000' in stage
    assert 'SAVE_GCODE_STATE NAME=CXM_BATCH_STAGE' in stage
    assert 'RESTORE_GCODE_STATE NAME=CXM_BATCH_STAGE MOVE=0' in stage
    assert 'CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y={target}' in stage
    assert '_CXM_PREPARE_CLEARANCE EXPECT=RELEASED' in test_start
    assert 'CXM_DECLARE_CARRIAGE' in blocks
    lift=blocks['_CXM_PREPARE_CLEARANCE']
    assert 'XYZ not homed' in lift and 'carriage sensor disagrees' in lift
    assert 'G1 ' not in lift and 'CXM_FAST_VERIFY EXPECT={expected}' in lift
    # There is intentionally no bed-relative Z>=20/25 limit: docks move with gantry.
    declare=blocks['CXM_DECLARE_CARRIAGE']
    assert declare.count('CXM_FAST_VERIFY EXPECT=RELEASED')==4
    assert declare.count('CXM_FAST_VERIFY EXPECT=PRESSED')==4
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
