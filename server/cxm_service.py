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
from cxm_t0 import (status as t0_status, record_sensor as t0_record_sensor,
                    confirm_staging as t0_confirm_staging, T0Error)
from cxm_manual import status as manual_status, jog as manual_jog, capture as manual_capture, ManualDockError
from cxm_native import (status as multi_status, start as multi_start,
                        stop as multi_stop, sync as native_sync,
                        select as native_select, confirm_empty as native_confirm_empty,
                        recover_empty as native_recover_empty, initialize as native_initialize,
                        invalidate_for_config_edit as native_invalidate,
                        NativeError)
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 4096

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
            elif self.path.startswith('/v1/manual/status?'):
                args=parse_qs(urlsplit(self.path).query)
                if set(args)!={'tool'} or len(args['tool'])!=1 or not args['tool'][0].isdigit():
                    raise ValueError('Select a valid motor-on calibration hotend')
                self.output(200,manual_status(int(args['tool'][0]),self.server.store))
            elif self.path == '/v1/health':
                self.output(200,{'ok':True,'version':'0.9.0','loopback_only':True})
            else:
                self.output(404,{'error':'Not found'})
        except (OSError, ValueError, SyntaxError, ManualDockError) as e:
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
            if self.path not in ('/v1/native/initialize','/v1/native/sync','/v1/native/confirm-empty','/v1/native/recover-empty','/v1/native/select','/v1/tools/multi/start','/v1/tools/multi/stop','/v1/tools/auto','/v1/tools/clear-fault','/v1/setting','/v1/offset','/v1/rollback','/v1/dock','/v1/migrate','/v1/manual/jog','/v1/manual/capture','/v1/t0/sensor','/v1/t0/motion','/v1/t0/confirm-stage','/v1/t0/auto','/v1/t0/clear-fault','/v1/t0/cycles','/v1/t0/cycles/stop'):
                self.output(404,{'error':'Not found'})
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
            if self.path == '/v1/native/select':
                if set(body)!={'tool','expected_revision','acknowledgement'} or body['acknowledgement']!='I_CONFIRMED_SELECTED_HOTEND_IDENTITY_AND_FULL_XY_PATH_CLEAR':
                    raise NativeError('Explicit tool identity and full XY path approval required')
                self.output(200,native_select(self.server.store,body['tool'],body['expected_revision']))
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
            if self.path == '/v1/manual/jog':
                if set(body)!={'tool','axis','distance','expected_revision','acknowledgement'}:
                    raise ValueError('Invalid supervised XY jog request')
                self.output(200,manual_jog(store=self.server.store,**body))
                return
            if self.path == '/v1/manual/capture':
                if set(body)!={'tool','expected_revision','acknowledgement'}:
                    raise ValueError('Invalid motor-on XY capture request')
                self.output(200,manual_capture(store=self.server.store,**body))
                return
            if not printer_safe():
                self.output(409,{'error':'Klipper status not confirmed idle/halted; save blocked'})
                return
            # Block stale Klipper geometry before any disk configuration change.
            # Invalidate only when the native macros are actually installed.
            try:
                native_invalidate()
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
        except (ValueError,TypeError,KeyError,SyntaxError,NativeError,ManualDockError) as e:
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
             Path(__file__).with_name('cxm_manual.py'),Path(__file__).with_name('cxm_runtime.py'),
             Path(__file__).with_name('cxm_t0.py'),
             Path(__file__).with_name('cxm_cxchanger.py'),
             Path(__file__).with_name('cxm_tools.py'),
             Path(__file__).with_name('cxm_native.py')]
    before=[p.stat().st_mtime_ns for p in watched]
    def monitor_updates():
        while True:
            time.sleep(3)
            try:
                if [p.stat().st_mtime_ns for p in watched] != before:
                    # Never intentionally interrupt an active multi-tool pass
                    # to reload CXM Python source while a tool may be attached.
                    try:
                        while multi_status(store)['running']:
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

