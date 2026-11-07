"""Guarded selected-hotend XY commissioning for T1–T11.

The shared carriage switch detects presence, NOT tool identity.
A dropoff is enabled only after this service positively confirmed pickup
of exactly that tool in the same Klipper process and config revision.
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
_STATE={'pid':None,'revision':None,'mounted_tool':None,'identity_source':None,'fault':None,'last_success':None}

def _context_guard(ctx):
    """Caller holds _LOCK. Invalidate tool identity on Klipper/config change."""
    if _STATE['pid'] != ctx['pid'] or _STATE['revision'] != ctx['revision']:
        _STATE.update(pid=ctx['pid'],revision=ctx['revision'],
                      mounted_tool=None,identity_source=None,fault=None,last_success=None)

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
            _STATE['identity_source']=None
            known=None
        fault=_STATE['fault']
        last=_STATE['last_success']
        identity_source=_STATE['identity_source']
    # A fault in the proven T0 controller must be physically inspected and
    # cleared there before a different tool is moved.
    t0_fault=(AUTO_STATE['fault'] if
              AUTO_STATE['pid']==ctx['pid'] and
              AUTO_STATE['revision']==ctx['revision'] else None)
    may_confirm_mounted=(signal==AUTO_MOUNTED and known is None and
        fault is None and not t0_fault and can_stage)
    if t0_fault:
        reason='T0 fault needs inspection/clearance before T'+str(tool)+' testing: '+str(t0_fault)
    elif fault:
        reason=fault
    elif not can_stage:
        reason='Carriage is inside the selected dock approach zone; safely rehome/park first'
    elif known is not None and known != tool:
        reason='T'+str(known)+' is still recorded as mounted. Drop it off safely before selecting T'+str(tool)
    elif signal==AUTO_MOUNTED and known != tool:
        reason='Carriage switch PRESSED but mounted hotend identity is not verified as T'+str(tool)+'. Do not drop an unknown hotend into this dock.'
    else:
        reason=None
    return {'ready':not bool(reason),'tool':tool,'saved_xy_mm':p['dock_reference_xy'],
            'safe_y_mm':p['safe_y'],'position_mm':ctx['position'],
            'automatic':{'enabled':not bool(reason),'reason':reason,'signal':signal,
                         'action':'dropoff' if signal==AUTO_MOUNTED else 'pickup',
                         'mounted_tool':known,'identity_source':identity_source,
                         'can_confirm_mounted':may_confirm_mounted,
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
    if acknowledgement != 'I_CONFIRMED_SELECTED_TOOL_XY_PATH_CLEAR_AND_WILL_SUPERVISE':
        raise ToolError('Physically confirm selected hotend and complete XY path')
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
        if kind=='dropoff' and auto['mounted_tool']!=tool:
            raise ToolError('Mounted tool identity not verified; cannot drop off T'+str(tool))
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
            _STATE['identity_source']='sensor_pickup' if kind=='pickup' else None
            _STATE['last_success']='T'+str(tool)+' '+kind
            _STATE['fault']=None
        return {'status':'T'+str(tool)+'_'+kind.upper()+'_SENSOR_CONFIRMED',
                'tool':tool,'kind':kind,'signal':final_signal,
                'position_mm':end['position'],'staging_performed':not auto['at_stage'],
                'note':'Presence switch transition verified; visually inspect tool seating. No tool commissioned.'}
    except Exception as exc:
        if sent:
            with _LOCK:
                _STATE['mounted_tool']=None
                _STATE['identity_source']=None
                _STATE['fault']=('T'+str(tool)+' '+kind+' result uncertain: '+str(exc)[:170]+
                    '. Inspect and clear only with an empty carriage.')
        raise
    finally:
        MOVE_LOCK.release()


def confirm_mounted_for_first_dropoff(*,store,tool,expected_revision,acknowledgement):
    """No-movement commissioning recovery for a hotend already attached.

    A PRESSED switch only proves presence. The operator must independently
    identify the specific hotend and verify its own dock is vacant. This
    does not certify a machine-verified pickup. The guarded dropoff remains
    separately acknowledged and uses only selected tool geometry.
    """
    if type(tool) is not int or not 1<=tool<=11:
        raise ToolError('Confirm mounted supports selected T1–T11 only')
    if acknowledgement!='I_IDENTIFIED_SELECTED_HOTEND_MOUNTED_EMPTY_DOCK_HOMED_XY_NOT_HAND_MOVED':
        raise ToolError('Physically identify the attached T'+str(tool)+
                        ', verify its dock is EMPTY and X/Y were genuinely homed and never hand-moved')
    if not MOVE_LOCK.acquire(blocking=False):
        raise ToolError('Another printer motion operation is running')
    try:
        snapshot=_snapshot(store,tool)
        if snapshot['_revision']!=expected_revision:
            raise ToolError('CXM configuration changed; refresh before confirming mounted identity')
        auto=snapshot['automatic']
        if not auto['can_confirm_mounted']:
            raise ToolError(auto.get('reason') or
                            'Cannot confirm mounted identity: check carriage switch, tool and dock')
        ctx=snapshot['_ctx']
        # A live PRESSED reading is required immediately before arming. A
        # polling status alone is not sufficient to record operator identity.
        if _sensor_value(AUTO_SENSOR,ctx['objects'])!=AUTO_MOUNTED:
            raise ToolError('Carriage presence switch changed before confirmation')
        with _LOCK:
            _context_guard(ctx)
            if (_STATE['mounted_tool'] is not None or _STATE['fault'] is not None or
                (AUTO_STATE['pid']==ctx['pid'] and
                 AUTO_STATE['revision']==ctx['revision'] and AUTO_STATE['fault'])):
                raise ToolError('Mounted state changed or unresolved fault; refresh and inspect')
            _STATE['mounted_tool']=tool
            _STATE['identity_source']='operator_confirmed'
        return {'status':'T'+str(tool)+'_MOUNTED_OPERATOR_CONFIRMED_NO_MOVEMENT',
                'tool':tool,'identity_source':'operator_confirmed',
                'note':'Operator identified hotend, switch PRESSED. No motion. Dropoff still requires a fresh clearance approval.'}
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
            _STATE['identity_source']=None
        return {'status':'TOOL_FAULT_CLEARED_NO_MOVEMENT','tool':tool}
    finally:
        MOVE_LOCK.release()
