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

def apply(path,expected_sha256):
    if type(expected_sha256) is not str or not SHA.fullmatch(expected_sha256):
        raise NativeX334Error('Invalid native configuration fingerprint')
    before=inspect(path)
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
        if inspect(target)['state']!='installed':
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
