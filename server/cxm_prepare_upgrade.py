"""Exact append-only guarded Klipper Dock XY Z21 macro installer.

Never alter existing motion code. Refuse unknown or conflicting macro definitions.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import os
import tempfile
from cxm_jog_upgrade import inspect as inspect_jog, JogUpgradeError

MARKER = '[gcode_macro CXM_MANUAL_DOCK_PREPARE]'
SOURCE = Path(__file__).resolve().parents[1] / 'vendor/cxm/cxm_native_toolchange.cfg'

class PrepareUpgradeError(RuntimeError):
    pass

def inspect(path):
    target=Path(path)
    if target.is_symlink() or not target.is_file():
        raise PrepareUpgradeError('Installed native macro must be a regular file')
    raw=target.read_bytes()
    try:
        body=raw.decode('utf8')
        source=SOURCE.read_text('utf8')
    except UnicodeDecodeError as exc:
        raise PrepareUpgradeError('Native macro text must be UTF-8') from exc
    if source.count(MARKER)!=1:
        raise PrepareUpgradeError('Source Z21 macro missing or duplicated')
    expected=source[source.index(MARKER):].strip()
    if '[gcode_macro ' in expected[len(MARKER):]:
        raise PrepareUpgradeError('Z21 source macro is not isolated at source end')
    if body.count(MARKER):
        if body.count(MARKER)!=1 or not body.rstrip().endswith(expected):
            raise PrepareUpgradeError('Unknown or modified installed Z21 macro; refusing replacement')
        state='installed'
        revised=raw
    else:
        # Existing installed native jog must have the proven revision 2 speed
        # before this append-only feature can be enabled.
        try:
            known=inspect_jog(target)
        except (JogUpgradeError, OSError) as exc:
            raise PrepareUpgradeError('Native jog is not recognized; refusing Z21 installation') from exc
        if known['state']!='installed':
            raise PrepareUpgradeError('Install and activate native jog revision 2 first')
        revised=(body.rstrip()+'\n\n'+expected+'\n').encode('utf8')
        state='needs_apply'
    return {'state':state,'sha256':hashlib.sha256(raw).hexdigest(),
            'original':raw,'updated':revised,'target':str(target)}

def apply(path,expected_sha256):
    data=inspect(path)
    if expected_sha256!=data['sha256']:
        raise PrepareUpgradeError('Installed macro changed since review; check again')
    if data['state']=='installed':
        return {'installed':True,'already_installed':True,'restart_required':False}
    target=Path(path)
    timestamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=target.with_name(target.name+'.before-z21.'+timestamp+'.bak')
    with backup.open('xb') as fd:
        fd.write(data['original'])
        fd.flush()
        os.fsync(fd.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
            tmp=Path(fd.name)
            os.fchmod(fd.fileno(),target.stat().st_mode & 0o777)
            fd.write(data['updated'])
            fd.flush()
            os.fsync(fd.fileno())
        if hashlib.sha256(target.read_bytes()).hexdigest()!=expected_sha256:
            raise PrepareUpgradeError('Installed macro changed during installation')
        os.replace(tmp,target)
        tmp=None
        if inspect(target)['state']!='installed':
            raise PrepareUpgradeError('Z21 macro not verified after write')
        return {'installed':True,'backup':backup.name,'restart_required':True}
    except BaseException:
        # Preserve the old proven macro on any failed readback.
        if target.read_bytes()!=data['original']:
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
                restored=Path(fd.name)
                fd.write(data['original'])
                fd.flush()
                os.fsync(fd.fileno())
            os.replace(restored,target)
        raise
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
