"""Shared Moonraker transport and motion lock for CXM native and manual tools.

No automatic dock measurement, coordinate reconstruction or Lineux dependency.
"""
import json
import re
import threading
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:7125'
MOVE_LOCK = threading.Lock()


class MeasurementError(RuntimeError):
    pass


def _rpc(path, payload=None, *, timeout_s=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE+path, data=data,
        headers={'Content-Type': 'application/json'} if data is not None else {},
        method='POST' if data is not None else 'GET')
    # Long-running supervised native tool streams may legitimately exceed
    # the 125s default POST read timeout at commissioning feed rates.
    # Only their explicit caller may increase this read timeout; all
    # existing native tool operations retain the original limits.
    if timeout_s is not None:
        if (type(timeout_s) not in (int,float) or
                not 4 <= timeout_s <= 600):
            raise ValueError('Moonraker read timeout outside approved 4–600s range')
    deadline = timeout_s if timeout_s is not None else 125 if data else 4
    try:
        with urllib.request.urlopen(req, timeout=deadline) as f:
            answer = json.load(f)
    except urllib.error.HTTPError as exc:
        try:
            detail=json.loads(exc.read(16384).decode('utf8')).get('error',{})
            trace=detail.get('traceback','')
            match=re.search(r'gcode\\.CommandError: ([^\\n]+)',trace)
            reason=match.group(1) if match else detail.get('message',str(exc))
        except (ValueError,UnicodeError,TypeError):
            reason=str(exc)
        raise MeasurementError('Klipper rejected command: '+str(reason)[:240]) from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise MeasurementError('Moonraker connection failed: '+str(exc)[:140]) from exc
    if not isinstance(answer, dict) or 'error' in answer or 'result' not in answer:
        raise MeasurementError('Invalid Moonraker response')
    return answer['result']



