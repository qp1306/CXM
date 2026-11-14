"""Exact-match, backed-up CXM Dock XY jog upgrade (no other Klipper changes).

No motion or Klipper restart is performed here. Only two recognised lines are
changed in cxm_native_toolchange.cfg; refuse any unknown/manual changes.
"""
import hashlib
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

OLD_REV = 'variable_jog_revision: 1'
NEW_REV = 'variable_jog_revision: 2'
OLD_FEED = '{% set feed=(180 if camera else 60) if axis == "Z" else (1200 if camera else 300) %}'
NEW_FEED = '{% set feed=(180 if camera else 60) if axis == "Z" else (1200 if camera else 3000) %}'
MARKER = '[gcode_macro CXM_MANUAL_DOCK_JOG]'

class JogUpgradeError(RuntimeError):
    pass

def _hash(data):
    return hashlib.sha256(data).hexdigest()

def inspect(path):
    target = Path(path)
    if target.is_symlink():
        raise JogUpgradeError('Native macro must be a regular file, not a symbolic link')
    raw = target.read_bytes()
    try:
        source = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise JogUpgradeError('Unexpected non-UTF8 native macro') from exc
    if source.count(MARKER)!=1 or source.count('[gcode_macro _CXM_NATIVE]')!=1:
        raise JogUpgradeError('Native macro sections are missing or duplicated')
    head, jog = source.split(MARKER,1)
    section, tail = jog.split('\n[',1) if '\n[' in jog else (jog,'')
    if (head.count(OLD_REV),head.count(NEW_REV)) == (1,0) and (section.count(OLD_FEED),section.count(NEW_FEED)) == (1,0):
        changed = head.replace(OLD_REV,NEW_REV)+MARKER+section.replace(OLD_FEED,NEW_FEED)+(('\n['+tail) if tail else '')
        state = 'needs_apply'
    elif (head.count(OLD_REV),head.count(NEW_REV)) == (0,1) and (section.count(OLD_FEED),section.count(NEW_FEED)) == (0,1):
        changed=source
        state='installed'
    else:
        raise JogUpgradeError('Unknown or partially modified native jog macro; refusing patch')
    if changed.count(MARKER)!=1 or changed.count(NEW_REV)!=1 or changed.count(NEW_FEED)!=1:
        raise JogUpgradeError('Patch did not produce a unique verified macro')
    return {'state':state,'sha256':_hash(raw),'target':str(target),
            'original':raw,'updated':changed.encode('utf-8')}

def apply(path,expected_sha256):
    state=inspect(path)
    if state['sha256']!=expected_sha256:
        raise JogUpgradeError('Native macro changed since preview; refresh Updates')
    if state['state']=='installed':
        return {'installed':True,'already_installed':True,'restart_required':False}
    target=Path(path)
    timestamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=target.with_name(target.name+'.before-jog50.'+timestamp+'.bak')
    with backup.open('xb') as f:
        f.write(state['original'])
        f.flush()
        os.fsync(f.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as f:
            tmp=Path(f.name)
            os.fchmod(f.fileno(),target.stat().st_mode & 0o777)
            f.write(state['updated'])
            f.flush()
            os.fsync(f.fileno())
        # Detect races immediately before replacing the installed file.
        if _hash(target.read_bytes())!=expected_sha256:
            raise JogUpgradeError('Native macro changed during update; original left intact')
        os.replace(tmp,target)
        tmp=None
        verify=inspect(target)
        if verify['state']!='installed':
            raise JogUpgradeError('Native jog patch did not verify after writing')
        return {'installed':True,'backup':backup.name,'restart_required':True}
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
