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
CXM_HOME_SESSION = {'pid':None,'revision':None,'at':0.0}
KNOWN_TOLERANCE_MM = 0.25  # Initial commissioning threshold, not established accuracy
NUMBER = r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))'


class MeasurementError(RuntimeError):
    pass


def _rpc(path, payload=None, *, timeout_s=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE+path, data=data,
        headers={'Content-Type': 'application/json'} if data is not None else {},
        method='POST' if data is not None else 'GET')
    # Long-running supervised native tool streams may legitimately exceed
    # the 125s default POST read timeout at commissioning feed rates.
    # Only their explicit caller may increase this read timeout; all
    # existing Lineux/T0/T1+ operations retain the original limits.
    if timeout_s is not None:
        if (type(timeout_s) not in (int,float) or
                not 4 <= timeout_s <= 600):
            raise ValueError('Moonraker read timeout outside approved 4–600s range')
    deadline = timeout_s if timeout_s is not None else 125 if data else 4
    try:
        with urllib.request.urlopen(req, timeout=deadline) as f:
            answer = json.load(f)
    except urllib.error.HTTPError as exc:
        try:
            detail=json.loads(exc.read(16384).decode('utf8')).get('error',{})
            trace=detail.get('traceback','')
            match=re.search(r'gcode\\.CommandError: ([^\\n]+)',trace)
            reason=match.group(1) if match else detail.get('message',str(exc))
        except (ValueError,UnicodeError,TypeError):
            reason=str(exc)
        raise MeasurementError('Klipper rejected command: '+str(reason)[:240]) from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise MeasurementError('Moonraker connection failed: '+str(exc)[:140]) from exc
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
    if mode not in ('dock','known','prepare','home'):
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
        objects = _rpc('/printer/objects/list').get('objects', [])
        if not isinstance(objects, list) or not {'idle_timeout','toolhead','configfile'} <= set(objects):
            raise MeasurementError('Klipper status objects unavailable')
        qs = {'idle_timeout':'state','toolhead':'homed_axes,position',
              'configfile':'settings'}
        if 'stepper_enable' not in objects:
            reasons.append('Cannot verify stepper motor power states')
        else:
            qs['stepper_enable']='steppers'
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
        if mode != 'home' and ('z' not in axes or len(position) < 3 or type(position[2]) not in (int,float) or position[2] < 20):
            reasons.append('Home Z and establish at least 20 mm actual clearance before dock positioning')
        settings = status.get('configfile',{}).get('settings',{})
        if not isinstance(settings, dict):
            raise MeasurementError('Configfile settings unavailable')
        if 'homing_override' not in settings:
            reasons.append('Tested CXM homing_override not active')
        expected, resolution, move = _endstop_settings(settings)
        enabled=status.get('stepper_enable',{}).get('steppers',{})
        if not isinstance(enabled,dict):
            enabled={}
        z_steppers=('stepper_z','stepper_z1','stepper_z2','stepper_z3')
        if mode != 'home' and not all(enabled.get(name) is True for name in z_steppers):
            reasons.append('All four Z steppers must be powered and physically level')
        if mode == 'home':
            # A full home may begin with unhomed or released motors.
            # Runtime status, print lockout, engine configuration and the
            # operator's clear-travel acknowledgement still apply.
            pass
        elif mode == 'known':
            # Klipper SET_STEPPER_ENABLE ENABLE=0 does not clear homing state.
            # After hand repositioning, displayed XY is stale and must never
            # be used as the ground truth of a "known position" test.
            if enabled.get('stepper_x') is not True or enabled.get('stepper_y') is not True:
                reasons.append('KNOWN XY INVALID: X/Y steppers were released; use Measure selected dock, not Verify known XY')
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
        else:
            # Mode 'prepare' is the powered stage immediately before releasing XY.
            # Mode 'dock' is the hand-positioned, unknown-XY measurement stage.
            # Neither is contingent on a separate known-position test; that
            # proof was already physically established during engineering.
            if not all(axis in axes for axis in 'xyz'):
                reasons.append('Home X/Y/Z before releasing motors for dock calibration')
            if mode == 'prepare':
                if enabled.get('stepper_x') is not True or enabled.get('stepper_y') is not True:
                    reasons.append('Cannot release X/Y: axes must currently be powered after homing')
                if len(position) >= 2 and (
                    type(position[0]) not in (int,float) or
                    type(position[1]) not in (int,float) or
                    not math.isfinite(position[0]) or not math.isfinite(position[1]) or
                    not expected['x']['position_min']+30 <= position[0] <= expected['x']['position_max']-30 or
                    not expected['y']['position_min']+30 <= position[1] <= expected['y']['position_max']-30
                ):
                    reasons.append('Move carriage to a central safe XY before releasing motors')
            elif enabled.get('stepper_x') is not False or enabled.get('stepper_y') is not False:
                reasons.append('Release only X/Y motors, then hand-align the carriage to the dock')
            # Original Lineux issues G91 G1 X+3 before homing. Its current
            # logical X still has to leave room for that G-code move, even
            # though physical X was changed with motors released.
            if (len(position)<1 or type(position[0]) not in (int,float)
                or not math.isfinite(position[0])
                or not expected['x']['position_min']+5 <= position[0]
                <= expected['x']['position_max']-abs(move)-5):
                reasons.append('Reported X leaves no safe software margin for Lineux +3 mm jog; seed a central XY before releasing motors')
        meta = {'endstops_mm':{axis:v['endstop'] for axis,v in expected.items()},
                'resolution_mm_per_step':resolution,'initial_x_jog_mm':move,
                'idle':idle,'print_state':print_state,'homed_axes':axes,
                'z_mm':position[2] if len(position)>=3 else None,
                'known_start_xy_mm':position[:2] if len(position)>=2 else None,
                'klipper_pid':info.get('process_id'),
                'xy_motor_enabled':{axis:enabled.get('stepper_'+axis) for axis in 'xy'},
                'z_motor_enabled':{name:enabled.get(name) for name in z_steppers},
                'xy_position_is_known':mode == 'known' and
                    enabled.get('stepper_x') is True and enabled.get('stepper_y') is True}
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
    """Compare the ORIGINAL Lineux report directly with homed starting XY.

    Real CXM observation on 2026-11-06: from X195/Y170 with a +3mm
    calibration jog, the original Lineux module correctly returned
    X195.01/Y170.05. The built-in calculation ALREADY incorporates
    the jog; adding it again produces a false +3mm error.

    The separate x_docking_adjust setting is a mechanical docking
    adjustment, NOT an accuracy correction or part of this validation.
    """
    if len(known_xy) != 2:
        raise MeasurementError('Known XY datum missing')
    start={axis:_num(known_xy[i], 'known '+axis.upper()) for i,axis in enumerate('xy')}
    raw={axis:_num(raw_xy[axis], 'Lineux '+axis.upper()) for axis in 'xy'}
    jog=_num(calibration_move_x,'calibration X jog')
    if not 0.5 <= abs(jog) <= 5:
        raise MeasurementError('Unexpected calibration jog')
    err={axis:round(raw[axis]-start[axis],4) for axis in 'xy'}
    passed=max(abs(e) for e in err.values()) <= tolerance
    return {'status':'KNOWN_POSITION_PASSED' if passed else 'KNOWN_POSITION_FAILED',
            'passed':passed,'known_start_xy_mm':start,'lineux_raw_xy_mm':raw,
            'known_position_error_mm':err,'raw_error_mm':err,
            'calibration_move_x_mm':jog,
            'tolerance_mm':tolerance,'save_permitted':False,
            'dock_measurement_permitted':passed,
            'note':'Unmodified Lineux coordinates evaluated as reported. The internal 3mm move must not be added a second time. This single test does not prove repeatability, manual dock seating, pickup or physical step loss.'}


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


def home_and_lift_for_dock(*, tool, expected_revision, acknowledgement, store):
    """Full verified CXM G28, lift to Z20 and park central to permit XY release.

    Does not touch firmware, Klipper configurations, T0 offsets, or Z leveling.
    All moves use the commissioned printer G28 and ordinary Klipper limits.
    """
    if acknowledgement != 'I_CONFIRM_CLEAR_G28_AND_Z20_PATH':
        raise MeasurementError('Confirm safe XYZ homing, level gantry and clear central travel')
    with MOVE_LOCK:
        snap=store.read()
        if type(expected_revision) is not str or snap['revision'] != expected_revision:
            raise MeasurementError('CXM settings changed; refresh before homing')
        pre=query_readiness(tool=tool,saved=snap,mode='home')
        if not pre['ready']:
            raise MeasurementError('Home and lift blocked: '+'; '.join(pre['blockers']))
        # Home first. Raise Z20, and centre XY *while Z20 is maintained*
        # to leave software space for Lineux's original initial +3 mm jog.
        _rpc('/printer/gcode/script',{'script':
            'G28\nG90\nG1 Z20 F300\nG1 X195 Y170 F3000'})
        # After Moonraker gcode/script returns, the idle_timeout state may
        # briefly be "Printing"; verify physical motor flags/coordinates, not
        # a premature idle_timeout transition.
        status=_rpc('/printer/objects/query?toolhead=homed_axes,position&stepper_enable=steppers')['status']
        h=status.get('toolhead',{})
        pos=h.get('position',[])
        motors=status.get('stepper_enable',{}).get('steppers',{})
        if (not all(a in h.get('homed_axes','') for a in 'xyz')
            or len(pos)<3 or any(type(n) not in (int,float) for n in pos[:3])
            or abs(pos[0]-195)>0.2 or abs(pos[1]-170)>0.2
            or abs(pos[2]-20)>0.2
            or not all(motors.get(n) is True for n in
                ('stepper_x','stepper_y','stepper_z','stepper_z1','stepper_z2','stepper_z3'))):
            raise MeasurementError('Homing completion not verified; inspect XYZ and all four Z motors before proceeding')
        CXM_HOME_SESSION.update(pid=pre['status']['klipper_pid'],revision=expected_revision,at=time.monotonic())
        return {'status':'HOMED_Z20_CENTRE','tool':tool,'position_mm':[195,170,20],
                'note':'CXM homed and parked X195 Y170 Z20. Check physical clearance before releasing XY.'}


def release_xy_for_dock(*, tool, expected_revision, acknowledgement, store):
    """Release only CoreXY motors; never switch off Z or move the gantry.

    Caller must confirm the safe homed-Z setup. No homing and no
    kinematic-coordinate reset is performed here. Displayed XY becomes stale
    immediately after a manual carriage movement.
    """
    if acknowledgement != 'I_CONFIRM_Z_SUPPORTED_RELEASE_XY':
        raise MeasurementError('Confirm physically level Z20 and safe free carriage before releasing X/Y')
    with MOVE_LOCK:
        snap=store.read()
        if type(expected_revision) is not str or expected_revision != snap['revision']:
            raise MeasurementError('CXM settings changed; refresh before release')
        pre=query_readiness(tool=tool,saved=snap,mode='prepare')
        if not pre['ready']:
            raise MeasurementError('XY release blocked: '+'; '.join(pre['blockers']))
        CXM_HOME_SESSION.update(pid=None,revision=None,at=0.0)
        _rpc('/printer/gcode/script',{'script':
            'SET_STEPPER_ENABLE STEPPER=stepper_x ENABLE=0\n'
            'SET_STEPPER_ENABLE STEPPER=stepper_y ENABLE=0'})
        # Confirm the actual motor-enable state, not the idle_timeout state.
        # Klipper may report "Printing" briefly after the command completes.
        status=_rpc('/printer/objects/query?stepper_enable=steppers')['status']
        steppers=status.get('stepper_enable',{}).get('steppers',{})
        if (steppers.get('stepper_x') is not False or
            steppers.get('stepper_y') is not False or
            not all(steppers.get(z) is True for z in
                    ('stepper_z','stepper_z1','stepper_z2','stepper_z3'))):
            raise MeasurementError('XY release confirmation failed; verify power to all four Z motors before touching carriage')
        return {'status':'XY_RELEASED_Z_REMAINS_POWERED','tool':tool,
                'release_confirmed':True,
                'note':'Align carriage by hand. Reported XY is now stale; confirm +3mm physical clearance and full Y/Y/X homing route before measurement.'}


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
        adjust_y=_num(latest['config']['globals']['y_docking_adjust'],'y_docking_adjust')
        return {'status':'PROVISIONAL_LINEUX_UNVERIFIED',
                'tool':tool,'expected_revision':expected_revision,
                'raw_xy_mm':xy,'separate_x_docking_adjust_mm':adjust,
                'separate_y_docking_adjust_mm':adjust_y,
                'adjusted_x_preview_mm':round(xy['x']+adjust,4),
                'adjusted_y_preview_mm':round(xy['y']+adjust_y,4),
                'datum_kind':'Lineux measured carriage XY, converted to CxChanger locking-hole datum',
                'save_permitted':False,'verified':False,
                'note':'Measurement is raw Lineux XY. Apply reviewed X/Y datum correction in the draft; CxChanger motion uses only accepted dock XY. No coordinates saved yet.'}