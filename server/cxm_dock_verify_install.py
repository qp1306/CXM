"""Append-only CXM EMPTY-carriage dock verification macro upgrade.

Never replace or modify existing native CxChanger motion macros. Refuse
unknown source geometry and stale fingerprints. Back up before applying.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import os
import tempfile
from cxm_jog_upgrade import inspect as inspect_jog, JogUpgradeError

MARKER='[gcode_macro CXM_DOCK_VERIFY_MOVE]'
SOURCE=Path(__file__).resolve().parents[1]/'vendor/cxm/cxm_native_toolchange.cfg'

class DockVerifyInstallError(RuntimeError):
    pass

def inspect(path):
    target=Path(path)
    if not target.is_file() or target.is_symlink():
        raise DockVerifyInstallError('Native macro must be an existing regular file')
    original=target.read_bytes()
    try:
        source=SOURCE.read_text('utf8')
        installed=original.decode('utf8')
    except UnicodeDecodeError as e:
        raise DockVerifyInstallError('Native macro is not UTF-8') from e
    if source.count(MARKER)!=1:
        raise DockVerifyInstallError('Expected one approved source dock verification macro')
    approved=source[source.index(MARKER):].strip()
    if '\n[' in approved:
        raise DockVerifyInstallError('Dock verification macro must be last in source')
    # Recognise only the EXACT previously released v1 macro. Do not match
    # arbitrary user-edited code or replace any preceding proven toolchange.
    legacy=approved.replace(
        'description: Supervised 50mm/s dock XY calibration; filament sensor is telemetry',
        'description: Locked-hotend EMPTY-carriage 50mm/s dock alignment and travel'
    ).replace('variable_version: 2','variable_version: 1')
    legacy=legacy.replace(
        '    {% elif printer["gcode_macro _CXM_TEST_STATE"].running|int != 0 %}',
        '    {% elif printer["gcode_button cxm_tool_detect"].state != "RELEASED" %}\\n'
        '      {action_raise_error("CXM dock verify: carriage must be EMPTY (FILAMENT ABSENT)")}\\n'
        '    {% elif printer["gcode_macro _CXM_TEST_STATE"].running|int != 0 %}'
    )
    if installed.count(MARKER):
        if installed.count(MARKER)!=1:
            raise DockVerifyInstallError('Duplicated installed dock macro')
        head,old_section=installed.split(MARKER,1)
        old_macro=MARKER+old_section.strip()
        if old_macro==approved:
            result='installed'
            changed=original
        elif old_macro==legacy:
            changed=(head.rstrip()+'\\n\\n'+approved+'\\n').encode('utf8')
            result='needs_apply'
        else:
            raise DockVerifyInstallError('Unknown modified dock macro; refusing replacement')
    else:
        try:
            jog=inspect_jog(target)
        except (JogUpgradeError,OSError) as e:
            raise DockVerifyInstallError('Native 50mm/s jog source not recognized') from e
        if jog['state']!='installed':
            raise DockVerifyInstallError('Install native jog revision 2 before dock verification')
        changed=(installed.rstrip()+'\n\n'+approved+'\n').encode('utf8')
        result='needs_apply'
    return {'state':result,'sha256':hashlib.sha256(original).hexdigest(),
            'original':original,'updated':changed}

def apply(path,expected_sha256):
    data=inspect(path)
    if data['sha256']!=expected_sha256:
        raise DockVerifyInstallError('Macro changed since preview. Check status again')
    if data['state']=='installed':
        return {'installed':True,'already_installed':True,'restart_required':False}
    target=Path(path)
    date=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=target.with_name(target.name+'.before-dock-empty.'+date+'.bak')
    with backup.open('xb') as fd:
        fd.write(data['original'])
        fd.flush()
        os.fsync(fd.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
            tmp=Path(fd.name)
            os.fchmod(fd.fileno(),target.stat().st_mode&0o777)
            fd.write(data['updated'])
            fd.flush()
            os.fsync(fd.fileno())
        if hashlib.sha256(target.read_bytes()).hexdigest()!=expected_sha256:
            raise DockVerifyInstallError('Installed macro changed during patch')
        os.replace(tmp,target)
        tmp=None
        if inspect(target)['state']!='installed':
            raise DockVerifyInstallError('Installed macro did not verify')
        return {'installed':True,'backup':backup.name,'restart_required':True}
    except BaseException:
        # A failed post-install readback must not leave a partially accepted
        # Klipper source on disk. Restore byte-for-byte original from backup.
        if target.read_bytes()!=data['original']:
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
                restore=Path(fd.name)
                os.fchmod(fd.fileno(),target.stat().st_mode&0o777)
                fd.write(data['original'])
                fd.flush()
                os.fsync(fd.fileno())
            os.replace(restore,target)
        raise
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
