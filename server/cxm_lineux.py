"""CXM bridge for the unchanged Lineux Klipper dock location module.

No stored calibration values are written here. A verified motion command runs
only after a stringent machine preflight and explicit operator acknowledgement.
All returned XY is PROVISIONAL, tool-scoped, and revision-scoped.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:7125'
MOVE_LOCK = threading.Lock()
# In-memory known-position evidence. Reset on service restart and invalidated on Klipper PID change.
KNOWN_SESSION = {'pid': None, 'at': 0.0}
KNOWN_MAX_AGE_SEC = 3600
KNOWN_TOLERANCE_MM = 0.25  # Initial commissioning threshold, not established accuracy
NUMBER = r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))'


class MeasurementError(RuntimeError):
    pass


def _rpc(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE+path, data=data,
        headers={'Content-Type': 'application/json'} if data is not None else {},
        method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=125 if data else 4) as f:
            answer = json.load(f)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise MeasurementError('Moonraker unavailable: '+str(exc)[:140]) from exc
    if not isinstance(answer, dict) or 'error' in answer or 'result' not in answer:
        raise MeasurementError('Invalid Moonraker response')
    return answer['result']


def _num(v, name):
    if type(v) not in (float, int) or not math.isfinite(v):
        raise MeasurementError('Invalid '+name)
    return float(v)


def _endstop_settings(settings):
    try:
        x, y = settings['stepper_x'], settings['stepper_y']
        engine = settings['dock_locate_calibrate']
    except (KeyError, TypeError) as exc:
        raise MeasurementError('Lineux Klipper module/config not installed: '+str(exc)) from exc
    expected = {}
    for axis, cfg in [('x', x), ('y', y)]:
        end = _num(cfg['position_endstop'], 'position_endstop '+axis)
        high = _num(cfg['position_max'], 'position_max '+axis)
        low = _num(cfg.get('position_min', 0), 'position_min '+axis)
        if not low < end <= high or not high - 1.0 <= end:
            raise MeasurementError('Only positive-endstop CoreXY homing is supported for '+axis)
        step = (_num(cfg['rotation_distance'], 'rotation_distance') / (
            _num(cfg.get('full_steps_per_rotation', 200), 'steps per revolution') *
            _num(cfg['microsteps'], 'microsteps')))
        expected[axis] = {'endstop': end, 'mm_per_mcu_step': step,
                          'position_min': low, 'position_max': high}
    if abs(expected['x']['mm_per_mcu_step']-expected['y']['mm_per_mcu_step']) > 1e-9:
        raise MeasurementError('X/Y motor step lengths differ; Lineux formula unsupported')
    resolution = _num(engine['xy_resolution'], 'Lineux xy_resolution')
    if abs(expected['x']['mm_per_mcu_step']-resolution) > 1e-8:
        raise MeasurementError('Lineux xy_resolution mismatch with active motor config')
    for axis in ('x','y'):
        if abs(_num(engine[axis+'_endstop'], 'Lineux '+axis+'_endstop')-
               expected[axis]['endstop']) > 1e-5:
            raise MeasurementError('Lineux '+axis+'_endstop differs from active '+axis+' endstop')
    move = _num(engine['calibrate_move_x'], 'calibrate_move_x')
    if not 0.5 <= abs(move) <= 5:
        raise MeasurementError('Unreviewed Lineux calibration move; expected 0.5–5 mm')
    return expected, resolution, move


def query_readiness(*, tool, saved, mode='dock'):
    """Read-only readiness check, returning an explicit list of blockers."""
    reasons = []
    engine = False
    meta = {}
    if mode not in ('dock','known'):
        raise MeasurementError('Unknown measurement mode')
    known_verified = False
    if type(tool) is not int or not 0 <= tool < saved['config']['globals']['tool_count']:
        reasons.append('Tool outside active tool_count')
    elif saved['migration_required']:
        reasons.append('CXM configuration migration required')
    elif saved['config']['tools'][tool]['maintenance_lockout']:
        reasons.append('Tool under maintenance lockout')
    try:
        info = _rpc('/printer/info')
        if info.get('state') != 'ready':
            reasons.append('Klipper is not ready')
        pid = info.get('process_id')
        if mode == 'known' and (type(pid) is not int or pid <= 1):
            reasons.append('Cannot verify Klipper process identity for known-position evidence')
        known_verified = (type(pid) is int and pid > 1
                          and KNOWN_SESSION['pid'] == pid
                          and time.monotonic() - KNOWN_SESSION['at'] <= KNOWN_MAX_AGE_SEC)
        if mode == 'dock' and not known_verified:
            reasons.append('Run known-position validation first in this Klipper session')
        objects = _rpc('/printer/objects/list').get('objects', [])
        if not isinstance(objects, list) or not {'idle_timeout','toolhead','configfile'} <= set(objects):
            raise MeasurementError('Klipper status objects unavailable')
        qs = {'idle_timeout':'state','toolhead':'homed_axes,position',
              'configfile':'settings'}
        for n, field in [('print_stats','state'),('virtual_sdcard','is_active'),
                         ('pause_resume','is_paused')]:
            if n in objects: qs[n] = field
        status = _rpc('/printer/objects/query?'+urllib.parse.urlencode(qs))['status']
        idle = status.get('idle_timeout',{}).get('state')
        if idle not in ('Idle','Ready'):
            reasons.append('Klipper motion state not idle')
        print_state = status.get('print_stats',{}).get('state')
        if print_state not in (None,'standby','complete','cancelled','error'):
            reasons.append('A print is in progress or paused')
        if 'virtual_sdcard' in objects and status.get('virtual_sdcard',{}).get('is_active') is not False:
            reasons.append('Virtual SD print status active or unknown')
        if 'pause_resume' in objects and status.get('pause_resume',{}).get('is_paused') is not False:
            reasons.append('Klipper reports paused')
        # Hardware commissioning may have neither print_stats nor virtual_sdcard.
        # In that case Ready is expected after a manual G28; the operator must
        # still confirm no host-streaming G-code is active. This is not a proof
        # of a globally exclusive printer lock.
        axes = status.get('toolhead',{}).get('homed_axes','')
        position = status.get('toolhead',{}).get('position',[])
        if 'z' not in axes or len(position) < 3 or type(position[2]) not in (int,float) or position[2] < 15:
            reasons.append('Home Z and establish at least 15 mm clear height before dock positioning')
        settings = status.get('configfile',{}).get('settings',{})
        if not isinstance(settings, dict):
            raise MeasurementError('Configfile settings unavailable')
        if 'homing_override' not in settings:
            reasons.append('Tested CXM homing_override not active')
        expected, resolution, move = _endstop_settings(settings)
        if mode == 'known':
            if not all(axis in axes for axis in 'xyz'):
                reasons.append('Known-position validation requires XYZ to be homed')
            if len(position) < 3 or any(type(v) not in (float,int) or not math.isfinite(v)
                                        for v in position[:3]):
                reasons.append('Known XY coordinates unavailable')
            else:
                # Separate safe-area test; no manual carriage movement allowed.
                x0,y0,z0=position[:3]
                if (not 30 <= x0 <= expected['x']['position_max']-30
                    or not 30 <= y0 <= expected['y']['position_max']-30
                    or not x0+move <= expected['x']['position_max']-25
                    or z0 < 20):
                    reasons.append('Known check requires homed X/Y in central clear area and Z >= 20 mm')
        meta = {'endstops_mm':{axis:v['endstop'] for axis,v in expected.items()},
                'resolution_mm_per_step':resolution,'initial_x_jog_mm':move,
                'idle':idle,'print_state':print_state,'homed_axes':axes,
                'z_mm':position[2] if len(position)>=3 else None,
                'known_start_xy_mm':position[:2] if len(position)>=2 else None,
                'klipper_pid':info.get('process_id')}
        cmds = _rpc('/printer/gcode/help')
        engine = isinstance(cmds, dict) and 'DOCK_LOCATE_CALIBRATE' in cmds
        if not engine:
            reasons.append('Lineux DOCK_LOCATE_CALIBRATE not registered in Klipper')
        if not isinstance(cmds, dict) or 'RESPOND' not in cmds:
            reasons.append('Klipper [respond] / RESPOND G-code must be enabled for result capture')
    except (MeasurementError, KeyError, TypeError, ValueError) as exc:
        reasons.append(str(exc)[:160])
    return {'ready':not reasons, 'engine_present':engine,'blockers':reasons,
            'status':meta,'tool':tool,'mode':mode,'known_verified':known_verified,
            'warning':'Lineux homes Y, then calls CXM G28 X which homes Y again. Duplicate Y homing and kinematic resets MUST be supervised.'}


def parse_report(text):
    # Klipper's gcode.respond_info prefixes EACH output line with "// ".
    # Moonraker retains these prefixes in gcode_store. Normalize only
    # that known prefix before interpreting a multiline Lineux report.
    if type(text) is not str:
        raise MeasurementError('Invalid Lineux response')
    normalized='\n'.join(re.sub(r'^\s*//[ \t]?', '', line)
                         for line in text.splitlines())
    if normalized.count('Lineux Hotswap Dock Calibration') != 1:
        raise MeasurementError('Missing or duplicate Lineux report')
    match = re.search(r'Calculated Dock Location:\s*X:\s*'+NUMBER+
                      r'\s*mm\s*Y:\s*'+NUMBER+r'\s*mm',normalized,re.I)
    if not match:
        raise MeasurementError('Lineux calculated X/Y not found in response')
    x,y=map(float,match.groups())
    if not math.isfinite(x) or not math.isfinite(y):
        raise MeasurementError('Nonfinite Lineux result')
    return {'x':x,'y':y}


def _report_between(events, start, end):
    starts = [i for i,e in enumerate(events) if start in str(e.get('message','')) and e.get('type')=='response']
    ends = [i for i,e in enumerate(events) if end in str(e.get('message','')) and e.get('type')=='response']
    if len(starts)!=1 or len(ends)!=1 or starts[0]>=ends[0]:
        raise MeasurementError('Lineux capture markers missing or ambiguous')
    body='\n'.join(str(e.get('message','')) for e in events[starts[0]+1:ends[0]]
                   if e.get('type')=='response')
    return parse_report(body)


def evaluate_known_position(*, raw_xy, known_xy, calibration_move_x,
                            tolerance=KNOWN_TOLERANCE_MM):
    """Test original Lineux report against a genuine, previously homed XY datum.

    The original routine includes its X jog in counted motor travel. Comparing
    both raw and jog-corrected output exposes that bias without silently
    modifying Lineux or interpreting docking adjustment as compensation.
    """
    if len(known_xy) != 2:
        raise MeasurementError('Known XY datum missing')
    start={axis:_num(known_xy[i], 'known '+axis.upper()) for i,axis in enumerate('xy')}
    raw={axis:_num(raw_xy[axis], 'raw '+axis.upper()) for axis in 'xy'}
    corrected={'x':raw['x']+_num(calibration_move_x,'calibration X jog'),
               'y':raw['y']}
    err={axis:round(corrected[axis]-start[axis],4) for axis in 'xy'}
    raw_err={axis:round(raw[axis]-start[axis],4) for axis in 'xy'}
    passed=max(abs(e) for e in err.values()) <= tolerance
    return {'status':'KNOWN_POSITION_PASSED' if passed else 'KNOWN_POSITION_FAILED',
            'passed':passed,'known_start_xy_mm':start,'lineux_raw_xy_mm':raw,
            'lineux_x_jog_corrected_xy_mm':corrected,
            'raw_error_mm':raw_err,'jog_corrected_error_mm':err,
            'tolerance_mm':tolerance,'save_permitted':False,
            'dock_measurement_permitted':passed,
            'note':'This validates maths against a homed coordinate only. It does not validate manual dock seating, pickup or physical step loss.'}


def _run_original_lineux(pre):
    """Execute exactly the existing original G-code; isolate its report."""
    nonce=uuid.uuid4().hex[:16]
    start='CXM_LINEUX_'+nonce+'_START'
    end='CXM_LINEUX_'+nonce+'_END'
    _rpc('/printer/gcode/script',{'script':
        'RESPOND TYPE=echo MSG='+start+'\nDOCK_LOCATE_CALIBRATE\nRESPOND TYPE=echo MSG='+end})
    entries = _rpc('/server/gcode_store?count=1000').get('gcode_store', [])
    if not isinstance(entries,list):
        raise MeasurementError('Moonraker G-code response log missing')
    xy = _report_between(entries,start,end)
    for axis in 'xy':
        endstop=pre['status']['endstops_mm'][axis]
        if not 0 <= xy[axis] <= endstop:
            raise MeasurementError('Measured '+axis.upper()+' outside physical axis travel')
    return xy


def perform_known_check(*, tool, expected_revision, acknowledgement, store):
    if acknowledgement != 'I_CONFIRM_HOMED_KNOWN_XY_CLEAR_PATH':
        raise MeasurementError('Known-position physical clearance acknowledgement required')
    with MOVE_LOCK:
        snap=store.read()
        if type(expected_revision) is not str or snap['revision'] != expected_revision:
            raise MeasurementError('CXM settings changed; refresh before testing')
        pre=query_readiness(tool=tool,saved=snap,mode='known')
        if not pre['ready']:
            raise MeasurementError('Known-position preflight blocked: '+'; '.join(pre['blockers']))
        xy=_run_original_lineux(pre)
        result=evaluate_known_position(raw_xy=xy,
            known_xy=pre['status']['known_start_xy_mm'],
            calibration_move_x=pre['status']['initial_x_jog_mm'])
        after=store.read()
        if after['revision'] != snap['revision']:
            raise MeasurementError('Settings changed during test; evidence discarded')
        if result['passed']:
            KNOWN_SESSION.update(pid=pre['status']['klipper_pid'],at=time.monotonic())
        else:
            KNOWN_SESSION.update(pid=None,at=0.0)
        result.update(tool=tool,expected_revision=expected_revision,
                      known_verified_in_session=bool(result['passed'] and KNOWN_SESSION['pid']))
        return result


def perform_measurement(*, tool, expected_revision, acknowledgement, store):
    if acknowledgement != 'I_CONFIRM_CLEAR_DOCK_PATH':
        raise MeasurementError('Explicit physical clearance acknowledgement required')
    with MOVE_LOCK:
        snapshot = store.read()
        if type(expected_revision) is not str or snapshot['revision']!=expected_revision:
            raise MeasurementError('CXM settings changed; refresh and recheck tool')
        pre = query_readiness(tool=tool,saved=snapshot)
        if not pre['ready']:
            raise MeasurementError('Preflight blocked: '+'; '.join(pre['blockers']))
        xy = _run_original_lineux(pre)
        latest=store.read()
        if latest['revision']!=snapshot['revision']:
            raise MeasurementError('Settings changed during measurement; result discarded')
        adjust=_num(latest['config']['globals']['x_docking_adjust'],'x_docking_adjust')
        return {'status':'PROVISIONAL_LINEUX_UNVERIFIED',
                'tool':tool,'expected_revision':expected_revision,
                'raw_xy_mm':xy,'separate_x_docking_adjust_mm':adjust,
                'adjusted_x_preview_mm':round(xy['x']+adjust,4),
                'save_permitted':False,'verified':False,
                'note':'No coordinates saved. Use the separate dock draft review; dock Z and physical verification remain required.'}