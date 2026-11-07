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
        # Upstream _release_tool: enter at dock Y, shift to open lever,
        # retreat through dodge Y, reset lever, then travel clear.
        'dropoff':[(x,y),(x+dx,y),(x+dx,y+dy),(x,y+dy),(x,safe)],
        'shift_x':dx,'dodge_y':dy,'safe_y':safe,
        'clearance_y':clearance,'dock_reference_xy':{'x':x,'y':y},
        'motion_source':'CxChanger','measurement_source':'Lineux (separate)',
    }

def gcode(points,kind,safe_feed=600,test_feed=240,latch_feed=180):
    if kind=='stage':
        speeds=[safe_feed]
    elif kind=='pickup':
        speeds=[test_feed,test_feed,test_feed,latch_feed,test_feed]
    elif kind=='dropoff':
        speeds=[test_feed,latch_feed,test_feed,test_feed,test_feed]
    else:
        raise ValueError('Unknown CxChanger motion')
    lines=['G90']
    if kind=='stage':
        x,y=points[0]
        lines.extend([f'G1 Y{y:.5f} F{safe_feed}',f'G1 X{x:.5f} F{safe_feed}'])
    else:
        for (x,y),feed in zip(points,speeds):
            lines.append(f'G1 X{x:.5f} Y{y:.5f} F{feed}')
    lines.append('M400')
    return '\n'.join(lines)

def automatic_script(path,kind,*,at_stage,safe_feed=600,test_feed=240,latch_feed=180):
    movement=gcode(path[kind],kind,safe_feed,test_feed,latch_feed).splitlines()
    if at_stage:
        return '\n'.join(movement)
    stage=gcode(path['stage'],'stage',safe_feed,test_feed,latch_feed).splitlines()
    return '\n'.join(stage+movement[1:])
