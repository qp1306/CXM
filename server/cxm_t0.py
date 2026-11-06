"""CXM T0 slow-speed XY pickup/dropoff commissioning.

Explicit operator-supervised actions only, scoped to T0. No printer.cfg
editing, no Z movement, no heater control, and no automatic tool activation.
The tested Lineux dock X/Y is used without x_docking_adjust correction.
"""
from __future__ import annotations
import math
import threading
import time
import urllib.parse
from cxm_lineux import _rpc, MOVE_LOCK, MeasurementError

SESSION_LOCK=threading.Lock()
SESSION={'pid':None,'revision':None,'stage':None,'sensor':None,
         'samples':{},'last_action':None,'xy':None,'path':None}
MOTORS=('stepper_x','stepper_y','stepper_z','stepper_z1','stepper_z2','stepper_z3')
SAFE_FEED=600
TEST_FEED=240
LATCH_FEED=180
POSITION_TOL=0.2

class T0Error(MeasurementError):
    pass

def number(n,label,lo,hi):
    if type(n) not in (int,float) or not math.isfinite(n) or not lo<=n<=hi:
        raise T0Error(label+' outside safe configured range')
    return float(n)

def _safe_context(saved, *, require_homed=True, require_in_park=False):
    if saved['migration_required'] or saved['config']['globals']['tool_count']!=1:
        raise T0Error('T0-only commissioning requires exactly one active hotend')
    t=saved['config']['tools'][0]
    if t['maintenance_lockout']:
        raise T0Error('T0 is under maintenance lockout')
    if t['dock_x'] is None or t['dock_y'] is None:
        raise T0Error('Save T0 dock X/Y first')
    x=number(t['dock_x'],'Dock X',0,335)
    y=number(t['dock_y'],'Dock Y',0,362)
    safe=number(saved['config']['globals']['safe_y'],'Configured safe Y',0,362)
    if safe<y+35:
        raise T0Error('Configured safe Y is too close to dock for guarded path')
    if x<10 or x>325 or y<10 or y>320:
        raise T0Error('T0 dock outside supervised test zone')
    info=_rpc('/printer/info')
    if info.get('state')!='ready' or type(info.get('process_id')) is not int:
        raise T0Error('Klipper not ready or identity unavailable')
    objects=_rpc('/printer/objects/list').get('objects',[])
    necessary={'toolhead','stepper_enable','idle_timeout'}
    if not necessary.issubset(set(objects)):
        raise T0Error('Cannot verify homing, motor power and idle status')
    query={'toolhead':'homed_axes,position',
           'stepper_enable':'steppers','idle_timeout':'state'}
    for key,field in [('print_stats','state'),('virtual_sdcard','is_active'),
                      ('pause_resume','is_paused')]:
        if key in objects: query[key]=field
    status=_rpc('/printer/objects/query?'+urllib.parse.urlencode(query)).get('status',{})
    if status.get('idle_timeout',{}).get('state') not in ('Idle','Ready'):
        raise T0Error('Klipper is not idle')
    if status.get('print_stats',{}).get('state') not in (None,'standby','complete','cancelled','error'):
        raise T0Error('Printer has a print active or paused')
    if 'virtual_sdcard' in objects and status.get('virtual_sdcard',{}).get('is_active') is not False:
        raise T0Error('Virtual SD print active or unknown')
    if 'pause_resume' in objects and status.get('pause_resume',{}).get('is_paused') is not False:
        raise T0Error('Printer paused')
    homed=status.get('toolhead',{}).get('homed_axes','')
    pos=status.get('toolhead',{}).get('position',[])
    motors=status.get('stepper_enable',{}).get('steppers',{})
    if require_homed and (not all(axis in homed for axis in 'xyz')
                          or len(pos)<3 or any(type(v) not in (float,int) or not math.isfinite(v) for v in pos[:3])
                          or pos[2]<20):
        raise T0Error('Home XYZ and maintain at least Z20 physical clearance')
    if require_homed and not all(motors.get(name) is True for name in MOTORS):
        raise T0Error('All X/Y and four Z steppers must be powered; rehome after manual positioning')
    if require_in_park and (abs(pos[0]-x)>POSITION_TOL or abs(pos[1]-safe)>POSITION_TOL):
        raise T0Error('Carriage must be at verified staging X/Y before pickup/dropoff')
    return {'pid':info['process_id'],'x':x,'y':y,'safe_y':safe,
            'position':pos[:3],'objects':objects,'revision':saved['revision']}

def _sensor_value(name,objects):
    if type(name) is not str or name not in objects:
        raise T0Error('Selected carriage switch is not registered in Klipper')
    if name.startswith('gcode_button '):
        field='state'
    elif name.startswith('filament_switch_sensor '):
        field='filament_detected'
    else:
        raise T0Error('Use a Klipper gcode_button or filament_switch_sensor object')
    status=_rpc('/printer/objects/query?'+urllib.parse.urlencode({name:field})).get('status',{})
    value=status.get(name,{}).get(field)
    if field=='state':
        if value not in ('PRESSED','RELEASED'): raise T0Error('Switch state unavailable')
    elif type(value) is not bool:
        raise T0Error('Filament switch state unavailable')
    return value

def _candidates(objects):
    return sorted(o for o in objects if
                  o.startswith('gcode_button ') or o.startswith('filament_switch_sensor '))

def plan(saved,shift_x=-3.0,dodge_y=14.0):
    # Geometry follows the original CxChanger sequence. These are tentative
    # mechanical adjustments, NOT a claim of verified actual T0 geometry.
    t=saved['config']['tools'][0]
    x=number(t['dock_x'],'Dock X',0,335)
    y=number(t['dock_y'],'Dock Y',0,362)
    safe=number(saved['config']['globals']['safe_y'],'Safe Y',0,362)
    dx=number(shift_x,'Lateral shift X',-8,-1)
    dy=number(dodge_y,'Dodge Y',5,25)
    if x+dx<5 or x+dx>330 or y+dy+20>safe:
        raise T0Error('Pickup/dropoff path conflicts with physical limits or safe Y')
    return {'stage':[(x,safe)],
            'pickup':[(x,y+dy),(x+dx,y+dy),(x+dx,y),(x,y),(x,safe)],
            'dropoff':[(x,y),(x+dx,y),(x+dx,y+dy),(x,y+dy),(x,safe)],
            'shift_x':dx,'dodge_y':dy,'safe_y':safe}

def status(store):
    saved=store.read()
    try:
        ctx=_safe_context(saved)
        p=plan(saved)
        with SESSION_LOCK:
            _invalidate(ctx)
            stage=SESSION['stage']
            sensor=SESSION['sensor']
            samples=SESSION['samples'].copy()
            last=SESSION['last_action']
        candidate=_candidates(ctx['objects'])
        live={}
        for name in candidate:
            try: live[name]=_sensor_value(name,ctx['objects'])
            except T0Error: live[name]=None
        return {'ready':True,'tool':0,'saved_xy_mm':{'x':ctx['x'],'y':ctx['y']},
                'safe_y_mm':ctx['safe_y'],'position_mm':ctx['position'],
                'plan':p,'sensor_candidates':candidate,'sensor_states':live,
                'sensor':sensor,'sensor_samples':samples,
                'sensor_calibrated':sensor is not None and 'empty' in samples
                                    and 'mounted' in samples and samples['empty']!=samples['mounted'],
                'stage':stage,'last_action':last,'blockers':[],
                'warning':'T0 test moves the carriage. All waypoints require physical clearance; tool pickup is not inferred from coordinates.'}
    except (T0Error,ValueError,KeyError,TypeError) as e:
        return {'ready':False,'tool':0,'blockers':[str(e)],'stage':None,'sensor_candidates':[],
                'sensor_calibrated':False}

def _invalidate(ctx):
    if SESSION['pid']!=ctx['pid'] or SESSION['revision']!=ctx['revision']:
        SESSION.update(pid=ctx['pid'],revision=ctx['revision'],stage=None,
                       last_action=None,sensor=None,samples={},xy=None,path=None)

def record_sensor(*,store,expected_revision,name,condition,acknowledgement):
    if acknowledgement!='I_CHECKED_THE_PHYSICAL_T0_SENSOR':
        raise T0Error('Visually confirm actual empty/mounted T0 before recording sensor')
    if condition not in ('empty','mounted'):
        raise T0Error('Invalid sensor calibration condition')
    saved=store.read()
    if saved['revision']!=expected_revision: raise T0Error('Dock settings changed; refresh')
    ctx=_safe_context(saved)
    with SESSION_LOCK:
        _invalidate(ctx)
        candidates=_candidates(ctx['objects'])
        if name not in candidates: raise T0Error('No supported sensor object selected')
        value=_sensor_value(name,ctx['objects'])
        if SESSION['sensor']!=name:
            SESSION['sensor']=name
            SESSION['samples']={}
            SESSION['stage']=None
        SESSION['samples'][condition]=value
        samples=SESSION['samples'].copy()
        verified='empty' in samples and 'mounted' in samples and samples['empty']!=samples['mounted']
    return {'recorded':condition,'value':value,'both_states_distinct':verified,
            'note':'Sensor signal evidence only; visually verify coupling for every supervised test.'}

def _gcode(points,kind):
    if kind=='stage':
        speeds=[SAFE_FEED]
    elif kind=='pickup':
        speeds=[TEST_FEED,TEST_FEED,TEST_FEED,LATCH_FEED,TEST_FEED]
    else:
        speeds=[TEST_FEED,LATCH_FEED,TEST_FEED,TEST_FEED,TEST_FEED]
    lines=['G90']
    if kind=='stage':
        # Go to the known-configured safe-Y line before crossing toward dock X
        x,y=points[0]
        lines.extend([f'G1 Y{y:.5f} F{SAFE_FEED}',f'G1 X{x:.5f} F{SAFE_FEED}'])
    else:
        for (x,y),feed in zip(points,speeds):
            lines.append(f'G1 X{x:.5f} Y{y:.5f} F{feed}')
    lines.append('M400')
    return '\n'.join(lines)

def motion(*,store,expected_revision,kind,acknowledgement,
           shift_x=-3.0,dodge_y=14.0):
    if kind not in ('stage','pickup','dropoff'):
        raise T0Error('Unsupported test command')
    if acknowledgement!='I_VISUALLY_VERIFIED_T0_CLEARANCE_AND_TEST_PATH':
        raise T0Error('Physical path confirmation required')
    if not MOVE_LOCK.acquire(blocking=False):
        raise T0Error('Another printer motion operation is in progress')
    try:
        saved=store.read()
        if saved['revision']!=expected_revision: raise T0Error('T0 coordinates changed; refresh')
        ctx=_safe_context(saved,require_in_park=(kind!='stage'))
        points=plan(saved,shift_x,dodge_y)[kind]
        with SESSION_LOCK:
            _invalidate(ctx)
            if kind=='stage':
                # Require starting from behind the nominal safe Y line.
                if ctx['position'][1]<ctx['safe_y']:
                    raise T0Error('Stage only from Y at or beyond safe Y; home and park centrally first')
            else:
                if SESSION['stage']!='staged':
                    raise T0Error('First run Approach T0 and inspect its staging position')
                sensor=SESSION['sensor']
                samples=SESSION['samples']
                if (sensor is None or 'empty' not in samples or 'mounted' not in samples
                    or samples['empty']==samples['mounted']):
                    raise T0Error('Carriage switch must be tested in EMPTY and MOUNTED states before pickup/dropoff')
                live=_sensor_value(sensor,ctx['objects'])
                expected=samples['empty' if kind=='pickup' else 'mounted']
                if live!=expected:
                    raise T0Error('T0 sensor not in expected pre-motion state')
                if kind=='dropoff' and SESSION['last_action']!='pickup':
                    raise T0Error('Dropoff requires successful supervised pickup in this session')
                if kind=='pickup' and SESSION['last_action'] not in (None,'dropoff','staged'):
                    raise T0Error('Cannot pick up again until T0 is released')
            # Disarm before any irreversible movement. On failure, a fresh
            # staging test and manual inspection are always required.
            SESSION['stage']=None
        code=_gcode(points,kind)
        _rpc('/printer/gcode/script',{'script':code})
        # Re-evaluate actual position, motor power, and state after motion.
        after=_safe_context(store.read(),require_in_park=True)
        if kind!='stage':
            with SESSION_LOCK:
                sensor=SESSION['sensor']
                samples=SESSION['samples'].copy()
            live=_sensor_value(sensor,after['objects'])
            if live!=samples['mounted' if kind=='pickup' else 'empty']:
                raise T0Error('Sensor did not confirm '+kind+' after motion. Inspect carriage and do not continue.')
        with SESSION_LOCK:
            SESSION.update(stage='staged',last_action=kind,xy=[after['x'],after['safe_y']],
                           path={'shift_x':shift_x,'dodge_y':dodge_y})
        return {'status':'SUPERVISED_T0_'+kind.upper()+'_COMPLETE',
                'position_mm':after['position'],'source_dock_xy_mm':[ctx['x'],ctx['y']],
                'steps':len(points),'sensor_confirmed':kind!='stage',
                'note':'Operator must independently inspect physical T0 engagement. No active-tool or commissioning flags changed.'}
    finally:
        MOVE_LOCK.release()
