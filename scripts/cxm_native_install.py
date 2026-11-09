#!/usr/bin/env python3
"""Install native CXM Klipper macro. Dry-run by default; never moves printer."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import tempfile

INCLUDE='[include cxm_native_toolchange.cfg]'
MACROS=('CXM_SELECT_TOOL','_CXM_NATIVE','_CXM_CHECK_TOOL',
        '_CXM_PICKUP_MOTION','_CXM_RELEASE_MOTION',
        '_CXM_VERIFY','_CXM_COMMIT_STATE','CXM_CONFIRM_EMPTY',
        '_CXM_TEST_STATE','CXM_TEST_START','CXM_TEST_STOP',
        '_CXM_TEST_ADVANCE')
def atomic_write(path,contents):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        tmp=Path(f.name)
        f.write(contents)
        f.flush()
        os.fsync(f.fileno())
    try:os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)


def included_macro_collisions(printer, macro_names):
    """Inspect local [include] graph before adding any native macros."""
    import glob
    visited=set()
    collisions=[]
    def visit(path):
        path=path.resolve()
        if path in visited:return
        visited.add(path)
        if not path.is_file():
            raise RuntimeError('Missing Klipper include: '+str(path))
        raw=path.read_text('utf8')
        for name in macro_names:
            if re.search(r'(?mi)^\s*\[gcode_macro\s+'+re.escape(name)+r'\s*\]\s*
    ap=argparse.ArgumentParser()
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--repo',type=Path,default=Path.home()/'CXM')
    ap.add_argument('--printer-config',type=Path,default=Path.home()/'printer_data/config/printer.cfg')
    a=ap.parse_args()
    source=(a.repo/'vendor/cxm/cxm_native_toolchange.cfg').expanduser().resolve()
    printer=a.printer_config.expanduser().resolve()
    dest=printer.parent/'cxm_native_toolchange.cfg'
    if not source.is_file() or not printer.is_file():
        raise RuntimeError('Source or printer.cfg missing')
    src=source.read_bytes()
    raw=printer.read_text('utf8')
    for name in MACROS:
        signature='[gcode_macro '+name+']'
        if src.count(signature.encode())!=1:
            raise RuntimeError('Macro source does not define exactly one '+name)
    collisions=included_macro_collisions(printer,MACROS)
    if collisions:
        raise RuntimeError('Existing macro definitions collide with native CXM: '+
                           ', '.join(name+' in '+location for name,location in collisions)+
                           '. Back up and migrate those definitions before installation.')
    if src.count(b'[delayed_gcode CXM_NATIVE_TEST_STEP]')!=1:
        raise RuntimeError('Native delayed test controller missing')
    if not re.search(r'(?m)^\s*\[include\s+cxm_fast_guard\.cfg\s*\]\s*$',raw,re.I):
        raise RuntimeError('CXM_FAST_VERIFY guard must already be installed in printer.cfg')
    matches=re.findall(r'(?mi)^\s*\[include cxm_native_toolchange\.cfg\]\s*$',raw)
    if len(matches)>1:
        raise RuntimeError('Duplicate native include found')
    if dest.exists() and dest.read_bytes()!=src:
        raise RuntimeError('Installed native macro differs from source; review manually')
    if dest.exists() and len(matches)==1:
        print('Already installed and identical: no changes')
        return
    if not matches:
        marker='#*# <---------------------- SAVE_CONFIG'
        updated=(raw.replace(marker,INCLUDE+'\n\n'+marker,1)
                 if marker in raw else raw.rstrip()+'\n\n'+INCLUDE+'\n')
    else:
        updated=raw
    print('Source:',source)
    print('Destination:',dest)
    print('Printer configuration:',printer)
    print('New include:',not bool(matches))
    print('No physical motion; no restart performed; native geometry remains INVALID until runtime sync.')
    if not a.apply:
        print('DRY RUN ONLY. Inspect printer.cfg for other includes defining these macros.')
        return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=printer.parent/'cxm_backups'/('native-'+stamp)
    backup.mkdir(parents=True,exist_ok=False)
    shutil.copy2(printer,backup/'printer.cfg')
    if dest.exists():shutil.copy2(dest,backup/'cxm_native_toolchange.cfg')
    created=not dest.exists()
    try:
        if created:atomic_write(dest,src)
        if updated!=raw:atomic_write(printer,updated.encode('utf8'))
    except BaseException:
        atomic_write(printer,(backup/'printer.cfg').read_bytes())
        if created:dest.unlink(missing_ok=True)
        raise
    print('Installed with backups:',backup)
    print('One deliberate Klipper RESTART required after safe physical inspection.')
    print('After restart and G28, sync accepted dock geometry, then confirm physically EMPTY.')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError) as e:
        print('CXM NATIVE INSTALL REFUSED:',e)
        raise SystemExit(2)
,raw):
                collisions.append((name,str(path)))
        for pattern in re.findall(r'(?mi)^\s*\[include\s+([^\]]+)\s*\]\s*
    ap=argparse.ArgumentParser()
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--repo',type=Path,default=Path.home()/'CXM')
    ap.add_argument('--printer-config',type=Path,default=Path.home()/'printer_data/config/printer.cfg')
    a=ap.parse_args()
    source=(a.repo/'vendor/cxm/cxm_native_toolchange.cfg').expanduser().resolve()
    printer=a.printer_config.expanduser().resolve()
    dest=printer.parent/'cxm_native_toolchange.cfg'
    if not source.is_file() or not printer.is_file():
        raise RuntimeError('Source or printer.cfg missing')
    src=source.read_bytes()
    raw=printer.read_text('utf8')
    for name in MACROS:
        signature='[gcode_macro '+name+']'
        if src.count(signature.encode())!=1:
            raise RuntimeError('Macro source does not define exactly one '+name)
        if re.search(r'(?m)^\s*\[gcode_macro\s+'+re.escape(name)+r'\s*\]\s*$',raw,re.I):
            raise RuntimeError('Duplicate native macro in printer.cfg: '+name)
    if src.count(b'[delayed_gcode CXM_NATIVE_TEST_STEP]')!=1:
        raise RuntimeError('Native delayed test controller missing')
    if not re.search(r'(?m)^\s*\[include\s+cxm_fast_guard\.cfg\s*\]\s*$',raw,re.I):
        raise RuntimeError('CXM_FAST_VERIFY guard must already be installed in printer.cfg')
    matches=re.findall(r'(?mi)^\s*\[include cxm_native_toolchange\.cfg\]\s*$',raw)
    if len(matches)>1:
        raise RuntimeError('Duplicate native include found')
    if dest.exists() and dest.read_bytes()!=src:
        raise RuntimeError('Installed native macro differs from source; review manually')
    if dest.exists() and len(matches)==1:
        print('Already installed and identical: no changes')
        return
    if not matches:
        marker='#*# <---------------------- SAVE_CONFIG'
        updated=(raw.replace(marker,INCLUDE+'\n\n'+marker,1)
                 if marker in raw else raw.rstrip()+'\n\n'+INCLUDE+'\n')
    else:
        updated=raw
    print('Source:',source)
    print('Destination:',dest)
    print('Printer configuration:',printer)
    print('New include:',not bool(matches))
    print('No physical motion; no restart performed; native geometry remains INVALID until runtime sync.')
    if not a.apply:
        print('DRY RUN ONLY. Inspect printer.cfg for other includes defining these macros.')
        return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=printer.parent/'cxm_backups'/('native-'+stamp)
    backup.mkdir(parents=True,exist_ok=False)
    shutil.copy2(printer,backup/'printer.cfg')
    if dest.exists():shutil.copy2(dest,backup/'cxm_native_toolchange.cfg')
    created=not dest.exists()
    try:
        if created:atomic_write(dest,src)
        if updated!=raw:atomic_write(printer,updated.encode('utf8'))
    except BaseException:
        atomic_write(printer,(backup/'printer.cfg').read_bytes())
        if created:dest.unlink(missing_ok=True)
        raise
    print('Installed with backups:',backup)
    print('One deliberate Klipper RESTART required after safe physical inspection.')
    print('After restart and G28, sync accepted dock geometry, then confirm physically EMPTY.')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError) as e:
        print('CXM NATIVE INSTALL REFUSED:',e)
        raise SystemExit(2)
,raw):
            pattern=pattern.strip()
            if pattern=='cxm_native_toolchange.cfg':continue
            matches=glob.glob(str(path.parent/pattern))
            if not matches:raise RuntimeError('Unresolved Klipper include: '+pattern)
            for match in matches:visit(Path(match))
    visit(printer)
    return collisions

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--repo',type=Path,default=Path.home()/'CXM')
    ap.add_argument('--printer-config',type=Path,default=Path.home()/'printer_data/config/printer.cfg')
    a=ap.parse_args()
    source=(a.repo/'vendor/cxm/cxm_native_toolchange.cfg').expanduser().resolve()
    printer=a.printer_config.expanduser().resolve()
    dest=printer.parent/'cxm_native_toolchange.cfg'
    if not source.is_file() or not printer.is_file():
        raise RuntimeError('Source or printer.cfg missing')
    src=source.read_bytes()
    raw=printer.read_text('utf8')
    for name in MACROS:
        signature='[gcode_macro '+name+']'
        if src.count(signature.encode())!=1:
            raise RuntimeError('Macro source does not define exactly one '+name)
        if re.search(r'(?m)^\s*\[gcode_macro\s+'+re.escape(name)+r'\s*\]\s*$',raw,re.I):
            raise RuntimeError('Duplicate native macro in printer.cfg: '+name)
    if src.count(b'[delayed_gcode CXM_NATIVE_TEST_STEP]')!=1:
        raise RuntimeError('Native delayed test controller missing')
    if not re.search(r'(?m)^\s*\[include\s+cxm_fast_guard\.cfg\s*\]\s*$',raw,re.I):
        raise RuntimeError('CXM_FAST_VERIFY guard must already be installed in printer.cfg')
    matches=re.findall(r'(?mi)^\s*\[include cxm_native_toolchange\.cfg\]\s*$',raw)
    if len(matches)>1:
        raise RuntimeError('Duplicate native include found')
    if dest.exists() and dest.read_bytes()!=src:
        raise RuntimeError('Installed native macro differs from source; review manually')
    if dest.exists() and len(matches)==1:
        print('Already installed and identical: no changes')
        return
    if not matches:
        marker='#*# <---------------------- SAVE_CONFIG'
        updated=(raw.replace(marker,INCLUDE+'\n\n'+marker,1)
                 if marker in raw else raw.rstrip()+'\n\n'+INCLUDE+'\n')
    else:
        updated=raw
    print('Source:',source)
    print('Destination:',dest)
    print('Printer configuration:',printer)
    print('New include:',not bool(matches))
    print('No physical motion; no restart performed; native geometry remains INVALID until runtime sync.')
    if not a.apply:
        print('DRY RUN ONLY. Inspect printer.cfg for other includes defining these macros.')
        return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=printer.parent/'cxm_backups'/('native-'+stamp)
    backup.mkdir(parents=True,exist_ok=False)
    shutil.copy2(printer,backup/'printer.cfg')
    if dest.exists():shutil.copy2(dest,backup/'cxm_native_toolchange.cfg')
    created=not dest.exists()
    try:
        if created:atomic_write(dest,src)
        if updated!=raw:atomic_write(printer,updated.encode('utf8'))
    except BaseException:
        atomic_write(printer,(backup/'printer.cfg').read_bytes())
        if created:dest.unlink(missing_ok=True)
        raise
    print('Installed with backups:',backup)
    print('One deliberate Klipper RESTART required after safe physical inspection.')
    print('After restart and G28, sync accepted dock geometry, then confirm physically EMPTY.')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError) as e:
        print('CXM NATIVE INSTALL REFUSED:',e)
        raise SystemExit(2)
