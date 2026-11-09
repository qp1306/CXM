"""Read-only native CXM compatibility helper for historic T0 status.

All Python-owned pickup, dropoff, sensor-wait motion loops and tool-state
mutation paths have been deleted. Klipper owns the active tool state.
"""
import urllib.parse
from cxm_lineux import _rpc

def mounted_other_tool(*,pid,revision):
    """Never silently infer tool identity from a shared occupancy switch."""
    query=urllib.parse.urlencode({
        'gcode_macro _CXM_NATIVE':'protocol,ready,current_tool,fault'})
    try:
        status=_rpc('/printer/objects/query?'+query).get('status',{}).get(
            'gcode_macro _CXM_NATIVE',{})
        if status.get('protocol')!=1 or status.get('ready')!=1 or status.get('fault')!=0:
            return -2  # unknown identity; historic T0 UI must not enable motion
        tool=status.get('current_tool',-2)
        if type(tool) is not int:
            return -2
        return tool if tool not in (-1,0) else None
    except (OSError,ValueError,KeyError,TypeError,RuntimeError):
        return -2
