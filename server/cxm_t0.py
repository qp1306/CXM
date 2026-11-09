"""CXM T0 slow-speed XY pickup/dropoff commissioning.

Explicit operator-supervised actions only, scoped to T0. No printer.cfg
editing, no Z movement, no heater control, and no automatic tool activation.
The accepted CxChanger datum and saved motion geometry are used throughout.
"""
from __future__ import annotations
import math
import threading
import time
import urllib.parse
from cxm_runtime import _rpc, MOVE_LOCK, MeasurementError
from cxm_cxchanger import plan as cxchanger_plan

SESSION_LOCK=threading.Lock()
SESSION={'pid':None,'revision':None,'stage':None,'sensor':None,
         'samples':{},'last_action':None,'xy':None,'path':None}
MOTORS=('stepper_x','stepper_y','stepper_z','stepper_z1','stepper_z2','stepper_z3')
SAFE_FEED=600
TEST_FEED=240
LATCH_FEED=180
POSITION_TOL=0.2

# T0's physically trialled settings. Never apply to dock coordinate storage.
AUTO_SENSOR='gcode_button cxm_tool_detect'
AUTO_MOUNTED='PRESSED'
AUTO_EMPTY='RELEASED'
# Motion distances now come exclusively from schema-3 CXM_variables.cfg.
AUTO_STATE={'pid':None,'revision':None,'fault':None,'last_success':None}
CYCLE_LOCK=threading.Lock()
CYCLE_MAX=20
CYCLE_STATE={'running':False,'requested':0,'completed':0,'phase':'idle',
             'stop_requested':False,'error':None,'last_result':None}

def cycle_status():
    with CYCLE_LOCK:
        return CYCLE_STATE.copy()

def stop_cycles(*, acknowledgement):
    if acknowledgement!='STOP_AFTER_CURRENT_T0_CYCLE':
        raise T0Error('Invalid T0 cycle stop request')
    with CYCLE_LOCK:
        if CYCLE_STATE['running']:
            CYCLE_STATE['stop_requested']=True
        return CYCLE_STATE.copy()

def _cycle_update(**changes):
    with CYCLE_LOCK:
        CYCLE_STATE.update(changes)

def _cycle_stop_requested():
    with CYCLE_LOCK:
        return bool(CYCLE_STATE['stop_requested'])


def _auto_invalidate(ctx):
    # Backend lifetime does not attest to hardware tool attachment: always
    # read the physical signal again before each operation.
    if AUTO_STATE['pid']!=ctx['pid'] or AUTO_STATE['revision']!=ctx['revision']:
        AUTO_STATE.update(pid=ctx['pid'],revision=ctx['revision'],fault=None,last_success=None)


class T0Error(MeasurementError):
    pass

def number(n,label,lo,hi):
    if type(n) not in (int,float) or not math.isfinite(n) or not lo<=n<=hi:
        raise T0Error(label+' outside safe configured range')
    return float(n)

def _safe_context(saved, *, tool=0, require_homed=True, require_in_park=False,
                  validated_objects=None, expected_pid=None, sensor_name=None):
    if saved['migration_required']:
        raise T0Error('CXM settings migration required before T0 testing')
    # The existing /t0 endpoints always use tool=0. A separate guarded bridge
    # may reuse this read-only hardware preflight with T1..T11.
    count=saved['config']['globals'].get('tool_count')
    if type(count) is not int or not 1 <= count <= 12:
        raise T0Error('Invalid configured hotend count')
    if type(tool) is not int or not 0 <= tool < count:
        raise T0Error('Selected hotend is outside configured tool count')
    t=saved['config']['tools'][tool]
    if t['maintenance_lockout']:
        raise T0Error('T'+str(tool)+' is under maintenance lockout')
    if t['dock_x'] is None or t['dock_y'] is None:
        raise T0Error('Save T'+str(tool)+' dock X/Y first')
    # The Lineux calibration result is not a motion model. The CxChanger
    # engine owns the accepted locking-hole datum and the relative Y clearance.
    p=plan(saved,tool=tool)
    x=p['dock_reference_xy']['x']
    y=p['dock_reference_xy']['y']
    safe=p['safe_y']
    info=_rpc('/printer/info')
    if info.get('state')!='ready' or type(info.get('process_id')) is not int:
        raise T0Error('Klipper not ready or identity unavailable')
    if validated_objects is not None:
        # An object registry snapshot is reusable only inside the same
        # physically verified Klipper process. Never trust it across a
        # restart, nor allow callers to pass it without a PID guard.
        if type(expected_pid) is not int:
            raise T0Error('Cached Klipper objects require a verified process ID')
        if info['process_id']!=expected_pid:
            raise T0Error('Klipper process changed; cached objects are invalid')
        if type(validated_objects) not in (tuple,list) or not all(
                type(x) is str for x in validated_objects):
            raise T0Error('Cached Klipper object registry invalid')
        objects=list(validated_objects)
    else:
        objects=_rpc('/printer/objects/list').get('objects',[])
    necessary={'toolhead','stepper_enable','idle_timeout'}
    if not necessary.issubset(set(objects)):
        raise T0Error('Cannot verify homing, motor power and idle status')
    query={'toolhead':'homed_axes,position',
           'stepper_enable':'steppers','idle_timeout':'state'}
    for key,field in [('print_stats','state'),('virtual_sdcard','is_active'),
                      ('pause_resume','is_paused')]:
        if key in objects: query[key]=field
    # The multi-tool controller can request the carriage switch in the SAME
    # live Klipper snapshot as homing, powered steppers, idle and print state.
    # This avoids a second 250ms object-query request before each movement.
    # Standalone T0 and T1+ routes leave sensor_name unset, unchanged.
    if sensor_name is not None:
        if sensor_name != AUTO_SENSOR or sensor_name not in objects:
            raise T0Error('Carriage presence switch unavailable for combined live status')
        query[sensor_name]='state'
    status=_rpc('/printer/objects/query?'+urllib.parse.urlencode(query)).get('status',{})
    if status.get('idle_timeout',{}).get('state') not in ('Idle','Ready'):
        raise T0Error('Klipper is not idle')
    if 'print_stats' in objects and status.get('print_stats',{}).get('state') not in (
            'standby','complete','cancelled','error'):
        # If an object we already verified exists has disappeared from
        # the query, do not infer an idle printer from a missing state.
        raise T0Error('Printer has a print active, paused or unknown state')
    if 'virtual_sdcard' in objects and status.get('virtual_sdcard',{}).get('is_active') is not False:
        raise T0Error('Virtual SD print active or unknown')
    if 'pause_resume' in objects and status.get('pause_resume',{}).get('is_paused') is not False:
        raise T0Error('Printer paused')
    sensor_signal=None
    if sensor_name is not None:
        sensor_signal=status.get(sensor_name,{}).get('state')
        if sensor_signal not in (AUTO_MOUNTED,AUTO_EMPTY):
            raise T0Error('Carriage switch live state unavailable in combined status')
    homed=status.get('toolhead',{}).get('homed_axes','')
    pos=status.get('toolhead',{}).get('position',[])
    motors=status.get('stepper_enable',{}).get('steppers',{})
    if require_homed and (not all(axis in homed for axis in 'xyz')
                          or len(pos)<3 or any(type(v) not in (float,int) or not math.isfinite(v) for v in pos[:3])
                          or pos[2]<20):
        raise T0Error('Home XYZ and maintain at least Z20 physical clearance')
    if require_homed and not all(motors.get(name) is True for name in MOTORS):
        raise T0Error('All X/Y and four Z steppers must be powered; rehome after manual positioning')
    # XYZ homing and stepper power are read directly from Klipper above.
    # Do not require a transient CXM-service memory token: source updates and
    # backend reloads invalidate that token without changing Klipper homing.
    # Operators must never hand-move/re-enable X/Y after homing and then trust
    # stale Klipper coordinates. Every motion still needs physical clearance
    # acknowledgement plus powered motors, Z>=20 and idle printer.
    if require_in_park and (abs(pos[0]-x)>POSITION_TOL or abs(pos[1]-safe)>POSITION_TOL):
        raise T0Error('Carriage must be at verified staging X/Y before pickup/dropoff')
    return {'pid':info['process_id'],'tool':tool,'x':x,'y':y,'safe_y':safe,
            'position':pos[:3],'objects':objects,'revision':saved['revision'],
            'sensor_signal':sensor_signal}

def _wait_for_idle_after_move(saved, *, parked, expected_pid, timeout_sec=10.0,
                              tool=0, validated_objects=None):
    """Read-only wait for Klipper to settle after a completed G-code script.

    Moonraker can return from an M400-ended script before Klipper's
    idle_timeout state changes from Printing to Ready/Idle. Retry only that
    known transient status, never a homing, motor-power, print, position,
    config, or sensor failure. No motion commands are issued while waiting.
    """
    deadline=time.monotonic()+timeout_sec
    while True:
        try:
            ctx=_safe_context(saved,tool=tool,require_in_park=parked,
                              validated_objects=validated_objects,
                              expected_pid=(expected_pid if validated_objects is not None
                                            else None))
        except T0Error as exc:
            if str(exc)!='Klipper is not idle':
                raise
            if time.monotonic()>=deadline:
                raise T0Error(
                    'Klipper did not return to idle after the preceding T0 movement; '
                    'toolchange stopped before the next movement. '
                    'Inspect T0 and the dock before clearing the test fault.'
                ) from exc
            time.sleep(0.25)
            continue
        if ctx['pid']!=expected_pid:
            raise T0Error('Klipper instance changed during the T0 test')
        return ctx


def _sensor_value(name,objects):
    if type(name) is not str or name not in objects:
        raise T0Error('Selected carriage switch is not registered in Klipper')
    if name.startswith('gcode_button '):
        field='state'
    elif name.startswith('filament_switch_sensor '):
        field='filament_detected'
    else:
        raise T0Error('Use a Klipper gcode_button or filament_switch_sensor object')
    status=_rpc('/printer/objects/query?'+urllib.parse.urlencode({name:field})).get('status',{})
    value=status.get(name,{}).get(field)
    if field=='state':
        if value not in ('PRESSED','RELEASED'): raise T0Error('Switch state unavailable')
    elif type(value) is not bool:
        raise T0Error('Filament switch state unavailable')
    return value

def _candidates(objects):
    return sorted(o for o in objects if
                  o.startswith('gcode_button ') or o.startswith('filament_switch_sensor '))

def plan(saved,shift_x=None,dodge_y=None,*,tool=0):
    try:
        return cxchanger_plan(saved,shift_x=shift_x,dodge_y=dodge_y,tool=tool)
    except (ValueError, KeyError, TypeError) as exc:
        raise T0Error(str(exc)) from exc


def _auto_snapshot(ctx, saved):
    """Actual Klipper sensor state; never derived from staging history."""
    with SESSION_LOCK:
        _auto_invalidate(ctx)
        fault=AUTO_STATE['fault']
        last=AUTO_STATE['last_success']
    p=plan(saved)
    if AUTO_SENSOR not in ctx['objects']:
        return {'enabled':False,'sensor':AUTO_SENSOR,
                'reason':'T0 carriage switch is not registered in Klipper'}
    signal=_sensor_value(AUTO_SENSOR,ctx['objects'])
    if signal not in (AUTO_MOUNTED,AUTO_EMPTY):
        raise T0Error('Unknown T0 presence switch state')
    attached=(signal==AUTO_MOUNTED)
    at_stage=(abs(ctx['position'][0]-ctx['x'])<=POSITION_TOL
              and abs(ctx['position'][1]-ctx['safe_y'])<=POSITION_TOL)
    # If already at the start of dock approach, no staging movement needed.
    # Otherwise never cross from inside the dock region blindly.
    can_stage=at_stage or ctx['position'][1]>=ctx['safe_y']-POSITION_TOL
    # Prevent the legacy T0-only endpoint from releasing a T1+ hotend when
    # its shared presence switch is PRESSED.
    from cxm_tools import mounted_other_tool
    other=mounted_other_tool(pid=ctx['pid'],revision=ctx['revision'])
    reason=('T'+str(other)+' is mounted; T0 controls cannot drop it' if other is not None else
            fault if fault else
            None if can_stage else
            'Carriage is inside the dock approach zone; safely reposition before running an automatic test')
    return {'enabled':not bool(reason),'reason':reason,'fault':fault,
            'sensor':AUTO_SENSOR,'signal':signal,'attached':attached,
            'action':'dropoff' if attached else 'pickup',
            'at_stage':at_stage,
            'staging_x_mm':ctx['x'],'staging_y_mm':ctx['safe_y'],
            'shift_x_mm':p['shift_x'],'dodge_y_mm':p['dodge_y'],
            'safe_clearance_mm':p['clearance_y'],
            'plan':p,'last_success':last,
            'note':'Switch signal is a tool-presence indication, not independent mechanical-latch proof.'}


# Deprecated Python pickup/dropoff and repeat-cycle execution removed.
# Physical toolchanges are exclusively CXM_SELECT_TOOL in Klipper.

def status(store):
    saved=store.read()
    try:
        ctx=_safe_context(saved)
        p=plan(saved)
        with SESSION_LOCK:
            _invalidate(ctx)
            stage=SESSION['stage']
            sensor=SESSION['sensor']
            samples=SESSION['samples'].copy()
            last=SESSION['last_action']
        candidate=_candidates(ctx['objects'])
        live={}
        for name in candidate:
            try: live[name]=_sensor_value(name,ctx['objects'])
            except T0Error: live[name]=None
        first_dropoff_ready=(stage=='staged' and last=='stage' and sensor is not None
                             and 'mounted' in samples and 'empty' not in samples
                             and live.get(sensor)==samples['mounted'])
        # Sensor registration after Approach clears stage but intentionally
        # leaves last_action='stage'. Recover this valid first-cycle state as
        # well as a fresh null/null state, always with operator confirmation.
        # Never recover after attempted pickup/dropoff or other actions.
        can_confirm_staging=(
            stage is None and last in (None,'stage') and
            sensor in candidate and 'mounted' in samples and 'empty' not in samples and
            live.get(sensor)==samples['mounted'] and
            abs(ctx['position'][0]-ctx['x'])<=POSITION_TOL and
            abs(ctx['position'][1]-ctx['safe_y'])<=POSITION_TOL)
        return {'ready':True,'tool':0,'saved_xy_mm':{'x':ctx['x'],'y':ctx['y']},
                'safe_y_mm':ctx['safe_y'],'position_mm':ctx['position'],
                'plan':p,'sensor_candidates':candidate,'sensor_states':live,
                'sensor':sensor,'sensor_samples':samples,
                'sensor_calibrated':sensor is not None and 'empty' in samples
                                    and 'mounted' in samples and samples['empty']!=samples['mounted'],
                'stage':stage,'last_action':last,
                'can_confirm_staging':can_confirm_staging,
                'first_dropoff_ready':first_dropoff_ready,
                'first_dropoff_pending_empty':last=='first_dropoff_pending',
                'automatic':_auto_snapshot(ctx,saved),
                'blockers':[],
                'warning':'T0 test moves the carriage. All waypoints require physical clearance; tool pickup is not inferred from coordinates.'}
    except (T0Error,ValueError,KeyError,TypeError) as e:
        return {'ready':False,'tool':0,'blockers':[str(e)],'stage':None,'sensor_candidates':[],
                'sensor_calibrated':False,
                'automatic':{'enabled':False,'reason':str(e)}}

def _invalidate(ctx):
    if SESSION['pid']!=ctx['pid'] or SESSION['revision']!=ctx['revision']:
        SESSION.update(pid=ctx['pid'],revision=ctx['revision'],stage=None,
                       last_action=None,sensor=None,samples={},xy=None,path=None)

def confirm_staging(*, store, expected_revision, acknowledgement):
    """Reconfirm an already staged T0 without issuing printer movement.

    A backend reload or a test-control page refresh can lose volatile stage
    state. Do not jog the toolhead merely to reconstruct that bookkeeping.
    Confirm the real Klipper position and the carriage-mounted sensor,
    require an explicit physical operator check, then re-arm only the initial
    mounted-T0 first-dropoff step. This never certifies pickup or creates an
    EMPTY sensor sample.
    """
    if acknowledgement!='I_PHYSICALLY_CONFIRMED_T0_STAGED_AND_XY_NOT_HAND_MOVED':
        raise T0Error('Confirm physical T0 staging and that X/Y were not manually moved after homing')
    if not MOVE_LOCK.acquire(blocking=False):
        raise T0Error('Another printer motion operation is in progress')
    try:
        saved=store.read()
        if saved['revision']!=expected_revision:
            raise T0Error('T0 coordinates changed; refresh before confirming')
        # Verifies Klipper truly ready and idle, XYZ homed, Z>=20, all 6 motors
        # energized, valid stored dock XY, and current X/Y matches staging.
        ctx=_safe_context(saved,require_in_park=True)
        plan(saved)
        with SESSION_LOCK:
            _invalidate(ctx)
            if (SESSION['stage'] is not None or
                SESSION['last_action'] not in (None,'stage')):
                raise T0Error('Only an untouched first-cycle staging record can be restored')
            sensor=SESSION['sensor']
            samples=SESSION['samples']
            if (sensor is None or sensor not in _candidates(ctx['objects'])
                or 'mounted' not in samples or 'empty' in samples):
                raise T0Error('Record the actual T0 MOUNTED sensor first')
            live=_sensor_value(sensor,ctx['objects'])
            if live!=samples['mounted']:
                raise T0Error('T0 presence switch does not match recorded MOUNTED')
            SESSION.update(stage='staged',last_action='stage',
                           xy=[ctx['x'],ctx['safe_y']],path=None)
        return {'status':'SUPERVISED_T0_STAGING_CONFIRMED_NO_MOVEMENT',
                'position_mm':ctx['position'],
                'note':'Live X/Y, motor power, homing and MOUNTED switch checked. '
                       'No G-code issued. Physically verify dropoff travel before moving.'}
    finally:
        MOVE_LOCK.release()


def record_sensor(*,store,expected_revision,name,condition,acknowledgement):
    if acknowledgement!='I_CHECKED_THE_PHYSICAL_T0_SENSOR':
        raise T0Error('Visually confirm actual empty/mounted T0 before recording sensor')
    if condition not in ('empty','mounted'):
        raise T0Error('Invalid sensor calibration condition')
    saved=store.read()
    if saved['revision']!=expected_revision: raise T0Error('Dock settings changed; refresh')
    ctx=_safe_context(saved)
    with SESSION_LOCK:
        _invalidate(ctx)
        candidates=_candidates(ctx['objects'])
        if name not in candidates: raise T0Error('No supported sensor object selected')
        value=_sensor_value(name,ctx['objects'])
        if SESSION['last_action']=='first_dropoff_pending':
            if name!=SESSION['sensor'] or condition!='empty':
                raise T0Error('First dropoff awaits physical EMPTY confirmation on the original sensor')
            if value==SESSION['samples'].get('mounted'):
                raise T0Error('Sensor still reports MOUNTED; T0 is not verified released')
        if SESSION['sensor']!=name:
            SESSION['sensor']=name
            SESSION['samples']={}
            SESSION['stage']=None
        SESSION['samples'][condition]=value
        # First mounted-hotend commissioning: the mechanism just returned
        # T0 to its dock and the operator physically confirmed EMPTY.
        # This is the only route from the initial cycle to normal pickup.
        if condition=='empty' and SESSION['last_action']=='first_dropoff_pending':
            SESSION['last_action']='dropoff'
        samples=SESSION['samples'].copy()
        verified='empty' in samples and 'mounted' in samples and samples['empty']!=samples['mounted']
    return {'recorded':condition,'value':value,'both_states_distinct':verified,
            'note':'Sensor signal evidence only; visually verify coupling for every supervised test.'}

