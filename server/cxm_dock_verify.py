"""Supervised dock XY verification; sensor is telemetry, not motion interlock.

Operator confirms dock engagement and a clear physical path. Automatic
pickup/dropoff retains its strict independent presence-sensor protections.
"""
import math
import time
from cxm_manual import _check, _check_after_own_command, ManualDockError
from cxm_runtime import MOVE_LOCK, _rpc

ACK = 'I_INSPECTED_LOCKED_DOCK_AND_CLEAR_PATH'
VERSION = 2
VERIFY_LIFETIME = 600.0

def _state(tool, store, *, after=False):
    if after:
        return _check_after_own_command(tool,store,jog=True,expected_sensor=None)
    return _check(tool,store.read(),getattr(store,'_completed_dock_move',None),
                  expected_sensor=None)

def _ready_macro():
    q='/printer/objects/query?gcode_macro%20CXM_DOCK_VERIFY_MOVE=version'
    state=_rpc(q).get('status',{}).get('gcode_macro CXM_DOCK_VERIFY_MOVE',{})
    if state.get('version')!=VERSION:
        raise ManualDockError('Locked-dock verification macro not installed in Klipper. Use CXM Updates.')

def _verified(store, d):
    result=getattr(store,'_verified_dock',None)
    if not result or time.monotonic()>result['expires']:
        return False
    return (result['tool']==d['tool'] and result['revision']==d['revision']
            and result['native_identity']==d['native_tool_identity']
            and abs(result['xy']['x']-d['xy']['x'])<=0.02
            and abs(result['xy']['y']-d['xy']['y'])<=0.02)

def status(tool,store):
    d=_state(tool,store)
    d.pop('_motion_signature',None)
    d['dock_locked_operator_confirmation_required']=True
    d['travel_verified']=_verified(store,d)
    try:
        _ready_macro()
        d['macro_loaded']=True
    except (ManualDockError, OSError, ValueError):
        d['macro_loaded']=False
    return d

def _one_move(tool,axis,distance,store,before):
    if axis not in ('X','Y') or not math.isfinite(distance):
        raise ManualDockError('Invalid guarded dock movement')
    q='CXM_DOCK_VERIFY_MOVE TOOL=%d AXIS=%s DIST=%.4f' % (tool,axis,distance)
    _rpc('/printer/gcode/script',{'script':q})
    after=_state(tool,store,after=True)
    expected=before['xy'][axis.lower()]+distance
    if after['revision']!=before['revision'] or after['native_tool_identity']!=before['native_tool_identity']:
        raise ManualDockError('Configuration or tool identity changed during movement')
    if abs(after['xy'][axis.lower()]-expected)>0.08:
        raise ManualDockError('Motion endpoint not verified')
    other='y' if axis=='X' else 'x'
    if abs(after['xy'][other]-before['xy'][other])>0.02 or abs(after['z']-before['z'])>0.02:
        raise ManualDockError('Unexpected other-axis movement')
    store._completed_dock_move=(time.monotonic()+3.0,after['_motion_signature'])
    return after

def roundtrip(*,tool,expected_revision,acknowledgement,store):
    if acknowledgement!=ACK:
        raise ManualDockError('Confirm physical dock alignment and full XY travel clear')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ManualDockError('Another CXM movement is running')
    try:
        store._verified_dock=None
        before=_state(tool,store)
        if before['revision']!=expected_revision:
            raise ManualDockError('Saved dock configuration changed; refresh')
        if before['jog_revision']!=2:
            raise ManualDockError('Native 50 mm/s jog revision 2 required')
        _ready_macro()
        x,y=before['xy']['x'],before['xy']['y']
        if y+100.0>before['limits']['y'][1]:
            raise ManualDockError('Not enough positive Y travel for 100 mm out-and-back')
        # Continuous outward move. Check position, homing and motor status before return.
        outward=_one_move(tool,'Y',100.0,store,before)
        # Re-check position, homing, motors, tool identity and printer state.
        back=_one_move(tool,'Y',-100.0,store,outward)
        if abs(back['xy']['x']-x)>0.02 or abs(back['xy']['y']-y)>0.02:
            raise ManualDockError('Return position differs from original dock datum')
        store._verified_dock={'tool':tool,'revision':expected_revision,
            'native_identity':back['native_tool_identity'],'xy':dict(back['xy']),
            'expires':time.monotonic()+VERIFY_LIFETIME}
        return {'verified':True,'tool':tool,'start':{'x':x,'y':y},
                'end':dict(back['xy']),'out_mm':100,'back_mm':100,
                'sensor':back['sensor'],'revision':expected_revision}
    finally:
        MOVE_LOCK.release()

def adjust(*,tool,axis,distance,expected_revision,acknowledgement,store):
    if acknowledgement!=ACK:
        raise ManualDockError('Confirm dock alignment and clear fine-adjust path')
    if axis not in ('x','y') or type(distance) not in (float,int) or not math.isfinite(distance):
        raise ManualDockError('Invalid dock alignment adjustment')
    if abs(distance) not in (0.01,0.1,1.0):
        raise ManualDockError('Use 0.01, 0.1 or 1 mm adjustments')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ManualDockError('Another CXM operation is running')
    try:
        store._verified_dock=None
        before=_state(tool,store)
        if before['revision']!=expected_revision:
            raise ManualDockError('Dock configuration changed')
        _ready_macro()
        next_value=before['xy'][axis]+distance
        lo,hi=before['limits'][axis]
        if next_value<lo or next_value>hi:
            raise ManualDockError('Adjustment exceeds configured machine limits')
        after=_one_move(tool,axis.upper(),distance,store,before)
        return {'adjusted':True,'xy':dict(after['xy']),
                'sensor':after['sensor'],'repeat_test_required':True,
                'revision':expected_revision}
    finally:
        MOVE_LOCK.release()

def save(*,tool,expected_revision,acknowledgement,store):
    if acknowledgement!=ACK:
        raise ManualDockError('Confirm which hotend is physically LOCKED in its dock')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ManualDockError('Another CXM operation is running')
    try:
        before=_state(tool,store)
        if expected_revision!=before['revision'] or not _verified(store,before):
            raise ManualDockError('Pass +100/-100 locked-dock test at the current XY before saving')
        _rpc('/printer/gcode/script',{'script':'M400'})
        stable=_state(tool,store,after=True)
        if not _verified(store,stable):
            raise ManualDockError('Carriage moved or dock state changed before Save')
        from cxm_native import invalidate_for_config_edit
        invalidate_for_config_edit(permit_supervised_dock_calibration=True,store=store,tool=tool)
        after=_state(tool,store,after=True)
        # Invalidation changes the native identity to -2. All other state must
        # remain unchanged before persistent save.
        if after['revision']!=expected_revision:
            raise ManualDockError('Printer state changed; dock NOT saved')
        if any(abs(after['xy'][axis]-stable['xy'][axis])>0.02 for axis in 'xy'):
            raise ManualDockError('XY changed during invalidation; dock NOT saved')
        result=store.save_dock(tool,dict(stable['xy']),expected_revision)
        verified=store.read()
        saved=verified['config']['tools'][tool]
        if not saved['dock_reference_accepted'] or saved['dock_x']!=stable['xy']['x'] or saved['dock_y']!=stable['xy']['y']:
            raise ManualDockError('Saved dock XY did not verify on disk')
        store._verified_dock=None
        return {'saved':True,'verified':True,'tool':tool,'xy':dict(stable['xy']),
                'backup':result.get('backup'),'revision':verified['revision'],
                'needs_native_sync':True}
    finally:
        MOVE_LOCK.release()
