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

SCHEMA = 1
TOOL_MAX = 12
FIELDS = {
    "enabled": ("bool", None, None),
    "dock_x": ("float", -50, 600),
    "dock_y": ("float", -50, 600),
    "dock_z": ("float", -20, 600),
    "offset_x": ("float", -20, 20),
    "offset_y": ("float", -20, 20),
    "offset_z": ("float", -10, 10),
    "approach_speed": ("float", 10, 15000),
    "dock_speed": ("float", 10, 5000),
}
GLOBAL_FIELDS = {
    "tool_count": ("int", 1, 12),
    "safe_y": ("float", 0, 600),
    "x_docking_adjust": ("float", -20, 20),
}

def template():
    tools = []
    for n in range(TOOL_MAX):
        tools.append({
            "enabled": n < 6,
            "dock_x": None, "dock_y": None, "dock_z": None,
            "offset_x": 0.0, "offset_y": 0.0, "offset_z": 0.0,
            "approach_speed": 1200.0, "dock_speed": 800.0,
        })
    return {"schema": SCHEMA, "globals": {"tool_count": 6, "safe_y": 120.0,
            "x_docking_adjust": 3.0}, "tools": tools}

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

def validate(data):
    if type(data) is not dict or set(data) != {'schema','globals','tools'} or data['schema'] != SCHEMA:
        raise ValueError('Unsupported CXM schema')
    if type(data['globals']) is not dict or set(data['globals']) != set(GLOBAL_FIELDS):
        raise ValueError('Invalid global settings')
    for k, spec in GLOBAL_FIELDS.items():
        check_value(k, data['globals'][k], spec)
    if type(data['tools']) is not list or len(data['tools']) != TOOL_MAX:
        raise ValueError('Exactly 12 tool profiles are required')
    for n, tool in enumerate(data['tools']):
        if type(tool) is not dict or set(tool) != set(FIELDS):
            raise ValueError(f'Invalid T{n} settings')
        for key, spec in FIELDS.items():
            check_value(key, tool[key], spec, nullable=key.startswith('dock_'))
    return data

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
    return validate({'schema': parts['variable_schema_version'], 'globals': parts['variable_globals'],
                     'tools': [parts[f'variable_t{i}'] for i in range(TOOL_MAX)]})

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
            return {'config': d, 'revision': self._hash(raw), 'active_in_klipper': False}
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
            data = copy.deepcopy(data)
            if tool == 'global':
                if key not in GLOBAL_FIELDS:
                    raise ValueError('Unknown global setting')
                data['globals'][key] = check_value(key, value, GLOBAL_FIELDS[key])
            else:
                if type(tool) is not int or not 0 <= tool < TOOL_MAX or key not in FIELDS:
                    raise ValueError('Unknown tool or setting')
                data['tools'][tool][key] = check_value(key, value, FIELDS[key], nullable=key.startswith('dock_'))
            new = render(data)
            if new == old:
                return {'saved': True, 'unchanged': True, 'revision': self._hash(old), 'active_in_klipper': False}
            return self._commit(old, new)
    def rollback(self, name, expected_revision):
        if not isinstance(name, str) or not re.fullmatch(r'\d{8}T\d{12}Z-[0-9a-f]{12}\.cfg', name):
            raise ValueError('Invalid backup ID')
        with self.lock.open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            _, old = self._current()
            if self._hash(old) != expected_revision:
                raise RuntimeError('Configuration changed; reload before rollback')
            new = (self.backups/name).read_text(encoding='utf-8')
            parse(new)
            return self._commit(old, new)
