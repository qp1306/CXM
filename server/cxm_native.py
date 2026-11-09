"""CXM Klipper-native toolchange service bridge.

Python validates/synchronizes accepted calibration and dispatches macro names.
It NEVER generates, sends or coordinates XY motion G-code.
"""
import urllib.parse
import math

from cxm_lineux import _rpc, MOVE_LOCK
from cxm_cxchanger import plan as geometry_plan

class NativeError(RuntimeError):
    pass

def _native_status():
    q=urllib.parse.urlencode({
        'gcode_macro _CXM_NATIVE':'protocol,ready,current_tool,fault,tool_count,profile',
        'gcode_macro _CXM_TEST_STATE':'running,stop,index,cycles,completed,tool_a,tool_b,tool_c,state',
        'gcode_button cxm_tool_detect':'state'})
    result=_rpc('/printer/objects/query?'+q).get('status',{})
    native=result.get('gcode_macro _CXM_NATIVE',{})
    test=result.get('gcode_macro _CXM_TEST_STATE',{})
    signal=result.get('gcode_button cxm_tool_detect',{}).get('state')
    if native.get('protocol') not in (1,2) or not test:
        raise NativeError('Install and load CXM native Klipper macro before using toolchanges')
    return native,test,signal

def status(store):
    native,test,signal=_native_status()
    running=test.get('running')==1
    selected=[x for x in (test.get('tool_a'),test.get('tool_b'),test.get('tool_c')) if type(x) is int and x >= 0]
    count=len(selected)
    saved=store.read()
    candidates=[]
    for n in range(saved['config']['globals']['tool_count']):
        tool=saved['config']['tools'][n]
        eligible=not saved['migration_required'] and not tool['maintenance_lockout'] and tool['dock_reference_accepted'] is True
        reason=None
        if eligible:
            try:
                geometry_plan(saved,tool=n)
            except (ValueError,TypeError,KeyError) as exc:
                eligible=False
                reason='Geometry: '+str(exc)
        else:
            reason='Dock XY not accepted / maintenance lockout / migration required'
        candidates.append({'tool':n,'eligible':eligible,'reason':reason,
                           'xy':{'x':tool['dock_x'],'y':tool['dock_y']}})
    return {'candidates':candidates,'max_repeat_cycles':20,'max_total_movements':120,
            'run_id':'native-klipper' if selected else None,
            'state':'running' if running else test.get('state','idle'),
            'running':running,'execution_mode':'native',
            'travel_profile':native.get('profile','standard'),
            'tools':selected,
            'requested_cycles':test.get('cycles',0),
            'completed_cycles':test.get('completed',0),
            'total_steps':2*count*test.get('cycles',0),
            'completed_steps':2*(count*test.get('completed',0)+test.get('index',0)),
            'current_cycle':test.get('completed',0)+1 if running else None,
            'current_action':'native_macro_pair' if running else None,
            'stop_requested':bool(test.get('stop')),
            'native_protocol':native.get('protocol'),
            'current_tool':native.get('current_tool'),
            'sensor':signal,'native_ready':bool(native.get('ready')),
            'fault':native.get('fault'),
            'last_event':'Klipper-native macro owns each complete tool pair',
            'error':None,'results':[],
            'revision':store.read()['revision']}

def sync(store,expected_revision,*,declared_tool=None):
    """Explicit idle-only runtime geometry synchronization; invalidates tool state."""
    saved=store.read()
    if saved['migration_required'] or saved['revision']!=expected_revision:
        raise NativeError('CXM config migration/revision mismatch; refresh before synchronization')
    native,test,signal=_native_status()
    if test.get('running')==1:
        raise NativeError('Cannot change geometry during a running native tool test')
    # Never silently resynchronize while a physical hotend may be attached.
    if type(declared_tool) is not int or declared_tool < -1 or declared_tool >= saved['config']['globals']['tool_count']:
        if declared_tool is not None:
            raise NativeError('Invalid declared carriage identity')
    expected='RELEASED' if declared_tool in (None,-1) else 'PRESSED'
    if signal!=expected:
        raise NativeError('Carriage sensor disagrees with declared physical identity; do not retry blindly')
    if native.get('current_tool') not in (-2,-1,declared_tool):
        raise NativeError('Existing known mounted tool differs; refuse to overwrite identity')
    if not MOVE_LOCK.acquire(blocking=False):
        raise NativeError('CXM calibration or motion operation already running')
    try:
        info=_rpc('/printer/info')
        if info.get('state')!='ready':
            raise NativeError('Klipper is not ready')
        count=saved['config']['globals']['tool_count']
        g=saved['config']['globals']
        # Prepare and validate ALL accepted tool datums before writing anything.
        paths={}
        for n in range(count):
            t=saved['config']['tools'][n]
            if t['maintenance_lockout'] or not t['dock_reference_accepted']:
                continue
            paths[n]=geometry_plan(saved,tool=n)
        lines=['SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=ready VALUE=0',
               'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=1',
               'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE=-2',
               'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=tool_count VALUE='+str(count)]
        for key,attr in [('shift_x','cxm_shift_x'),('dodge_y','cxm_dodge_y'),
                         ('clearance_y','cxm_safe_clearance_y')]:
            lines.append('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE='+key+
                         ' VALUE='+str(float(g[attr])))
        for i in range(12):
            p=paths.get(i)
            x=float(p['dock_reference_xy']['x']) if p else -1.0
            y=float(p['dock_reference_xy']['y']) if p else -1.0
            for suffix,value in [('x',x),('y',y),('accepted',int(bool(p)))]:
                lines.append('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=t'+str(i)+
                             '_'+suffix+' VALUE='+str(value))
        # Fixed baseline only. New speed profiles must be validated independently.
        for field,val in [('travel_feed',600),('approach_feed',240),('latch_feed',180),
                          ('segmented',0),('margin_y',15.0)]:
            lines.append('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE='+field+' VALUE='+str(val))
        lines.append('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=profile VALUE="\'standard\'"')
        lines.append('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=ready VALUE=1')
        if store.read()['revision']!=expected_revision:
            raise NativeError('Saved calibration changed during synchronization')
        _rpc('/printer/gcode/script',{'script':'\n'.join(lines)})
        return {'synced':True,'revision':expected_revision,'accepted_tools':sorted(paths),
                'current_tool':'UNKNOWN','requires_confirm_empty':True,
                'note':'No XY motion. Klipper-native tool identity intentionally invalidated.'}
    finally:
        MOVE_LOCK.release()

def initialize(store,expected_revision,carriage_tool):
    """One explicit declaration. Sync if needed, then Klipper verifies and lifts Z safely."""
    if type(carriage_tool) is not int or not -1<=carriage_tool<store.read()['config']['globals']['tool_count']:
        raise NativeError('Choose EMPTY or a configured tool number')
    if store.read()['revision']!=expected_revision:
        raise NativeError('CXM calibration changed; reload tools before declaring the carriage')
    native,test,signal=_native_status()
    if native.get('protocol')!=2:
        raise NativeError('Install the updated CXM native Klipper macro and restart Klipper before using one-click setup')
    if test.get('running'):
        raise NativeError('Tool cycle still running; inspect and stop before declaring tool identity')
    if signal!=('RELEASED' if carriage_tool==-1 else 'PRESSED'):
        raise NativeError('Physical carriage sensor disagrees: '+('EMPTY needs RELEASED' if carriage_tool==-1 else 'mounted T'+str(carriage_tool)+' needs PRESSED'))
    if carriage_tool>=0:
        tool=store.read()['config']['tools'][carriage_tool]
        if tool['maintenance_lockout'] or not tool['dock_reference_accepted']:
            raise NativeError('Declared mounted tool is not an accepted, unlocked dock')
    if native.get('ready')!=1:
        sync(store,expected_revision,declared_tool=carriage_tool)
    _rpc('/printer/gcode/script',{'script':'CXM_DECLARE_CARRIAGE TOOL='+str(carriage_tool)})
    after,_,sensor=_native_status()
    if after.get('ready')!=1 or after.get('fault')!=0 or after.get('current_tool')!=carriage_tool or sensor!=('RELEASED' if carriage_tool==-1 else 'PRESSED'):
        raise NativeError('Carriage declaration not verified; inspect machine before any toolchange')
    return {'ready':True,'current_tool':carriage_tool,'sensor':sensor,
            'note':'Geometry and carriage identity checked; Klipper raises Z to 25 mm only if needed and safe'}

def invalidate_for_config_edit():
    """No movement. Invalidate previous Klipper geometry BEFORE on-disk changes."""
    native,test,signal=_native_status()
    if test.get('running')==1 or native.get('current_tool') not in (-1,-2) or signal!='RELEASED':
        raise NativeError('Cannot edit tool configuration during native test or with mounted/unknown hotend')
    _rpc('/printer/gcode/script',{'script':
        'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=ready VALUE=0\n'
        'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=fault VALUE=1\n'
        'SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=current_tool VALUE=-2'})
    return {'invalidated':True,'needs_native_sync':True}

def confirm_empty():
    native,test,signal=_native_status()
    if test.get('running'):
        raise NativeError('Native cycle running')
    if signal!='RELEASED':
        raise NativeError('Carriage physically not empty')
    _rpc('/printer/gcode/script',{'script':'CXM_CONFIRM_EMPTY'})
    return {'empty_confirmed':True}

def recover_empty():
    """Manual fault recovery, only with physically inspected EMPTY carriage.

    The HTTP handler must independently require an explicit acknowledgement
    and a confirmed idle printer. This macro does no motion.
    """
    native,test,signal=_native_status()
    if native.get('ready')!=1 or signal!='RELEASED':
        raise NativeError('Native geometry must be synchronized and physical carriage EMPTY')
    if not MOVE_LOCK.acquire(blocking=False):
        raise NativeError('Another calibration/motion operation is active')
    try:
        _rpc('/printer/gcode/script',{'script':'CXM_TEST_RESET\nCXM_CONFIRM_EMPTY'})
        return {'recovered':True,'empty_confirmed':True,
                'note':'No movement; inspected EMPTY state restored and native test reset'}
    finally:
        MOVE_LOCK.release()

def select(store,tool,expected_revision):
    saved=store.read()
    if saved['revision']!=expected_revision:
        raise NativeError('CXM configuration revision mismatch')
    if type(tool) is not int or not -1<=tool<saved['config']['globals']['tool_count']:
        raise NativeError('Invalid tool')
    native,test,signal=_native_status()
    if test.get('running'):
        raise NativeError('Native test already running')
    # Klipper performs all live machine/sensor checks and physical movements.
    _rpc('/printer/gcode/script',{'script':'CXM_SELECT_TOOL TOOL='+str(tool)})
    return {'requested_tool':tool,'execution':'native_klipper','result':'check live native status'}

def start(store,tools,expected_revision,acknowledgement,travel_profile='standard',
          cycles=1,execution_mode='native',custom_speeds=None):
    if acknowledgement!='I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH':
        raise NativeError('Physical carriage and dock inspection required')
    if type(tools) is not list or not 2<=len(tools)<=3 or any(type(n) is not int for n in tools) or tools != sorted(set(tools)):
        raise NativeError('Native commissioning requires 2–3 ascending accepted tools')
    profiles=('standard','faster','performance','sprint','race','boost','custom')
    if travel_profile not in profiles:
        raise NativeError('Unknown CXM speed profile')
    if travel_profile=='custom':
        if type(custom_speeds) is not dict or set(custom_speeds)!={'travel','approach','latch'}:
            raise NativeError('Enter all three custom speeds: travel, approach and latch')
        values=[custom_speeds[k] for k in ('travel','approach','latch')]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
            raise NativeError('Custom speeds must be finite numeric values')
        travel,approach,latch=values
        if not (10<=travel<=600 and 1<=approach<=120 and 1<=latch<=40 and travel>=approach>=latch):
            raise NativeError('Custom limits: travel 10–600, approach 1–120, latch 1–40 mm/s; travel ≥ approach ≥ latch')
    elif custom_speeds is not None:
        raise NativeError('Custom speeds are only accepted with Custom profile')
    if travel_profile in ('sprint','race','boost','custom') and cycles!=1:
        raise NativeError('High-speed/custom profiles require exactly one supervised cycle')
    if type(cycles) is not int or not 1<=cycles<=20:
        raise NativeError('Cycles must be 1–20')
    saved=store.read()
    if saved['revision']!=expected_revision:
        raise NativeError('Configuration changed; refresh and synchronize')
    for n in tools:
        t=saved['config']['tools'][n]
        if n<0 or n>=saved['config']['globals']['tool_count'] or t['maintenance_lockout'] or not t['dock_reference_accepted']:
            raise NativeError('Selected dock is not accepted and available')
    native,test,signal=_native_status()
    if native.get('ready')!=1 or native.get('fault')!=0 or native.get('current_tool')!=-1 or signal!='RELEASED':
        raise NativeError('Native state is not verified EMPTY, ready and fault-free')
    if test.get('running'):
        raise NativeError('Native test already running')
    script='CXM_SET_PROFILE PROFILE='+travel_profile
    if travel_profile=='custom':
        script+=' TRAVEL='+str(travel)+' APPROACH='+str(approach)+' LATCH='+str(latch)
    script+='\nCXM_TEST_START A='+str(tools[0])+' B='+str(tools[1])
    if len(tools)==3:
        script+=' C='+str(tools[2])
    script+=' CYCLES='+str(cycles)
    _rpc('/printer/gcode/script',{'script':script})
    return {'started':True,'tools':tools,'cycles':cycles,'execution_mode':'native','travel_profile':travel_profile,
            'custom_speeds':custom_speeds,
            'note':'Klipper controls tool pairs and checks sensor after each pickup and dropoff'}

def stop(acknowledgement):
    if acknowledgement!='STOP_AFTER_CURRENT_TOOL_PAIR':
        raise NativeError('Explicit stop acknowledgement required')
    _rpc('/printer/gcode/script',{'script':'CXM_TEST_STOP'})
    return {'stop_requested':True,'note':'Klipper will stop at a completed tool-pair boundary if queued stop is processed before the next step; use emergency stop for immediate danger'}
