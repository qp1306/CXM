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
        reason = f'Moonraker HTTP {exc.code} on {path.split("?")[0]}'
        try:
            detail = json.loads(exc.read(16384)).get('error', {})
            if isinstance(detail, dict):
                trace = str(detail.get('traceback') or '')
                matches = re.findall(r'(?:gcode\.(?:CommandError|error)|ServerError): ([^\r\n]+)', trace)
                message = detail.get('message')
                for candidate in [*reversed(matches), message]:
                    if isinstance(candidate, str) and candidate.strip().lower() not in ('', 'unknown'):
                        reason = candidate.strip()
                        break
            elif isinstance(detail, str) and detail:
                reason = detail
        except (ValueError, AttributeError):
            pass
        raise MeasurementError('Klipper rejected command: '+reason[:300]) from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise MeasurementError('Moonraker connection failed: '+str(exc)[:140]) from exc
    if not isinstance(answer, dict) or 'error' in answer or 'result' not in answer:
        raise MeasurementError('Invalid Moonraker response')
    return answer['result']



