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
    """Calculate original CxChanger path for any configured T0..T11 datum."""
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
    x=finite(t['dock_x'],'CxChanger dock X',10,325)
    y=finite(t['dock_y'],'CxChanger dock Y',10,320)
    dx=finite(g['cxm_shift_x'] if shift_x is None else shift_x,'X latch travel',-8,-1)
    dy=finite(g['cxm_dodge_y'] if dodge_y is None else dodge_y,'Y dodge',5,25)
    clearance=finite(g['cxm_safe_clearance_y'],'Y safe travel from dock',35,160)
    safe=y+clearance
    if clearance < dy+20:
        raise ValueError('CxChanger safe travel must exceed Y dodge by at least 20 mm')
    if x+dx<5 or x+dx>330 or safe>362:
        raise ValueError('CxChanger docking path exceeds guarded X/Y travel')
    return {
        'stage':[(x,safe)],
        # Upstream CxChanger _pickup_tool: enter at dodge Y, shift toward
        # release side, push to dock Y, latch back to X datum, retreat.
        'pickup':[(x,y+dy),(x+dx,y+dy),(x+dx,y),(x,y),(x,safe)],
        # Saved XY is mechanically LOCKED in the dock. Release requires
        # only a straight positive-Y withdrawal at constant dock X.
        'dropoff':[(x,y),(x,safe)],
        'shift_x':dx,'dodge_y':dy,'safe_y':safe,
        'clearance_y':clearance,'dock_reference_xy':{'x':x,'y':y},
        'motion_source':'CxChanger','measurement_source':'Lineux (separate)',
    }

# Motion lives entirely in vendor/cxm/cxm_native_toolchange.cfg.
# Only geometry validation remains in Python for calibration and UI.
