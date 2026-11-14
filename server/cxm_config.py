"""CXM V0.2 validated persistent store; stdlib only, no Klipper imports."""
import ast
import copy
import fcntl
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone

SCHEMA = 3
PREVIOUS_SCHEMA = 2
LEGACY_SCHEMA = 1
TOOL_MAX = 12
FIELDS = {
    "maintenance_lockout": ("bool", None, None),
    # These flags are recorded by future, separately verified calibration
    # routines. They are NOT editable through the generic settings API.
    "offset_xy_accepted": ("bool", None, None),
    "offset_z_accepted": ("bool", None, None),
    "dock_verified": ("bool", None, None),
    "offset_xy_verified": ("bool", None, None),
    "offset_z_verified": ("bool", None, None),
    "pickup_verified": ("bool", None, None),
    "dropoff_verified": ("bool", None, None),
    "heater_verified": ("bool", None, None),
    "sensor_verified": ("bool", None, None),
    "reference_verified": ("bool", None, None),
    "commissioned": ("bool", None, None),
    "dock_x": ("float", -50, 600),
    "dock_y": ("float", -50, 600),
    "lineux_raw_x": ("float", -50, 600),
    "lineux_raw_y": ("float", -50, 600),
    "dock_reference_accepted": ("bool", None, None),
    "dock_z": ("float", -20, 600),  # Legacy field; gantry docks use XY only
    "offset_x": ("float", -20, 20),
    "offset_y": ("float", -20, 20),
    "offset_z": ("float", -10, 10),
    "approach_speed": ("float", 10, 15000),
    "dock_speed": ("float", 10, 5000),
}
LEGACY_FIELDS = {"enabled": ("bool", None, None), **{
    key: value for key, value in FIELDS.items()
    if key not in {"maintenance_lockout","offset_xy_accepted","offset_z_accepted",
        "dock_verified","offset_xy_verified","offset_z_verified","pickup_verified",
        "dropoff_verified","heater_verified","sensor_verified","reference_verified",
        "commissioned","lineux_raw_x","lineux_raw_y","dock_reference_accepted"}
}}
EDITABLE_TOOL_FIELDS = {
    "maintenance_lockout","dock_x","dock_y",
    "offset_x","offset_y","offset_z","approach_speed","dock_speed",
}
VERIFICATION_FLAGS = set(FIELDS) - EDITABLE_TOOL_FIELDS
GLOBAL_FIELDS = {
    "tool_count": ("int", 1, 12),
    "safe_y": ("float", 0, 600),
    "x_docking_adjust": ("float", -20, 20),
}
V2_GLOBAL_FIELDS = dict(GLOBAL_FIELDS)
V2_FIELDS = {key:spec for key,spec in FIELDS.items()
             if key not in ('lineux_raw_x','lineux_raw_y','dock_reference_accepted')}
GLOBAL_FIELDS.update({
    "y_docking_adjust": ("float", -20, 20),
    "cxm_shift_x": ("float", -8, 8),
    "cxm_dodge_y": ("float", 5, 25),
    "cxm_safe_clearance_y": ("float", 35, 160),
})

def template():
    tools = []
    for n in range(TOOL_MAX):
        tools.append({
            "maintenance_lockout": False,
            "offset_xy_accepted": False, "offset_z_accepted": False,
            "dock_verified": False,
            "offset_xy_verified": False, "offset_z_verified": False,
            "pickup_verified": False, "dropoff_verified": False,
            "heater_verified": False, "sensor_verified": False,
            "reference_verified": False, "commissioned": False,
            "dock_x": None, "dock_y": None, "dock_z": None,
            "lineux_raw_x": None, "lineux_raw_y": None,
            "dock_reference_accepted": False,
            "offset_x": 0.0, "offset_y": 0.0, "offset_z": 0.0,
            "approach_speed": 1200.0, "dock_speed": 800.0,
        })
    return {"schema": SCHEMA, "globals": {"tool_count": 6, "safe_y": 120.0,
            "x_docking_adjust": 0.0, "y_docking_adjust": 0.0,
            "cxm_shift_x": 4.4, "cxm_dodge_y": 14.0,
            "cxm_safe_clearance_y": 100.0}, "tools": tools}

def check_value(field, value, spec, *, nullable=False):
    typ, lo, hi = spec
    if nullable and value is None:
        return None
    if typ == 'bool':
        if type(value) is not bool:
            raise ValueError(f"{field} must be true or false")
        return value
    if typ == 'int':
        if type(value) is not int:
            raise ValueError(f"{field} must be an integer")
        v = value
    else:
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        v = float(value)
    if not lo <= v <= hi:
        raise ValueError(f"{field} must be between {lo} and {hi}")
    return v

def validate(data, schema=SCHEMA):
    if type(data) is not dict or set(data) != {'schema','globals','tools'} or data['schema'] != schema:
        raise ValueError('Unsupported CXM schema')
    global_fields = GLOBAL_FIELDS if schema==SCHEMA else V2_GLOBAL_FIELDS
    if type(data['globals']) is not dict or set(data['globals']) != set(global_fields):
        raise ValueError('Invalid global settings')
    for k, spec in global_fields.items():
        check_value(k, data['globals'][k], spec)
    if type(data['tools']) is not list or len(data['tools']) != TOOL_MAX:
        raise ValueError('Exactly 12 tool profiles are required')
    fields = FIELDS if schema == SCHEMA else V2_FIELDS if schema == PREVIOUS_SCHEMA else LEGACY_FIELDS
    for n, tool in enumerate(data['tools']):
        if type(tool) is not dict or set(tool) != set(fields):
            raise ValueError(f'Invalid T{n} settings')
        for key, spec in fields.items():
            check_value(key, tool[key], spec,
                        nullable=key in ('dock_x','dock_y','dock_z',
                                         'lineux_raw_x','lineux_raw_y'))
    return data


def schema_on_disk(raw):
    """Read strict saved schema from config text, never infer from file date."""
    values = [line.partition(':')[2].strip() for line in raw.splitlines()
              if line.startswith('variable_schema_version:')]
    if len(values) != 1:
        raise ValueError('Missing or duplicated CXM schema version')
    try:
        version = ast.literal_eval(values[0])
    except (SyntaxError, ValueError) as exc:
        raise ValueError('Invalid CXM schema version') from exc
    if type(version) is not int or version not in (LEGACY_SCHEMA, PREVIOUS_SCHEMA, SCHEMA):
        raise ValueError('Unsupported CXM schema version')
    return version


def upgrade_legacy(config):
    """Produce an UNVERIFIED schema-2 projection without changing source data."""
    validate(config, LEGACY_SCHEMA)
    out = template()
    out['globals'].update(copy.deepcopy(config['globals']))
    for n, old in enumerate(config['tools']):
        tool = out['tools'][n]
        for key in LEGACY_FIELDS:
            if key != 'enabled':
                tool[key] = old[key]
        # The first six tools were enabled by default in v1. A disabled one
        # in this group was likely manually locked. Preserve that block.
        # T6–T11 were disabled by default: do not treat the default as fault.
        # Regardless, ALL migrated tools are unverified and uncommissioned.
        tool['maintenance_lockout'] = n < 6 and not old['enabled']
    return out

def upgrade_v2(config):
    """Backed-up schema 2 migration: retain measured values, invalidate motion."""
    validate(config, PREVIOUS_SCHEMA)
    out=template()
    out['globals'].update(copy.deepcopy(config['globals']))
    for old,new in zip(config['tools'],out['tools']):
        for key in V2_FIELDS:
            new[key]=copy.deepcopy(old[key])
        new['dock_reference_accepted']=False
        new['dock_verified']=False
        new['pickup_verified']=False
        new['dropoff_verified']=False
        new['commissioned']=False
    return out


def render(data):
    validate(data)
    # Python literals are compatible with Klipper's macro variable parsing.
    lines = [
        '# CXM auto-managed settings - DO NOT edit by hand while the service is running',
        '# Not included in printer.cfg until the CXM macro integration is installed',
        '[gcode_macro _CXM_VARIABLES]',
        f"variable_schema_version: {SCHEMA}",
        f"variable_globals: {repr(data['globals'])}",
    ]
    lines += [f"variable_t{n}: {repr(tool)}" for n, tool in enumerate(data['tools'])]
    lines.extend(['gcode:', '  {% set cxm_values_loaded = 1 %}', ''])
    return '\n'.join(lines)

def parse(s):
    parts = {}
    for line in s.splitlines():
        if line.startswith('variable_'):
            k, sep, v = line.partition(':')
            if not sep or k in parts:
                raise ValueError('Malformed or duplicate CXM variable')
            parts[k] = ast.literal_eval(v.strip())
    required = {'variable_schema_version', 'variable_globals'} | {f'variable_t{i}' for i in range(TOOL_MAX)}
    if set(parts) != required:
        raise ValueError('Unrecognised or missing CXM variables')
    raw_data = {'schema': parts['variable_schema_version'], 'globals': parts['variable_globals'],
                'tools': [parts[f'variable_t{i}'] for i in range(TOOL_MAX)]}
    version = raw_data['schema']
    if version == LEGACY_SCHEMA:
        return upgrade_legacy(raw_data)
    if version == PREVIOUS_SCHEMA:
        return upgrade_v2(raw_data)
    if version == SCHEMA:
        return validate(raw_data)
    raise ValueError('Unsupported CXM schema version')

class Store:
    def __init__(self, folder):
        self.folder = Path(folder).expanduser().resolve()
        if not self.folder.is_dir():
            raise FileNotFoundError('CXM configuration directory does not exist')
        self.path = self.folder/'CXM_variables.cfg'
        self.backups = self.folder/'cxm_backups'
        self.lock = self.folder/'.cxm_config.lock'
    @staticmethod
    def _hash(raw):
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()
    @staticmethod
    def _atomic(path, raw):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                  prefix='.cxm-', delete=False) as f:
                tmp = Path(f.name)
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
            fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if tmp and tmp.exists():
                tmp.unlink()
    def _current(self):
        if not self.path.is_file():
            raise FileNotFoundError('CXM_variables.cfg not initialised')
        raw = self.path.read_text(encoding='utf-8')
        return parse(raw), raw
    def initialize(self):
        self.backups.mkdir(exist_ok=True)
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            if self.path.exists():
                data, raw = self._current()
                return {'created': False, 'revision': self._hash(raw)}
            raw = render(template())
            self._atomic(self.path, raw)
            return {'created': True, 'revision': self._hash(raw)}
    def read(self):
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            d, raw = self._current()
            return {'config': d, 'revision': self._hash(raw), 'active_in_klipper': False,
                    'migration_required': schema_on_disk(raw) != SCHEMA}

    def migrate(self, expected_revision):
        """Explicit, revision-checked v1/v2 -> v3; backup before replacement."""
        if type(expected_revision) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected_revision):
            raise ValueError('Valid expected revision required')
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data, old = self._current()
            if self._hash(old) != expected_revision:
                raise RuntimeError('Configuration changed; reload before migrating')
            if schema_on_disk(old) == SCHEMA:
                return {'saved': True, 'unchanged': True, 'revision': self._hash(old),
                        'active_in_klipper': False, 'migration_required': False}
            result = self._commit(old, render(data))
            result['migration_required'] = False
            return result
    def _backup(self, raw):
        self.backups.mkdir(exist_ok=True)
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+self._hash(raw)[:12]+'.cfg'
        self._atomic(self.backups/name, raw)
        return name
    def history(self):
        if not self.backups.exists():
            return []
        return [p.name for p in sorted(self.backups.glob('*.cfg'), reverse=True)[:40]]
    def _commit(self, old, new):
        previous = self._backup(old)
        self._atomic(self.path, new)
        return {'saved': True, 'revision': self._hash(new), 'backup': previous,
                'active_in_klipper': False}
    def set_value(self, tool, key, value, expected_revision):
        if type(expected_revision) is not str or not re.fullmatch(r'[0-9a-f]{64}',expected_revision):
            raise ValueError('Valid expected revision required')
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data, old = self._current()
            if self._hash(old) != expected_revision:
                raise RuntimeError('Configuration changed; reload before editing')
            if schema_on_disk(old) != SCHEMA:
                raise RuntimeError('Explicit configuration migration required before editing')
            data = copy.deepcopy(data)
            if tool == 'global':
                if key not in GLOBAL_FIELDS:
                    raise ValueError('Unknown global setting')
                previous = data['globals'][key]
                data['globals'][key] = check_value(key, value, GLOBAL_FIELDS[key])
                if key in ('safe_y','x_docking_adjust','y_docking_adjust',
                            'cxm_shift_x','cxm_dodge_y','cxm_safe_clearance_y') and previous != data['globals'][key]:
                    for entry in data['tools']:
                        if key in ('x_docking_adjust','y_docking_adjust') and (
                                entry['lineux_raw_x'] is not None or
                                entry['lineux_raw_y'] is not None):
                            entry['dock_reference_accepted'] = False
                        entry['dock_verified'] = False
                        entry['pickup_verified'] = False
                        entry['dropoff_verified'] = False
                        entry['commissioned'] = False
            else:
                if type(tool) is not int or not 0 <= tool < TOOL_MAX or key not in EDITABLE_TOOL_FIELDS:
                    raise ValueError('Unknown or protected tool setting')
                if tool >= data['globals']['tool_count']:
                    raise ValueError('Tool not selected within configured count')
                entry = data['tools'][tool]
                entry[key] = check_value(key, value, FIELDS[key], nullable=key.startswith('dock_'))
                if key.startswith('dock_'):
                    entry['dock_reference_accepted'] = False
                    entry['dock_verified'] = False
                    entry['pickup_verified'] = False
                    entry['dropoff_verified'] = False
                    entry['commissioned'] = False
                if key in ('offset_x','offset_y'):
                    entry['offset_xy_accepted'] = False
                    entry['offset_xy_verified'] = False
                    entry['commissioned'] = False
                if key == 'offset_z':
                    entry['offset_z_accepted'] = False
                    entry['offset_z_verified'] = False
                    entry['commissioned'] = False
                if key in ('approach_speed','dock_speed','maintenance_lockout'):
                    entry['pickup_verified'] = False
                    entry['dropoff_verified'] = False
                    entry['commissioned'] = False
            new = render(data)
            if new == old:
                return {'saved': True, 'unchanged': True, 'revision': self._hash(old), 'active_in_klipper': False}
            return self._commit(old, new)
    def apply_verified_t0_motion(self, expected_revision):
        """Atomically save the demonstrated T0 X+4.4/Y+100 motion settings.

        Never overwrite a separately measured physical dock position. A
        previous accepted dock datum must be independently measured and
        within guarded CxChanger XY limits. Never assume old dock coordinates.
        This only changes global motion parameters, not saved dock XY.
        """
        if type(expected_revision) is not str or not re.fullmatch(r'[0-9a-f]{64}',expected_revision):
            raise ValueError('Valid expected revision required')
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data,old=self._current()
            if self._hash(old)!=expected_revision:
                raise RuntimeError('Configuration changed; reload before installing baseline')
            if schema_on_disk(old)!=SCHEMA:
                raise RuntimeError('Configuration migration required before installing baseline')
            t0=data['tools'][0]
            if (t0['dock_reference_accepted'] is not True
                or type(t0['dock_x']) not in (int,float)
                or type(t0['dock_y']) not in (int,float)
                or not (10 <= t0['dock_x'] <= 320)
                or not (10 <= t0['dock_y'] <= 320)):
                raise ValueError('T0 must have a newly measured accepted dock XY inside the guarded motion region')
            updated=copy.deepcopy(data)
            updated['globals']['cxm_shift_x']=4.4
            updated['globals']['cxm_safe_clearance_y']=100.0
            if updated==data:
                return {'saved':True,'unchanged':True,'revision':self._hash(old),
                        'dock_x':t0['dock_x'],'dock_y':t0['dock_y']}
            # Motion changed: retain accepted dock XY, but reset previously
            # validated automatic motion flags for all tools.
            for tool in updated['tools']:
                for flag in ('dock_verified','pickup_verified','dropoff_verified','commissioned'):
                    tool[flag]=False
            result=self._commit(old,render(updated))
            result.update({'dock_x':t0['dock_x'],'dock_y':t0['dock_y']})
            return result

    def save_dock(self, tool, xy, expected_revision, raw_xy=None):
        """Save X/Y of a gantry-mounted dock atomically with backup.

        The physical dock moves with the gantry: there is no independent dock
        Z position. Preserve the legacy nullable dock_z schema field for old
        files, but deliberately clear it on an accepted XY calibration to
        avoid retaining a fictitious Z docking target. This does not touch
        nozzle/tool relative offset_z or any motion configuration.
        """
        if type(tool) is not int or not 0 <= tool < TOOL_MAX:
            raise ValueError('Invalid tool index')
        if type(xy) is not dict or set(xy) != {'x','y'}:
            raise ValueError('Exactly X and Y are required for gantry-mounted docks')
        if type(expected_revision) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected_revision):
            raise ValueError('Valid expected revision required')
        values = {
            'dock_x': check_value('dock_x', xy['x'], FIELDS['dock_x']),
            'dock_y': check_value('dock_y', xy['y'], FIELDS['dock_y']),
            'dock_z': None,
            'dock_reference_accepted': True,
            'lineux_raw_x': None,
            'lineux_raw_y': None,
        }
        if raw_xy is not None:
            raise ValueError('Legacy MCU-derived XY provenance retired; use motor-on capture')
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data, old = self._current()
            if self._hash(old) != expected_revision:
                raise RuntimeError('Configuration changed; reload before saving dock')
            if schema_on_disk(old) != SCHEMA:
                raise RuntimeError('Explicit configuration migration required before editing')
            if tool >= data['globals']['tool_count'] or data['tools'][tool]['maintenance_lockout']:
                raise ValueError('Tool outside count or in maintenance lockout')
            data = copy.deepcopy(data)
            entry = data['tools'][tool]
            changed = any(entry[k] != v for k, v in values.items())
            entry.update(values)
            if changed:
                entry['dock_verified'] = False
                entry['pickup_verified'] = False
                entry['dropoff_verified'] = False
                entry['commissioned'] = False
            new = render(data)
            if new == old:
                return {'saved': True, 'unchanged': True, 'revision': self._hash(old),
                        'active_in_klipper': False, 'verified_pickup': False}
            result = self._commit(old, new)
            result['verified_pickup'] = False
            return result
    def save_offsets(self, tool, axes, values, expected_revision):
        """Atomically store operator-measured relative offsets with backup.

        Accepted *numbers* are not evidence of a nozzle measurement or
        mechanical verification. Runtime Klipper offsets are not changed.
        T0 is the mathematical reference and must remain exactly zero.
        """
        expected_keys={'xy':{'x','y'},'z':{'z'}}
        if type(axes) is not str or axes not in expected_keys:
            raise ValueError('Choose XY or Z offset')
        if type(values) is not dict or set(values)!=expected_keys[axes]:
            raise ValueError('Supply exactly the chosen axis values')
        if type(tool) is not int or not 0<=tool<TOOL_MAX:
            raise ValueError('Invalid tool index')
        if type(expected_revision) is not str or not re.fullmatch(r'[0-9a-f]{64}',expected_revision):
            raise ValueError('Valid expected revision required')
        update={}
        for axis,raw in values.items():
            key='offset_'+axis
            update[key]=check_value(key,raw,FIELDS[key])
        if tool==0 and any(value!=0.0 for value in update.values()):
            raise ValueError('T0 is the reference: relative offsets must remain zero')
        with self.lock.open('a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            data,old=self._current()
            if self._hash(old)!=expected_revision:
                raise RuntimeError('Configuration changed; refresh first')
            if schema_on_disk(old)!=SCHEMA:
                raise RuntimeError('Configuration migration required')
            if tool>=data['globals']['tool_count'] or data['tools'][tool]['maintenance_lockout']:
                raise ValueError('Tool not selected or maintenance locked')
            data=copy.deepcopy(data)
            entry=data['tools'][tool]
            changed=any(entry[key]!=value for key,value in update.items())
            if changed:
                entry.update(update)
                if axes=='xy':
                    entry['offset_xy_accepted']=False
                    entry['offset_xy_verified']=False
                else:
                    entry['offset_z_accepted']=False
                    entry['offset_z_verified']=False
                entry['commissioned']=False
            new=render(data)
            if new==old:
                return {'saved':True,'unchanged':True,'revision':self._hash(old),
                        'active_in_klipper':False,'physically_verified':False}
            result=self._commit(old,new)
            result['physically_verified']=False
            return result

    def reset_commissioning(self, expected_revision):
        """Back up then replace ALL 12 tool calibrations with a blank schema-3 slate.

        Called only after the API has invalidated live Klipper tool geometry.
        Never alters printer.cfg, homing, hardware or the backup archive.
        """
        if type(expected_revision) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected_revision):
            raise ValueError('Valid CXM configuration revision required')
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            _, old = self._current()
            if self._hash(old) != expected_revision:
                raise RuntimeError('CXM configuration changed; reset refused before writing')
            if schema_on_disk(old) != SCHEMA:
                raise RuntimeError('Migrate CXM to schema 3 before resetting commissioning')
            fresh = template()
            # Begin at T0 only; the guided UI enables T1..T11 as each dock
            # is physically remeasured. All 12 stored profiles are cleared.
            fresh['globals']['tool_count'] = 1
            new = render(fresh)
            result = self._commit(old, new)
            if not (self.backups/result['backup']).is_file() or (
                    self._hash((self.backups/result['backup']).read_text('utf-8'))
                    != expected_revision):
                raise RuntimeError('CXM old-state backup could not be verified')
            result.update({'reset_commissioning': True, 'cleared_tools': 12,
                           'selected_tool_count': 1, 'all_docks_unaccepted': True,
                           'all_offsets_unverified': True})
            return result

    def rollback(self, name, expected_revision):
        if not isinstance(name, str) or not re.fullmatch(r'\d{8}T\d{12}Z-[0-9a-f]{12}\.cfg', name):
            raise ValueError('Invalid backup ID')
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            _, old = self._current()
            if self._hash(old) != expected_revision:
                raise RuntimeError('Configuration changed; reload before rollback')
            saved = (self.backups/name).read_text(encoding='utf-8')
            restored = parse(saved)
            # Old backups must not downgrade the live file to v1. Restore
            # the numbers through an unverified v2 projection instead.
            new = render(restored)
            return self._commit(old, new)
