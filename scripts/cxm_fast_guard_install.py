#!/usr/bin/env python3
"""One-time CXM rapid Klipper macro installer. DRY RUN by default.

Does NOT move printer or restart Klipper. Backups before any edits.
A single intentional Klipper RESTART is required after --apply to load
the new [gcode_macro CXM_FAST_VERIFY] include. This will clear homing.
"""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import os
import re
import shutil
import tempfile

INCLUDE='[include cxm_fast_guard.cfg]'
MACRO='[gcode_macro CXM_FAST_VERIFY]'

def atomic_bytes(path,data):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        tmp=Path(f.name)
        f.write(data);f.flush();os.fsync(f.fileno())
    try:os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)

def plan(repo,printer):
    src=repo/'vendor/cxm/cxm_fast_guard.cfg'
    dest=printer.parent/'cxm_fast_guard.cfg'
    if not src.is_file() or not printer.is_file():
        raise RuntimeError('Missing CXM rapid guard source or printer.cfg')
    raw=printer.read_text('utf-8')
    source=src.read_bytes()
    if source.count(MACRO.encode()) != 1 or source.count(b'[gcode_macro') != 1:
        raise RuntimeError('CXM rapid guard source malformed')
    if len(source)>20000:
        raise RuntimeError('Unexpectedly large guard source')
    if len(re.findall(r'(?m)^\\s*\\[include cxm_fast_guard\\.cfg\\]\\s*$',raw))>1:
        raise RuntimeError('Duplicate CXM rapid include')
    if MACRO in raw:
        raise RuntimeError('CXM_FAST_VERIFY already defined in printer.cfg')
    if dest.exists() and dest.read_bytes()!=source:
        raise RuntimeError('Existing rapid guard differs: manual review required')
    included=bool(re.search(r'(?m)^\\s*\\[include cxm_fast_guard\\.cfg\\]\\s*$',raw))
    if not included:
        # Never write inside auto-generated SAVE_CONFIG footer.
        marker='#*# <---------------------- SAVE_CONFIG'
        if marker in raw:
            updated=raw.replace(marker,INCLUDE+'\\n\\n'+marker,1)
        else:
            updated=raw.rstrip()+'\\n\\n'+INCLUDE+'\\n'
    else:updated=raw
    return src,dest,source,updated,included

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--apply',action='store_true')
    p.add_argument('--repo',type=Path,default=Path.home()/'CXM')
    p.add_argument('--printer-config',type=Path,default=Path.home()/'printer_data/config/printer.cfg')
    a=p.parse_args()
    repo=a.repo.expanduser().resolve()
    printer=a.printer_config.expanduser().resolve()
    src,dest,source,updated,included=plan(repo,printer)
    print('Printer configuration:',printer)
    print('Macro source:',src)
    print('Installed include:',dest,'(same content)' if dest.exists() else '(new)')
    print('Include:', 'already present' if included else 'to be added')
    print('No motion; no restart; no changes to existing CXM dock calibration.')
    if not a.apply:
        print('DRY RUN. Review, then repeat with --apply.')
        return
    if dest.exists() and included and updated==printer.read_text('utf-8'):
        print('Already installed; no changes needed.')
        return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=printer.parent/'cxm_backups'/('rapid-'+stamp)
    backup.mkdir(parents=True,exist_ok=False)
    shutil.copy2(printer,backup/'printer.cfg')
    if dest.exists():shutil.copy2(dest,backup/'cxm_fast_guard.cfg')
    created=False
    try:
        if not dest.exists():
            atomic_bytes(dest,source);created=True
        if updated!=printer.read_text('utf-8'):
            atomic_bytes(printer,updated.encode('utf-8'))
    except BaseException:
        atomic_bytes(printer,(backup/'printer.cfg').read_bytes())
        if created:dest.unlink(missing_ok=True)
        print('Restored printer.cfg. Review any partially installed file.')
        raise
    print('Installed. BACKUPS:',backup)
    print('When all tools are safely docked and carriage EMPTY,')
    print('perform ONE Klipper RESTART in Mainsail and rehome XYZ.')
    print('Do not run the rapid test until CXM reports it available.')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError) as e:
        print('CXM rapid installer REFUSED:',e)
        raise SystemExit(2)
