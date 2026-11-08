"""Supervised one-pass CXM CxChanger multi-hotend mechanical XY test.

This is NOT production toolchanging. Dock XY may be accepted while XY/Z
offsets, heater wiring and overall commissioning remain unverified.

Every pass starts with a genuinely EMPTY carriage, then performs one
pickup+dropoff per explicitly selected, individually accepted dock.
The running worker holds the same movement lock used by existing Lineux,
T0 and T1+ routes. Stop is honoured AFTER the current tool is dropped.
Any uncertain state stops with a fault and requires physical inspection.
"""
from __future__ import annotations

import copy
import threading
import uuid

from cxm_lineux import MOVE_LOCK, _rpc
from cxm_cxchanger import plan as cxchanger_plan, automatic_script
from cxm_t0 import (_safe_context, _wait_for_idle_after_move, _sensor_value,
                    AUTO_SENSOR, AUTO_MOUNTED, AUTO_EMPTY, AUTO_STATE,
                    SESSION_LOCK, SAFE_FEED, TEST_FEED, LATCH_FEED,
                    POSITION_TOL)
from cxm_tools import (_stable_sensor, _STATE as TOOL_STATE,
                       _LOCK as TOOL_STATE_LOCK, _context_guard)

class MultiToolError(RuntimeError):
    pass

RUN_LOCK=threading.Lock()
RUN={'running':False,'run_id':None,'state':'idle','tools':[],
     'total_steps':0,'completed_steps':0,'current_tool':None,
     'current_action':None,'last_event':'No multi-tool test started',
     'stop_requested':False,'results':[],'error':None}

START_ACK='I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH'
STOP_ACK='STOP_AFTER_CURRENT_TOOL_PAIR'

def _update(**changes):
    with RUN_LOCK:
        RUN.update(changes)

def _event(message, *,tool=None,action=None,step_done=False):
    with RUN_LOCK:
        if step_done:
            RUN['completed_steps']+=1
        RUN['last_event']=message
        RUN['current_tool']=tool
        RUN['current_action']=action
        RUN['results'].append({'tool':tool,'action':action,'message':message,
                               'step':RUN['completed_steps']})
        RUN['results']=RUN['results'][-80:]

def _stop_requested():
    with RUN_LOCK:
        return RUN['stop_requested']

def candidates(store):
    """Read-only dock eligibility: never conflate saved XY with full READY."""
    saved=store.read()
    c=saved['config']
    count=c['globals']['tool_count']
    tools=[]
    for n in range(count):
        tool=c['tools'][n]
        reason=None
        if saved['migration_required']:
            reason='Configuration migration required'
        elif tool['maintenance_lockout']:
            reason='Maintenance lockout'
        elif tool['dock_x'] is None or tool['dock_y'] is None or tool['dock_reference_accepted'] is not True:
            reason='Dock XY not measured and accepted'
        else:
            try:cxchanger_plan(saved,tool=n)
            except (ValueError,KeyError,TypeError) as exc:
                reason='Dock movement geometry: '+str(exc)
        tools.append({'tool':n,'eligible':reason is None,'reason':reason,
                      'xy':{'x':tool['dock_x'],'y':tool['dock_y']},
                      'dock_accepted':tool['dock_reference_accepted'] is True})
    return {'revision':saved['revision'],'candidates':tools,
            'note':'Eligible means accepted CxChanger dock XY ONLY, not full tool commissioning.'}

def status(store):
    with RUN_LOCK:
        state=copy.deepcopy(RUN)
    return {**state,**candidates(store)}

def _validate_selection(selected,saved):
    if type(selected) is not list or not 2<=len(selected)<=12:
        raise MultiToolError('Select at least 2 and at most 12 dock-calibrated hotends')
    if any(type(n) is not int for n in selected) or len(set(selected))!=len(selected):
        raise MultiToolError('Tool numbers must be distinct integers')
    count=saved['config']['globals']['tool_count']
    if selected!=sorted(selected) or any(n<0 or n>=count for n in selected):
        raise MultiToolError('Tool numbers must be selected in ascending T0..T11 order')
    if saved['migration_required']:
        raise MultiToolError('CXM configuration migration required')
    paths={}
    for n in selected:
        t=saved['config']['tools'][n]
        if t['maintenance_lockout']:
            raise MultiToolError('T'+str(n)+' maintenance lockout')
        if t['dock_reference_accepted'] is not True or t['dock_x'] is None or t['dock_y'] is None:
            raise MultiToolError('T'+str(n)+' requires accepted Lineux/CxChanger dock XY before this test')
        try:
            paths[n]=cxchanger_plan(saved,tool=n)
        except (ValueError,TypeError,KeyError) as exc:
            raise MultiToolError('T'+str(n)+' unsafe CxChanger geometry: '+str(exc)) from exc
    return paths

def _check_no_pending_fault(ctx):
    with TOOL_STATE_LOCK:
        _context_guard(ctx)
        tool_fault=TOOL_STATE['fault']
        mounted=TOOL_STATE['mounted_tool']
    with SESSION_LOCK:
        t0_fault=(AUTO_STATE['fault'] if AUTO_STATE['pid']==ctx['pid'] and
                  AUTO_STATE['revision']==ctx['revision'] else None)
    if tool_fault:
        raise MultiToolError('T1+ tool fault requires physical inspection: '+str(tool_fault))
    if t0_fault:
        raise MultiToolError('T0 fault requires physical inspection: '+str(t0_fault))
    if mounted is not None:
        raise MultiToolError('T'+str(mounted)+' is still recorded attached; empty carriage required')

def _prepare(store,selected,revision):
    saved=store.read()
    if type(revision) is not str or revision!=saved['revision']:
        raise MultiToolError('Configuration changed: refresh the list of eligible docks')
    paths=_validate_selection(selected,saved)
    ctx=_safe_context(saved,tool=selected[0])
    _check_no_pending_fault(ctx)
    if AUTO_SENSOR not in ctx['objects']:
        raise MultiToolError('Carriage presence switch is unavailable')
    # One-click sequences may only start EMPTY and outside every selected
    # dock's approach zone. Software-reported XY must be genuinely homed;
    # the operator separately attests that XY was not hand moved.
    max_safe=max(p['safe_y'] for p in paths.values())
    if ctx['position'][1]<max_safe-POSITION_TOL:
        raise MultiToolError('Home/park with Y outside every selected dock safe-Y boundary')
    if _sensor_value(AUTO_SENSOR,ctx['objects'])!=AUTO_EMPTY:
        raise MultiToolError('Carriage FILAMENT PRESENT: first safely drop off the mounted hotend')
    _stable_sensor(AUTO_SENSOR,ctx['objects'],AUTO_EMPTY,timeout_s=1.25)
    if store.read()['revision']!=revision:
        raise MultiToolError('Configuration changed during preflight')
    return {'revision':revision,'pid':ctx['pid'],'paths':paths}

def _mark_tool(tool,kind,ctx,revision):
    if tool==0:
        with SESSION_LOCK:
            AUTO_STATE.update(pid=ctx['pid'],revision=revision,
                              last_success='T0 '+kind,fault=None)
    else:
        with TOOL_STATE_LOCK:
            _context_guard(ctx)
            TOOL_STATE.update(mounted_tool=tool if kind=='pickup' else None,
                              last_success='T'+str(tool)+' '+kind,
                              fault=None)

def _latch_tool_fault(tool,kind,pid,revision,error):
    message=('T'+str(tool)+' '+kind+' result uncertain: multi-tool pass '+ 
             str(error)[:175]+'. Inspect physical carriage and selected dock.')
    if tool==0:
        with SESSION_LOCK:
            AUTO_STATE.update(pid=pid,revision=revision,fault=message)
    else:
        with TOOL_STATE_LOCK:
            TOOL_STATE.update(pid=pid,revision=revision,mounted_tool=None,
                              fault=message)
    return message

def _step(store,tool,kind,expected_revision,expected_pid,paths):
    wanted_before=AUTO_EMPTY if kind=='pickup' else AUTO_MOUNTED
    wanted_after=AUTO_MOUNTED if kind=='pickup' else AUTO_EMPTY
    saved=store.read()
    if saved['revision']!=expected_revision:
        raise MultiToolError('Saved tool positions changed during cycle')
    ctx=_safe_context(saved,tool=tool)
    if ctx['pid']!=expected_pid:
        raise MultiToolError('Klipper restarted while multi-tool test was running')
    # At each tool's staging line or further out in the shared transfer
    # corridor. Previous tools finish at their own safe-Y line.
    safe_boundary=min(p['safe_y'] for p in paths.values())
    if ctx['position'][1]<safe_boundary-POSITION_TOL:
        raise MultiToolError('Carriage is inside the multi-tool safe transfer corridor')
    if _sensor_value(AUTO_SENSOR,ctx['objects'])!=wanted_before:
        raise MultiToolError('T'+str(tool)+' '+kind+' blocked: sensor before motion is not '+wanted_before)
    # Check the pre-action switch is stable before dispatching any G-code.
    _stable_sensor(AUTO_SENSOR,ctx['objects'],wanted_before,timeout_s=1.25)
    p=paths[tool]
    at_stage=(abs(ctx['position'][0]-p['dock_reference_xy']['x'])<=POSITION_TOL and
              abs(ctx['position'][1]-p['safe_y'])<=POSITION_TOL)
    script=automatic_script(p,kind,at_stage=at_stage,
                            safe_feed=SAFE_FEED,test_feed=TEST_FEED,
                            latch_feed=LATCH_FEED)
    if store.read()['revision']!=expected_revision:
        raise MultiToolError('CXM dock revision changed before movement')
    _rpc('/printer/gcode/script',{'script':script})
    finished=store.read()
    if finished['revision']!=expected_revision:
        raise MultiToolError('Configuration changed while tool was moving')
    end=_wait_for_idle_after_move(finished,parked=True,
                                  expected_pid=expected_pid,tool=tool)
    confirmation=_stable_sensor(AUTO_SENSOR,end['objects'],wanted_after)
    _mark_tool(tool,kind,end,expected_revision)
    return {'tool':tool,'kind':kind,'signal':confirmation['signal'],
            'samples':confirmation['samples'],
            'x':p['dock_reference_xy']['x'],'y':p['dock_reference_xy']['y']}

def _worker(store,selected,prepared):
    tool=None
    kind=None
    try:
        for tool in selected:
            # "Stop after current tool" is checked before pickup of the
            # next hotend, never between pickup and its required dropoff.
            if _stop_requested():
                _update(state='stopped',last_event='Stopped with empty carriage after previous tool')
                return
            for kind in ('pickup','dropoff'):
                if store.read()['revision']!=prepared['revision']:
                    raise MultiToolError('Configuration revision changed before T'+str(tool)+' '+kind)
                _event('T'+str(tool)+' '+kind+' started · supervise movement',
                       tool=tool,action=kind)
                result=_step(store,tool,kind,prepared['revision'],
                             prepared['pid'],prepared['paths'])
                _event('T'+str(tool)+' '+kind+' confirmed · sensor '+result['signal'],
                       tool=tool,action=kind,step_done=True)
            if _stop_requested():
                _update(state='stopped',
                        last_event='Stopped safely after T'+str(tool)+' dropoff · carriage EMPTY')
                return
        _update(state='complete',last_event='All selected tool pairs completed · carriage EMPTY')
    except Exception as exc:
        # Fail closed; no automatic retry or forced dropoff after an uncertain
        # pickup. The physical state may differ from the last sampled signal.
        message=_latch_tool_fault(tool,kind,prepared['pid'],prepared['revision'],exc)
        _update(state='failed',error=message,last_event=message)
        _event(message,tool=tool,action=kind)
    finally:
        _update(running=False,stop_requested=False,current_action=None)
        MOVE_LOCK.release()

def start(*,store,tools,expected_revision,acknowledgement):
    if acknowledgement!=START_ACK:
        raise MultiToolError('Confirm the real carriage is EMPTY, all selected docks are safe and the XY path is clear')
    with RUN_LOCK:
        if RUN['running']:
            raise MultiToolError('A multi-tool pass is already running')
        if RUN['state']=='failed':
            # Revalidate and clear the underlying individual fault before
            # starting again; don't hide a failed toolchange by repeating.
            pass
    if not MOVE_LOCK.acquire(blocking=False):
        raise MultiToolError('Another CXM tool/dock motion operation is running')
    try:
        prepared=_prepare(store,tools,expected_revision)
        run_id=str(uuid.uuid4())
        with RUN_LOCK:
            RUN.update(running=True,run_id=run_id,state='running',
                       tools=tools[:],total_steps=len(tools)*2,
                       completed_steps=0,current_tool=None,current_action=None,
                       last_event='Preflight passed; multi-tool pass starting',
                       stop_requested=False,results=[],error=None)
        worker=threading.Thread(target=_worker,
                                args=(store,tools[:],prepared),
                                daemon=True,name='cxm-multi-tool-pass')
        try:
            worker.start()
        except Exception:
            _update(running=False,state='failed',
                    error='Multi-tool worker could not start',
                    last_event='No movement started: worker thread failed')
            raise
        return {'started':True,'run_id':run_id,'tools':tools,'total_steps':len(tools)*2,
                'note':'Supervised XY only; printer remains uncommissioned.'}
    except Exception:
        MOVE_LOCK.release()
        raise

def stop(*,acknowledgement):
    if acknowledgement!=STOP_ACK:
        raise MultiToolError('Explicit Stop After Current Tool acknowledgement required')
    with RUN_LOCK:
        if not RUN['running']:
            return {'stop_requested':False,'reason':'No active multi-tool pass'}
        RUN['stop_requested']=True
        return {'stop_requested':True,
                'note':'The current tool pair completes unless the operator presses the real emergency stop.'}
