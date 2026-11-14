"""Single guarded CXM Dock XY calibration install: sensor-neutral jog, Z22, verify v2.

Patch ONLY the independently scoped calibration macros. Preserve all native
pickup/dropoff and tool state logic byte-for-byte. Install with backup and
hash-constrained atomic replacement; fail on unknown macro changes.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import os
import tempfile
from cxm_jog_upgrade import inspect as inspect_jog, JogUpgradeError

SOURCE=Path(__file__).resolve().parents[1]/'vendor/cxm/cxm_native_toolchange.cfg'
JOG='[gcode_macro CXM_MANUAL_DOCK_JOG]'
Z22='[gcode_macro CXM_MANUAL_JOG_PREPARE_Z22]'
VERIFY='[gcode_macro CXM_DOCK_VERIFY_MOVE]'
OLD_GUARD='''    {% elif printer["gcode_button cxm_tool_detect"].state != "PRESSED" %}
      {action_raise_error("CXM calibration: mounted hotend required")}
'''
OLD_VERIFY_GUARD='''    {% elif printer["gcode_button cxm_tool_detect"].state != "RELEASED" %}
      {action_raise_error("CXM dock verify: carriage must be EMPTY (FILAMENT ABSENT)")}
'''

class Z22UpgradeError(RuntimeError):
    pass

def _section(code,marker):
    if code.count(marker)!=1:
        raise Z22UpgradeError('Expected exactly one '+marker+' calibration macro')
    start=code.index(marker)
    next_start=code.find('\n[',start+len(marker))
    end=len(code) if next_start<0 else next_start+1
    return start,end,code[start:end].rstrip()

def _source_macro(text,marker):
    return _section(text,marker)[2]

def inspect(path):
    target=Path(path)
    if not target.is_file() or target.is_symlink():
        raise Z22UpgradeError('Native macro must be a regular file')
    raw=target.read_bytes()
    try:
        code=raw.decode('utf8');src=SOURCE.read_text('utf8')
    except UnicodeDecodeError as e:
        raise Z22UpgradeError('Native macro encoding must be UTF-8') from e
    try:
        jog=inspect_jog(target)
    except (JogUpgradeError,OSError) as e:
        raise Z22UpgradeError('Native 50 mm/s jog is unknown; refusing calibration patch') from e
    if jog['state']!='installed':
        raise Z22UpgradeError('Install native 50 mm/s jog revision 2 first')
    # Source is authoritative only for the specific independent calibration
    # sections. Every other installed line stays identical.
    approved_jog=_source_macro(src,JOG)
    approved_z22=_source_macro(src,Z22)
    approved_verify=_source_macro(src,VERIFY)
    start,end,jog_section=_section(code,JOG)
    if jog_section==approved_jog:
        pass
    elif jog_section.replace(OLD_GUARD,'') == approved_jog and jog_section.count(OLD_GUARD)==1:
        code=code[:start]+approved_jog+'\n'+code[end:]
    else:
        raise Z22UpgradeError('Unrecognised manual Dock XY jog macro; refusing modification')
    if code.count(Z22)==0:
        code=code.rstrip()+'\n\n'+approved_z22+'\n'
    elif code.count(Z22)==1:
        _,_,section=_section(code,Z22)
        if section!=approved_z22:
            raise Z22UpgradeError('Unknown Z22 preparation macro; refusing replacement')
    else:
        raise Z22UpgradeError('Duplicated Z22 preparation macro')
    if code.count(VERIFY)==1:
        start,end,old=_section(code,VERIFY)
        # Only exact known v1 -> approved v2. Unknown custom changes refused.
        legacy=approved_verify.replace(
            'description: Supervised 50mm/s dock XY calibration; filament sensor is telemetry',
            'description: Locked-hotend EMPTY-carriage 50mm/s dock alignment and travel'
        ).replace('variable_version: 2','variable_version: 1')
        legacy=legacy.replace(
            '    {% elif printer["gcode_macro _CXM_TEST_STATE"].running|int != 0 %}',
            OLD_VERIFY_GUARD+'    {% elif printer["gcode_macro _CXM_TEST_STATE"].running|int != 0 %}'
        )
        if old==approved_verify:
            pass
        elif old==legacy:
            code=code[:start]+approved_verify+'\n'+code[end:]
        else:
            raise Z22UpgradeError('Unknown locked-dock verification macro; refusing replacement')
    elif code.count(VERIFY)!=0:
        raise Z22UpgradeError('Duplicated locked-dock verification macro')
    updated=code.encode('utf8')
    return {'state':'installed' if updated==raw else 'needs_apply',
            'sha256':hashlib.sha256(raw).hexdigest(),
            'original':raw,'updated':updated}

def apply(path,sha256):
    data=inspect(path)
    if data['sha256']!=sha256:
        raise Z22UpgradeError('Installed native file changed since review')
    if data['state']=='installed':
        return {'installed':True,'restart_required':False,'already_installed':True}
    target=Path(path)
    backup=target.with_name(target.name+'.before-dock-calibration.'+
           datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.bak')
    with backup.open('xb') as fd:
        fd.write(data['original']);fd.flush();os.fsync(fd.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
            tmp=Path(fd.name)
            os.fchmod(fd.fileno(),target.stat().st_mode&0o777)
            fd.write(data['updated']);fd.flush();os.fsync(fd.fileno())
        if hashlib.sha256(target.read_bytes()).hexdigest()!=sha256:
            raise Z22UpgradeError('Installed macro changed during upgrade')
        os.replace(tmp,target);tmp=None
        if inspect(target)['state']!='installed':
            raise Z22UpgradeError('Post-install calibration verification failed')
        return {'installed':True,'restart_required':True,'backup':backup.name}
    except BaseException:
        if target.read_bytes()!=data['original']:
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
                saved=Path(fd.name)
                os.fchmod(fd.fileno(),target.stat().st_mode&0o777)
                fd.write(data['original']);fd.flush();os.fsync(fd.fileno())
            os.replace(saved,target)
        raise
    finally:
        if tmp is not None:tmp.unlink(missing_ok=True)
