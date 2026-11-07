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
from cxm_lineux import MOVE_LOCK, _rpc, MeasurementError
from cxm_t0 import (_safe_context, _wait_for_idle_after_move, _sensor_value,
                    AUTO_SENSOR, AUTO_MOUNTED, AUTO_EMPTY, AUTO_STATE,
                    SAFE_FEED, TEST_FEED, LATCH_FEED, POSITION_TOL)
from cxm_cxchanger import plan as geometry_plan, automatic_script

class ToolError(MeasurementError):
    pass

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
        reason='T'+str(known)+' is recorded as mounted. Select T'+str(known)+
               ' and safely drop it off before operating T'+str(tool)
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
        final_signal=_sensor_value(AUTO_SENSOR,end['objects'])
        wanted=AUTO_MOUNTED if kind=='pickup' else AUTO_EMPTY
        if final_signal!=wanted:
            raise ToolError('T'+str(tool)+' '+kind+' failed: presence switch reports '+str(final_signal)+
                            ', expected '+wanted+'. Inspect the carriage and dock.')
        with _LOCK:
            _context_guard(end)
            _STATE['mounted_tool']=tool if kind=='pickup' else None
            _STATE['last_success']='T'+str(tool)+' '+kind
            _STATE['fault']=None
        return {'status':'T'+str(tool)+'_'+kind.upper()+'_SENSOR_CONFIRMED',
                'tool':tool,'kind':kind,'signal':final_signal,
                'identity_source':(auto['identity_source'] if kind=='dropoff' else 'operator_selected'),
                'position_mm':end['position'],'staging_performed':not auto['at_stage'],
                'note':'Presence switch transition verified; visually inspect tool seating. No tool commissioned.'}
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
    if acknowledgement!='I_INSPECTED_SELECTED_TOOL_AND_CONFIRMED_EMPTY_CARRIAGE':
        raise ToolError('Physical inspection and empty-carriage confirmation required')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ToolError('Another printer motion operation is running')
    try:
        current=_snapshot(store,tool)
        if current['_revision']!=expected_revision:
            raise ToolError('Configuration changed; refresh before clearing fault')
        if current['automatic']['signal']!=AUTO_EMPTY:
            raise ToolError('Cannot clear tool fault until carriage switch reads RELEASED and carriage is physically empty')
        with _LOCK:
            _context_guard(current['_ctx'])
            _STATE['fault']=None
            _STATE['mounted_tool']=None
        return {'status':'TOOL_FAULT_CLEARED_NO_MOVEMENT','tool':tool}
    finally:
        MOVE_LOCK.release()
