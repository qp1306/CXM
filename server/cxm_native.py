"""CXM Klipper-native toolchange service bridge.

Python validates/synchronizes accepted calibration and dispatches macro names.
It NEVER generates, sends or coordinates XY motion G-code.
"""
import urllib.parse

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
    if native.get('protocol')!=1 or not test:
        raise NativeError('Install and load CXM native Klipper macro before using toolchanges')
    return native,test,signal

def status(store):
    native,test,signal=_native_status()
    running=test.get('running')==1
    selected=[x for x in (test.get('tool_a'),test.get('tool_b'),test.get('tool_c')) if type(x) is int and x >= 0]
    count=len(selected)
    return {'state':'running' if running else test.get('state','idle'),
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
            'current_tool':native.get('current_tool'),
            'sensor':signal,'native_ready':bool(native.get('ready')),
            'fault':native.get('fault'),
            'last_event':'Klipper-native macro owns each complete tool pair',
            'error':None,'results':[],
            'revision':store.read()['revision']}

def sync(store,expected_revision):
    """Explicit idle-only runtime geometry synchronization; invalidates tool state."""
    saved=store.read()
    if saved['migration_required'] or saved['revision']!=expected_revision:
        raise NativeError('CXM config migration/revision mismatch; refresh before synchronization')
    native,test,signal=_native_status()
    if test.get('running')==1:
        raise NativeError('Cannot change geometry during a running native tool test')
    # Never silently resynchronize while a physical hotend may be attached.
    if signal!='RELEASED' or native.get('current_tool') not in (-2,-1):
        raise NativeError('Physically inspect and clear carriage before geometry synchronization')
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
        for field,val in [('travel_feed',600),('approach_feed',240),('latch_feed',180)]:
            lines.append('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE='+field+' VALUE='+str(val))
        lines.append('SET_GCODE_VARIABLE MACRO=_CXM_NATIVE VARIABLE=ready VALUE=1')
        if store.read()['revision']!=expected_revision:
            raise NativeError('Saved calibration changed during synchronization')
        _rpc('/printer/gcode/script',{'script':'\n'.join(lines)})
        return {'synced':True,'revision':expected_revision,'accepted_tools':sorted(paths),
                'current_tool':'UNKNOWN','requires_confirm_empty':True,
                'note':'No XY motion. Klipper-native tool identity intentionally invalidated.'}
    finally:
        MOVE_LOCK.release()

def confirm_empty():
    native,test,signal=_native_status()
    if test.get('running'):
        raise NativeError('Native cycle running')
    if signal!='RELEASED':
        raise NativeError('Carriage physically not empty')
    _rpc('/printer/gcode/script',{'script':'CXM_CONFIRM_EMPTY'})
    return {'empty_confirmed':True}

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
          cycles=1,execution_mode='native'):
    if acknowledgement!='I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH':
        raise NativeError('Physical carriage and dock inspection required')
    if type(tools) is not list or not 2<=len(tools)<=3 or any(type(n) is not int for n in tools) or tools != sorted(set(tools)):
        raise NativeError('Native commissioning requires 2–3 ascending accepted tools')
    profiles=('standard','faster','performance','sprint','race','boost')
    if travel_profile not in profiles:
        raise NativeError('Unknown CXM speed profile')
    if travel_profile in ('sprint','race','boost') and cycles!=1:
        raise NativeError('Experimental high-speed profiles require exactly one supervised cycle')
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
    script='CXM_SET_PROFILE PROFILE='+travel_profile+'\nCXM_TEST_START A='+str(tools[0])+' B='+str(tools[1])
    if len(tools)==3:
        script+=' C='+str(tools[2])
    script+=' CYCLES='+str(cycles)
    _rpc('/printer/gcode/script',{'script':script})
    return {'started':True,'tools':tools,'cycles':cycles,'execution_mode':'native','travel_profile':travel_profile,
            'note':'Klipper controls tool pairs and checks sensor after each pickup and dropoff'}

def stop(acknowledgement):
    if acknowledgement!='STOP_AFTER_CURRENT_TOOL_PAIR':
        raise NativeError('Explicit stop acknowledgement required')
    _rpc('/printer/gcode/script',{'script':'CXM_TEST_STOP'})
    return {'stop_requested':True,'note':'Klipper will stop at a completed tool-pair boundary if queued stop is processed before the next step; use emergency stop for immediate danger'}
