"""CXM guarded cold Tool Z runner.

All physical motion is Klipper macro-owned; this module only sequences named,
preflighted macros, verifies live state, and records provisional measurements.
There are NO offset writes, heating, auto-homing, or unattended recovery paths.
"""
from __future__ import annotations
import math
import os
import threading
from statistics import median
from datetime import datetime, timezone
from cxm_native import _native_status, NativeError
from cxm_runtime import _rpc, MOVE_LOCK

class ZAutoError(RuntimeError):
    pass

RANGE_LIMIT = 0.050
REDOCK_LIMIT = 0.050
TARGET_X, TARGET_Y = 195.0, 170.0


def physical_enabled():
    return os.environ.get('CXM_Z_AUTO_ENABLE_PHYSICAL', '') == 'I_ACCEPT_SUPERVISED_COLD_TEST'


def max_commissioned_tool():
    raw = os.environ.get('CXM_Z_AUTO_MAX_TOOL', '0')
    try:
        n = int(raw)
    except ValueError:
        return 0
    return n if 0 <= n <= 11 else 0


def _object_status():
    import urllib.parse
    fields = {
        'toolhead':'homed_axes,position',
        'extruder':'target',
        'heater_bed':'target',
        'cartographer':'touch',
        'gcode_move':'gcode_position',
        'bed_mesh':'mesh_matrix',
        'idle_timeout':'state',
        'print_stats':'state',
    }
    available=set(_rpc('/printer/objects/list').get('objects',[]))
    selected={name:attrs for name,attrs in fields.items() if name in available}
    if 'toolhead' not in selected or 'extruder' not in selected or 'cartographer' not in selected:
        raise ZAutoError('Required live Klipper measurement objects missing')
    query=urllib.parse.urlencode(selected)
    return _rpc('/printer/objects/query?'+query).get('status',{})


def selected_tools(tool_count):
    """Strict, ordered, explicit tool selection. T0 anchors every relative Z run.

    Legacy integer 1..N remains supported; new list supports T0,T5,T8.
    Invalid selections never cause motion or silently add omitted tools.
    """
    if type(tool_count) is int:
        if not 1 <= tool_count <= 12:
            raise ValueError('Select 1–12 tools')
        return list(range(tool_count))
    if type(tool_count) is not list or not 1 <= len(tool_count) <= 12:
        raise ValueError('Select T0 and at least one valid tool')
    if any(type(t) is not int or not 0 <= t < 12 for t in tool_count):
        raise ValueError('Tool IDs must be integers from T0 to T11')
    if tool_count != sorted(set(tool_count)) or tool_count[0] != 0:
        raise ValueError('Select T0 once as reference and unique ascending tools')
    return list(tool_count)


def assess(store, tool_count):
    """No motion; fail closed on any unknown or mismatched condition."""
    snapshot=store.read()
    cfg=snapshot['config']
    available=cfg['globals']['tool_count']
    errors=[]
    try:
        selection=selected_tools(tool_count)
    except ValueError as exc:
        selection=[]
        errors.append(str(exc))
    if any(t>=available for t in selection):
        errors.append('Selected tool is not enabled in saved CXM configuration')
    if any(t>max_commissioned_tool() for t in selection):
        errors.append('Selected tools exceed physical commissioning gate T'+str(max_commissioned_tool()))
    if snapshot.get('migration_required'):
        errors.append('Complete configuration migration first')
    for t in selection:
        if t>=available or t>=len(cfg['tools']):
            continue
        p=cfg['tools'][t]
        if p.get('maintenance_lockout') or not p.get('dock_reference_accepted'):
            errors.append(f'T{t} must have an accepted, unlocked dock')
        else:
            try:
                from cxm_cxchanger import plan
                plan(snapshot,tool=t)
            except (KeyError, ValueError, TypeError) as exc:
                errors.append(f'T{t} dock geometry invalid: {exc}')
    native,test,sensor=_native_status()
    if native.get('ready')!=1 or native.get('fault')!=0:
        errors.append('Native toolchanger must be READY and fault-free')
    if native.get('tool_count')!=available:
        errors.append('Native tool count differs from saved configuration; synchronise geometry')
    if test.get('running'):
        errors.append('Stop the native tool-cycle test first')
    fitted=native.get('current_tool')
    if type(fitted) is not int or fitted < -1 or fitted >= available:
        errors.append('Physical tool identity must be confirmed after Klipper restart')
    if sensor != ('RELEASED' if fitted==-1 else 'PRESSED'):
        errors.append('Sensor disagrees with mounted-tool identity; inspect carriage')
    status=_object_status()
    head=status.get('toolhead',{})
    if not all(axis in head.get('homed_axes','') for axis in 'xyz'):
        errors.append('XYZ must be homed using the proven homing sequence')
    pos=head.get('position')
    if not isinstance(pos,list) or len(pos)<3 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in pos[:3]):
        errors.append('Live XYZ position unavailable')
    else:
        if pos[2]<1.0 or pos[2]>330.0:
            errors.append('Current Z outside validated 1–330 mm staging envelope')
        limit=max((float(p['dock_y'])+float(cfg['globals']['cxm_safe_clearance_y'])
                   for p in cfg['tools'][:available] if p.get('dock_reference_accepted')),default=0.0)
        if pos[1]<limit-0.15:
            errors.append('Carriage is inside dock staging area: do not automatically lift or transfer')
    for key in ('extruder','heater_bed'):
        obj=status.get(key,{})
        if key=='extruder' and obj.get('target') != 0:
            errors.append('Extruder heater target must equal zero')
        if key=='heater_bed' and obj.get('target') not in (None,0):
            errors.append('Bed heater target must equal zero')
    cart=status.get('cartographer',{})
    touch=cart.get('touch') if isinstance(cart,dict) else None
    if not isinstance(touch,dict) or not touch.get('current_model'):
        errors.append('Cartographer Touch calibration model not active')
    if status.get('idle_timeout',{}).get('state') not in ('Idle','Ready'):
        errors.append('Printer not idle')
    if status.get('print_stats',{}).get('state') not in (None,'standby','complete','cancelled','error'):
        errors.append('Active print in progress')
    if any(len(row) > 0 for row in (status.get('bed_mesh', {}).get('mesh_matrix') or [])):
        errors.append('Clear active bed mesh first')
    if physical_enabled():
        try:
            available_cmds=_rpc('/printer/gcode/help')
            for command in ('CXM_Z_AUTO_LIFT','CXM_Z_AUTO_POSITION','CXM_Z_AUTO_TOUCH','CXM_SELECT_TOOL'):
                if command not in available_cmds:
                    errors.append('Missing Klipper command: '+command)
        except Exception as exc:
            errors.append('Unable to verify installed Klipper commands: '+type(exc).__name__)
    if not physical_enabled():
        errors.append('Hardware execution disabled; commissioned release has not been explicitly armed')
    return {'ready':not errors,'blockers':errors,'mode':'COLD_0C_TARGETS',
            'revision':snapshot['revision'],'tool_count':len(selection), 'selected_tools':selection,
            'native_tool':fitted,'sensor':sensor,'position':pos,
            'enabled':physical_enabled(),'max_tool':max_commissioned_tool(),
            'limits_mm':{'range':RANGE_LIMIT,'redock_drift':REDOCK_LIMIT},
            'warnings':['Disconnected thermistor cannot prove nozzle is cold',
                        'Unverified Z-offset sign: results are provisional and NEVER applied',
                        'Physical Z gantry movement and emergency stop require operator supervision']}


def calculate(trials, mode='verify_redock'):
    """Evaluate exactly one quick three-Touch set OR two full redock sets.

    Quick mode deliberately cannot claim redock accuracy: those fields remain None.
    Neither mode saves or applies offsets, and both require T0 as reference.
    """
    if mode not in ('quick', 'verify_redock'):
        raise ValueError('Unknown Z calibration mode')
    if not isinstance(trials,dict) or not trials or 'T0' not in trials:
        raise ValueError('T0 required')
    required_sets=1 if mode=='quick' else 2
    out={}
    for key,sets in trials.items():
        if not isinstance(sets,list) or len(sets)!=required_sets or any(
            not isinstance(values,list) or len(values)!=3 for values in sets
        ):
            raise ValueError(key+': expected '+str(required_sets)+' set(s) of 3 Touch readings')
        if any(not isinstance(v,(float,int)) or isinstance(v,bool) or not math.isfinite(v)
               for trial in sets for v in trial):
            raise ValueError('Invalid Touch reading')
        first=sets[0]
        a=float(median(first))
        r1=float(max(first)-min(first))
        if mode=='verify_redock':
            second=sets[1]
            b=float(median(second))
            r2=float(max(second)-min(second))
            delta=abs(b-a)
            passed=r1<=RANGE_LIMIT and r2<=RANGE_LIMIT and delta<=REDOCK_LIMIT
        else:
            second=[]
            b=None
            r2=None
            delta=None
            passed=r1<=RANGE_LIMIT
        contact=a if b is None else b
        out[key]={
            'contact_mm':contact,'before_mm':a,'after_mm':b,
            'range_before_mm':r1,'range_after_mm':r2,'redock_drift_mm':delta,
            'redock_verified':mode=='verify_redock',
            'passed':passed,'samples_before':list(first),'samples_after':list(second)
        }
    ref=out['T0']['contact_mm']
    for key,v in out.items():
        v['relative_to_t0_mm']=0.0 if key=='T0' else v['contact_mm']-ref
    return {'passed':all(x['passed'] for x in out.values()),'tools':out,
            'measurement_mode':mode,'redock_verified':mode=='verify_redock',
            't0_contact_mm':ref,'offsets_applied':False,'offsets_saved':False,
            'status':('PROVISIONAL_QUICK_MEASUREMENTS_NOT_APPLIED' if mode=='quick'
                      else 'PROVISIONAL_MEASUREMENTS_NOT_APPLIED')}


class Controller:
    def __init__(self):
        self.mutex=threading.Lock()
        self.busy=False
        self.stop_event=threading.Event()
        self.data={'state':'idle','step':'','error':None,'measurements':{},'result':None}

    def status(self):
        with self.mutex:
            return dict(self.data, running=self.busy, stop_requested=self.stop_event.is_set(),
                        physical_enabled=physical_enabled(),max_commissioned_tool=max_commissioned_tool())

    def reset_idle_history(self):
        """Discard provisional in-memory Tool Z readings during a full CXM reset."""
        with self.mutex:
            if self.busy:
                raise ZAutoError('Cannot erase Tool Z history during active calibration')
            self.stop_event.clear()
            self.data={'state':'idle','step':'','error':None,
                       'measurements':{},'result':None}
            return {'history_reset':True}

    def _set(self,**kw):
        with self.mutex:
            self.data.update(kw)

    def stop(self):
        with self.mutex:
            if not self.busy: raise ZAutoError('No Z calibration is running')
            self.stop_event.set()
        return {'stop_requested':True,'notice':'Stop after current Klipper command; use physical emergency stop for immediate hazard'}

    def start(self,store,tool_count,expected_revision,acknowledgement,mode='quick'):
        if mode not in ('quick','verify_redock'):
            raise ZAutoError('Select Quick or Full redock verification mode')
        if acknowledgement != 'I_VERIFIED_COLD_NOZZLE_BED_LATCHES_DOCKS_AND_SUPERVISE_MOTION':
            raise ZAutoError('Inspect nozzle/bed temperature, docks, hotend latch and gantry before starting')
        if not MOVE_LOCK.acquire(blocking=False):
            raise ZAutoError('Another CXM motion operation is in progress')
        try:
            check=assess(store,tool_count)
            if check['revision']!=expected_revision:
                raise ZAutoError('Configuration revision changed; refresh the page')
            if not check['ready']:
                raise ZAutoError('; '.join(check['blockers']))
            with self.mutex:
                if self.busy: raise ZAutoError('Tool Z already running')
                self.busy=True
                self.stop_event.clear()
                self.data={'state':'running','step':'Beginning T0','error':None,
                           'measurements':{},'result':None,'tool_count':len(check['selected_tools']),
                           'selected_tools':check['selected_tools'],'measurement_mode':mode}
            thread=threading.Thread(target=self._run,args=(store,check['selected_tools'],expected_revision,mode),daemon=True)
            thread.start()
            return {'started':True,'mode':'cold','measurement_mode':mode,
                    'selected_tools':check['selected_tools'],'tool_count':len(check['selected_tools'])}
        except Exception:
            MOVE_LOCK.release()
            raise

    def _assert_live(self,store,rev,expected_tool):
        if self.stop_event.is_set():
            raise ZAutoError('Operator requested stop between Klipper actions')
        if store.read()['revision']!=rev:
            raise ZAutoError('Saved configuration changed during measurement')
        n,test,sensor=_native_status()
        if (n.get('ready')!=1 or n.get('fault')!=0 or n.get('current_tool')!=expected_tool
            or test.get('running') or sensor != ('RELEASED' if expected_tool==-1 else 'PRESSED')):
            raise ZAutoError(f'Carriage identity/sensor/fault mismatch after T{expected_tool}; inspect before recovery')
        obj=_object_status()
        if not all(c in obj.get('toolhead',{}).get('homed_axes','') for c in 'xyz'):
            raise ZAutoError('Homing lost during calibration')
        if obj.get('extruder',{}).get('target')!=0 or obj.get('heater_bed',{}).get('target') not in (None,0):
            raise ZAutoError('Heater target changed during cold test')
        if obj.get('print_stats',{}).get('state') not in (None,'standby','complete','cancelled','error'):
            raise ZAutoError('Printing began during Tool Z calibration')
        return obj

    def _command(self,code):
        if self.stop_event.is_set():
            raise ZAutoError('Operator stop requested')
        _rpc('/printer/gcode/script',{'script':code},timeout_s=240)

    def _read_touch(self):
        status=_object_status()
        touch=status.get('cartographer',{}).get('touch',{})
        reading=touch.get('last_z_result') if isinstance(touch,dict) else None
        if isinstance(reading,bool) or not isinstance(reading,(int,float)) or not math.isfinite(reading) or abs(reading)>1.0:
            raise ZAutoError('No finite plausible Cartographer Touch result: stop for investigation')
        return float(reading)

    def _run(self,store,count,rev,mode='quick'):
        captured={}
        try:
            current=_native_status()[0].get('current_tool')
            self._assert_live(store,rev,current)
            for t in selected_tools(count):
                name='T'+str(t)
                self._set(step=f'{name}: lifting for transfer')
                self._command('CXM_Z_AUTO_LIFT')
                self._assert_live(store,rev,current)
                if current!=t:
                    self._set(step=f'{name}: automatic pickup')
                    self._command(f'CXM_SELECT_TOOL TOOL={t}')
                    current=t
                    self._assert_live(store,rev,current)
                trials=[]
                trial_count=1 if mode=='quick' else 2
                for trial in range(trial_count):
                    self._set(step=f'{name}: positioning for Touch')
                    self._command(f'CXM_Z_AUTO_POSITION TOOL={t}')
                    self._assert_live(store,rev,t)
                    readings=[]
                    for sample in range(3):
                        label=(f'{name}: Touch reading {sample+1}/3' if mode=='quick'
                               else f'{name}: Touch trial {trial+1}/2 reading {sample+1}/3')
                        self._set(step=label)
                        self._command(f'CXM_Z_AUTO_TOUCH TOOL={t} CONFIRM=COLD_TEST')
                        self._assert_live(store,rev,t)
                        readings.append(self._read_touch())
                    trials.append(readings)
                    captured[name]=trials
                    self._set(measurements=dict(captured))
                    if mode=='verify_redock' and trial==0:
                        self._set(step=f'{name}: redock and reseat verification')
                        self._command('CXM_Z_AUTO_LIFT')
                        self._assert_live(store,rev,t)
                        self._command('CXM_SELECT_TOOL TOOL=-1')
                        current=-1
                        self._assert_live(store,rev,current)
                        self._command(f'CXM_SELECT_TOOL TOOL={t}')
                        current=t
                        self._assert_live(store,rev,current)
                # Only evaluate the checks actually measured in the selected mode.
                partial=calculate({'T0':trials} if t==0 else {'T0':captured['T0'],name:trials},mode=mode)
                if not partial['tools'][name]['passed']:
                    detail=('Touch range' if mode=='quick' else 'Touch range or redock drift')
                    raise ZAutoError(name+' '+detail+' outside limits; no offsets saved')
            self._set(step='Returning last tool to dock')
            self._command('CXM_Z_AUTO_LIFT')
            self._assert_live(store,rev,current)
            self._command('CXM_SELECT_TOOL TOOL=-1')
            self._assert_live(store,rev,-1)
            results=calculate(captured,mode=mode)
            self._set(state='complete' if results['passed'] else 'review',step='Finished; results are provisional',result=results)
        except Exception as exc:
            # Do not move or infer tool identity after error. Stop at current hardware state.
            self._set(state='stopped_error',error=str(exc)[:600],step='Inspect printer; no automatic recovery')
        finally:
            with self.mutex:self.busy=False
            MOVE_LOCK.release()

CONTROLLER=Controller()
