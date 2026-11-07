"""Guarded selected-hotend XY commissioning for T1–T11.

The selected hotend is the operator-declared identity. The shared carriage
switch reports only PRESENT or ABSENT: it cannot identify which tool is
mounted. A PRESSED signal permits a supervised dropoff of the selected tool
only after a fresh physical-identity/path approval. Verified pickup history
still prevents switching to a different tool while one is known mounted.
T0's existing tested API remains separate and unchanged.
"""
from __future__ import annotations

import threading
import time
from cxm_lineux import MOVE_LOCK, _rpc, MeasurementError
from cxm_t0 import (_safe_context, _wait_for_idle_after_move, _sensor_value,
                    AUTO_SENSOR, AUTO_MOUNTED, AUTO_EMPTY, AUTO_STATE,
                    SAFE_FEED, TEST_FEED, LATCH_FEED, POSITION_TOL)
from cxm_cxchanger import plan as geometry_plan, automatic_script

class ToolError(MeasurementError):
    pass

# Klipper's gcode_button status can lag the physical pickup/release briefly.
# Require sustained state after M400/idle, without issuing any more movement.
POST_MOVE_SENSOR_TIMEOUT_S=2.5
POST_MOVE_SENSOR_INTERVAL_S=0.15
POST_MOVE_SENSOR_CONSECUTIVE=4

def _stable_sensor(name,objects,wanted,*,timeout_s=POST_MOVE_SENSOR_TIMEOUT_S,
                   interval_s=POST_MOVE_SENSOR_INTERVAL_S,
                   consecutive=POST_MOVE_SENSOR_CONSECUTIVE):
    """Read-only debounced verification. Unexpected/missing samples fail closed."""
    deadline=time.monotonic()+timeout_s
    streak=0
    samples=0
    last=None
    while True:
        last=_sensor_value(name,objects)
        samples+=1
        streak=streak+1 if last==wanted else 0
        if streak>=consecutive:
            return {'signal':wanted,'samples':samples,'consecutive':consecutive}
        if time.monotonic()>=deadline:
            raise ToolError('Carriage presence switch did not stabilise at '+str(wanted)+
                            ' after motion (last '+str(last)+', '+str(samples)+
                            ' samples within '+str(timeout_s)+' s). Inspect hotend seating and switch.')
        time.sleep(interval_s)

_LOCK=threading.Lock()
_STATE={'pid':None,'revision':None,'mounted_tool':None,'fault':None,'last_success':None}

def _context_guard(ctx):
    """Caller holds _LOCK. Invalidate tool identity on Klipper/config change."""
    if _STATE['pid'] != ctx['pid'] or _STATE['revision'] != ctx['revision']:
        _STATE.update(pid=ctx['pid'],revision=ctx['revision'],
                      mounted_tool=None,fault=None,last_success=None)

def mounted_other_tool(*,pid,revision):
    """Never allow legacy T0 to drop off a T1+ proven to be mounted."""
    with _LOCK:
        return (_STATE['mounted_tool']
                if _STATE['pid']==pid and _STATE['revision']==revision else None)

def _snapshot(store,tool):
    if type(tool) is not int or not 1 <= tool <= 11:
        raise ToolError('Select a valid hotend T1–T11')
    saved=store.read()
    if saved['migration_required']:
        raise ToolError('CXM configuration migration required')
    count=saved['config']['globals']['tool_count']
    if tool>=count:
        raise ToolError('T'+str(tool)+' is outside the configured hotend count')
    profile=saved['config']['tools'][tool]
    if profile['maintenance_lockout']:
        raise ToolError('T'+str(tool)+' is under maintenance lockout')
    if (profile['dock_x'] is None or profile['dock_y'] is None or
        profile['dock_reference_accepted'] is not True):
        raise ToolError('T'+str(tool)+' CxChanger dock XY must be measured and accepted before movement')
    ctx=_safe_context(saved,tool=tool)
    p=geometry_plan(saved,tool=tool)
    if AUTO_SENSOR not in ctx['objects']:
        raise ToolError('Shared carriage presence switch not available in Klipper')
    signal=_sensor_value(AUTO_SENSOR,ctx['objects'])
    at_stage=(abs(ctx['position'][0]-ctx['x'])<=POSITION_TOL and
              abs(ctx['position'][1]-ctx['safe_y'])<=POSITION_TOL)
    can_stage=at_stage or ctx['position'][1]>=ctx['safe_y']-POSITION_TOL
    with _LOCK:
        _context_guard(ctx)
        known=_STATE['mounted_tool']
        if known is not None and signal==AUTO_EMPTY:
            _STATE['fault']='Presence switch unexpectedly RELEASED while T'+str(known)+' was recorded mounted; inspect the coupling.'
            _STATE['mounted_tool']=None
            known=None
        fault=_STATE['fault']
        last=_STATE['last_success']
    # A fault in the proven T0 controller must be physically inspected and
    # cleared there before a different tool is moved.
    t0_fault=(AUTO_STATE['fault'] if
              AUTO_STATE['pid']==ctx['pid'] and
              AUTO_STATE['revision']==ctx['revision'] else None)
    if t0_fault:
        reason='T0 fault needs inspection/clearance before T'+str(tool)+' testing: '+str(t0_fault)
    elif fault:
        reason=fault
    elif not can_stage:
        reason='Carriage is inside the selected dock approach zone; safely rehome/park first'
    elif known is not None and known != tool:
        reason=('T'+str(known)+' is recorded as mounted. Select T'+str(known)+
                ' and safely drop it off before operating T'+str(tool))
    else:
        reason=None
    # The switch is only a presence sensor, never a tool-ID sensor. If it
    # reads PRESSED with no recorded pickup, selection + separate deliberate
    # approval supplies the operator's declared tool identity.
    identity_source=('verified_pickup' if known==tool else
                     'operator_selected' if signal==AUTO_MOUNTED and known is None else
                     None)
    return {'ready':not bool(reason),'tool':tool,'saved_xy_mm':p['dock_reference_xy'],
            'safe_y_mm':p['safe_y'],'position_mm':ctx['position'],
            'automatic':{'enabled':not bool(reason),'reason':reason,'signal':signal,
                         'action':'dropoff' if signal==AUTO_MOUNTED else 'pickup',
                         'mounted_tool':known,'identity_source':identity_source,
                         'at_stage':at_stage,'fault':fault,'last_success':last},
            'blockers':[reason] if reason else [],
            '_ctx':ctx,'_geometry':p,'_revision':saved['revision']}

def status(*,store,tool):
    try:
        r=_snapshot(store,tool)
        return {k:v for k,v in r.items() if not k.startswith('_')}
    except (ToolError,MeasurementError,ValueError,KeyError,TypeError) as exc:
        return {'ready':False,'tool':tool,'blockers':[str(exc)],
                'automatic':{'enabled':False,'reason':str(exc)}}

def automatic_toolchange(*,store,tool,expected_revision,kind,acknowledgement):
    if type(tool) is not int or not 1<=tool<=11:
        raise ToolError('This endpoint supports selected T1–T11 only')
    if kind not in ('pickup','dropoff'):
        raise ToolError('Choose pickup or dropoff')
    if acknowledgement != 'I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR':
        raise ToolError('Confirm selected hotend identity, carriage state and complete XY path')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ToolError('Another printer motion operation is running')
    sent=False
    ctx=None
    try:
        before=_snapshot(store,tool)
        ctx=before['_ctx']
        if before['_revision']!=expected_revision:
            raise ToolError('CXM configuration changed; refresh before movement')
        if not before['ready']:
            raise ToolError(before['automatic']['reason'] or 'Tool test blocked')
        auto=before['automatic']
        expected=AUTO_EMPTY if kind=='pickup' else AUTO_MOUNTED
        if auto['signal']!=expected:
            raise ToolError('Wrong operation for live carriage switch state')
        if kind=='dropoff' and auto['mounted_tool'] not in (None,tool):
            raise ToolError('Another hotend is recorded as mounted; cannot drop off T'+str(tool))
        # When PRESSED but without verified pickup history, the operator has
        # explicitly selected T{tool} and approved its identity/path. This is
        # a declaration, NOT positive electrical identification. The sensor
        # transition after the move must still independently confirm release.
        if kind=='pickup' and auto['mounted_tool'] is not None:
            raise ToolError('Carriage must be empty before pickup')
        script=automatic_script(before['_geometry'],kind,at_stage=auto['at_stage'],
                                safe_feed=SAFE_FEED,test_feed=TEST_FEED,latch_feed=LATCH_FEED)
        if store.read()['revision']!=expected_revision:
            raise ToolError('CXM settings changed immediately before movement')
        sent=True
        _rpc('/printer/gcode/script',{'script':script})
        fresh=store.read()
        if fresh['revision']!=expected_revision:
            raise ToolError('CXM settings changed during motion. Inspect physical tool.')
        end=_wait_for_idle_after_move(fresh,parked=True,expected_pid=ctx['pid'],tool=tool)
        wanted=AUTO_MOUNTED if kind=='pickup' else AUTO_EMPTY
        confirmation=_stable_sensor(AUTO_SENSOR,end['objects'],wanted)
        final_signal=confirmation['signal']
        with _LOCK:
            _context_guard(end)
            _STATE['mounted_tool']=tool if kind=='pickup' else None
            _STATE['last_success']='T'+str(tool)+' '+kind
            _STATE['fault']=None
        return {'status':'T'+str(tool)+'_'+kind.upper()+'_SENSOR_CONFIRMED',
                'tool':tool,'kind':kind,'signal':final_signal,
                'identity_source':(auto['identity_source'] if kind=='dropoff' else 'operator_selected'),
                'position_mm':end['position'],'staging_performed':not auto['at_stage'],
                'sensor_verification':confirmation,
                'note':'Presence switch sustained after movement; visually inspect tool seating. No tool commissioned.'}
    except Exception as exc:
        if sent:
            with _LOCK:
                _STATE['mounted_tool']=None
                _STATE['fault']=('T'+str(tool)+' '+kind+' result uncertain: '+str(exc)[:170]+
                    '. Inspect and clear only with an empty carriage.')
        raise
    finally:
        MOVE_LOCK.release()

def clear_fault(*,store,tool,expected_revision,acknowledgement):
    """No movement; only recover a known, inspected physical state.

    A failed pickup may read RELEASED at verification and PRESENT later. In
    that exact case, allow a deliberate inspected Tn-mounted recovery without
    forcing a mechanical removal or restarting the service to hide the fault.
    All other PRESSED faults remain locked.
    """
    if not MOVE_LOCK.acquire(blocking=False):
        raise ToolError('Another printer motion operation is running')
    try:
        current=_snapshot(store,tool)
        if current['_revision']!=expected_revision:
            raise ToolError('Configuration changed; refresh before clearing fault')
        auto=current['automatic']
        signal=auto['signal']
        fault=auto.get('fault')
        if not fault:
            raise ToolError('No selected-tool fault to clear')
        if signal==AUTO_EMPTY:
            required='I_INSPECTED_SELECTED_TOOL_AND_CONFIRMED_EMPTY_CARRIAGE'
        elif signal==AUTO_MOUNTED and fault.startswith(
                'T'+str(tool)+' pickup result uncertain:'):
            required='I_INSPECTED_SELECTED_TOOL_MOUNTED_AND_DOCK_EMPTY'
        else:
            raise ToolError('Carriage PRESENT with an unresolved fault other than a failed pickup. Inspect before recovery.')
        if acknowledgement!=required:
            raise ToolError('Physically inspect T'+str(tool)+
                            ' and confirm its real mounted/empty state before clearing this fault')
        # The required state must be sustained; a one-off switch reading is
        # insufficient to dismiss a latched motion-verification fault.
        confirmation=_stable_sensor(AUTO_SENSOR,current['_ctx']['objects'],signal,
                                    timeout_s=1.25)
        with _LOCK:
            _context_guard(current['_ctx'])
            if _STATE['fault']!=fault:
                raise ToolError('Tool fault changed during inspection; refresh')
            _STATE['fault']=None
            _STATE['mounted_tool']=None  # operator-selected identity, not sensor ID
        return {'status':'TOOL_FAULT_CLEARED_NO_MOVEMENT','tool':tool,
                'signal':signal,'sensor_verification':confirmation,
                'note':'No movement. Verify the selected tool physically before the next independently approved motion.'}
    finally:
        MOVE_LOCK.release()
