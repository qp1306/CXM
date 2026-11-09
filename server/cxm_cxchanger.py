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


# Faster *clearance* segments for supervised mechanical-only multi-tool
# testing. Tested T0/T1+ single-tool scripts stay unchanged. Speed F is mm/min.
FAST_TRANSFER_FEED=1800       # 30 mm/s: dock-to-dock staging and clear corridor
DOCK_CLEARANCE_MARGIN_Y=10.0 # stay 10 mm outside the Y-dodge point at speed

def faster_cycle_script(path,kind,*,at_stage,travel_feed=FAST_TRANSFER_FEED,
                        test_feed=240,latch_feed=180,
                        margin_y=DOCK_CLEARANCE_MARGIN_Y,
                        _performance_limits=False, _trial_limits=False):
    """Same final docking geometry, faster ONLY when safely clear of dock.

    Entry is slowed at Y=dock_y+dodge_y+margin_y, before the coupling can
    interact with the dock. Exit runs slowly to this exact point, then
    speeds up. X latch, dodge-Y, dock contact and locking moves retain
    the existing trialled 240/180 mm/min. No Z, heater or extrusion G-code.
    """
    if kind not in ('pickup','dropoff'):
        raise ValueError('Select pickup or dropoff for faster travel')
    # Separate opt-in performance envelope; the physically proven Faster
    # mode retains its original strict 30/4/3 mm/s limits and behaviour.
    # A 15mm approach margin protects the coupling from 80mm/s travel.
    travel=finite(travel_feed,'Fast clear-corridor feed',600,
                  15000 if _trial_limits else 4800 if _performance_limits else 1800)
    test=finite(test_feed,'Dock approach feed',120,
                3000 if _trial_limits else 480 if _performance_limits else 240)
    latch=finite(latch_feed,'Dock latch feed',90,720 if _trial_limits else 180)
    margin=finite(margin_y,'Dock approach safety margin',8,15)
    x=path['dock_reference_xy']['x']
    y=path['dock_reference_xy']['y']
    dy=path['dodge_y']
    safe=path['safe_y']
    near=y+dy+margin
    if not (10<=x<=325 and 0<y<y+dy<near<=safe-8 and safe<=362):
        raise ValueError('Fast transfer must have a clear, separated Y corridor')
    points=path[kind]
    if len(points)!=5 or len(path['stage'])!=1:
        raise ValueError('Unexpected CxChanger motion geometry')
    lines=['G90']
    if not at_stage:
        # Preserve the native stage sequence: exit to safe Y BEFORE
        # crossing horizontally to the new tool's X coordinate.
        lines.extend([f'G1 Y{safe:.5f} F{travel:.0f}',
                      f'G1 X{x:.5f} F{travel:.0f}',
                      'M400'])
    def move(x_,y_,feed):
        lines.append(f'G1 X{x_:.5f} Y{y_:.5f} F{feed:.0f}')
    move(x,near,travel)   # clear corridor; speed up only outside dock
    if kind=='pickup':
        # Same CxChanger pickup coordinates and exact contact feed rates.
        for p,feed in zip(points[:4],[test,test,test,latch]):
            move(*p,feed)
    else:
        # Slow approach to the actual dock, then unchanged latch and
        # movement through the Y-dodge point.
        for p,feed in zip(points[:4],[test,latch,test,test]):
            move(*p,feed)
    move(x,near,test)     # slowly clear dock and dodge zone
    move(x,safe,travel)   # speed up only after verified Y clearance
    lines.append('M400')
    return '\n'.join(lines)

# Performance trial: open corridor 80mm/s; guided approach 8mm/s;
# latch / release lever stays at the original physically proven 3mm/s.
# Distinct opt-in only. Never applied to T0/T1+ single-tool controls,
# existing Standard, or original 30mm/s Faster profile.
PERFORMANCE_TRAVEL_FEED=4800
PERFORMANCE_APPROACH_FEED=480
PERFORMANCE_LATCH_FEED=180
PERFORMANCE_MARGIN_Y=15.0

def performance_cycle_script(path,kind,*,at_stage):
    """Explicit performance profile preserving exact CxChanger path & latch."""
    return faster_cycle_script(path,kind,at_stage=at_stage,
                               travel_feed=PERFORMANCE_TRAVEL_FEED,
                               test_feed=PERFORMANCE_APPROACH_FEED,
                               latch_feed=PERFORMANCE_LATCH_FEED,
                               margin_y=PERFORMANCE_MARGIN_Y,
                               _performance_limits=True)

# Two strictly opt-in SPEED TRIALS based on the validated CxChanger
# motion geometry. These feed rates are NOT commissioned for the
# assembled CXM. Advance one profile per supervised, witnessed pass;
# stop on impact, missed steps, latch trouble or unexpected tool state.
#
# Original CxChanger normal mode is considerably faster (~400 mm/s
# clear travel, ~83.3 mm/s coupling), but do not assume that the user's
# printed mechanism and XY acceleration can safely match it.
SPRINT_TRAVEL_FEED=9000      # 150 mm/s open corridor
SPRINT_APPROACH_FEED=1500    # 25 mm/s guided dock movement
SPRINT_LATCH_FEED=360       # 6 mm/s lever / latch action
RACE_TRAVEL_FEED=15000      # 250 mm/s open corridor
RACE_APPROACH_FEED=3000     # 50 mm/s guided dock movement
RACE_LATCH_FEED=720        # 12 mm/s lever / latch action
TRIAL_MARGIN_Y=15.0        # enter slow zone 15 mm outside Y dodge point

def sprint_cycle_script(path,kind,*,at_stage):
    """First-stage speed trial: never alters accepted docking positions."""
    return faster_cycle_script(path,kind,at_stage=at_stage,
                               travel_feed=SPRINT_TRAVEL_FEED,
                               test_feed=SPRINT_APPROACH_FEED,
                               latch_feed=SPRINT_LATCH_FEED,
                               margin_y=TRIAL_MARGIN_Y,
                               _trial_limits=True)

def race_cycle_script(path,kind,*,at_stage):
    """Second-stage speed trial: ONLY after supervised Sprint passes."""
    return faster_cycle_script(path,kind,at_stage=at_stage,
                               travel_feed=RACE_TRAVEL_FEED,
                               test_feed=RACE_APPROACH_FEED,
                               latch_feed=RACE_LATCH_FEED,
                               margin_y=TRIAL_MARGIN_Y,
                               _trial_limits=True)
