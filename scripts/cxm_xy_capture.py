#!/usr/bin/env python3
"""CXM Stage 1: non-saving real-hardware XY step-counter validation.

Read-only by default.  With --apply-known-check and an explicit clearance
acknowledgement, performs two +10 mm calibration jogs and the PROVEN G28 X
(Y-then-X) operation, captures Klipper MCU counters, and checks that the
original, known Cartesian position can be reconstructed to within tolerance.

This is NOT a dock measurement. It NEVER disables steppers, picks/drops tools,
changes Klipper configuration, sets kinematic position, or writes dock values.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from cxm_xy_measure import CoreXYTransform

COUNTER = re.compile(r"\b(stepper_[a-zA-Z0-9_]+):(-?\d+)(?=\s|$)")
MCU = re.compile(r"(?:^|\s)(?://\s*)?mcu:\s*(.+)$", re.IGNORECASE)
START_TOKEN = "CXMXY_{token}_START"
END_TOKEN = "CXMXY_{token}_END"
JOG_MM = 10.0
TOLERANCE_MM = 0.25  # Commissioning gate, NOT demonstrated accuracy


class CaptureError(RuntimeError):
    pass


def parse_mcu(message: str) -> dict[str, int]:
    """Parse one Klipper GET_POSITION mcu record, rejecting malformed data."""
    lines = [m.group(1) for ln in message.splitlines()
             if (m := MCU.search(ln.strip()))]
    if len(lines) != 1:
        raise CaptureError("Exactly one mcu: line required")
    raw = lines[0].strip()
    found = list(COUNTER.finditer(raw))
    if not found or COUNTER.sub("", raw).strip():
        raise CaptureError("Unexpected MCU counter format: " + raw[:180])
    output = {}
    for m in found:
        if m.group(1) in output:
            raise CaptureError("Duplicate MCU stepper name")
        output[m.group(1)] = int(m.group(2))
    return output


def extract_marked_snapshot(events: list[dict], token: str) -> dict[str, int]:
    """A unique start/end marker must enclose exactly one MCU response."""
    start = START_TOKEN.format(token=token)
    end = END_TOKEN.format(token=token)
    begins = [i for i,e in enumerate(events)
              if e.get('type') == 'response' and start in e.get('message','')]
    ends = [i for i,e in enumerate(events)
            if e.get('type') == 'response' and end in e.get('message','')]
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        raise CaptureError("Capture markers missing/ambiguous; gcode_store may be too small")
    section = events[begins[0]+1:ends[0]]
    if any(e.get('type') == 'command' for e in section):
        raise CaptureError("Unrelated Moonraker command interleaved with capture")
    mcu = [e.get('message','') for e in section
           if e.get('type') == 'response' and MCU.search(e.get('message',''))]
    if len(mcu) != 1:
        raise CaptureError("Exactly one GET_POSITION mcu response required")
    return parse_mcu(mcu[0])


def motor_delta(before: dict, after: dict, names=('stepper_x','stepper_y')) -> tuple[int,int]:
    if set(before) != set(after):
        raise CaptureError("MCU stepper set changed: possible restart or incomplete capture")
    try:
        return tuple(after[n] - before[n] for n in names)
    except KeyError as exc:
        raise CaptureError("Missing X/Y MCU stepper " + str(exc)) from exc


def verify_z_unchanged(before: dict, after: dict) -> None:
    zs = [name for name in before if name == 'stepper_z' or re.fullmatch(r'stepper_z\d+', name)]
    if not zs:
        raise CaptureError("No Z MCU stepper counters found; cannot verify zero Z motion")
    if any(before[z] != after[z] for z in zs):
        raise CaptureError("Z MCU step counts changed during XY-only test")


def reconstruct_known_xy(*, matrix, before, after, end_xy, known_xy, tolerance=TOLERANCE_MM):
    dx,dy = matrix.cartesian_travel(motor_delta(before,after))
    x,y = end_xy[0]-dx, end_xy[1]-dy
    error_x,error_y = x-known_xy[0], y-known_xy[1]
    if not all(math.isfinite(t) for t in (x,y,dx,dy,error_x,error_y)):
        raise CaptureError("Non-finite reconstruction")
    passed = max(abs(error_x),abs(error_y)) <= tolerance
    return dict(inferred_start_xy_mm=[round(x,5),round(y,5)],
                known_start_xy_mm=[round(n,5) for n in known_xy],
                home_travel_mm=[round(dx,5),round(dy,5)],
                error_mm=[round(error_x,5),round(error_y,5)],
                tolerance_mm=tolerance,passed=passed)


class Moonraker:
    def __init__(self, base):
        parts = urlparse(base.rstrip('/'))
        if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1','localhost','::1'):
            raise CaptureError('Run on the printer host with --url http://127.0.0.1:7125 only')
        if parts.path not in ('','/') or parts.username or parts.password or parts.query:
            raise CaptureError('Moonraker URL must not contain credentials/path/query')
        self.base = base.rstrip('/')

    def request(self, path, payload=None):
        if payload is not None:
            content = json.dumps(payload).encode('utf-8')
            req = Request(self.base+path, content, {'Content-Type':'application/json'},method='POST')
        else:
            req = Request(self.base+path,method='GET')
        try:
            with urlopen(req, timeout=90) as response:
                raw = json.load(response)
        except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
            raise CaptureError('Moonraker request failed: '+str(exc)) from exc
        if not isinstance(raw,dict) or 'error' in raw:
            raise CaptureError('Moonraker returned error: '+repr(raw)[:400])
        return raw.get('result',raw)

    def status(self):
        # Discover optional status objects.  A machine with no print_stats
        # status must not be mistaken for a printing (or idle) machine.
        available=self.request('/printer/objects/list').get('objects')
        if not isinstance(available,list):
            raise CaptureError('Cannot identify Klipper status objects')
        required={'toolhead','configfile','idle_timeout'}
        if not required.issubset(available):
            raise CaptureError('Required Klipper status object missing: '
                               + ', '.join(sorted(required-set(available))))
        query={'toolhead':'position,homed_axes', 'configfile':'settings',
               'idle_timeout':'state'}
        for name,fields in (('print_stats','state'),
                            ('virtual_sdcard','is_active'),
                            ('pause_resume','is_paused')):
            if name in available:
                query[name]=fields
        raw=self.request('/printer/objects/query?'+urlencode(query))
        return raw['status']

    def gcode(self, lines):
        self.request('/printer/gcode/script', {'script':lines})

    def snapshot(self):
        # M400 flushes movement before reading MCU counters.  The markers
        # detect response loss/interleaving, not physical missed steps.
        token=uuid.uuid4().hex[:16].upper()
        start=START_TOKEN.format(token=token)
        end=END_TOKEN.format(token=token)
        self.gcode('M400\nRESPOND TYPE=echo MSG="'+start+'"\nGET_POSITION\nRESPOND TYPE=echo MSG="'+end+'"')
        entries=self.request('/server/gcode_store?count=1000')['gcode_store']
        return extract_marked_snapshot(entries,token)


def validate_preflight(status):
    try:
        th=status['toolhead']; idle=status['idle_timeout']['state']
        cfg=status['configfile']['settings']
        xcfg=cfg['stepper_x']; ycfg=cfg['stepper_y']
        override=cfg['homing_override']
    except (KeyError,TypeError) as exc:
        raise CaptureError('Missing printer/override configuration: '+str(exc)) from exc
    axes=th.get('homed_axes','')
    ps=status.get('print_stats',{})
    state=ps.get('state')
    xyz=th['position']
    if idle not in ('Idle','Ready'):
        raise CaptureError('Printer is not idle; idle_timeout.state='+str(idle))
    if state not in (None,'standby','complete','cancelled','error'):
        raise CaptureError('Printer print job not idle; print_stats.state='+str(state))
    vs=status.get('virtual_sdcard')
    if vs is not None and vs.get('is_active') is not False:
        raise CaptureError('Virtual SD activity is active or unknown')
    pause=status.get('pause_resume')
    if pause is not None and pause.get('is_paused') is not False:
        raise CaptureError('Printer paused state is active or unknown')
    # Klipper may not expose print_stats on an unused printer, or may
    # return null.  In that case an Idle state is acceptable; a Ready
    # state requires an explicit inactive virtual-SD signal.
    if state is None and idle == 'Ready' and vs is None:
        raise CaptureError('Cannot confirm no print is active: '
                           'print_stats is absent and virtual_sdcard unavailable')
    if not all(a in axes for a in 'xyz'):
        raise CaptureError('Home and verify XYZ safely before the known-position check')
    if len(xyz)<3 or xyz[2] < 10:
        raise CaptureError('Z must already be homed and >= 10 mm high')
    if 'xyz' not in str(override.get('axes','xyz')).lower():
        raise CaptureError('Expected active XYZ homing override')
    bounds={}
    for axis,cfg_axis,coord in (('x',xcfg,xyz[0]),('y',ycfg,xyz[1])):
        try:
            lo=float(cfg_axis.get('position_min',0.0))
            hi=float(cfg_axis['position_max'])
            end=float(cfg_axis['position_endstop'])
        except (KeyError,ValueError,TypeError) as exc:
            raise CaptureError('Incomplete '+axis.upper()+' travel limits') from exc
        if not (lo<hi and hi-1.0<=end<=hi+0.1):
            raise CaptureError('Requires verified positive '+axis.upper()+' endstop near position_max')
        if not (lo+15.0<=coord<=hi-JOG_MM-15.0):
            raise CaptureError(axis.upper()+' too close to travel boundary; reposition safely')
        bounds[axis]=dict(min_mm=lo,max_mm=hi,endstop_mm=end)
    return {'known_xy_mm':[float(xyz[0]),float(xyz[1])],
            'z_mm':float(xyz[2]),'homed_axes':axes,'print_state':state,
            'idle_timeout_state':idle,'virtual_sd_active':None if vs is None else vs['is_active'],
            'paused':None if pause is None else pause['is_paused'],
            'bounds':bounds,'homing_override_present':True}


def checked_jog(api,axis,step=JOG_MM):
    # Leave the user's gcode absolute/relative and offsets as they were.
    api.gcode('SAVE_GCODE_STATE NAME=CXM_XY_MEASURE\nG91\n'
              'G1 '+axis.upper()+f'{step:.3f} F600\nM400\n'
              'RESTORE_GCODE_STATE NAME=CXM_XY_MEASURE MOVE=0')


def live_known_check(api, preflight):
    if validate_preflight(api.status())['known_xy_mm'] != preflight['known_xy_mm']:
        raise CaptureError('Starting XY changed after confirmation')
    start=api.snapshot()
    checked_jog(api,'x')
    sx=api.snapshot()
    verify_z_unchanged(start,sx)
    checked_jog(api,'y')
    sy=api.snapshot()
    verify_z_unchanged(sx,sy)

    dx=motor_delta(start,sx)
    dy=motor_delta(sx,sy)
    matrix=CoreXYTransform.calibrate(JOG_MM,dx,JOG_MM,dy)
    known=[preflight['known_xy_mm'][0]+JOG_MM,
           preflight['known_xy_mm'][1]+JOG_MM]
    current=api.status()['toolhead']['position']
    if max(abs(current[i]-known[i]) for i in range(2)) > 0.05:
        raise CaptureError('Unexpected XY after calibration jogs')

    # V2.0 G28 X is verified by operator to home Y then X; no new override.
    # This is one combined operation, not G28 Y followed by G28 X.
    api.gcode('G28 X\nM400')
    end=api.snapshot()
    verify_z_unchanged(sy,end)
    after=api.status()
    if not all(a in after['toolhead']['homed_axes'] for a in 'xy'):
        raise CaptureError('G28 X did not leave X/Y marked homed')
    end_xy=[preflight['bounds'][i]['endstop_mm'] for i in ('x','y')]
    actual_after=after['toolhead']['position']
    if max(abs(actual_after[i]-end_xy[i]) for i in range(2))>0.05:
        raise CaptureError('Unexpected XY after G28 X; inspect override')
    result=reconstruct_known_xy(matrix=matrix,before=sy,after=end,
                                end_xy=end_xy,known_xy=known)
    return {'status':'KNOWN_POSITION_TEST_PASSED' if result['passed'] else 'REJECTED',
            'save_permitted':False,'dock_measurement_permitted':False,
            'motion_performed':True,'no_z_step_change':True,
            'matrix_steps_per_mm':{'ax':matrix.ax,'ay':matrix.ay,'bx':matrix.bx,'by':matrix.by},
            'raw_mcu_snapshots':{'before_x_jog':start,'after_x_jog':sx,
                                 'after_y_jog':sy,'after_g28_x':end},
            'configured_endstops_mm':{'x':end_xy[0],'y':end_xy[1]},
            'test':result,
            'warnings':['NOT a dock measurement; no CXM variables were written.',
                        'This proves only commanded-step consistency in this trial.',
                        'Physically inspect for skipped steps and clear travel before any dock test.']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url',default='http://127.0.0.1:7125')
    parser.add_argument('--apply-known-check',action='store_true',help='Move +10 X, +10 Y, then G28 X')
    parser.add_argument('--confirm',default='',help='Required with --apply-known-check: CLEAR_XY_PATH')
    args=parser.parse_args(argv)
    try:
        api=Moonraker(args.url)
        preflight=validate_preflight(api.status())
        if not args.apply_known_check:
            print(json.dumps({'status':'READ_ONLY_PREFLIGHT_PASSED','motion_performed':False,
                              'save_permitted':False,'known_check_available':True,
                              'preflight':preflight},indent=2))
            return 0
        if args.confirm!='CLEAR_XY_PATH':
            raise CaptureError('Motion requires --confirm CLEAR_XY_PATH after physical XY clearance check')
        result=live_known_check(api,preflight)
        print(json.dumps(result,indent=2))
        return 0 if result['status']=='KNOWN_POSITION_TEST_PASSED' else 2
    except (CaptureError,KeyError,ValueError,TypeError) as exc:
        print('CXM XY validation REJECTED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())