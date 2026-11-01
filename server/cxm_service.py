"""Loopback-only CXM configuration API (web access is proxied by local Nginx)."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import threading
import time
import urllib.error
import urllib.request
from cxm_config import Store

MAX_BODY = 4096


def printer_safe():
    """Only change disk settings when no print can be active."""
    try:
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/info', timeout=2) as r:
            info = json.load(r)['result']
        if info['state'] != 'ready':
            # Klipper cannot execute motion when halted/not configured.
            return True
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
    server_version = 'CXMConfig/0.2'
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
            elif self.path == '/v1/health':
                self.output(200,{'ok':True,'version':'0.2.0','loopback_only':True})
            else:
                self.output(404,{'error':'Not found'})
        except (OSError, ValueError, SyntaxError) as e:
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
            if self.path not in ('/v1/setting','/v1/rollback'):
                self.output(404,{'error':'Not found'})
                return
            if not printer_safe():
                self.output(409,{'error':'Klipper status not confirmed idle/halted; save blocked'})
                return
            if self.path=='/v1/setting':
                if set(body) != {'tool','key','value','expected_revision'}:
                    raise ValueError('Unexpected setting parameters')
                result=self.server.store.set_value(**body)
            else:
                if set(body) != {'name','expected_revision'}:
                    raise ValueError('Unexpected rollback parameters')
                result=self.server.store.rollback(**body)
            self.output(200,result)
        except (ValueError,TypeError,KeyError,SyntaxError) as e:
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
    watched=[Path(__file__),Path(__file__).with_name('cxm_config.py')]
    before=[p.stat().st_mtime_ns for p in watched]
    def monitor_updates():
        while True:
            time.sleep(3)
            try:
                if [p.stat().st_mtime_ns for p in watched] != before:
                    os._exit(1)
            except OSError:
                os._exit(1)
    threading.Thread(target=monitor_updates,daemon=True).start()
    print('CXM config backend ready at 127.0.0.1:',a.port,flush=True)
    server.serve_forever()
if __name__=='__main__':
    main()

