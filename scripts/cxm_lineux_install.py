#!/usr/bin/env python3
"""One-time bridge setup for CXM Control Centre's original Lineux engine.

DRY RUN by default; --apply installs unchanged module and a minimal Klipper
configuration, with backups, duplicate guards and never restarts Klipper.
No automatic calibration motion. Assumes repo deployed at ~/CXM.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import configparser
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

ORIGINAL_SHA = 'b243104c0d711720802424ddc8c89b44f878577516f09058fc47a8c312632d8d'

def section(raw, name):
    pattern=r'(?ms)^\['+re.escape(name)+r'\][ \t]*$\n(.*?)(?=^\[|\Z)'
    matches=re.findall(pattern,raw)
    if len(matches)!=1: raise RuntimeError('Expected exactly one ['+name+'] in printer.cfg')
    pairs=dict(re.findall(r'(?m)^\s*([a-z_]+)\s*:\s*([^#\n]+)',matches[0]))
    return {k:v.strip() for k,v in pairs.items()}

def verify_existing_cfg(raw, *, resolution, xstop, ystop):
    """Accept equivalent settings regardless of comments, spacing or description.

    Reject unexpected sections, duplicate keys and different executable G-code.
    Never rewrite an existing operator-owned calibration file.
    """
    parser=configparser.ConfigParser(
        interpolation=None, strict=True, inline_comment_prefixes=('#',))
    parser.read_string(raw)
    names={'dock_locate_calibrate', 'gcode_macro DOCK_CALIBRATION'}
    if set(parser.sections()) != names:
        raise RuntimeError('Existing Lineux CFG has missing/extra sections; not replacing')
    engine=parser['dock_locate_calibrate']
    if set(engine) != {'xy_resolution','x_endstop','y_endstop','calibrate_move_x'}:
        raise RuntimeError('Existing Lineux CFG has missing/extra engine options')
    for field,expected in (
            ('xy_resolution',resolution),('x_endstop',xstop),
            ('y_endstop',ystop),('calibrate_move_x',3.0)):
        try:
            value=float(engine[field])
        except (TypeError,ValueError) as exc:
            raise RuntimeError('Invalid existing Lineux '+field) from exc
        if not math.isfinite(value) or abs(value-expected)>1e-7:
            raise RuntimeError('Existing Lineux '+field+
                               ' differs from CXM; manual review required')
    macro=parser['gcode_macro DOCK_CALIBRATION']
    if set(macro) != {'description','gcode'} or (
            macro['gcode'].strip() != 'DOCK_LOCATE_CALIBRATE'):
        raise RuntimeError('Existing DOCK_CALIBRATION G-code differs; review required')
    return True


def atomically_write(path, raw):
    with tempfile.NamedTemporaryFile('wb',dir=path.parent,delete=False) as f:
        temp=Path(f.name)
        f.write(raw);f.flush();os.fsync(f.fileno())
    try: os.replace(temp,path)
    finally: temp.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--apply',action='store_true',help='Install after inspecting the dry-run')
    p.add_argument('--repo',type=Path,default=Path.home()/'CXM')
    p.add_argument('--printer-config',type=Path,default=Path.home()/'printer_data/config/printer.cfg')
    p.add_argument('--klipper-extras',type=Path,default=Path.home()/'klipper/klippy/extras')
    a=p.parse_args()
    root=a.repo.expanduser().resolve()
    original=root/'vendor/lineux/dock_locate_calibrate.py'
    destination=a.klipper_extras.expanduser().resolve()/'dock_locate_calibrate.py'
    printer=a.printer_config.expanduser().resolve()
    cfg=printer.parent/'dock_locate_calibrate.cfg'
    if not original.is_file() or not destination.parent.is_dir() or not printer.is_file():
        raise RuntimeError('CXM repository, Klipper extras, or printer.cfg not present')
    src=original.read_bytes()
    if hashlib.sha256(src).hexdigest()!=ORIGINAL_SHA:
        raise RuntimeError('Original Lineux module hash mismatch; refusing installation')
    conf=printer.read_text('utf-8')
    x,y=section(conf,'stepper_x'),section(conf,'stepper_y')
    # The tested override may live in an included file; never modify it.
    # Control Centre also checks that a homing override is active.
    def float_key(c,key,default=None):
        if key not in c:
            if default is None: raise RuntimeError('Missing '+key+' in active configuration')
            return default
        return float(c[key])
    n=lambda d:float_key(d,'rotation_distance')/(float_key(d,'microsteps')*float_key(d,'full_steps_per_rotation',200))
    resolution=n(x)
    if abs(resolution-n(y))>1e-9: raise RuntimeError('X/Y microstep resolution mismatch')
    xstop,ystop=float_key(x,'position_endstop'),float_key(y,'position_endstop')
    if abs(float_key(x,'position_max')-xstop)>1 or abs(float_key(y,'position_max')-ystop)>1:
        raise RuntimeError('Expected X/Y endstops at positive limits')
    if not (0.002 < resolution < 0.03 and xstop>0 and ystop>0):
        raise RuntimeError('Unexpected motor resolution or endstops')
    content=('''# CXM Control Centre - Lineux calibrated measurement engine\n# Original Python module unchanged (SHA256 verified by installer).\n# Measurement must be initiated only after checking the dock clearance.\n[dock_locate_calibrate]\nxy_resolution: %.8f\nx_endstop: %.5f\ny_endstop: %.5f\ncalibrate_move_x: 3.0\n\n[gcode_macro DOCK_CALIBRATION]\ndescription: Lineux provisional dock XY measurement - supervised only\ngcode:\n    DOCK_LOCATE_CALIBRATE\n'''%(resolution,xstop,ystop)).encode('utf-8')
    if destination.exists() and destination.read_bytes()!=src:
        raise RuntimeError('Another dock_locate_calibrate.py exists; refusing overwrite')
    cfg_preserved=False
    if cfg.exists():
        # Existing CXM installation may have different explanatory comments.
        # Preserve the file if the configuration meaning is identical.
        try:
            verify_existing_cfg(cfg.read_text('utf-8'),
                resolution=resolution,xstop=xstop,ystop=ystop)
        except (configparser.Error, UnicodeError) as exc:
            raise RuntimeError('Existing Lineux CFG cannot be parsed safely: '+str(exc)) from exc
        cfg_preserved=True
    target='[include dock_locate_calibrate.cfg]'
    count=conf.count(target)
    if count>1:raise RuntimeError('Duplicate dock_locate_calibrate.cfg includes')
    print('Original Lineux SHA256 verified:',ORIGINAL_SHA)
    print('Active printer.cfg:',printer)
    print('Klipper module:',destination)
    print('Calibration settings:',{'resolution':resolution,'x_endstop':xstop,'y_endstop':ystop})
    print('Existing include count:',count)
    print('Lineux CFG:', 'existing verified; PRESERVE unchanged' if cfg_preserved else 'create new')
    print('NO printer movement; NO Klipper restart')
    if not a.apply:
        print('DRY RUN ONLY. Review before applying --apply.')
        return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backupdir=printer.parent/'cxm_backups'/('lineux-'+stamp)
    backupdir.mkdir(parents=True,exist_ok=False)
    shutil.copy2(printer,backupdir/'printer.cfg')
    if destination.exists():shutil.copy2(destination,backupdir/'dock_locate_calibrate.py')
    if cfg.exists():shutil.copy2(cfg,backupdir/'dock_locate_calibrate.cfg')
    try:
        if not destination.exists():atomically_write(destination,src)
        if not cfg.exists():atomically_write(cfg,content)
        if count==0:
            marker='#*# <---------------------- SAVE_CONFIG'
            if marker in conf:
                new=conf.replace(marker,target+'\n\n'+marker,1)
            else:
                new=conf.rstrip()+'\n\n'+target+'\n'
            atomically_write(printer,new.encode('utf-8'))
    except BaseException:
        atomically_write(printer,(backupdir/'printer.cfg').read_bytes())
        # Do not try to remove a newly copied module on a partial failure: report.
        print('Restored printer.cfg; inspect module and CFG before retrying.')
        raise
    print('Installed. Run RESTART in Mainsail when safe; verify module is active in Control Centre.')
    print('Backups:',backupdir)

if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,OSError) as exc:
        print('CXM Lineux installer REJECTED:',str(exc))
        raise SystemExit(2)