"""CXM CxChanger motion engine.

Lineux only establishes the XY measurement. This module implements the
CxChanger underactuated magnetic hotend dock geometry. The saved dock XY is
the locking-screw / large-hole datum. All Y travel distances here are
relative to that datum, exactly as in upstream CxChanger toolchange.cfg.

No homing, no Lineux calibration calls, no heaters, and no Z moves here.
"""
import math

def finite(v, label, lo, hi):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(label+' outside allowed CxChanger range')
    return float(v)

def plan(saved, shift_x=None, dodge_y=None, tool=0):
    """Calculate proven locked-dock pickup/dropoff for any T0..T11 datum."""
    if type(tool) is not int or not 0<=tool<12:
        raise ValueError('Invalid CxChanger hotend index')
    if tool>=saved['config']['globals']['tool_count']:
        raise ValueError('CxChanger hotend is not selected')
    t=saved['config']['tools'][tool]
    g=saved['config']['globals']
    if t['dock_x'] is None or t['dock_y'] is None:
        raise ValueError('Save CxChanger T'+str(tool)+' dock XY datum first')
    if not t.get('dock_reference_accepted',False):
        raise ValueError('CxChanger dock reference not accepted. Re-measure with Lineux and save the CxChanger datum.')
    x=finite(t['dock_x'],'CxChanger dock X',10,334)
    y=finite(t['dock_y'],'CxChanger dock Y',10,320)
    dx=finite(g['cxm_shift_x'] if shift_x is None else shift_x,'positive X pickup latch travel',0.1,8)
    dy=finite(g['cxm_dodge_y'] if dodge_y is None else dodge_y,'legacy Y dodge',5,25)
    clearance=finite(g['cxm_safe_clearance_y'],'Y safe travel from dock',35,160)
    safe=y+clearance
    if x+dx>334 or safe>362:
        raise ValueError('CxChanger docking path exceeds guarded X/Y travel')
    return {
        'stage':[(x,safe)],
        # Demonstrated T0 sequence: move Y in on saved X (release-side),
        # engage by shifting X+, then withdraw Y+ at mounted-side X.
        'pickup':[(x,y),(x+dx,y),(x+dx,safe)],
        # Exact reverse: enter Y- at mounted-side X, disengage X- to
        # saved dock X, then withdraw Y+ at release-side X.
        'dropoff':[(x+dx,y),(x,y),(x,safe)],
        'shift_x':dx,'dodge_y':dy,'safe_y':safe,
        'clearance_y':clearance,'dock_reference_xy':{'x':x,'y':y},
        'motion_source':'CxChanger','measurement_source':'Lineux (separate)',
    }

# Motion lives entirely in vendor/cxm/cxm_native_toolchange.cfg.
# Only geometry validation remains in Python for calibration and UI.
