"""Loopback-only CXM configuration API (web access is proxied by local Nginx)."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import re
import threading
import time
import urllib.error
import urllib.request
from cxm_config import Store
from cxm_runtime import MOVE_LOCK, _rpc
from cxm_jog_upgrade import inspect as inspect_jog_upgrade, apply as apply_jog_upgrade, JogUpgradeError
from cxm_dock_verify_install import inspect as inspect_dock_verify_install, apply as apply_dock_verify_install, DockVerifyInstallError
from cxm_dock_verify import status as dock_verify_status, roundtrip as dock_verify_roundtrip, adjust as dock_verify_adjust, save as dock_verify_save
from cxm_cxchanger import plan
from cxm_t0 import (status as t0_status, record_sensor as t0_record_sensor,
                    confirm_staging as t0_confirm_staging, T0Error)
from cxm_manual import status as manual_status, jog as manual_jog, capture as manual_capture, save as manual_save, ManualDockError
from cxm_dock_simple import status as simple_status, home as simple_home, enable as simple_enable, jog as simple_jog, test as simple_test, save as simple_save, DockSimpleError
from cxm_native import (camera_action, status as multi_status, start as multi_start,
                        stop as multi_stop, sync as native_sync,
                        select as native_select, simple_change as native_simple_change,
                        calibration_release as native_calibration_release,
                        confirm_empty as native_confirm_empty,
                        recover_empty as native_recover_empty, clear_all as native_clear_all,
                        reset_commissioning as native_reset_commissioning,
                        initialize as native_initialize,
                        invalidate_for_config_edit as native_invalidate,
                        NativeError)
from urllib.parse import parse_qs, urlsplit
from cxm_z_auto import CONTROLLER as zauto_controller, assess as zauto_assess, ZAutoError
from cxm_z_prepare import prepare as zauto_prepare, in_progress as zauto_preparing, ACK as ZAUTO_PREPARE_ACK

MAX_BODY = 4096

def parse_z_tool_query(raw):
    """GET ?count=3 (legacy) or ?tools=0,5,8, not both."""
    params=parse_qs(urlsplit(raw).query)
    if set(params)=={'count'} and len(params['count'])==1 and params['count'][0].isdigit():
        return int(params['count'][0])
    if set(params)=={'tools'} and len(params['tools'])==1:
        parts=params['tools'][0].split(',')
        if parts and all(re.fullmatch(r'(?:[0-9]|1[01])',p) for p in parts):
            return [int(x) for x in parts]
    raise ValueError('Provide count=N or tools=0,5,8; T0 is required')


def fine_adjust_x(store, tool, hundredths, expected_revision):
    snapshot = store.read()
    if snapshot['revision'] != expected_revision:
        raise RuntimeError('Dock settings changed. Refresh and review the adjustment.')
    if type(hundredths) is not int or not 1 <= abs(hundredths) <= 100:
        raise ValueError('Choose an X correction from 0.01 to 1.00 mm in either direction')
    if type(tool) is not int or not 0 <= tool < snapshot['config']['globals']['tool_count']:
        raise ValueError('Select a configured hotend')
    if tool == 1:
        raise ValueError('Revision 6 requires the measured T1 entry coordinates')
    entry = snapshot['config']['tools'][tool]
    if snapshot['migration_required'] or entry['maintenance_lockout'] or not entry['dock_reference_accepted']:
        raise ValueError('An accepted, unlocked dock is required')
    entry['dock_x'] = round(entry['dock_x'] + hundredths / 100, 5)
    geometry = plan(snapshot, tool=tool)
    native_invalidate()
    return store.save_dock(tool, geometry['dock_reference_xy'], expected_revision)


def parse_proc_start_ticks(raw, expected_pid):
    """Linux /proc/PID/stat field 22, accounting for spaces in process name."""
    if not isinstance(raw,str) or len(raw)>16384:
        raise ValueError('Invalid process metadata')
    prefix=str(expected_pid)+' ('
    if not raw.startswith(prefix):
        raise ValueError('Process ID mismatch')
    closing=raw.rfind(')')
    if closing<=len(prefix):
        raise ValueError('Invalid /proc stat')
    # After comm and closing parenthesis fields begin at field 3 (state).
    fields=raw[closing+1:].split()
    if len(fields)<20 or not fields[19].isdigit():
        raise ValueError('Missing process start ticks')
    return int(fields[19])

def runtime_evidence():
    """Read-only identity of the running Klipper *process*, not macro state.

    A matching identity before/after an AutoSave establishes that the Klipper
    host process was not replaced. It does not establish that disk settings
    became active, or exclude all in-process reloads.
    """
    result={'available':False,'identity':None,'klipper_state':'unknown',
            'source':'Linux process identity via Moonraker /printer/info',
            'active_in_klipper':False,'limitation':
            'Process continuity does not prove runtime macro updates or exclude in-process reloads.'}
    try:
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/info',timeout=2) as r:
            info=json.load(r)['result']
        result['klipper_state']=str(info.get('state','unknown'))
        pid=info.get('process_id')
        if type(pid) is not int or pid<=1:
            result['reason']='Moonraker did not provide a valid Klipper process_id'
            return result
        stat=Path('/proc') .joinpath(str(pid),'stat').read_text(encoding='utf8')
        ticks=parse_proc_start_ticks(stat,pid)
        boot=Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
        if not re.fullmatch(r'[a-fA-F0-9-]{36}',boot):
            raise ValueError('Invalid kernel boot ID')
        token=hashlib.sha256(f'{boot}:{pid}:{ticks}'.encode('ascii')).hexdigest()[:24]
        result.update({'available':True,'identity':token,'reason':None})
    except (OSError,ValueError,KeyError,TypeError,urllib.error.URLError) as exc:
        result['reason']=type(exc).__name__+': '+str(exc)[:140]
    return result



def printer_safe():
    """Only change disk settings when no print can be active."""
    try:
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/info', timeout=2) as r:
            info = json.load(r)['result']
        if info['state'] != 'ready':
            # Only the two explicitly recognised, primary-MCU startup failures
            # are safe for this hardware-free development instance. Other
            # Klipper failures have unknown machine state and fail closed.
            message = info.get('state_message', '')
            return info['state'] == 'error' and bool(
                re.search(r"""^mcu\s+['"]mcu['"]:\s*Unable to connect(?:\s|$)""", message, re.I)
                or re.search(r"""option\s+['"]?serial['"]?\s+in\s+section\s+['"]?mcu['"]?\s+must\s+be\s+specified""", message, re.I)
            )
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/objects/list', timeout=2) as r:
            objects = json.load(r)['result']['objects']
        query = ['idle_timeout']
        if 'print_stats' in objects:
            query.append('print_stats')
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/objects/query?'+'&'.join(query), timeout=2) as r:
            status = json.load(r)['result']['status']
        if status.get('idle_timeout',{}).get('state') not in ('Idle','Ready'):
            return False
        if 'print_stats' in objects and status.get('print_stats',{}).get('state') not in ('standby','complete','cancelled','error'):
            return False
        return True
    except (KeyError, ValueError, OSError, urllib.error.URLError):
        # Fail closed if Moonraker's state can't be determined.
        return False

class Handler(BaseHTTPRequestHandler):
    server_version = 'CXMConfig/0.6'
    def output(self, code, obj):
        payload=json.dumps(obj, allow_nan=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def do_GET(self):
        try:
            if self.path == '/v1/config':
                self.output(200,self.server.store.read())
            elif self.path == '/v1/history':
                self.output(200,{'backups':self.server.store.history()})
            elif self.path == '/v1/runtime':
                self.output(200,runtime_evidence())
            elif self.path == '/v1/t0/status':
                self.output(200,t0_status(self.server.store))
            elif self.path == '/v1/tools/multi/status' or self.path == '/v1/native/status':
                self.output(200,multi_status(self.server.store))
            elif self.path.startswith('/v1/tools/status?'):
                params=parse_qs(urlsplit(self.path).query)
                if set(params)!={'tool'} or len(params['tool'])!=1 or not params['tool'][0].isdigit():
                    raise ValueError('Select one tool number T1–T11')
                self.output(200,{'tool':int(params['tool'][0]),'ready':False,'blockers':['Native Klipper tool-state interface: use /v1/native/status after accepted geometry sync']})
            elif self.path == '/v1/t0/cycles/status':
                self.output(200,{'running':False,'phase':'retired','error':'Python toolchange cycles removed; use native Klipper cycle'})
            elif self.path.startswith('/v1/dock-simple/status?'):
                params=parse_qs(urlsplit(self.path).query)
                if set(params)!={'tool'} or len(params['tool'])!=1 or not params['tool'][0].isdigit():
                    raise ValueError('Select a Dock XY hotend')
                self.output(200,simple_status(self.server.store,int(params['tool'][0])))
            elif self.path.startswith('/v1/manual/status?'):
                args=parse_qs(urlsplit(self.path).query)
                if set(args)!={'tool'} or len(args['tool'])!=1 or not args['tool'][0].isdigit():
                    raise ValueError('Select a valid motor-on calibration hotend')
                self.output(200,manual_status(int(args['tool'][0]),self.server.store))
            elif self.path == '/v1/z-auto/status':
                self.output(200,zauto_controller.status())
            elif self.path.startswith('/v1/z-auto/preflight?'):
                self.output(200,zauto_assess(self.server.store,parse_z_tool_query(self.path)))
            elif self.path.startswith('/v1/dock-verify/status?'):
                args=parse_qs(urlsplit(self.path).query)
                if set(args)!={'tool'} or len(args['tool'])!=1 or not args['tool'][0].isdigit():
                    raise ValueError('Select a valid dock verification tool')
                self.output(200,dock_verify_status(int(args['tool'][0]),self.server.store))
            elif self.path == '/v1/update/dock-verify/status':
                info=inspect_dock_verify_install(self.server.store.path.parent/'cxm_native_toolchange.cfg')
                q='/printer/objects/query?gcode_macro%20CXM_DOCK_VERIFY_MOVE=version'
                macro=_rpc(q).get('status',{}).get('gcode_macro CXM_DOCK_VERIFY_MOVE',{})
                self.output(200,{'file_state':info['state'],'sha256':info['sha256'],
                                  'live_version':macro.get('version'),
                                  'restart_required':info['state']=='installed' and macro.get('version')!=1})
            elif self.path == '/v1/update/jog/status':
                info=inspect_jog_upgrade(self.server.store.path.parent / 'cxm_native_toolchange.cfg')
                query='/printer/objects/query?gcode_macro%20_CXM_NATIVE=jog_revision'
                native=_rpc(query).get('status',{}).get('gcode_macro _CXM_NATIVE',{})
                self.output(200,{'file_state':info['state'],'sha256':info['sha256'],
                                 'live_revision':native.get('jog_revision'),
                                 'restart_required':info['state']=='installed' and native.get('jog_revision')!=2})
            elif self.path == '/v1/health':
                self.output(200,{'ok':True,'version':'0.9.0','loopback_only':True})
            else:
                self.output(404,{'error':'Not found'})
        except (OSError, ValueError, SyntaxError, ManualDockError, DockSimpleError, JogUpgradeError, DockVerifyInstallError) as e:
            self.output(503,{'error':str(e)})
    def do_POST(self):
        # No CORS, strict same-origin and custom header to prevent cross-site form submits.
        host=self.headers.get('Host','')
        proto=self.headers.get('X-Forwarded-Proto','http')
        if (not host or self.headers.get('Origin') != f'{proto}://{host}'
            or self.headers.get('X-Requested-With') != 'CXM'):
            self.output(403,{'error':'Same-origin CXM request required'})
            return
        if self.headers.get('Content-Type','').split(';',1)[0].strip() != 'application/json':
            self.output(415,{'error':'Expected JSON'})
            return
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 1 <= length <= MAX_BODY:
                self.output(413,{'error':'Invalid request size'})
                return
            body=json.loads(self.rfile.read(length))
            if type(body) is not dict:
                raise ValueError('Invalid request')
            if self.path not in ('/v1/z-auto/start','/v1/z-auto/stop','/v1/z-auto/prepare','/v1/native/camera','/v1/native/initialize','/v1/native/sync','/v1/native/confirm-empty','/v1/native/recover-empty','/v1/native/clear-all','/v1/commissioning/reset','/v1/native/select','/v1/native/simple-change','/v1/native/calibration-release','/v1/tools/multi/start','/v1/tools/multi/stop','/v1/tools/auto','/v1/tools/clear-fault','/v1/setting','/v1/offset','/v1/rollback','/v1/dock/fine-x','/v1/dock','/v1/migrate','/v1/dock-simple/home','/v1/dock-simple/enable','/v1/dock-simple/jog','/v1/dock-simple/test','/v1/dock-simple/save','/v1/manual/jog','/v1/manual/capture','/v1/manual/save','/v1/dock-verify/roundtrip','/v1/dock-verify/adjust','/v1/dock-verify/save','/v1/update/dock-verify/apply','/v1/update/jog/apply','/v1/t0/sensor','/v1/t0/motion','/v1/t0/confirm-stage','/v1/t0/auto','/v1/t0/clear-fault','/v1/t0/cycles','/v1/t0/cycles/stop'):
                self.output(404,{'error':'Not found'})
                return
            if self.path == '/v1/update/dock-verify/apply':
                if set(body)!={'sha256','acknowledgement'} or body['acknowledgement']!='I_INSPECTED_EMPTY_CARRIAGE_AND_STOPPED_ALL_TESTS':
                    raise DockVerifyInstallError('Confirm carriage EMPTY and printer idle')
                if type(body['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',body['sha256']):
                    raise DockVerifyInstallError('Invalid install fingerprint')
                if not printer_safe() or zauto_controller.status()['running']:
                    raise DockVerifyInstallError('Printer must be ready and idle')
                if not MOVE_LOCK.acquire(blocking=False):
                    raise DockVerifyInstallError('Another CXM operation is running')
                try:
                    q='/printer/objects/query?gcode_button%20cxm_tool_detect=state&gcode_macro%20_CXM_TEST_STATE=running'
                    state=_rpc(q).get('status',{})
                    if state.get('gcode_button cxm_tool_detect',{}).get('state')!='RELEASED':
                        raise DockVerifyInstallError('Carriage must report RELEASED before installation')
                    if state.get('gcode_macro _CXM_TEST_STATE',{}).get('running')!=0:
                        raise DockVerifyInstallError('Native tool test is running')
                    target=self.server.store.path.parent/'cxm_native_toolchange.cfg'
                    self.output(200,apply_dock_verify_install(target,body['sha256']))
                finally:
                    MOVE_LOCK.release()
                return
            if self.path == '/v1/update/jog/apply':
                if set(body)!={'sha256','acknowledgement'} or body['acknowledgement']!='I_INSPECTED_EMPTY_CARRIAGE_AND_STOPPED_ALL_TESTS':
                    raise JogUpgradeError('Confirm physically EMPTY carriage before updating Klipper')
                if type(body['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',body['sha256']):
                    raise JogUpgradeError('Invalid reviewed native macro fingerprint')
                if not printer_safe() or zauto_controller.status()['running']:
                    raise JogUpgradeError('Printer must be ready and idle; no active calibration')
                if not MOVE_LOCK.acquire(blocking=False):
                    raise JogUpgradeError('Another CXM motion or configuration operation is active')
                try:
                    q='/printer/objects/query?gcode_button%20cxm_tool_detect=state&gcode_macro%20_CXM_TEST_STATE=running'
                    state=_rpc(q).get('status',{})
                    if state.get('gcode_button cxm_tool_detect',{}).get('state')!='RELEASED':
                        raise JogUpgradeError('Carriage sensor not RELEASED; remove tool and inspect')
                    if state.get('gcode_macro _CXM_TEST_STATE',{}).get('running')!=0:
                        raise JogUpgradeError('Native tool test active; update refused')
                    target=self.server.store.path.parent / 'cxm_native_toolchange.cfg'
                    self.output(200,apply_jog_upgrade(target,body['sha256']))
                finally:
                    MOVE_LOCK.release()
                return
            if self.path == '/v1/z-auto/stop':
                if body != {'acknowledgement':'STOP_AFTER_CURRENT_COMMAND'}:
                    raise ZAutoError('Explicit stop acknowledgement required')
                self.output(200,zauto_controller.stop())
                return
            if zauto_controller.status()['running']:
                raise ZAutoError('Tool Z calibration active: other CXM actions are locked')
            if zauto_preparing() and self.path != '/v1/z-auto/prepare':
                raise ZAutoError('Tool Z preparation in progress; other CXM actions are locked')
            if self.path == '/v1/z-auto/prepare':
                if set(body) not in ({'tool_count','expected_revision','acknowledgement'},
                                     {'tools','expected_revision','acknowledgement'}):
                    raise ValueError('Invalid Tool Z preparation request')
                if body['acknowledgement'] != ZAUTO_PREPARE_ACK:
                    raise ZAutoError('Physical EMPTY/cold/homing supervision acknowledgement required')
                if not printer_safe():
                    raise ZAutoError('Printer must be safely idle before Tool Z preparation')
                self.output(200,zauto_prepare(
                    self.server.store,body['expected_revision'],body.get('tools',body.get('tool_count')),
                    body['acknowledgement'],printer_safe))
                return
            if self.path == '/v1/z-auto/start':
                keys=set(body)
                basic=({'tool_count','expected_revision','acknowledgement'},
                       {'tools','expected_revision','acknowledgement'})
                if keys not in (*basic, *(k|{'mode'} for k in basic)):
                    raise ValueError('Invalid Z calibration request')
                if not printer_safe():
                    raise ZAutoError('Printer is not confirmed safely idle')
                self.output(200,zauto_controller.start(
                    self.server.store,tool_count=body.get('tools',body.get('tool_count')),
                    expected_revision=body['expected_revision'],
                    acknowledgement=body['acknowledgement'],mode=body.get('mode','quick')))
                return
            if self.path == '/v1/native/camera':
                if set(body) != {'action','tool','mounted_tool','expected_revision','token'}:
                    raise ValueError('Invalid camera request')
                if not printer_safe():
                    raise NativeError('Wait for printer motion to finish')
                self.output(200,camera_action(self.server.store,**body))
                return
            if self.path == '/v1/native/initialize':
                if set(body)!={'expected_revision','carriage_tool'}:
                    raise ValueError('Expected saved revision and explicit EMPTY or T0–T11 identity')
                if not printer_safe():
                    raise NativeError('Printer must be idle; no automatic homing or state recovery during prints')
                self.output(200,native_initialize(self.server.store,**body))
                return
            if self.path == '/v1/native/sync':
                if set(body)!={'expected_revision'}:
                    raise ValueError('Expected saved CXM revision for native runtime synchronization')
                if not printer_safe():
                    raise NativeError('Klipper must be safely idle for native geometry synchronization')
                self.output(200,native_sync(self.server.store,**body))
                return
            if self.path == '/v1/native/confirm-empty':
                if set(body)!={'acknowledgement'} or body['acknowledgement']!='I_PHYSICALLY_INSPECTED_EMPTY_CARRIAGE':
                    raise NativeError('Physical empty carriage inspection acknowledgement required')
                self.output(200,native_confirm_empty())
                return
            if self.path == '/v1/native/recover-empty':
                if set(body)!={'acknowledgement'} or body['acknowledgement']!='I_INSPECTED_ALL_DOCKS_AND_CONFIRMED_PHYSICALLY_EMPTY':
                    raise NativeError('Inspect carriage and every affected dock before recovery')
                if not printer_safe():
                    raise NativeError('Klipper not safely IDLE: cannot clear a live/uncertain cycle')
                self.output(200,native_recover_empty())
                return
            if self.path == '/v1/native/clear-all':
                if set(body) != {'expected_revision','acknowledgement'}:
                    raise ValueError('Clear All requires the current saved revision and explicit physical EMPTY inspection')
                if not printer_safe():
                    raise NativeError('Printer not safely IDLE: Clear All blocked')
                self.output(200,native_clear_all(self.server.store,
                    body['expected_revision'], body['acknowledgement']))
                return
            if self.path == '/v1/commissioning/reset':
                if set(body) != {'expected_revision','acknowledgement'}:
                    raise ValueError('Full commissioning reset needs current revision and physical EMPTY approval')
                if not printer_safe():
                    raise NativeError('Printer must be stationary, ready and idle for full commissioning reset')
                self.output(200,native_reset_commissioning(self.server.store,
                    body['expected_revision'], body['acknowledgement']))
                return
            if self.path == '/v1/native/select':
                if set(body)!={'tool','expected_revision','acknowledgement'} or body['acknowledgement']!='I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR':
                    raise NativeError('Explicit tool identity and full XY path approval required')
                self.output(200,native_select(self.server.store,body['tool'],body['expected_revision']))
                return
            if self.path == '/v1/native/simple-change':
                if set(body)!={'tool','mounted_tool','expected_revision'}:
                    raise ValueError('Choose tool, current mounted tool, and revision')
                if not printer_safe():
                    raise NativeError('Printer not idle; toolchange blocked')
                self.output(200,native_simple_change(
                    self.server.store,body['tool'],body['expected_revision'],
                    mounted_tool=body['mounted_tool']))
                return
            if self.path == '/v1/native/calibration-release':
                if set(body)!={'tool','expected_revision','acknowledgement'}:
                    raise ValueError('Expected selected tool, revision and supervised release approval')
                if not printer_safe():
                    raise NativeError('Printer must be safely idle before calibration release')
                self.output(200,native_calibration_release(
                    self.server.store,body['tool'],body['expected_revision'],
                    body['acknowledgement']))
                return
            if self.path == '/v1/tools/multi/start':
                required={'tools','expected_revision','acknowledgement'}
                allowed=required|{'travel_profile','cycles','execution_mode','custom_speeds'}
                if not required.issubset(body) or not set(body).issubset(allowed):
                    raise ValueError('Unexpected multi-tool pass request')
                self.output(200,multi_start(store=self.server.store,**body))
                return
            if self.path == '/v1/tools/multi/stop':
                if set(body) != {'acknowledgement'}:
                    raise ValueError('Unexpected multi-tool stop request')
                self.output(200,multi_stop(**body))
                return
            if self.path == '/v1/tools/auto':
                if set(body) != {'tool','expected_revision','kind','acknowledgement'}:
                    raise ValueError('Unexpected selected-tool motion request')
                raise NativeError('Legacy Python-generated movement removed. Use native /v1/native/select with accepted geometry sync')
                return
            if self.path == '/v1/tools/clear-fault':
                if set(body) != {'tool','expected_revision','acknowledgement'}:
                    raise ValueError('Unexpected selected-tool fault request')
                raise NativeError('Legacy Python tool fault service retired; inspect machine and use native empty confirmation after appropriate recovery')
                return
            if self.path == '/v1/t0/cycles':
                if set(body) != {'expected_revision','cycles','acknowledgement'}:
                    raise ValueError('Unexpected T0 repeat-cycle request')
                raise NativeError('Legacy Python T0 repeat motion removed. Use native two-tool Klipper cycle')
                return
            if self.path == '/v1/t0/cycles/stop':
                if set(body) != {'acknowledgement'}:
                    raise ValueError('Unexpected T0 stop request')
                raise NativeError('Legacy Python T0 stop retired. Use native Klipper stop')
                return
            if self.path == '/v1/t0/auto':
                if set(body) != {'expected_revision','kind','acknowledgement'}:
                    raise ValueError('Unexpected T0 auto-toolchange request')
                raise NativeError('Legacy Python T0 toolchange removed. Use native /v1/native/select')
                return
            if self.path == '/v1/t0/clear-fault':
                if set(body) != {'expected_revision','acknowledgement'}:
                    raise ValueError('Unexpected T0 fault-clearing request')
                self.output(200,t0_clear_fault(store=self.server.store,**body))
                return
            if self.path == '/v1/t0/confirm-stage':
                if set(body) != {'expected_revision','acknowledgement'}:
                    raise ValueError('Unexpected staging confirmation parameters')
                self.output(200,t0_confirm_staging(store=self.server.store,**body))
                return
            if self.path == '/v1/t0/sensor':
                if set(body) != {'expected_revision','name','condition','acknowledgement'}:
                    raise ValueError('Unexpected T0 sensor request')
                self.output(200,t0_record_sensor(store=self.server.store,**body))
                return
            if self.path == '/v1/t0/motion':
                if set(body) != {'expected_revision','kind','acknowledgement','shift_x','dodge_y'}:
                    raise ValueError('Unexpected T0 motion request')
                raise NativeError('Legacy Python XY tool motion retired; use accepted native CxChanger macros')
                return
            if self.path == '/v1/dock-verify/roundtrip':
                if set(body)!={'tool','expected_revision','acknowledgement'}:
                    raise ValueError('Invalid locked-dock roundtrip request')
                self.output(200,dock_verify_roundtrip(store=self.server.store,**body))
                return
            if self.path == '/v1/dock-verify/adjust':
                if set(body)!={'tool','axis','distance','expected_revision','acknowledgement'}:
                    raise ValueError('Invalid locked-dock XY adjustment')
                self.output(200,dock_verify_adjust(store=self.server.store,**body))
                return
            if self.path == '/v1/dock-verify/save':
                if set(body)!={'tool','expected_revision','acknowledgement'}:
                    raise ValueError('Invalid verified dock save')
                if not printer_safe():
                    raise ManualDockError('Printer not idle; dock save refused')
                self.output(200,dock_verify_save(store=self.server.store,**body))
                return
            if self.path.startswith('/v1/dock-simple/'):
                step=self.path.rsplit('/',1)[-1]
                required={'tool','expected_revision'} | ({'axis','distance'} if step=='jog' else set())
                if set(body)!=required:
                    raise ValueError('Invalid Dock XY request')
                method={'home':simple_home,'enable':simple_enable,'jog':simple_jog,'test':simple_test,'save':simple_save}.get(step)
                if method is None:
                    raise ValueError('Unknown Dock XY action')
                self.output(200,method(self.server.store,**body))
                return
            if self.path == '/v1/manual/jog':
                if set(body)!={'tool','axis','distance','expected_revision','acknowledgement'}:
                    raise ValueError('Invalid supervised XY jog request')
                self.output(200,manual_jog(store=self.server.store,**body))
                return
            if self.path == '/v1/manual/save':
                if set(body)!={'tool','expected_revision','acknowledgement'}:
                    raise ValueError('Select tool, revision and confirmed physical alignment')
                if not printer_safe():
                    raise ManualDockError('Printer not confirmed idle; dock save blocked')
                self.output(200,manual_save(store=self.server.store,**body))
                return
            if self.path == '/v1/manual/capture':
                if set(body)!={'tool','expected_revision','acknowledgement'}:
                    raise ValueError('Invalid motor-on XY capture request')
                self.output(200,manual_capture(store=self.server.store,**body))
                return
            if not printer_safe():
                self.output(409,{'error':'Klipper status not confirmed idle/halted; save blocked'})
                return
            if self.path == '/v1/dock/fine-x':
                if set(body) != {'tool', 'hundredths', 'expected_revision'}:
                    raise ValueError('Expected tool, X correction and saved revision')
                self.output(200, fine_adjust_x(self.server.store, **body))
                return
            # Block stale Klipper geometry before any disk configuration change.
            # Invalidate only when the native macros are actually installed.
            try:
                native_invalidate(
                    permit_mounted_provisional_dock=(self.path == '/v1/dock'),
                    store=self.server.store,
                    tool=body.get('tool') if self.path == '/v1/dock' else None)
            except NativeError as exc:
                if 'Install and load CXM native Klipper macro' not in str(exc):
                    raise
            if self.path=='/v1/setting':
                if set(body) != {'tool','key','value','expected_revision'}:
                    raise ValueError('Unexpected setting parameters')
                result=self.server.store.set_value(**body)
            elif self.path=='/v1/offset':
                if set(body)!={'tool','axes','values','expected_revision'}:
                    raise ValueError('Unexpected offset parameters')
                result=self.server.store.save_offsets(**body)
            elif self.path=='/v1/dock':
                if set(body) not in ({'tool','xy','expected_revision'},
                                     {'tool','xy','expected_revision','raw_xy'}):
                    raise ValueError('Unexpected dock datum parameters')
                result=self.server.store.save_dock(**body)
            elif self.path=='/v1/migrate':
                if set(body) != {'expected_revision'}:
                    raise ValueError('Unexpected migration parameters')
                result=self.server.store.migrate(**body)
            else:
                if set(body) != {'name','expected_revision'}:
                    raise ValueError('Unexpected rollback parameters')
                result=self.server.store.rollback(**body)
            self.output(200,result)
        except (ValueError,TypeError,KeyError,SyntaxError,NativeError,ManualDockError,DockSimpleError,ZAutoError,JogUpgradeError,DockVerifyInstallError) as e:
            self.output(400,{'error':str(e)})
        except RuntimeError as e:
            self.output(409,{'error':str(e)})
        except OSError as e:
            self.output(500,{'error':f'File operation failed: {e}'})

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config-dir',required=True)
    p.add_argument('--port',type=int,default=8765)
    a=p.parse_args()
    store=Store(a.config_dir)
    if not store.path.is_file():
        raise RuntimeError('Initialise configuration using installer before starting service')
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    server.store=store
    # GitHub updates modify repository files but should not need an SSH step.
    # systemd Restart=always relaunches the new Python code after a source change.
    watched=[Path(__file__),Path(__file__).with_name('cxm_config.py'),
             Path(__file__).with_name('cxm_manual.py'),Path(__file__).with_name('cxm_dock_simple.py'),Path(__file__).with_name('cxm_jog_upgrade.py'),Path(__file__).with_name('cxm_dock_verify.py'),Path(__file__).with_name('cxm_dock_verify_install.py'),Path(__file__).with_name('cxm_runtime.py'),
             Path(__file__).with_name('cxm_t0.py'),
             Path(__file__).with_name('cxm_cxchanger.py'),
             Path(__file__).with_name('cxm_tools.py'),
             Path(__file__).with_name('cxm_native.py'),
             Path(__file__).with_name('cxm_z_auto.py'),
             Path(__file__).with_name('cxm_z_prepare.py')]
    before=[p.stat().st_mtime_ns for p in watched]
    def monitor_updates():
        while True:
            time.sleep(3)
            try:
                if [p.stat().st_mtime_ns for p in watched] != before:
                    # Never intentionally interrupt an active multi-tool pass
                    # to reload CXM Python source while a tool may be attached.
                    try:
                        while multi_status(store)['running'] or zauto_controller.status()['running']:
                            time.sleep(1)
                    except (NativeError, OSError, KeyError, ValueError):
                        # Native macro not yet installed or Klipper in reload.
                        # Never block source reload indefinitely.
                        pass
                    os._exit(1)
            except OSError:
                os._exit(1)
    threading.Thread(target=monitor_updates,daemon=True).start()
    print('CXM config backend ready at 127.0.0.1:',a.port,flush=True)
    server.serve_forever()
if __name__=='__main__':
    main()

