"""Exact-match append-only installer for the guarded Dock XY Z22 prepare macro.

Never overwrite the installed proven CxChanger pickup/dropoff macros.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import tempfile
import os
from cxm_jog_upgrade import inspect as inspect_jog,JogUpgradeError

MARKER='[gcode_macro CXM_MANUAL_JOG_PREPARE_Z22]'
SOURCE=Path(__file__).resolve().parents[1]/'vendor/cxm/cxm_native_toolchange.cfg'

class Z22UpgradeError(RuntimeError):
    pass

def inspect(path):
    target=Path(path)
    if not target.is_file() or target.is_symlink():
        raise Z22UpgradeError('Native macro must be an existing regular file')
    raw=target.read_bytes()
    try:
        code=raw.decode('utf8')
        source=SOURCE.read_text('utf8')
    except UnicodeDecodeError as e:
        raise Z22UpgradeError('Invalid macro encoding') from e
    if source.count(MARKER)!=1:
        raise Z22UpgradeError('Approved Z22 macro missing or duplicated')
    following=source.split(MARKER,1)[1]
    approved=(MARKER+following.split('\n[gcode_macro ',1)[0]).strip()
    if code.count(MARKER)>1:
        raise Z22UpgradeError('Duplicate installed Z22 macro')
    if code.count(MARKER)==1:
        if not code.rstrip().endswith(approved):
            raise Z22UpgradeError('Installed Z22 macro differs; refusing replacement')
        state='installed';updated=raw
    else:
        try:
            jog=inspect_jog(target)
        except (JogUpgradeError,OSError) as e:
            raise Z22UpgradeError('Existing native jog is not recognised') from e
        if jog['state']!='installed':
            raise Z22UpgradeError('Install native jog revision 2 first')
        state='needs_apply'
        updated=(code.rstrip()+'\n\n'+approved+'\n').encode('utf8')
    return {'state':state,'sha256':hashlib.sha256(raw).hexdigest(),
            'original':raw,'updated':updated}

def apply(path,sha256):
    data=inspect(path)
    if data['sha256']!=sha256:
        raise Z22UpgradeError('Native file changed since preview')
    if data['state']=='installed':
        return {'installed':True,'restart_required':False,'already_installed':True}
    target=Path(path)
    backup=target.with_name(target.name+'.before-z22.'+
       datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.bak')
    with backup.open('xb') as fd:
        fd.write(data['original']);fd.flush();os.fsync(fd.fileno())
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
            temp=Path(fd.name)
            os.fchmod(fd.fileno(),target.stat().st_mode & 0o777)
            fd.write(data['updated']);fd.flush();os.fsync(fd.fileno())
        if hashlib.sha256(target.read_bytes()).hexdigest()!=sha256:
            raise Z22UpgradeError('Native file changed while installing')
        os.replace(temp,target)
        temp=None
        if inspect(target)['state']!='installed':
            raise Z22UpgradeError('Z22 install readback failed')
        return {'installed':True,'restart_required':True,'backup':backup.name}
    except BaseException:
        if target.read_bytes()!=data['original']:
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
                restoration=Path(fd.name)
                os.fchmod(fd.fileno(),target.stat().st_mode & 0o777)
                fd.write(data['original']);fd.flush();os.fsync(fd.fileno())
            os.replace(restoration,target)
        raise
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
