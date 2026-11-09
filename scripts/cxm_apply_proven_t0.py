#!/usr/bin/env python3
"""Save verified T0 motion baseline; read-only by default.

The dock X/Y is already stored from the Control Centre's physical alignment.
Do NOT overwrite it. This action applies global X+4.4/Y+100 motion settings,
with a revision-checked atomic file backup and without physical movement.
"""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from cxm_config import Store
from cxm_cxchanger import plan
from cxm_native import _native_status, invalidate_for_config_edit
from cxm_service import printer_safe

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--apply',action='store_true',help='Save motion globals after live checks')
    p.add_argument('--config-dir',default=str(Path.home()/'printer_data/config'))
    args=p.parse_args()
    store=Store(args.config_dir)
    current=store.read()
    t0=current['config']['tools'][0]
    x=t0['dock_x'];y=t0['dock_y']
    if (current['migration_required'] or t0['dock_reference_accepted'] is not True
        or x is None or y is None or abs(x-304.60)>0.05 or abs(y-65.60)>0.05):
        raise SystemExit('STOP: accepted T0 dock X/Y must match the proven X304.60 Y65.60 (+/- 0.05). No changes.')
    proposed=store.read()
    proposed['config']['globals']['cxm_shift_x']=4.4
    proposed['config']['globals']['cxm_safe_clearance_y']=100.0
    # Validate every accepted tool with the NEW global geometry before
    # changing any settings. A stale accepted dock near an axis limit must
    # never become an armed, out-of-bounds pickup/dropoff path.
    active=proposed['config']['globals']['tool_count']
    invalid=[]
    for number in range(active):
        candidate=proposed['config']['tools'][number]
        if candidate['maintenance_lockout'] or not candidate['dock_reference_accepted']:
            continue
        try:
            candidate_plan=plan(proposed,tool=number)
        except (ValueError,KeyError,TypeError) as exc:
            invalid.append('T%d: %s'%(number,exc))
            continue
        print('T%d verified geometric envelope: pickup %s, dropoff %s'%(
            number,candidate_plan['pickup'],candidate_plan['dropoff']))
    if invalid:
        raise SystemExit('STOP: accepted tool geometry incompatible with proven motion; '
                         'no changes made. '+ '; '.join(invalid))
    geometry=plan(proposed,tool=0)
    print('T0 accepted dock (untouched): X%.5f Y%.5f'%(x,y))
    print('Pickup path:',geometry['pickup'])
    print('Dropoff path:',geometry['dropoff'])
    print('Baseline: X+4.4 mm, Y+100 mm, F6000 mm/min')
    print('Existing globals: shift=%s clearance=%s'%(
        current['config']['globals']['cxm_shift_x'],
        current['config']['globals']['cxm_safe_clearance_y']))
    if not args.apply:
        print('DRY RUN. No geometry changed. Run again with --apply to save.')
        return
    if not printer_safe():
        raise SystemExit('STOP: Klipper printer is not idle.')
    native,test,sensor=_native_status()
    if test.get('running')==1 or sensor!='RELEASED':
        raise SystemExit('STOP: Tool cycle running or carriage not physically EMPTY (sensor RELEASED).')
    if (current['config']['globals']['cxm_shift_x']==4.4
        and current['config']['globals']['cxm_safe_clearance_y']==100.0):
        print('ALREADY SAVED: no changes.')
        return
    # Disable stale native geometry FIRST. No G0/G1, no printer restart.
    invalidate_for_config_edit()
    result=store.apply_verified_t0_motion(current['revision'])
    actual=store.read()
    assert actual['config']['globals']['cxm_shift_x']==4.4
    assert actual['config']['globals']['cxm_safe_clearance_y']==100.0
    assert actual['config']['tools'][0]['dock_x']==x
    assert actual['config']['tools'][0]['dock_y']==y
    print('SAVED AND VERIFIED. Backup:',result.get('backup','unchanged'))
    print('Native geometry invalidated; next LOAD automatically syncs accepted coordinates.')

if __name__=='__main__':
    main()
