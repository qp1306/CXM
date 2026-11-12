"""Explicit, operator-approved cold Tool Z preparation after a Klipper restart.

No G1 generation, no nozzle touch, no heating, no offset writes, and no blind
identity restoration. Homing is dispatched ONLY to the existing proven G28
Klipper homing override when unhomed. The native bridge owns geometry sync.
"""
from __future__ import annotations
import math
import threading
from cxm_native import _native_status, initialize as native_initialize
from cxm_runtime import _rpc, MOVE_LOCK
from cxm_z_auto import assess, selected_tools, physical_enabled, max_commissioned_tool, CONTROLLER, _object_status, ZAutoError

_PREPARE_LOCK = threading.Lock()
ACK = 'I_INSPECTED_EMPTY_CARRIAGE_COLD_HARDWARE_AND_WILL_SUPERVISE_HOMING'


def in_progress():
    return _PREPARE_LOCK.locked()


def _safe_preconditions(store, revision, count, printer_idle):
    if not physical_enabled():
        raise ZAutoError('Automatic Tool Z physical commissioning is not armed')
    saved = store.read()
    if saved['revision'] != revision or saved.get('migration_required'):
        raise ZAutoError('Saved calibration changed or requires migration; refresh before preparation')
    try:
        selection = selected_tools(count)
    except ValueError as exc:
        raise ZAutoError(str(exc)) from exc
    if any(t>=saved['config']['globals']['tool_count'] for t in selection):
        raise ZAutoError('Selected tool is not configured')
    if any(t>max_commissioned_tool() for t in selection):
        raise ZAutoError('Selected tool exceeds physical commissioning gate')
    if CONTROLLER.status()['running']:
        raise ZAutoError('Automatic Tool Z calibration is already running')
    if not printer_idle():
        raise ZAutoError('Klipper must be ready and safely idle; no printing or paused job')
    native, test, sensor = _native_status()
    if native.get('protocol') != 2:
        raise ZAutoError('CXM native toolchanger protocol mismatch')
    if test.get('running'):
        raise ZAutoError('Native tool cycle is active')
    if sensor != 'RELEASED':
        raise ZAutoError('Carriage sensor is not RELEASED; EMPTY preparation refused')
    if native.get('current_tool') not in (-2, -1):
        raise ZAutoError('Klipper still records a mounted tool; inspect carriage and resolve identity')
    status = _object_status()
    if status.get('extruder', {}).get('target') != 0 or status.get('heater_bed', {}).get('target') not in (None, 0):
        raise ZAutoError('Heater targets must both be zero before homing/preparation')
    touch = status.get('cartographer', {}).get('touch')
    if not isinstance(touch, dict) or not touch.get('current_model'):
        raise ZAutoError('Cartographer Touch model unavailable; do not home automatically')
    # Before any movement confirm the accepted datums can be planned safely.
    from cxm_cxchanger import plan
    for t in selection:
        entry = saved['config']['tools'][t]
        if entry.get('maintenance_lockout') or not entry.get('dock_reference_accepted'):
            raise ZAutoError(f'T{t}: accepted unlocked dock required')
        plan(saved, tool=t)
    return status


def prepare(store, expected_revision, tool_count, acknowledgement, printer_idle):
    if acknowledgement != ACK:
        raise ZAutoError('Approve physically EMPTY carriage, cold hardware, clear homing travel and supervision')
    if not _PREPARE_LOCK.acquire(blocking=False):
        raise ZAutoError('Preparation already running; do not submit again')
    events = []
    try:
        status = _safe_preconditions(store, expected_revision, tool_count, printer_idle)
        homed = status.get('toolhead', {}).get('homed_axes', '')
        if not all(x in homed for x in 'xyz'):
            # This is a *deliberate operator-initiated* G28 through the proven
            # Klipper homing override, not a SET_KINEMATIC_POSITION shortcut.
            # Hold the CXM motion lock; failure stops, never auto-retries.
            if not MOVE_LOCK.acquire(blocking=False):
                raise ZAutoError('Another CXM motion command is in progress')
            try:
                _rpc('/printer/gcode/script', {'script': 'G28'}, timeout_s=240)
            finally:
                MOVE_LOCK.release()
            events.append('G28 XYZ completed')
            status = _safe_preconditions(store, expected_revision, tool_count, printer_idle)
            if not all(x in status.get('toolhead',{}).get('homed_axes','') for x in 'xyz'):
                raise ZAutoError('G28 returned without XYZ homed: stop and inspect')
        else:
            events.append('XYZ already homed; no G28 sent')
        # At this point, all axes are homed and the carriage has been confirmed
        # physically empty. Do not auto-stage XY if it is inside the docks.
        pos = status.get('toolhead', {}).get('position', [])
        saved=store.read()
        if len(pos)<3 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in pos[:3]):
            raise ZAutoError('Valid measured XYZ position required after homing')
        max_safe_y = max((float(t['dock_y']) + float(saved['config']['globals']['cxm_safe_clearance_y'])
                          for t in saved['config']['tools'][:saved['config']['globals']['tool_count']]
                          if t.get('dock_reference_accepted')), default=0)
        if not (5 <= pos[0] <= 325 and pos[1]>=max_safe_y-0.15 and 1.0 <= pos[2] <= 330):
            raise ZAutoError('Carriage not in verified transfer corridor; do not automatically stage from this position')
        _safe_preconditions(store, expected_revision, tool_count, printer_idle)
        # Reuse the same verified geometry-sync+EMPTY declaration already used
        # by Tools. Never synthesize tool identity from the sensor if PRESSED.
        native_initialize(store, expected_revision, -1)
        events.append('Saved native geometry synchronised; EMPTY declared')
        _safe_preconditions(store, expected_revision, tool_count, printer_idle)
        # Clearing a session mesh is an idempotent Klipper command. It does not
        # delete saved calibration or change the motion-coordinate system.
        _rpc('/printer/gcode/script', {'script': 'BED_MESH_CLEAR'})
        events.append('Active bed mesh cleared')
        result = assess(store, tool_count)
        if not result['ready']:
            raise ZAutoError('Preparation completed but readiness blocked: '+'; '.join(result['blockers']))
        if result['native_tool'] != -1 or result['sensor'] != 'RELEASED':
            raise ZAutoError('Final carriage state not confirmed EMPTY')
        return {'prepared':True, 'events':events, 'ready':True,
                'revision':expected_revision, 'native_tool':-1, 'sensor':'RELEASED',
                'next':'Start automatic cold Tool Z calibration after final inspection'}
    except Exception as exc:
        # Operations may already have completed; never send automatic retry or
        # restore/park G-code. Raise useful progress for operator inspection.
        raise ZAutoError('Preparation stopped after '+(', '.join(events) or 'no operations')+
                         ': '+str(exc)[:350]+'. Inspect actual printer state before retrying') from exc
    finally:
        _PREPARE_LOCK.release()
