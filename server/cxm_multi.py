"""Supervised repeated CXM CxChanger multi-hotend mechanical XY test.

This is NOT production toolchanging. Dock XY may be accepted while XY/Z
offsets, heater wiring and overall commissioning remain unverified.

Every pass starts with a genuinely EMPTY carriage, then performs one
pickup+dropoff per explicitly selected, individually accepted dock.
Between passes Klipper, homing, position, and empty-sensor readiness are
checked again. All selected tools must be known safe before the first move.
The running worker holds the same movement lock used by existing Lineux,
T0 and T1+ routes. Stop is honoured AFTER the current tool is dropped.
Any uncertain state stops with a fault and requires physical inspection.
"""
from __future__ import annotations

import copy
import threading
import time
import uuid
import urllib.parse

from cxm_lineux import MOVE_LOCK, _rpc
from cxm_rapid import pair_script, stream_script, MAX_NATIVE_STREAM_TOOLS
from cxm_cxchanger import (plan as cxchanger_plan, automatic_script,
                           faster_cycle_script, performance_cycle_script,
                           sprint_cycle_script, race_cycle_script)
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
     'travel_profile':'standard','execution_mode':'legacy','requested_cycles':1,
     'completed_cycles':0,'current_cycle':None,
     'total_steps':0,'completed_steps':0,'current_tool':None,
     'current_action':None,'last_event':'No multi-tool test started',
     'stop_requested':False,'results':[],'error':None}

START_ACK='I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH'
STOP_ACK='STOP_AFTER_CURRENT_TOOL_PAIR'
TRAVEL_PROFILES=('standard','faster','performance','sprint','race')
EXECUTION_MODES=('legacy','rapid','stream')
RAPID_MACRO='gcode_macro CXM_FAST_VERIFY'
MAX_REPEAT_CYCLES=20
MAX_TOTAL_MOVEMENTS=240  # bound unattended batch size across tool counts
# This initial commissioning mode assumes an aligned front dock row. The
# stock per-tool CxChanger staging script is not a general safe transfer
# route between docks at very different Y depths.
MAX_SAFE_Y_SPREAD_MM=1.0

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
    return {**state,**candidates(store),
            'max_repeat_cycles':MAX_REPEAT_CYCLES,
            'max_total_movements':MAX_TOTAL_MOVEMENTS}

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
    safe_y_values=[p['safe_y'] for p in paths.values()]
    if max(safe_y_values)-min(safe_y_values)>MAX_SAFE_Y_SPREAD_MM:
        raise MultiToolError(
            'Selected docks have safe-Y staging lines more than 1 mm apart. '
            'Multi-tool transfer across different dock depths is not commissioned; '
            'test those docks individually.')
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

def _prepare(store,selected,revision,execution_mode='legacy'):
    saved=store.read()
    if type(revision) is not str or revision!=saved['revision']:
        raise MultiToolError('Configuration changed: refresh the list of eligible docks')
    paths=_validate_selection(selected,saved)
    ctx=_safe_context(saved,tool=selected[0],sensor_name=AUTO_SENSOR)
    _check_no_pending_fault(ctx)
    if AUTO_SENSOR not in ctx['objects']:
        raise MultiToolError('Carriage presence switch is unavailable')
    if execution_mode in ('rapid','stream'):
        if RAPID_MACRO not in ctx['objects']:
            raise MultiToolError('Rapid mode unavailable: install the native CXM guard, perform one Klipper RESTART, then rehome XYZ')
        result=_rpc('/printer/objects/query?'+urllib.parse.urlencode(
                    {RAPID_MACRO:'cxm_rapid_protocol'})).get('status',{})
        if result.get(RAPID_MACRO,{}).get('cxm_rapid_protocol')!=1:
            raise MultiToolError('Rapid Klipper safety macro version mismatch; inspect installed macro and Klipper RESTART')
    # One-click sequences may only start EMPTY and outside every selected
    # dock's approach zone. Software-reported XY must be genuinely homed;
    # the operator separately attests that XY was not hand moved.
    # Previous tool pairs finish at their own safe-Y line. These lines are
    # verified within 1 mm, and the next script moves Y to its safe staging
    # line BEFORE any cross-dock X travel. Therefore an already-finished
    # pass may safely start another without needless rehoming/repositioning.
    minimum_safe=min(p['safe_y'] for p in paths.values())
    if ctx['position'][1]<minimum_safe-POSITION_TOL:
        raise MultiToolError('Home/park with Y outside every selected dock safe-Y boundary')
    if ctx['sensor_signal']!=AUTO_EMPTY:
        raise MultiToolError('Carriage FILAMENT PRESENT: first safely drop off the mounted hotend')
    verified=_stable_sensor(AUTO_SENSOR,ctx['objects'],AUTO_EMPTY,timeout_s=1.25)
    if store.read()['revision']!=revision:
        raise MultiToolError('Configuration changed during preflight')
    # Evidence of sustained empty carriage for the *first* move. Each
    # subsequent move is backed by four post-motion stable samples.
    return {'revision':revision,'pid':ctx['pid'],'paths':paths,
            'validated_objects':tuple(ctx['objects']),
            'verified_signal':verified['signal']}

def _verify_between_cycles(store,prepared,selected):
    """Do not assume the previous sensor-confirmed pass is still safe."""
    saved=store.read()
    if saved['revision']!=prepared['revision']:
        raise MultiToolError('CXM dock settings changed between cycles')
    ctx=_safe_context(saved,tool=selected[0],
                      validated_objects=prepared['validated_objects'],
                      expected_pid=prepared['pid'],sensor_name=AUTO_SENSOR)
    if ctx['pid']!=prepared['pid']:
        raise MultiToolError('Klipper process changed between cycles')
    _check_no_pending_fault(ctx)
    if AUTO_SENSOR not in ctx['objects']:
        raise MultiToolError('Carriage presence switch unavailable between cycles')
    minimum=min(p['safe_y'] for p in prepared['paths'].values())
    if ctx['position'][1]<minimum-POSITION_TOL:
        raise MultiToolError('Carriage is not clear of all dock approaches between cycles')
    if ctx['sensor_signal']!=AUTO_EMPTY:
        raise MultiToolError('Carriage FILAMENT PRESENT between cycles; stop and inspect')
    confirmed=_stable_sensor(AUTO_SENSOR,ctx['objects'],AUTO_EMPTY,timeout_s=1.25)
    if store.read()['revision']!=prepared['revision']:
        raise MultiToolError('CXM dock settings changed during between-cycle check')
    return confirmed['signal']

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

def _step(store,tool,kind,expected_revision,expected_pid,paths,travel_profile='standard',
          verified_before=None,validated_objects=None):
    # Read-only wall-clock profiling: no additional G-code, RPCs or waits.
    # This measures exactly where the existing sequence spends its time.
    step_started=time.monotonic()
    wanted_before=AUTO_EMPTY if kind=='pickup' else AUTO_MOUNTED
    wanted_after=AUTO_MOUNTED if kind=='pickup' else AUTO_EMPTY
    saved=store.read()
    if saved['revision']!=expected_revision:
        raise MultiToolError('Saved tool positions changed during cycle')
    ctx=_safe_context(saved,tool=tool,
                      validated_objects=validated_objects,
                      expected_pid=(expected_pid if validated_objects is not None
                                    else None),sensor_name=AUTO_SENSOR)
    if ctx['pid']!=expected_pid:
        raise MultiToolError('Klipper restarted while multi-tool test was running')
    # At each tool's staging line or further out in the shared transfer
    # corridor. Previous tools finish at their own safe-Y line.
    safe_boundary=min(p['safe_y'] for p in paths.values())
    if ctx['position'][1]<safe_boundary-POSITION_TOL:
        raise MultiToolError('Carriage is inside the multi-tool safe transfer corridor')
    if verified_before is not None and verified_before!=wanted_before:
        raise MultiToolError('T'+str(tool)+' '+kind+
                             ' blocked: prior stable sensor confirmation is not '+wanted_before)
    # A fresh carriage-switch reading is included in the SAME live status
    # response that verifies homing, motor power, idle, print state and XY.
    # A mismatch still blocks motion, with no separate 250ms sensor query.
    if ctx['sensor_signal']!=wanted_before:
        raise MultiToolError('T'+str(tool)+' '+kind+' blocked: sensor before motion is not '+wanted_before)
    # Only standalone/direct callers without prior verified evidence retain
    # the original 4-sample precheck. The multi-tool worker always supplies
    # a trusted token generated by the guarded startup or previous movement.
    if verified_before is None:
        _stable_sensor(AUTO_SENSOR,ctx['objects'],wanted_before,timeout_s=1.25)
    p=paths[tool]
    at_stage=(abs(ctx['position'][0]-p['dock_reference_xy']['x'])<=POSITION_TOL and
              abs(ctx['position'][1]-p['safe_y'])<=POSITION_TOL)
    if travel_profile=='faster':
        script=faster_cycle_script(p,kind,at_stage=at_stage,
                                  test_feed=TEST_FEED,latch_feed=LATCH_FEED)
    elif travel_profile=='performance':
        script=performance_cycle_script(p,kind,at_stage=at_stage)
    elif travel_profile=='sprint':
        script=sprint_cycle_script(p,kind,at_stage=at_stage)
    elif travel_profile=='race':
        script=race_cycle_script(p,kind,at_stage=at_stage)
    elif travel_profile=='standard':
        # Exact existing physical-test baseline, no code or speed changes.
        script=automatic_script(p,kind,at_stage=at_stage,
                                safe_feed=SAFE_FEED,test_feed=TEST_FEED,
                                latch_feed=LATCH_FEED)
    else:
        raise MultiToolError('Unrecognised travel profile')
    if store.read()['revision']!=expected_revision:
        raise MultiToolError('CXM dock revision changed before movement')
    movement_started=time.monotonic()
    _rpc('/printer/gcode/script',{'script':script})
    motion_completed=time.monotonic()
    finished=store.read()
    if finished['revision']!=expected_revision:
        raise MultiToolError('Configuration changed while tool was moving')
    end=_wait_for_idle_after_move(finished,parked=True,
                                  expected_pid=expected_pid,tool=tool,
                                  validated_objects=validated_objects)
    idle_verified=time.monotonic()
    confirmation=_stable_sensor(AUTO_SENSOR,end['objects'],wanted_after)
    sensor_verified=time.monotonic()
    _mark_tool(tool,kind,end,expected_revision)
    completed=time.monotonic()
    breakdown={'preflight_sec':round(movement_started-step_started,2),
               'gcode_sec':round(motion_completed-movement_started,2),
               'idle_check_sec':round(idle_verified-motion_completed,2),
               'sensor_sec':round(sensor_verified-idle_verified,2),
               'record_sec':round(completed-sensor_verified,2)}
    return {'tool':tool,'kind':kind,'signal':confirmation['signal'],
            'samples':confirmation['samples'],
            'duration_sec':round(completed-movement_started,2),
            'total_sec':round(completed-step_started,2),
            'timing':breakdown,
            'x':p['dock_reference_xy']['x'],'y':p['dock_reference_xy']['y']}

def _rapid_pair(store,tool,expected_revision,expected_pid,paths,travel_profile):
    """Dispatch one synchronous Klipper pickup+dropoff pair.

    Klipper performs M400-separated live sensor gates on both actions.
    If the request raises or times out, never assume which tool is attached.
    """
    saved=store.read()
    if saved['revision']!=expected_revision:
        raise MultiToolError('Dock calibration changed before rapid tool pair')
    live=_rpc('/printer/info')
    if live.get('state')!='ready' or live.get('process_id')!=expected_pid:
        raise MultiToolError('Klipper not ready or restarted before rapid pair')
    script=pair_script(paths,tool,travel_profile)
    started=time.monotonic()
    _rpc('/printer/gcode/script',{'script':script})
    elapsed=round(time.monotonic()-started,2)
    if store.read()['revision']!=expected_revision:
        raise MultiToolError('Dock config changed during rapid pair; inspect tool')
    # A successful Klipper script confirms both 4-sample gates, homed XYZ,
    # stepper power, safe stage and empty carriage at final M400.
    _mark_tool(tool,'dropoff',{'pid':expected_pid,'revision':expected_revision},
               expected_revision)
    return {'signal':AUTO_EMPTY,'total_sec':elapsed}


def _stream_run(store,selected,prepared,travel_profile):
    """One native script across all selected tools, without HTTP handoffs.

    In contrast to Rapid per-pair mode, operator Stop-after-pair is
    unavailable while Klipper processes this script. Physical E-stop
    remains effective. Unknown results latch faults for all tool routes.
    """
    saved=store.read()
    if saved['revision']!=prepared['revision']:
        raise MultiToolError('Saved CXM dock coordinates changed before stream')
    info=_rpc('/printer/info')
    if info.get('state')!='ready' or info.get('process_id')!=prepared['pid']:
        raise MultiToolError('Klipper restarted or not ready before stream')
    script=stream_script(prepared['paths'],selected,travel_profile)
    began=time.monotonic()
    _rpc('/printer/gcode/script',{'script':script})
    elapsed=round(time.monotonic()-began,2)
    if store.read()['revision']!=prepared['revision']:
        raise MultiToolError('CXM dock config changed during stream; inspect all selected docks')
    for t in selected:
        _mark_tool(t,'dropoff',
                   {'pid':prepared['pid'],'revision':prepared['revision']},
                   prepared['revision'])
    return {'duration_sec':elapsed,'signal':AUTO_EMPTY}


def _latch_stream_fault(selected,prepared,error):
    message=('Uninterrupted '+' → '.join('T'+str(t) for t in selected)+
             ' stream result uncertain: '+str(error)[:160]+
             '. Inspect carriage and ALL selected docks before clearing faults.')
    # The shared presence switch cannot identify which tool was attached
    # when a multi-tool native script failed. Mark both T0 and T1+ routes
    # blocked to avoid accidental attempts with a falsely known tool.
    with SESSION_LOCK:
        AUTO_STATE.update(pid=prepared['pid'],revision=prepared['revision'],
                          fault=message)
    with TOOL_STATE_LOCK:
        TOOL_STATE.update(pid=prepared['pid'],revision=prepared['revision'],
                          mounted_tool=None,fault=message)
    return message


def _worker(store,selected,prepared,travel_profile,cycles,execution_mode='legacy'):
    tool=None
    kind=None
    # This token comes ONLY from four stable carriage sensor samples at
    # guarded startup, at the end of a prior movement, or between cycles.
    confirmed_signal=prepared['verified_signal']
    try:
        if execution_mode=='stream':
            kind='uninterrupted stream'
            _update(current_cycle=1,current_action=kind,current_tool=None)
            _event('Uninterrupted '+(' → '.join('T'+str(t) for t in selected))+
                   ' native stream · physical E-stop only; no queued Stop-after-pair')
            result=_stream_run(store,selected,prepared,travel_profile)
            for t in selected:
                _event('T'+str(t)+' native pickup confirmed (PRESSED)',
                       tool=t,action='pickup',step_done=True)
                _event('T'+str(t)+' native dropoff confirmed (RELEASED)',
                       tool=t,action='dropoff',step_done=True)
            _update(completed_cycles=1,state='complete',
                    last_event='All '+str(len(selected))+
                    ' pairs completed inside Klipper · carriage EMPTY · total '+
                    str(result['duration_sec'])+'s')
            return
        for cycle in range(1,cycles+1):
            if _stop_requested():
                _update(state='stopped',
                        last_event='Stopped between completed cycles · carriage EMPTY')
                return
            if cycle>1:
                _event('Cycle '+str(cycle)+'/'+str(cycles)+
                       ': rechecking Klipper and EMPTY carriage before continuing')
                confirmed_signal=_verify_between_cycles(store,prepared,selected)
            _update(current_cycle=cycle)
            for tool in selected:
                # Stop is handled before a new pickup, never between pickup
                # and the corresponding dock dropoff.
                if _stop_requested():
                    _update(state='stopped',
                            last_event='Stopped after '+str(RUN['completed_steps'])+
                            ' verified moves; carriage EMPTY')
                    return
                if execution_mode=='rapid':
                    kind='rapid pair'
                    _event('Cycle '+str(cycle)+'/'+str(cycles)+
                           ' · T'+str(tool)+' rapid pickup and dropoff in Klipper',
                           tool=tool,action=kind)
                    result=_rapid_pair(store,tool,prepared['revision'],prepared['pid'],
                                       prepared['paths'],travel_profile)
                    _event('Cycle '+str(cycle)+'/'+str(cycles)+
                           ' · T'+str(tool)+' native pickup confirmed (PRESSED)',
                           tool=tool,action='pickup',step_done=True)
                    _event('Cycle '+str(cycle)+'/'+str(cycles)+
                           ' · T'+str(tool)+' native dropoff confirmed (RELEASED)'+
                           ' · pair '+str(result['total_sec'])+'s · four samples/action',
                           tool=tool,action='dropoff',step_done=True)
                else:
                    for kind in ('pickup','dropoff'):
                        if store.read()['revision']!=prepared['revision']:
                            raise MultiToolError('Configuration changed before T'+str(tool)+' '+kind)
                        _event('Cycle '+str(cycle)+'/'+str(cycles)+
                               ' · T'+str(tool)+' '+kind+' started · supervise movement',
                               tool=tool,action=kind)
                        result=_step(store,tool,kind,prepared['revision'],
                                     prepared['pid'],prepared['paths'],travel_profile,
                                     verified_before=confirmed_signal,
                                     validated_objects=prepared['validated_objects'])
                        confirmed_signal=result['signal']
                        perf=result['timing']
                        _event('Cycle '+str(cycle)+'/'+str(cycles)+
                               ' · T'+str(tool)+' '+kind+' confirmed ('+result['signal']+
                               ') · total '+str(result['total_sec'])+'s'+
                               ' [preflight '+str(perf['preflight_sec'])+'s'+
                               ', G-code '+str(perf['gcode_sec'])+'s'+
                               ', idle '+str(perf['idle_check_sec'])+'s'+
                               ', sensor '+str(perf['sensor_sec'])+'s]',
                               tool=tool,action=kind,step_done=True)
                # After every complete pair, carriage is confirmed EMPTY.
                if _stop_requested():
                    # If the stop arrives at the last tool's dropoff, this
                    # entire cycle WAS completed and must count as complete.
                    changes={'state':'stopped',
                             'last_event':'Stopped after cycle '+str(cycle)+
                             ', T'+str(tool)+' dropoff · carriage EMPTY'}
                    if tool==selected[-1]:
                        changes['completed_cycles']=cycle
                    _update(**changes)
                    return
            _update(completed_cycles=cycle,
                    last_event='Cycle '+str(cycle)+'/'+str(cycles)+
                    ' completed · carriage EMPTY')
        _update(state='complete',last_event='All '+str(cycles)+
                ' cycles completed · carriage EMPTY')
    except Exception as exc:
        # No forced retry/dropoff after uncertain pickup. The sensor's last
        # state may not reflect a securely mounted tool.
        message=(_latch_stream_fault(selected,prepared,exc)
                 if execution_mode=='stream'
                 else _latch_tool_fault(tool,kind,prepared['pid'],prepared['revision'],exc))
        _update(state='failed',error=message,last_event=message)
        _event(message,tool=tool,action=kind)
    finally:
        _update(running=False,stop_requested=False,current_action=None)
        MOVE_LOCK.release()

def start(*,store,tools,expected_revision,acknowledgement,travel_profile='standard',
          cycles=1,execution_mode='legacy'):
    if acknowledgement!=START_ACK:
        raise MultiToolError('Confirm the real carriage is EMPTY, all selected docks are safe and the XY path is clear')
    if type(travel_profile) is not str or travel_profile not in TRAVEL_PROFILES:
        raise MultiToolError('Invalid travel profile: choose standard, faster, performance, sprint or race')
    if type(execution_mode) is not str or execution_mode not in EXECUTION_MODES:
        raise MultiToolError('Invalid execution mode: legacy, rapid or stream')
    if type(cycles) is not int or not 1<=cycles<=MAX_REPEAT_CYCLES:
        raise MultiToolError('Choose a whole number of complete cycles from 1 to '+
                             str(MAX_REPEAT_CYCLES))
    # These stages are new physical load cases, not yet commissioned for
    # repeated unsupervised tool changes. The first observed trial must
    # include only one complete pass; other proven modes remain unchanged.
    if travel_profile in ('sprint','race') and cycles!=1:
        raise MultiToolError('Experimental Sprint/Race requires exactly one supervised cycle')
    if execution_mode=='stream':
        if cycles!=1:
            raise MultiToolError('Uninterrupted stream requires one supervised cycle')
        if type(tools) is not list or not 2<=len(tools)<=MAX_NATIVE_STREAM_TOOLS:
            raise MultiToolError('Uninterrupted stream requires 2–3 selected docks')
        # This test intentionally prioritises uninterrupted movement, and
        # therefore cannot guarantee Stop-after-pair while the script runs.
        # It uses the real physical E-stop for immediate danger.
    if type(tools) is list and cycles*len(tools)*2>MAX_TOTAL_MOVEMENTS:
        raise MultiToolError('Batch exceeds the '+str(MAX_TOTAL_MOVEMENTS)+
                             '-movement safety limit; select fewer cycles or tools')
    with RUN_LOCK:
        if RUN['running']:
            raise MultiToolError('A multi-tool pass is already running')
    if not MOVE_LOCK.acquire(blocking=False):
        raise MultiToolError('Another CXM tool/dock motion operation is running')
    try:
        prepared=_prepare(store,tools,expected_revision,execution_mode)
        run_id=str(uuid.uuid4())
        with RUN_LOCK:
            RUN.update(running=True,run_id=run_id,state='running',
                       tools=tools[:],travel_profile=travel_profile,
                       execution_mode=execution_mode,
                       requested_cycles=cycles,completed_cycles=0,current_cycle=None,
                       total_steps=len(tools)*2*cycles,
                       completed_steps=0,current_tool=None,current_action=None,
                       last_event='Preflight passed; multi-tool pass starting',
                       stop_requested=False,results=[],error=None)
        worker=threading.Thread(target=_worker,
                                args=(store,tools[:],prepared,travel_profile,cycles,execution_mode),
                                daemon=True,name='cxm-multi-tool-pass')
        try:
            worker.start()
        except Exception:
            _update(running=False,state='failed',
                    error='Multi-tool worker could not start',
                    last_event='No movement started: worker thread failed')
            raise
        return {'started':True,'run_id':run_id,'tools':tools,'cycles':cycles,
                'travel_profile':travel_profile,'execution_mode':execution_mode,
                 'total_steps':len(tools)*2*cycles,
                'note':'Supervised repeated XY only; printer remains uncommissioned.'}
    except Exception:
        MOVE_LOCK.release()
        raise

def stop(*,acknowledgement):
    if acknowledgement!=STOP_ACK:
        raise MultiToolError('Explicit Stop After Current Tool acknowledgement required')
    with RUN_LOCK:
        if not RUN['running']:
            return {'stop_requested':False,'reason':'No active multi-tool pass'}
        if RUN['execution_mode']=='stream':
            return {'stop_requested':False,'emergency_stop_required':True,
                    'reason':'Uninterrupted Klipper stream: physical emergency stop only; a queued G-code Stop cannot interrupt it'}
        RUN['stop_requested']=True
        return {'stop_requested':True,
                'note':'The current tool pair completes unless the operator presses the real emergency stop.'}
