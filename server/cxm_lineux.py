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
import uuid
import urllib.error
import urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:7125'
MOVE_LOCK = threading.Lock()
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


def query_readiness(*, tool, saved):
    """Read-only readiness check, returning an explicit list of blockers."""
    reasons = []
    engine = False
    meta = {}
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
        meta = {'endstops_mm':{axis:v['endstop'] for axis,v in expected.items()},
                'resolution_mm_per_step':resolution,'initial_x_jog_mm':move,
                'idle':idle,'print_state':print_state,'homed_axes':axes,
                'z_mm':position[2] if len(position)>=3 else None}
        cmds = _rpc('/printer/gcode/help')
        engine = isinstance(cmds, dict) and 'DOCK_LOCATE_CALIBRATE' in cmds
        if not engine:
            reasons.append('Lineux DOCK_LOCATE_CALIBRATE not registered in Klipper')
    except (MeasurementError, KeyError, TypeError, ValueError) as exc:
        reasons.append(str(exc)[:160])
    return {'ready':not reasons, 'engine_present':engine,'blockers':reasons,
            'status':meta,'tool':tool,
            'warning':'Lineux homes Y, then calls CXM G28 X which homes Y again. Duplicate Y homing and kinematic resets MUST be supervised.'}


def parse_report(text):
    if text.count('Lineux Hotswap Dock Calibration') != 1:
        raise MeasurementError('Missing or duplicate Lineux report')
    match = re.search(r'Calculated Dock Location:\s*X:\s*'+NUMBER+
                      r'\s*mm\s*Y:\s*'+NUMBER+r'\s*mm',text,re.I)
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
        nonce=uuid.uuid4().hex[:16]
        start='CXM_LINEUX_'+nonce+'_START'
        end='CXM_LINEUX_'+nonce+'_END'
        # Fixed G-code only; no request data interpolated into commands.
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