"""One-time, backed-up Dock Batch macro upgrade: 1–12 accepted tools.

Replace only the five bounded batch-controller sections. Never touch any
pickup/dropoff movement, dock calibration, motor settings or global G-code.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import os
import re
import tempfile

class BatchUpgradeError(RuntimeError):
    pass

ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'vendor/cxm/cxm_native_toolchange.cfg'
SECTION=re.compile(r'(?m)^\[(gcode_macro|delayed_gcode) ([^\]\n]+)\][ \t]*$')
SHA=re.compile(r'[0-9a-f]{64}\Z')
NAMES=(
    ('gcode_macro','_CXM_TEST_STATE'),
    ('gcode_macro','CXM_TEST_START'),
    ('gcode_macro','_CXM_TEST_ADVANCE'),
    ('delayed_gcode','CXM_NATIVE_TEST_STEP'),
    ('gcode_macro','CXM_TEST_RESET'),
)
OLD_MARKERS={
    ('gcode_macro','_CXM_TEST_STATE'):(
        'variable_tool_c: -1','variable_state: "idle"'),
    ('gcode_macro','CXM_TEST_START'):(
        'selected dock safe-Y lines differ by more than 1 mm',
        'invalid ordered 1-3 tool cycle parameters',
        'VARIABLE=tool_c VALUE={c}',
        '_CXM_STAGE_TEST Y={([y_a,y_b,y_c]|max)}'),
    ('gcode_macro','_CXM_TEST_ADVANCE'):(
        'set count=3 if st.tool_c|int >= 0',
        'CXM_FAST_VERIFY EXPECT=RELEASED',
        'UPDATE_DELAYED_GCODE ID=CXM_NATIVE_TEST_STEP'),
    ('delayed_gcode','CXM_NATIVE_TEST_STEP'):(
        'st.tool_a|int if st.index|int == 0',
        'CXM_SELECT_TOOL TOOL={t}',
        '_CXM_TEST_ADVANCE'),
    ('gcode_macro','CXM_TEST_RESET'):(
        'VARIABLE=state VALUE="\'idle\'"',
        'UPDATE_DELAYED_GCODE ID=CXM_NATIVE_TEST_STEP DURATION=0'),
}

def sections(source):
    found={}
    matches=list(SECTION.finditer(source))
    if not matches:
        raise BatchUpgradeError('No Klipper batch macro sections found')
    for i,match in enumerate(matches):
        key=(match.group(1),match.group(2))
        if key in found:
            raise BatchUpgradeError('Duplicate Klipper macro '+str(key))
        end=matches[i+1].start() if i+1<len(matches) else len(source)
        found[key]=(match.start(),end,source[match.start():end])
    return found

def transform(source,vendor):
    installed=sections(source)
    reference=sections(vendor)
    if any(name not in installed or name not in reference for name in NAMES):
        raise BatchUpgradeError('Native batch macros missing; no modification')
    # Existing native transfer must already support guarded Y+ staging.
    stage=installed.get(('gcode_macro','_CXM_STAGE_TEST'))
    if not stage or 'G1 Y{target|round(5)} F6000' not in stage[2] or \
            'CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y={target}' not in stage[2]:
        raise BatchUpgradeError('Install prior guarded Y+ staging correction first')
    updates=[]
    for name in NAMES:
        start,end,old=installed[name]
        new=reference[name][2]
        if old==new:
            continue
        if not all(marker in old for marker in OLD_MARKERS[name]):
            raise BatchUpgradeError('Unknown '+name[1]+' version; refusing to overwrite custom controller')
        # Never silently overwrite a partially upgraded controller.
        if name==('gcode_macro','_CXM_TEST_STATE') and 'variable_batch_revision:' in old:
            raise BatchUpgradeError('Unexpected batch state revision; no modification')
        if name==('gcode_macro','CXM_TEST_START') and 'VARIABLE=tool_mask' in old:
            raise BatchUpgradeError('Partially upgraded batch runner; no modification')
        updates.append((start,end,new))
    for start,end,new in sorted(updates,reverse=True):
        source=source[:start]+new+source[end:]
    return source

def inspect(path):
    target=Path(path)
    if not target.is_file() or target.is_symlink():
        raise BatchUpgradeError('Installed native Klipper configuration must be a regular file')
    raw=target.read_bytes()
    try:
        source=raw.decode('utf-8')
        vendor=VENDOR.read_text(encoding='utf-8')
    except UnicodeError as exc:
        raise BatchUpgradeError('Invalid native macro text encoding') from exc
    revised=transform(source,vendor).encode('utf-8')
    return {'state':'installed' if revised==raw else 'needs_apply',
            'sha256':hashlib.sha256(raw).hexdigest(),'original':raw,'updated':revised}

def apply(path,expected_sha256):
    if not isinstance(expected_sha256,str) or not SHA.fullmatch(expected_sha256):
        raise BatchUpgradeError('Invalid Dock Batch macro fingerprint')
    before=inspect(path)
    if before['sha256']!=expected_sha256:
        raise BatchUpgradeError('Installed native Klipper file changed; refresh before applying')
    if before['state']=='installed':
        return {'already_installed':True,'patched':False,'restart_required':False}
    target=Path(path)
    backup=target.with_name(target.name+'.before-batch12-'+
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.bak')
    with backup.open('xb') as fd:
        fd.write(before['original']);fd.flush();os.fsync(fd.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
            tmp=Path(fd.name)
            os.fchmod(fd.fileno(),target.stat().st_mode&0o777)
            fd.write(before['updated']);fd.flush();os.fsync(fd.fileno())
        if hashlib.sha256(target.read_bytes()).hexdigest()!=expected_sha256:
            raise BatchUpgradeError('Native macros changed while applying batch correction')
        os.replace(tmp,target);tmp=None
        if inspect(target)['state']!='installed':
            raise BatchUpgradeError('Dock Batch macro upgrade did not verify after write')
        return {'patched':True,'restart_required':True,'backup':backup.name}
    except BaseException:
        if target.read_bytes()!=before['original']:
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
                restore=Path(fd.name)
                os.fchmod(fd.fileno(),target.stat().st_mode&0o777)
                fd.write(before['original']);fd.flush();os.fsync(fd.fileno())
            os.replace(restore,target)
        raise
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
