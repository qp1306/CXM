#!/usr/bin/env python3
"""CXM config API bootstrap and safe Nginx timeout upgrade. Read-only preflight by default."""
import argparse
import datetime
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import os
import sys

PROXY = '''# CXM v0.2 config API — loopback service, private LAN access only
location /cxm/api/ {
    allow 127.0.0.1;
    allow 10.0.0.0/8;
    allow 172.16.0.0/12;
    allow 192.168.0.0/16;
    deny all;
    proxy_pass http://127.0.0.1:8765/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 2s;
    proxy_read_timeout 150s;
}
'''
# Older CXM bootstrap releases used a six-second gateway timeout. Homing
# legitimately runs longer than that; the Lineux service allows 125 seconds.
LEGACY_PROXY = PROXY.replace('proxy_read_timeout 150s;', 'proxy_read_timeout 6s;')

def updated_proxy_snippet(current):
    """Upgrade only the exact historic CXM block; leave other Nginx config intact."""
    if current.count(PROXY.strip()) == 1:
        return current
    if current.count(LEGACY_PROXY.strip()) == 1:
        return current.replace(LEGACY_PROXY.strip(), PROXY.strip(), 1)
    if 'location /cxm/api/' in current:
        raise RuntimeError('Unrecognised or duplicated /cxm/api/ configuration; refusing to overwrite')
    return PROXY+'\n'+current

def cmd(*args):
    return subprocess.run([str(a) for a in args],check=True,text=True,
                          capture_output=True,timeout=35).stdout.strip()

def install_file(dest, content, sudo=False):
    with tempfile.NamedTemporaryFile('w',delete=False,encoding='utf-8') as f:
        f.write(content)
        temp=f.name
    try:
        if sudo:
            cmd('sudo','install','-m','644',temp,dest)
        else:
            # Write in destination directory for filesystem-safe atomic replace.
            target=Path(dest)
            with tempfile.NamedTemporaryFile('w',dir=target.parent,delete=False,encoding='utf-8') as w:
                w.write(content)
                w.flush(); os.fsync(w.fileno())
                wpath=Path(w.name)
            try:
                os.replace(wpath,target)
            finally:
                wpath.unlink(missing_ok=True)
    finally:
        Path(temp).unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description='CXM config API bootstrap and gateway timeout repair (dry-run by default)')
    p.add_argument('--apply',action='store_true')
    p.add_argument('--config-dir',default=str(Path.home()/'printer_data/config'))
    p.add_argument('--repo',default=str(Path.home()/'CXM'))
    p.add_argument('--nginx-snippet',default='/etc/nginx/snippets/cxm.conf')
    a=p.parse_args()
    repo=Path(a.repo).expanduser().resolve()
    config=Path(a.config_dir).expanduser().resolve()
    snippet=Path(a.nginx_snippet)
    unit=Path('/etc/systemd/system/cxm-config.service')
    if not config.is_dir() or not (config/'moonraker.conf').is_file():
        raise RuntimeError('Moonraker config folder not found')
    if not (repo/'server/cxm_service.py').is_file() or not (repo/'server/cxm_config.py').is_file():
        raise RuntimeError('CXM V0.2 source files not found. Update CXM via webpage first.')
    if not snippet.is_file():
        raise RuntimeError('CXM Nginx snippet not found; install V0.1 first')
    current=snippet.read_text(encoding='utf-8')
    new_snippet=updated_proxy_snippet(current)
    python=sys.executable if Path(sys.executable).is_file() else '/usr/bin/python3'
    unit_text=(f'[Unit]\nDescription=CXM Configuration Manager\nAfter=network.target moonraker.service\n\n'
               f'[Service]\nType=simple\nUser={cmd("id","-un")}\n'
               f'WorkingDirectory={repo}\nExecStart={python} {repo}/server/cxm_service.py --config-dir {config}\n'
               'Restart=always\nRestartSec=3\nNoNewPrivileges=true\nPrivateTmp=true\n'
               'ProtectSystem=full\nReadWritePaths='+str(config)+'\n\n'
               '[Install]\nWantedBy=multi-user.target\n')
    if unit.exists() and unit.read_text(encoding='utf-8') != unit_text:
        raise RuntimeError('An unexpected cxm-config.service already exists; refusing to replace')
    print('Config storage: ',config/'CXM_variables.cfg')
    print('Python service: ',unit)
    print('Nginx proxy: ',snippet)
    print('Gateway read timeout: 150s (CXM motion RPC up to 125s)')
    print('Nginx change: ', 'required' if new_snippet != current else 'already current')
    print('Klipper restart: not required')
    if not a.apply:
        print('DRY RUN only. Use --apply after reviewing.')
        return
    # Read/write check before beginning privileged work.
    from importlib.util import spec_from_file_location, module_from_spec
    spec=spec_from_file_location('cxm_config',repo/'server/cxm_config.py')
    module=module_from_spec(spec);spec.loader.exec_module(module)
    store=module.Store(config)
    initialized=store.initialize()
    print('Configuration:', 'created' if initialized['created'] else 'preserved')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backups=[]
    try:
        if new_snippet != current:
            bak=snippet.with_name(snippet.name+'.before-cxm02-'+stamp)
            cmd('sudo','cp',snippet,bak)
            backups.append((snippet,bak))
            install_file(snippet,new_snippet,sudo=True)
        if not unit.exists():
            install_file(unit,unit_text,sudo=True)
        cmd('sudo','nginx','-t')
        cmd('sudo','systemctl','daemon-reload')
        cmd('sudo','systemctl','enable','--now','cxm-config.service')
        cmd('sudo','systemctl','restart','cxm-config.service')
        cmd('sudo','systemctl','reload','nginx')
        print('Installed. Open http://YOUR-PRINTER-IP/cxm/ and select Settings.')
        print('No changes made to printer.cfg or Klipper process.')
    except Exception:
        for dest,bak in reversed(backups):
            try: cmd('sudo','cp',bak,dest)
            except Exception as exc: print('WARNING: restore failed:',exc)
        raise

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('CXM v0.2 bootstrap failed:',exc)
        raise SystemExit(1)
