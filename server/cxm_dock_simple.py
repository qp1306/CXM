"""CXM Dock XY commissioning: home, select, Z22, jog, test, adjust, save, next.

No filament or tool-presence sensor is queried anywhere in this module.
Uses ordinary Klipper G-code so a normal CXM source update is sufficient:
there are no new installed macros and no Klipper restart for these controls.

The test reproduces the native CxChanger X latch and Y clearance motion,
but does NOT claim to verify actual pickup/dropoff engagement. Only the
operator can inspect physical engagement during unsensored calibration.
Automatic CXM_SELECT_TOOL is unchanged and still uses its own checks.
"""
import math
from cxm_runtime import MOVE_LOCK, _rpc

class DockSimpleError(RuntimeError):
    pass

def _snapshot():
    status=_rpc('/printer/objects/query?webhooks=state&toolhead=homed_axes,position,axis_minimum,axis_maximum&idle_timeout=state&print_stats=state&gcode_macro%20_CXM_TEST_STATE=running').get('status',{})
    if status.get('webhooks',{}).get('state')!='ready':
        raise DockSimpleError('Klipper not ready')
    head=status.get('toolhead',{})
    xyz=head.get('position')
    lower=head.get('axis_minimum')
    upper=head.get('axis_maximum')
    if not all(isinstance(a,list) and len(a)>=3 for a in (xyz,lower,upper)):
        raise DockSimpleError('Klipper position or axis limits unavailable')
    if not all(type(v) in (int,float) and math.isfinite(v) for a in (xyz,lower,upper) for v in a[:3]):
        raise DockSimpleError('Klipper position or axis limits invalid')
    return {
        'xyz':{'x':float(xyz[0]),'y':float(xyz[1]),'z':float(xyz[2])},
        'limits':{axis:(float(lower[i]),float(upper[i])) for i,axis in enumerate('xyz')},
        'homed':all(axis in str(head.get('homed_axes','')).lower() for axis in 'xyz'),
        # Klipper briefly reports idle_timeout=Printing even after an M400
        # manual move. Print job state is the useful conflict signal here.
        'idle':status.get('print_stats',{}).get('state') in (None,'standby','complete','cancelled','error'),
        'test_running':status.get('gcode_macro _CXM_TEST_STATE',{}).get('running')==1,
    }

def _checked(saved,tool,*,homed=True):
    if type(tool) is not int or not 0<=tool<saved['config']['globals']['tool_count']:
        raise DockSimpleError('Select T0 through the enabled tool count')
    current=_snapshot()
    if current['test_running'] or not current['idle']:
        raise DockSimpleError('Printer is busy')
    if homed and not current['homed']:
        raise DockSimpleError('Home XYZ first')
    return current

def _inside(snapshot,axis,value):
    low,high=snapshot['limits'][axis]
    # The printer's configured Klipper travel limits, not the obsolete X325 cap.
    if value<low or value>high:
        raise DockSimpleError(axis.upper()+' move exceeds configured Klipper travel')

def _send(lines):
    # Klipper owns kinematics, motor commands and its configured end limits.
    # RESTORE does NOT travel back to any position.
    script=('SAVE_GCODE_STATE NAME=CXM_SIMPLE_DOCK\nG90\n'+'\n'.join(lines)+
            '\nM400\nRESTORE_GCODE_STATE NAME=CXM_SIMPLE_DOCK MOVE=0')
    _rpc('/printer/gcode/script',{'script':script})

def _after(store,tool,expected_revision,expected_xyz,*,tol=0.08):
    # M400 already drained the commanded moves. Do not mistake Klipper's
    # transient idle_timeout=Printing label for an unfinished jog.
    state=_snapshot()
    if not state['homed']:
        raise DockSimpleError('Homing state changed during movement')
    if store.read()['revision']!=expected_revision:
        raise DockSimpleError('Configuration changed during movement')
    if any(abs(state['xyz'][axis]-value)>tol for axis,value in expected_xyz.items()):
        raise DockSimpleError('Actual position differs from commanded position')
    return state

def status(store,tool):
    saved=store.read()
    current=_snapshot()
    if type(tool) is not int or not 0<=tool<saved['config']['globals']['tool_count']:
        raise DockSimpleError('Select an enabled hotend')
    t=saved['config']['tools'][tool]
    return {'tool':tool,'tool_count':saved['config']['globals']['tool_count'],
            'xyz':current['xyz'],'homed':current['homed'],'idle':current['idle'],
            'saved_xy':{'x':t['dock_x'],'y':t['dock_y']},
            'accepted':t['dock_reference_accepted'],'revision':saved['revision'],
            'shift_x':saved['config']['globals']['cxm_shift_x'],
            'clearance_y':saved['config']['globals']['cxm_safe_clearance_y']}

def _action(store,tool,expected_revision,kind,axis=None,distance=None):
    if not MOVE_LOCK.acquire(blocking=False):
        raise DockSimpleError('CXM movement already in progress')
    try:
        saved=store.read()
        if saved['revision']!=expected_revision:
            raise DockSimpleError('Configuration changed; refresh')
        if kind=='home':
            state=_checked(saved,tool,homed=False)
            _rpc('/printer/gcode/script',{'script':'G28'})
            return status(store,tool)
        state=_checked(saved,tool)
        xyz=state['xyz']
        if kind=='enable':
            if xyz['z']<22:
                _inside(state,'z',22)
                _send(['G1 Z22 F1500'])
                _after(store,tool,expected_revision,{'x':xyz['x'],'y':xyz['y'],'z':22})
            return status(store,tool)
        if kind in ('jog','test') and xyz['z']<21.95:
            raise DockSimpleError('Enable jogging first to prepare Z22')
        if kind=='jog':
            if axis not in ('x','y') or type(distance) not in (int,float) or not math.isfinite(distance):
                raise DockSimpleError('Choose X or Y and a valid step')
            if abs(distance) not in (10.0,1.0,0.1,0.01):
                raise DockSimpleError('Choose 10, 1, 0.1 or 0.01 mm')
            next_value=xyz[axis]+distance
            _inside(state,axis,next_value)
            _send(['G1 '+axis.upper()+f'{next_value:.5f}'+' F3000'])
            _after(store,tool,expected_revision,{**xyz,axis:next_value})
            return status(store,tool)
        if kind=='test':
            # Identical machine-space geometry and order as the proven native
            # CxChanger pickup/release: released-side x, latch x+shift_x,
            # dock y, staging y+clearance. Start/finish at original release XY.
            x,y=xyz['x'],xyz['y']
            shift=saved['config']['globals']['cxm_shift_x']
            clearance=saved['config']['globals']['cxm_safe_clearance_y']
            mounted_x=x+shift
            safe_y=y+clearance
            for a,v in (('x',x),('x',mounted_x),('y',y),('y',safe_y)):
                _inside(state,a,v)
            lines=[
                f'G1 Y{safe_y:.5f} F6000',
                f'G1 Y{y:.5f} F6000',
                f'G1 X{mounted_x:.5f} F6000',
                f'G1 Y{safe_y:.5f} F6000',
                f'G1 Y{y:.5f} F6000',
                f'G1 X{x:.5f} F6000',
                f'G1 Y{safe_y:.5f} F6000',
                f'G1 Y{y:.5f} F6000'
            ]
            _send(lines)
            _after(store,tool,expected_revision,xyz)
            return {'tested':True,'start_xy':{'x':x,'y':y},'end_xy':{'x':x,'y':y},
                    'motion':'CxChanger pickup and release path','tool':tool}
        raise DockSimpleError('Unknown Dock XY operation')
    finally:
        MOVE_LOCK.release()

def home(store,tool,expected_revision):
    return _action(store,tool,expected_revision,'home')

def enable(store,tool,expected_revision):
    return _action(store,tool,expected_revision,'enable')

def jog(store,tool,expected_revision,axis,distance):
    return _action(store,tool,expected_revision,'jog',axis,distance)

def test(store,tool,expected_revision):
    return _action(store,tool,expected_revision,'test')

def save(store,tool,expected_revision):
    if not MOVE_LOCK.acquire(blocking=False):
        raise DockSimpleError('CXM movement already in progress')
    try:
        saved=store.read()
        if saved['revision']!=expected_revision:
            raise DockSimpleError('Configuration changed; refresh')
        state=_checked(saved,tool)
        _rpc('/printer/gcode/script',{'script':'M400'})
        pos=_after(store,tool,expected_revision,state['xyz'],tol=0.02)['xyz']
        if any(abs(state['xyz'][a]-pos[a])>0.02 for a in 'xy'):
            raise DockSimpleError('Carriage moved during capture')
        # Never leave stale Klipper native tool geometry armed after saving.
        # Disarm *state only*, with no filament-state query or physical motion.
        native=_rpc('/printer/objects/query?gcode_macro%20_CXM_NATIVE=ready,fault,current_tool&gcode_macro%20_CXM_TEST_STATE=running').get('status',{})
        if native.get('gcode_macro _CXM_TEST_STATE',{}).get('running')==1:
            raise DockSimpleError('Native toolchange is running')
        if 'gcode_macro _CXM_NATIVE' in native:
            _rpc('/printer/gcode/script',{'script':
                'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=ready VALUE=0\n'
                'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=1\n'
                'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE=-2'})
            confirm=_rpc('/printer/objects/query?gcode_macro%20_CXM_NATIVE=ready,fault,current_tool').get('status',{}).get('gcode_macro _CXM_NATIVE',{})
            if confirm.get('ready')!=0 or confirm.get('fault')!=1 or confirm.get('current_tool')!=-2:
                raise DockSimpleError('Native geometry was not disarmed; coordinates not saved')
        xy={'x':pos['x'],'y':pos['y']}
        result=store.save_dock(tool,xy,expected_revision)
        current=store.read()
        entry=current['config']['tools'][tool]
        if entry['dock_x']!=xy['x'] or entry['dock_y']!=xy['y'] or not entry['dock_reference_accepted']:
            raise DockSimpleError('Saved coordinates did not read back correctly')
        # The measured dock datum is already committed above. Now withdraw
        # the carriage along the proven release-side Y+ path to the next
        # hotend's clear staging position. Never save this staging Y as dock Y.
        # Use the same 100 mm and feed as the working dock test.
        retreat_y=pos['y']+100.0
        try:
            _inside(state,'y',retreat_y)
            _send([f'G1 Y{retreat_y:.5f} F6000'])
            end=_after(store,tool,current['revision'],
                       {'x':pos['x'],'y':retreat_y,'z':pos['z']})
        except Exception as exc:
            # Disk Save succeeded, even if Klipper refused the withdrawal or
            # its result is uncertain. Report both facts distinctly; never
            # pretend Save failed and never automatically repeat the motion.
            return {'saved':True,'tool':tool,'xy':xy,
                    'revision':current['revision'],'backup':result.get('backup'),
                    'retreated':False,'retreat_error':str(exc)}
        return {'saved':True,'tool':tool,'xy':xy,
                'revision':current['revision'],'backup':result.get('backup'),
                'retreated':True,'staging_xy':{'x':end['xyz']['x'],'y':end['xyz']['y']}}
    finally:
        MOVE_LOCK.release()
