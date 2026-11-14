"""Patch obsolete X325 limits and one hard-coded T1 release guard in Klipper cfg.

This is a targeted in-place config correction, not a macro replacement.
Preserve ALL other native macro code, dock geometry, timings, sensor checks
and operator changes byte-for-byte. Back up before atomic replacement.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import os
import re
import tempfile

class NativeX334Error(RuntimeError):
    pass

# Every replacement must be confined to its named macro.
RULES={
    '_CXM_STAGE_TEST':(
        ('pos.x|float > 325.0','pos.x|float > 334.0'),
    ),
    '_CXM_CHECK_TOOL':(
        ('x>325 or y<10','x>334 or y<10'),
        ('x+st.shift_x|float>325','x+st.shift_x|float>334'),
    ),
    '_CXM_CLEAR_TRANSFER':(
        ('pos.x > 325','pos.x > 334'),
    )
}
# This two-line condition is known from the operator's LIVE Klipper evidence.
# It incorrectly forces T1 to an older X264.70/Y65.60 datum instead of the
# saved, synchronized T1 XY. Remove it only on an exact match.
LEGACY_T1_CONDITION = (
    '{% elif t == 1 and ((x-264.70)|abs > 0.00001 or (y-65.60)|abs > 0.00001) %}'
)
LEGACY_ERROR = 'CXM: T1 synchronized coordinates differ from the proven release point'
LEGACY_T1_ACTION = '{action_raise_error("' + LEGACY_ERROR + '")}'
# Klipper's live config strips indentation; installed source may preserve it.
# Only accept the exact old condition and associated exception on two lines,
# allowing indentation and LF/CRLF, not arbitrary source-code substitutions.
LEGACY_T1_PATTERN = re.compile(
    r'(?m)^[ \t]*' + re.escape(LEGACY_T1_CONDITION) +
    r'[ \t]*\r?\n[ \t]*' + re.escape(LEGACY_T1_ACTION) +
    r'[ \t]*(?:\r?\n|$)'
)
# Convert only the obsolete Dock Batch check-only staging to automatic Y+.
OLD_STAGE_CLEARANCE = (
    '    {% elif pos.y|float < min_clear - 0.2 %}\n'
    '      {action_raise_error("CXM: below dock mechanical clearance Y; no automatic movement possible from this position")}\n'
    '    {% elif pos.x|float < 5.0 or pos.x|float > 334.0 %}'
)
NEW_STAGE_CLEARANCE = '    {% elif pos.x|float < 5.0 or pos.x|float > 334.0 %}'
OLD_STAGE_START = (
    '    {% if pos.y|float < target - 0.001 %}\n'
    '      {action_raise_error("CXM: start on or above the clear staging line")}\n'
    '    {% endif %}\n'
    '    CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y={target}'
)
NEW_STAGE_START = (
    '    {% if pos.y|float < target - 0.001 %}\n'
    '      SAVE_GCODE_STATE NAME=CXM_BATCH_STAGE\n'
    '      G90\n'
    '      G1 Y{target|round(5)} F6000\n'
    '      M400\n'
    '      RESTORE_GCODE_STATE NAME=CXM_BATCH_STAGE MOVE=0\n'
    '    {% endif %}\n'
    '    CXM_FAST_VERIFY EXPECT=RELEASED MIN_Y={target}'
)
STAGE_UPDATES=((OLD_STAGE_CLEARANCE,NEW_STAGE_CLEARANCE),
               (OLD_STAGE_START,NEW_STAGE_START))

MACRO=re.compile(r'(?m)^\[gcode_macro ([^\]]+)\]\s*$')
SHA=re.compile(r'^[a-f0-9]{64}$')

def _transform(source):
    matches=list(MACRO.finditer(source))
    if not matches:
        raise NativeX334Error('Klipper macro sections not found')
    sections={}
    for index,match in enumerate(matches):
        end=matches[index+1].start() if index+1<len(matches) else len(source)
        sections[match.group(1)]=(match.start(),end)
    if any(name not in sections for name in RULES):
        raise NativeX334Error('Required native CxChanger macro sections unavailable')
    spans=[]
    for name,pairs in RULES.items():
        start,end=sections[name]
        section=source[start:end]
        changed=section
        for old,new in pairs:
            olds=changed.count(old);news=changed.count(new)
            # Refuse unexpected, duplicated or partially-customized guards.
            if (olds,news)==(1,0):
                changed=changed.replace(old,new,1)
            elif (olds,news)==(0,1):
                continue
            else:
                raise NativeX334Error(name+' has unknown or duplicated X guard: '+old)
        if name=='_CXM_STAGE_TEST':
            for old,new in STAGE_UPDATES:
                n=changed.count(old)
                if n==1:
                    changed=changed.replace(old,new,1)
                elif n==0 and changed.count(new)==1:
                    continue
                else:
                    raise NativeX334Error(
                        'Unknown or duplicated Dock Batch staging guard; no modification')
        if name=='_CXM_CLEAR_TRANSFER':
            matches=list(LEGACY_T1_PATTERN.finditer(changed))
            if len(matches)==1:
                changed=LEGACY_T1_PATTERN.sub('',changed,count=1)
                if LEGACY_ERROR in changed:
                    raise NativeX334Error(
                        'Unexpected T1 release guard; refusing partial removal')
            elif (matches or LEGACY_ERROR in changed or
                  re.search(r'(?m)^[ \t]*\{%\s*elif\s+t\s*==\s*1\b', changed)):
                raise NativeX334Error(
                    'Unexpected T1 release guard; refusing to change installed macro')
        spans.append((start,end,changed))
    for start,end,section in sorted(spans,reverse=True):
        source=source[:start]+section+source[end:]
    return source

def _transform_stale_t1_only(source):
    """Independently remove the one verified obsolete T1 rule.

    Real installed CXM native files may differ from the vendored version in
    unrelated macros; never require rewriting those to fix this exact rule.
    """
    matches=list(MACRO.finditer(source))
    spans={}
    for i,match in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(source)
        spans[match.group(1)]=(match.start(),end)
    if '_CXM_CLEAR_TRANSFER' not in spans:
        raise NativeX334Error('Installed Klipper _CXM_CLEAR_TRANSFER macro is missing')
    start,end=spans['_CXM_CLEAR_TRANSFER']
    section=source[start:end]
    found=list(LEGACY_T1_PATTERN.finditer(section))
    if len(found)!=1 or section.count(LEGACY_ERROR)!=1:
        raise NativeX334Error('Installed T1 check is not the proven obsolete two-line rule')
    replacement=LEGACY_T1_PATTERN.sub('',section,count=1)
    if LEGACY_ERROR in replacement:
        raise NativeX334Error('Duplicate T1 release rule remains; refusing partial change')
    return source[:start]+replacement+source[end:]


def inspect_t1_only(path):
    target=Path(path)
    if not target.is_file() or target.is_symlink():
        raise NativeX334Error('Native Klipper config must be a regular file')
    raw=target.read_bytes()
    source=raw.decode('utf-8')
    updated=_transform_stale_t1_only(source).encode('utf-8')
    return {'state':'needs_apply','sha256':hashlib.sha256(raw).hexdigest(),
            'original':raw,'updated':updated,'mode':'t1_only'}


def inspect_compat(path):
    """Use whole-file known patch if possible; fall back ONLY for the proven
    T1 rule when unrelated installed macro variants block whole-file matching.
    """
    try:
        info=inspect(path)
        info['mode']='normal'
        return info
    except NativeX334Error as full_error:
        try:
            return inspect_t1_only(path)
        except (NativeX334Error,UnicodeError):
            raise full_error


def inspect(path):
    target=Path(path)
    if not target.is_file() or target.is_symlink():
        raise NativeX334Error('Native Klipper config must be a regular file')
    raw=target.read_bytes()
    try:
        source=raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise NativeX334Error('Native Klipper macro encoding not UTF-8') from exc
    revised=_transform(source).encode('utf-8')
    return {'state':'installed' if revised==raw else 'needs_apply',
            'sha256':hashlib.sha256(raw).hexdigest(),
            'original':raw,'updated':revised}

def apply(path,expected_sha256,*,inspector=inspect):
    if type(expected_sha256) is not str or not SHA.fullmatch(expected_sha256):
        raise NativeX334Error('Invalid native configuration fingerprint')
    before=inspector(path)
    if before['sha256']!=expected_sha256:
        raise NativeX334Error('Native Klipper file changed; refresh and retry')
    if before['state']=='installed':
        return {'patched':False,'restart_required':False,'already_installed':True}
    target=Path(path)
    backup=target.with_name(target.name+'.before-X334-'+
      datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.bak')
    with backup.open('xb') as fd:
        fd.write(before['original']);fd.flush();os.fsync(fd.fileno())
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as fd:
            tmp=Path(fd.name)
            os.fchmod(fd.fileno(),target.stat().st_mode & 0o777)
            fd.write(before['updated']);fd.flush();os.fsync(fd.fileno())
        if hashlib.sha256(target.read_bytes()).hexdigest()!=expected_sha256:
            raise NativeX334Error('Native macro changed during correction')
        os.replace(tmp,target);tmp=None
        if inspector is inspect_t1_only:
            if LEGACY_ERROR in target.read_text(encoding='utf-8'):
                raise NativeX334Error('Obsolete T1 guard remained after patch')
        elif inspector(target)['state']!='installed':
            raise NativeX334Error('Native X334 correction did not verify')
        return {'patched':True,'restart_required':True,'backup':backup.name}
    except BaseException:
        # Roll back any unsuccessful file replacement, preserving the backup.
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

def apply_compat(path,expected_sha256):
    inspected=inspect_compat(path)
    inspector=inspect_t1_only if inspected.get('mode')=='t1_only' else inspect
    result=apply(path,expected_sha256,inspector=inspector)
    result['mode']=inspected['mode']
    return result


def loaded_t1_release_guard(rpc):
    """Report whether active Klipper still contains the obsolete T1 datum."""
    try:
        data=rpc('/printer/objects/query?configfile=config')
        source=(data.get('status',{}).get('configfile',{})
                  .get('config',{}).get('gcode_macro _CXM_CLEAR_TRANSFER',{})
                  .get('gcode',''))
        if not isinstance(source,str) or not source:
            return 'unknown'
        return 'obsolete_t1' if LEGACY_ERROR in source else 'clear'
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,AttributeError):
        return 'unknown'

def live_status(rpc):
    """Inspect loaded Klipper config; never infer activation from disk alone."""
    try:
        data=rpc('/printer/objects/query?configfile=config')
        sections=data.get('status',{}).get('configfile',{}).get('config',{})
        check=sections.get('gcode_macro _CXM_CHECK_TOOL',{}).get('gcode','')
        if 'x+st.shift_x|float>334' in check and 'x+st.shift_x|float>325' not in check:
            return 'x334'
        if 'x+st.shift_x|float>325' in check:
            return 'x325'
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,AttributeError):
        pass
    return 'unknown'
