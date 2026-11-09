"""CXM V2 dock positioning: motor-on, homed, bounded manual XY jog and capture.

No motor release, automatic search, calibration homing, Lineux, or pickup motion.
Only the existing native CxChanger Klipper macros perform tool changes.
"""
import math
import time
import urllib.parse

from cxm_runtime import MOVE_LOCK, _rpc

class ManualDockError(RuntimeError):
    pass

def _check(tool, saved):
    if type(tool) is not int or not 0 <= tool < saved['config']['globals']['tool_count']:
        raise ManualDockError('Select an active T0–T11 dock')
    if saved['migration_required'] or saved['config']['tools'][tool]['maintenance_lockout']:
        raise ManualDockError('Configuration migration or tool maintenance lockout')
    info=_rpc('/printer/info')
    if info.get('state')!='ready':
        raise ManualDockError('Klipper is not ready')
    keys=['toolhead','idle_timeout','print_stats','stepper_enable',
          'gcode_button cxm_tool_detect','gcode_macro _CXM_TEST_STATE',
          'gcode_macro _CXM_NATIVE','configfile']
    q='&'.join(urllib.parse.quote(k,safe='') for k in keys)
    state=_rpc('/printer/objects/query?'+q).get('status',{})
    head=state.get('toolhead',{})
    axes=str(head.get('homed_axes','')).lower()
    pos=head.get('position')
    if not all(k in axes for k in 'xyz') or not isinstance(pos,list) or len(pos)<3:
        raise ManualDockError('Home XYZ before motor-on alignment')
    if type(pos[2]) not in (int,float) or pos[2]<20:
        raise ManualDockError('Physical Z clearance below 20 mm; stop')
    if state.get('idle_timeout',{}).get('state') not in ('Idle','Ready'):
        raise ManualDockError('Printer is busy; manual dock motion disabled')
    if state.get('print_stats',{}).get('state') not in ('standby','complete','cancelled','error',None):
        raise ManualDockError('Print is active')
    motors=state.get('stepper_enable',{}).get('steppers',{})
    for name in ('stepper_x','stepper_y','stepper_z','stepper_z1','stepper_z2','stepper_z3'):
        if motors.get(name) is not True:
            raise ManualDockError(name+' is not energised; rehome and recheck')
    # Mechanical dock alignment REQUIRES the selected hotend to be mounted.
    # This mode is separate from native pickup/dropoff, which retains its own
    # strict EMPTY/PRESSED transition and identity interlocks.
    signal=state.get('gcode_button cxm_tool_detect',{}).get('state')
    if signal!='PRESSED':
        raise ManualDockError('Manual dock alignment requires a MOUNTED hotend (sensor PRESSED)')
    test=state.get('gcode_macro _CXM_TEST_STATE',{})
    native=state.get('gcode_macro _CXM_NATIVE',{})
    if test.get('running')==1:
        raise ManualDockError('Native tool test running; alignment blocked')
    identity=native.get('current_tool')
    # For MANUAL alignment only, the selected tool is an operator declaration:
    # the presence switch cannot identify a hotend and native identity may be
    # stale after a physical change. We invalidate it before any disk save.
    # Automatic toolchanges still require confirmed identity and sensor state.
    limits=state.get('configfile',{}).get('settings',{})
    xy={}
    for i,ax in enumerate('xy'):
        cfg=limits.get('stepper_'+ax,{})
        low=cfg.get('position_min',0)
        high=cfg.get('position_max')
        value=pos[i]
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (low,high,value)):
            raise ManualDockError('Missing physical '+ax.upper()+' travel limits')
        xy[ax]={'position':float(value),'min':float(low)+1.0,'max':float(high)-1.0}
        if not xy[ax]['min']<=value<=xy[ax]['max']:
            raise ManualDockError('Carriage outside guarded '+ax.upper()+' travel')
    return {'tool':tool,'xy':{'x':xy['x']['position'],'y':xy['y']['position']},
            'limits':{ax:[xy[ax]['min'],xy[ax]['max']] for ax in 'xy'},
            'z':float(pos[2]),'homed':True,'motors_enabled':True,
            'sensor':'PRESSED','identity_source':'operator_selected',
            'native_tool_identity':identity,'revision':saved['revision'],'ready':True}

def _check_after_own_command(tool, store):
    """Wait for Klipper's transient idle_timeout=Printing after our own M400.

    This is ONLY used after a successfully submitted manual jog/capture command.
    Do not send another movement while waiting. Revalidate all other guards
    on every sample. Fail closed after a short bounded deadline.
    """
    deadline=time.monotonic()+3.0
    while True:
        try:
            return _check(tool,store.read())
        except ManualDockError as exc:
            if str(exc)!='Printer is busy; manual dock motion disabled':
                raise
            if time.monotonic()>=deadline:
                raise ManualDockError(
                    'Klipper did not return to idle after commanded movement; '
                    'motion result uncertain. Inspect before retrying') from exc
            time.sleep(0.15)

def status(tool,store):
    return _check(tool,store.read())

def jog(*,tool,axis,distance,expected_revision,acknowledgement,store):
    if acknowledgement!='I_APPROVE_SUPERVISED_MOTOR_ON_JOG':
        raise ManualDockError('Fresh operator approval required')
    if axis not in ('x','y') or type(distance) not in (int,float) or not math.isfinite(distance):
        raise ManualDockError('Jog axis/distance invalid')
    if abs(distance) not in (10.0,1.0,0.1,0.01):
        raise ManualDockError('Use only the supported 10, 1, 0.1 or 0.01 mm jog increments')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ManualDockError('Another CXM motion or configuration operation is running')
    try:
        before=_check(tool,store.read())
        if expected_revision != before['revision']:
            raise ManualDockError('Settings changed; reload and approve jog')
        next_value=before['xy'][axis]+distance
        lo,hi=before['limits'][axis]
        if not lo <= next_value <= hi:
            raise ManualDockError('Jog would exceed guarded physical travel')
        # Klipper alone owns all physical movement and modal G-code.
        # The service only requests the named, independently guarded macro.
        command='CXM_MANUAL_DOCK_JOG TOOL=%d AXIS=%s DIST=%.4f' % (
            tool,axis.upper(),distance)
        _rpc('/printer/gcode/script',{'script':command})
        after=_check_after_own_command(tool,store)
        if after['sensor']!='PRESSED' or after['native_tool_identity']!=before['native_tool_identity']:
            raise ManualDockError('Carriage state changed during jog; inspect printer')
        if abs(after['xy'][axis]-next_value)>0.08:
            raise ManualDockError('Commanded jog and reported coordinates differ; inspect printer')
        return {'jogged':True,'position':after['xy'],'revision':after['revision']}
    finally:
        MOVE_LOCK.release()

def _capture_locked(tool,expected_revision,store):
    """Capture stable XY after M400; caller holds MOVE_LOCK."""
    before=_check(tool,store.read())
    if expected_revision!=before['revision']:
        raise ManualDockError('Settings changed; refresh before capture')
    _rpc('/printer/gcode/script',{'script':'M400'})
    after=_check_after_own_command(tool,store)
    if after['sensor']!='PRESSED':
        raise ManualDockError('Mounted sensor changed during capture')
    if after['revision']!=before['revision']:
        raise ManualDockError('Settings changed during capture')
    for axis in 'xy':
        if abs(after['xy'][axis]-before['xy'][axis])>0.02:
            raise ManualDockError('Position moved during capture; repeat alignment')
    return after


def capture(*,tool,expected_revision,acknowledgement,store):
    if acknowledgement!='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON':
        raise ManualDockError('Physical alignment confirmation required')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ManualDockError('Another CXM operation is running')
    try:
        after=_capture_locked(tool,expected_revision,store)
        return {'captured':True,'tool':tool,'xy':after['xy'],
                'expected_revision':after['revision'],'saved':False,
                'verified':False,'note':'Stationary capture only; use Save to persist.'}
    finally:
        MOVE_LOCK.release()


def save(*,tool,expected_revision,acknowledgement,store):
    """ONE atomic operator workflow: live capture -> invalidation -> disk save.

    The motion lock spans capture, native invalidation and file confirmation.
    The config Store uses its own revision-checked atomic write and backup.
    Never send X/Y/Z motion. The operator-selected tool is the identity source;
    the switch confirms PRESENT only, not tool number.
    """
    if acknowledgement!='I_INSPECTED_DOCK_ALIGNMENT_WITH_MOTORS_ON':
        raise ManualDockError('Confirm which tool is physically aligned in its dock')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ManualDockError('Another CXM operation is running')
    try:
        from cxm_native import invalidate_for_config_edit
        after=_capture_locked(tool,expected_revision,store)
        xy=dict(after['xy'])
        invalidate_for_config_edit(
            permit_mounted_provisional_dock=True,store=store,tool=tool)
        # Recheck after runtime invalidation: no external Mainsail command
        # must move the tool between the measured capture and persistent save.
        final=_check_after_own_command(tool,store)
        if final['revision']!=expected_revision or final['sensor']!='PRESSED':
            raise ManualDockError('Dock state changed before Save; coordinates NOT written')
        if any(abs(final['xy'][axis]-xy[axis])>0.02 for axis in 'xy'):
            raise ManualDockError('Dock moved after capture; coordinates NOT written')
        result=store.save_dock(tool,xy,expected_revision)
        verified=store.read()
        stored=verified['config']['tools'][tool]
        if (stored['dock_x']!=xy['x'] or stored['dock_y']!=xy['y']
            or stored['dock_reference_accepted'] is not True
            or stored['dock_z'] is not None):
            raise ManualDockError('Disk read-back does not match captured dock XY')
        return {'saved':True,'verified':True,'tool':tool,'xy':xy,
                'backup':result.get('backup'),'revision':verified['revision'],
                'needs_native_sync':True}
    finally:
        MOVE_LOCK.release()
