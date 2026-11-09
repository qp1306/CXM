#!/usr/bin/env python3
"""Remove only known legacy Lineux dock calibration components from CXM printer.

Default DRY-RUN. --apply backs up then removes the obsolete Klipper module,
its two-section config file, and the include in printer.cfg.
Never modifies CXM movement macros, saved XY or other printer configurations.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import os
import re
import shutil
import tempfile

INCLUDE_RE=re.compile(r'(?im)^\s*\[include\s+dock_locate_calibrate\.cfg\s*\]\s*\n?')
def write_atomic(path,content):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        tmp=Path(f.name);f.write(content);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--apply',action='store_true')
    p.add_argument('--printer-config',type=Path,default=Path.home()/'printer_data/config/printer.cfg')
    p.add_argument('--klipper-module',type=Path,default=Path.home()/'klipper/klippy/extras/dock_locate_calibrate.py')
    a=p.parse_args()
    printer=a.printer_config.expanduser().resolve()
    module=a.klipper_module.expanduser().resolve()
    if not printer.is_file() or not module.parent.is_dir():
        raise RuntimeError('Active printer.cfg or Klipper extras directory missing')
    cfg=printer.parent/'dock_locate_calibrate.cfg'
    original=printer.read_text('utf8')
    count=len(INCLUDE_RE.findall(original))
    if count>1:
        raise RuntimeError('More than one Lineux include: refuse to guess')
    if module.exists():
        data=module.read_text('utf8')
        for token in ('class DockLocateCalibrate','DOCK_LOCATE_CALIBRATE','def load_config('):
            if token not in data:
                raise RuntimeError('Installed module is not recognised Lineux source; refusing removal')
    if cfg.exists():
        content=cfg.read_text('utf8')
        sections=re.findall(r'(?m)^\s*\[([^\]]+)\]\s*$',content)
        if sorted(sections)!=sorted(['dock_locate_calibrate','gcode_macro DOCK_CALIBRATION']):
            raise RuntimeError('Calibration CFG contains custom sections: inspect manually before removal')
    modified=INCLUDE_RE.sub('',original)
    print('Lineux include count:',count)
    print('Old module exists:',module.exists())
    print('Old CFG exists:',cfg.exists())
    print('Native CxChanger macros and CXM_variables.cfg: PRESERVE')
    print('No printer movement; no automatic Klipper restart.')
    if not a.apply:
        print('DRY RUN: use --apply after checking output')
        return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=printer.parent/'cxm_backups'/('manual-calibration-v2-'+stamp)
    backup.mkdir(parents=True,exist_ok=False)
    files=[printer]+[x for x in (module,cfg) if x.exists()]
    for path in files:
        shutil.copy2(path,backup/path.name)
    try:
        if modified!=original:
            write_atomic(printer,modified.encode('utf8'))
        if cfg.exists(): cfg.unlink()
        if module.exists(): module.unlink()
    except BaseException:
        write_atomic(printer,(backup/printer.name).read_bytes())
        for item in (module,cfg):
            source=backup/item.name
            if source.exists():shutil.copy2(source,item)
        raise
    print('Legacy Lineux module/config removed, native movement untouched.')
    print('BACKUP:',backup)
    print('Run RESTART in Mainsail when safe; confirm ready before motor-on jogging.')

if __name__=='__main__':
    main()
