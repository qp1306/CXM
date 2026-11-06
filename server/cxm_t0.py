"""CXM T0 slow-speed XY pickup/dropoff commissioning.

Explicit operator-supervised actions only, scoped to T0. No printer.cfg
editing, no Z movement, no heater control, and no automatic tool activation.
The tested Lineux dock X/Y is used without x_docking_adjust correction.
"""
from __future__ import annotations
import math
import threading
import time
import urllib.parse
from cxm_lineux import _rpc, MOVE_LOCK, MeasurementError

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
AUTO_SHIFT_X=-4.8
AUTO_DODGE_Y=14.0
AUTO_STATE={'pid':None,'revision':None,'fault':None,'last_success':None}

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

def _safe_context(saved, *, require_homed=True, require_in_park=False):
    if saved['migration_required']:
        raise T0Error('CXM settings migration required before T0 testing')
    # The commissioning command always targets tool index 0. Other enabled
    # tool slots may exist, but they are never selected or moved by this API.
    # Do not confuse "T0-only test" with "printer has one configured tool".
    count=saved['config']['globals'].get('tool_count')
    if type(count) is not int or not 1 <= count <= 12:
        raise T0Error('Invalid configured hotend count')
    t=saved['config']['tools'][0]
    if t['maintenance_lockout']:
        raise T0Error('T0 is under maintenance lockout')
    if t['dock_x'] is None or t['dock_y'] is None:
        raise T0Error('Save T0 dock X/Y first')
    x=number(t['dock_x'],'Dock X',0,335)
    y=number(t['dock_y'],'Dock Y',0,362)
    safe=number(saved['config']['globals']['safe_y'],'Configured safe Y',0,362)
    if safe<y+35:
        raise T0Error('Configured safe Y is too close to dock for guarded path')
    if x<10 or x>325 or y<10 or y>320:
        raise T0Error('T0 dock outside supervised test zone')
    info=_rpc('/printer/info')
    if info.get('state')!='ready' or type(info.get('process_id')) is not int:
        raise T0Error('Klipper not ready or identity unavailable')
    objects=_rpc('/printer/objects/list').get('objects',[])
    necessary={'toolhead','stepper_enable','idle_timeout'}
    if not necessary.issubset(set(objects)):
        raise T0Error('Cannot verify homing, motor power and idle status')
    query={'toolhead':'homed_axes,position',
           'stepper_enable':'steppers','idle_timeout':'state'}
    for key,field in [('print_stats','state'),('virtual_sdcard','is_active'),
                      ('pause_resume','is_paused')]:
        if key in objects: query[key]=field
    status=_rpc('/printer/objects/query?'+urllib.parse.urlencode(query)).get('status',{})
    if status.get('idle_timeout',{}).get('state') not in ('Idle','Ready'):
        raise T0Error('Klipper is not idle')
    if status.get('print_stats',{}).get('state') not in (None,'standby','complete','cancelled','error'):
        raise T0Error('Printer has a print active or paused')
    if 'virtual_sdcard' in objects and status.get('virtual_sdcard',{}).get('is_active') is not False:
        raise T0Error('Virtual SD print active or unknown')
    if 'pause_resume' in objects and status.get('pause_resume',{}).get('is_paused') is not False:
        raise T0Error('Printer paused')
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
    return {'pid':info['process_id'],'x':x,'y':y,'safe_y':safe,
            'position':pos[:3],'objects':objects,'revision':saved['revision']}

def _wait_for_idle_after_move(saved, *, parked, expected_pid, timeout_sec=10.0):
    """Read-only wait for Klipper to settle after a completed G-code script.

    Moonraker can return from an M400-ended script before Klipper's
    idle_timeout state changes from Printing to Ready/Idle. Retry only that
    known transient status, never a homing, motor-power, print, position,
    config, or sensor failure. No motion commands are issued while waiting.
    """
    deadline=time.monotonic()+timeout_sec
    while True:
        try:
            ctx=_safe_context(saved,require_in_park=parked)
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

def plan(saved,shift_x=-3.0,dodge_y=14.0):
    # Geometry follows the original CxChanger sequence. These are tentative
    # mechanical adjustments, NOT a claim of verified actual T0 geometry.
    t=saved['config']['tools'][0]
    x=number(t['dock_x'],'Dock X',0,335)
    y=number(t['dock_y'],'Dock Y',0,362)
    safe=number(saved['config']['globals']['safe_y'],'Safe Y',0,362)
    dx=number(shift_x,'Lateral shift X',-8,-1)
    dy=number(dodge_y,'Dodge Y',5,25)
    if x+dx<5 or x+dx>330 or y+dy+20>safe:
        raise T0Error('Pickup/dropoff path conflicts with physical limits or safe Y')
    return {'stage':[(x,safe)],
            'pickup':[(x,y+dy),(x+dx,y+dy),(x+dx,y),(x,y),(x,safe)],
            'dropoff':[(x,y),(x+dx,y),(x+dx,y+dy),(x,y+dy),(x,safe)],
            'shift_x':dx,'dodge_y':dy,'safe_y':safe}

def _auto_snapshot(ctx, saved):
    """Actual Klipper sensor state; never derived from staging history."""
    with SESSION_LOCK:
        _auto_invalidate(ctx)
        fault=AUTO_STATE['fault']
        last=AUTO_STATE['last_success']
    p=plan(saved,AUTO_SHIFT_X,AUTO_DODGE_Y)
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
    reason=(fault if fault else
            None if can_stage else
            'Carriage is inside the dock approach zone; safely reposition before running an automatic test')
    return {'enabled':not bool(reason),'reason':reason,'fault':fault,
            'sensor':AUTO_SENSOR,'signal':signal,'attached':attached,
            'action':'dropoff' if attached else 'pickup',
            'at_stage':at_stage,
            'staging_x_mm':ctx['x'],'staging_y_mm':ctx['safe_y'],
            'shift_x_mm':AUTO_SHIFT_X,'dodge_y_mm':AUTO_DODGE_Y,
            'plan':p,'last_success':last,
            'note':'Switch signal is a tool-presence indication, not independent mechanical-latch proof.'}


def _automatic_script(path, kind, *, at_stage):
    """Build ONE sequential XY script for staging and tool movement.

    Keep the original tested path and feeds. M400 between stages guarantees
    that the X positioning at Safe Y completes before entering dock Y.
    Moonraker receives one /printer/gcode/script request for the whole cycle.
    """
    movement=_gcode(path[kind],kind).splitlines()
    if at_stage:
        return '\\n'.join(movement)
    stage=_gcode(path['stage'],'stage').splitlines()
    return '\\n'.join(stage+movement[1:])


def automatic_toolchange(*,store,expected_revision,kind,acknowledgement):
    """One operator-confirmed T0 pickup or dropoff, with automatic staging.

    Only the verified T0 carriage switch decides the allowed action.
    Every move is at reduced commissioning speed; no heaters, Z movement,
    external tool selection or permanent configuration writes.
    """
    if kind not in ('pickup','dropoff'):
        raise T0Error('Only T0 pickup or dropoff can be commanded')
    if acknowledgement!='I_CONFIRMED_T0_XY_PATH_CLEAR_AND_WILL_SUPERVISE':
        raise T0Error('Physically confirm the complete T0 approach path before movement')
    if not MOVE_LOCK.acquire(blocking=False):
        raise T0Error('Another printer motion operation is in progress')
    movement_sent=False
    ctx=None
    try:
        saved=store.read()
        if saved['revision']!=expected_revision:
            raise T0Error('T0 coordinates changed; refresh the controller')
        ctx=_safe_context(saved)
        auto=_auto_snapshot(ctx,saved)
        if not auto['enabled']:
            raise T0Error(auto.get('reason') or 'T0 automatic test blocked')
        expected=AUTO_MOUNTED if kind=='dropoff' else AUTO_EMPTY
        after_signal=AUTO_EMPTY if kind=='dropoff' else AUTO_MOUNTED
        if auto['signal']!=expected:
            raise T0Error('T0 switch indicates '+('attached' if auto['attached'] else 'empty')+
                          '; '+kind+' is the wrong operation')
        p=plan(saved,AUTO_SHIFT_X,AUTO_DODGE_Y)
        with SESSION_LOCK:
            # Ordinary test session does not determine hardware state.
            # Clear obsolete staging state to avoid cross-workflow approval.
            _invalidate(ctx)
            SESSION['stage']=None
            SESSION['last_action']=None
        # One complete ordered Klipper script. The previous two-request
        # handoff stopped at staging when Moonraker briefly reported Printing.
        # Do not introduce an HTTP/API readiness dependency between XY moves.
        # Preflight and the live switch state were checked immediately above;
        # neither the stored stage flag nor manual switch sampling is needed.
        script=_automatic_script(p,kind,at_stage=auto['at_stage'])
        movement_sent=True
        _rpc('/printer/gcode/script',{'script':script})
        finished_saved=store.read()
        if finished_saved['revision']!=expected_revision:
            raise T0Error('CXM configuration changed during T0 test')
        end=_wait_for_idle_after_move(finished_saved,parked=True,
                                      expected_pid=ctx['pid'])
        actual=_sensor_value(AUTO_SENSOR,end['objects'])
        if actual!=after_signal:
            raise T0Error('T0 '+kind+' failed: presence switch still reports '+
                          str(actual)+', expected '+after_signal+
                          '. Inspect the physical carriage and dock.')
        with SESSION_LOCK:
            AUTO_STATE['last_success']=kind
            AUTO_STATE['fault']=None
        return {'status':'T0_'+kind.upper()+'_SENSOR_CONFIRMED',
                'kind':kind,'signal':actual,'at_stage':True,
                'position_mm':end['position'],
                'staging_performed':not auto['at_stage'],
                'note':'Physical switch transition confirmed. Visually inspect hotend seating; this does not certify full tool commissioning.'}
    except Exception as exc:
        if movement_sent:
            with SESSION_LOCK:
                AUTO_STATE['fault']=('T0 '+kind+' interrupted: '+str(exc)[:150]+
                                     '. Inspect the carriage and dock before clearing this fault.')
        raise
    finally:
        MOVE_LOCK.release()


def clear_automatic_fault(*,store,expected_revision,acknowledgement):
    if acknowledgement!='I_PHYSICALLY_INSPECTED_T0_AND_PATH_AFTER_TEST_FAILURE':
        raise T0Error('Physical carriage and dock inspection is required')
    if not MOVE_LOCK.acquire(blocking=False):
        raise T0Error('Another printer motion operation is in progress')
    try:
        saved=store.read()
        if saved['revision']!=expected_revision:
            raise T0Error('T0 coordinates changed; refresh')
        ctx=_safe_context(saved)
        if AUTO_SENSOR not in ctx['objects']:
            raise T0Error('T0 switch is unavailable')
        _sensor_value(AUTO_SENSOR,ctx['objects'])
        with SESSION_LOCK:
            _auto_invalidate(ctx)
            AUTO_STATE['fault']=None
        return {'status':'T0_TEST_FAULT_CLEARED_NO_MOVEMENT',
                'note':'Operator confirmed physical inspection; no G-code issued.'}
    finally:
        MOVE_LOCK.release()


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

def _gcode(points,kind):
    if kind=='stage':
        speeds=[SAFE_FEED]
    elif kind=='pickup':
        speeds=[TEST_FEED,TEST_FEED,TEST_FEED,LATCH_FEED,TEST_FEED]
    else:
        speeds=[TEST_FEED,LATCH_FEED,TEST_FEED,TEST_FEED,TEST_FEED]
    lines=['G90']
    if kind=='stage':
        # Go to the known-configured safe-Y line before crossing toward dock X
        x,y=points[0]
        lines.extend([f'G1 Y{y:.5f} F{SAFE_FEED}',f'G1 X{x:.5f} F{SAFE_FEED}'])
    else:
        for (x,y),feed in zip(points,speeds):
            lines.append(f'G1 X{x:.5f} Y{y:.5f} F{feed}')
    lines.append('M400')
    return '\n'.join(lines)

def motion(*,store,expected_revision,kind,acknowledgement,
           shift_x=-3.0,dodge_y=14.0):
    if kind not in ('stage','pickup','dropoff'):
        raise T0Error('Unsupported test command')
    if acknowledgement!='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH':
        raise T0Error('Physical path confirmation required')
    if not MOVE_LOCK.acquire(blocking=False):
        raise T0Error('Another printer motion operation is in progress')
    try:
        saved=store.read()
        if saved['revision']!=expected_revision: raise T0Error('T0 coordinates changed; refresh')
        ctx=_safe_context(saved,require_in_park=(kind!='stage'))
        points=plan(saved,shift_x,dodge_y)[kind]
        first_dropoff=False
        with SESSION_LOCK:
            _invalidate(ctx)
            if kind=='stage':
                # Require starting from behind the nominal safe Y line.
                if ctx['position'][1]<ctx['safe_y']:
                    raise T0Error('Stage only from Y at or beyond safe Y; home and park centrally first')
            else:
                if SESSION['stage']!='staged':
                    raise T0Error('First run Approach T0 and inspect its staging position')
                sensor=SESSION['sensor']
                samples=SESSION['samples']
                last=SESSION['last_action']
                if sensor is None:
                    raise T0Error('Select and record the carriage hotend-presence sensor first')
                live=_sensor_value(sensor,ctx['objects'])
                # First commissioning cycle can start with T0 already mounted.
                # Permit only the FIRST observed dropoff from the verified
                # staged position and the recorded mounted sensor signal.
                # Learn EMPTY only after movement AND human inspection.
                first_dropoff=(kind=='dropoff' and last=='stage' and
                               'mounted' in samples and 'empty' not in samples)
                if first_dropoff:
                    if live!=samples['mounted']:
                        raise T0Error('First dropoff blocked: live sensor does not show T0 MOUNTED')
                else:
                    if ('empty' not in samples or 'mounted' not in samples
                        or samples['empty']==samples['mounted']):
                        raise T0Error('Verify carriage sensor EMPTY and MOUNTED before pickup/dropoff')
                    expected=samples['empty' if kind=='pickup' else 'mounted']
                    if live!=expected:
                        raise T0Error('T0 sensor not in expected pre-motion state')
                    if kind=='dropoff' and last!='pickup':
                        raise T0Error('Dropoff requires a successful supervised pickup')
                    if kind=='pickup' and last not in (None,'dropoff','stage'):
                        raise T0Error('Cannot pick up again until T0 is released')
            # Disarm before any irreversible movement. On failure, a fresh
            # staging test and manual inspection are always required.
            SESSION['stage']=None
        code=_gcode(points,kind)
        _rpc('/printer/gcode/script',{'script':code})
        # Re-evaluate actual position, motor power, and state after motion.
        after=_safe_context(store.read(),require_in_park=True)
        if kind!='stage':
            with SESSION_LOCK:
                sensor=SESSION['sensor']
                samples=SESSION['samples'].copy()
            live=_sensor_value(sensor,after['objects'])
            if first_dropoff:
                if live==samples['mounted']:
                    raise T0Error('First dropoff did not change sensor. Inspect T0 and do not continue.')
            elif live!=samples['mounted' if kind=='pickup' else 'empty']:
                raise T0Error('Sensor did not confirm '+kind+' after motion. Inspect carriage and do not continue.')
        with SESSION_LOCK:
            SESSION.update(stage='staged',
                           last_action='first_dropoff_pending' if first_dropoff else kind,
                           xy=[after['x'],after['safe_y']],
                           path={'shift_x':shift_x,'dodge_y':dodge_y})
        return {'status':('SUPERVISED_T0_FIRST_DROPOFF_AWAITING_EMPTY_CONFIRMATION'
                          if first_dropoff else
                          'SUPERVISED_T0_'+kind.upper()+'_COMPLETE'),
                'position_mm':after['position'],'source_dock_xy_mm':[ctx['x'],ctx['y']],
                'steps':len(points),'sensor_confirmed':kind!='stage' and not first_dropoff,
                'note':('Visually confirm T0 is fully seated in its dock and carriage is EMPTY; '
                        'then press Record carriage EMPTY. No tool pickup is enabled until confirmed.'
                        if first_dropoff else
                        'Operator must independently inspect physical T0 engagement. '
                        'No active-tool or commissioning flags changed.')}
    finally:
        MOVE_LOCK.release()
