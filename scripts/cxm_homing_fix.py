#!/usr/bin/env python3
"""CXM V0.9.3 Y-before-X safe homing correction.

Default mode is READ-ONLY. --apply edits only printer.cfg after Klipper is
confirmed ready and idle, makes a backup, and NEVER reloads or moves Klipper.

Public G28 X ALWAYS homes Y first, then X.
G28 Y homes only Y.
Full G28 retains the existing Z-lift / Y / X / Cartographer Z routine.

Supports both original CXM xyz override and previously installed v0.9.2
Z-only override. Refuses unknown changes and duplicate G28 macro definitions.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import urllib.request

OLD_Y = "{% set home_y = home_all or 'Y' in params or 'X' in params %}"
OLD_X = "{% set home_x = home_all or 'X' in params %}"
NEW_Y = ("{% set home_y = home_all or 'Y' in params or 'X' in params "
         "or ('Z' in params and 'y' not in printer.toolhead.homed_axes) %}")
NEW_X = ("{% set home_x = home_all or 'X' in params "
         "or ('Z' in params and 'x' not in printer.toolhead.homed_axes) %}")

# A public G28 wrapper enforces Y before X on EVERY normal G28 X command.
# G28.1 is the private renamed homing_override command. The override's own
# internal calls MUST also use G28.1 so they reach native Klipper homing
# when homing_override.in_script is set. This avoids extra Y homes and
# recursive macro execution.
PUBLIC_G28 = """
#####################################################################
# CXM — enforced Y-before-X homing; Z override remains authoritative
# Do not manually call the private G28.1 alias for normal operation.
#####################################################################
[gcode_macro G28]
description: CXM Y-first homing, with Cartographer Z override retained
rename_existing: G28.1
gcode:
    {% set all_axes = 'X' not in params and 'Y' not in params and 'Z' not in params %}
    {% set wants_x = 'X' in params %}
    {% set wants_y = 'Y' in params %}
    {% set wants_z = 'Z' in params %}
    {% if all_axes or (wants_z and (wants_x or wants_y)) %}
        # Full homing: Z override lifts, homes Y then X, then Cartographer Z.
        G28.1
    {% elif wants_z %}
        # Z-only: override homes any missing XY axes before Cartographer.
        G28.1 Z
    {% else %}
        # Even a standalone G28 X must home Y before X.
        {% if wants_y or wants_x %}
            G28.1 Y
        {% endif %}
        {% if wants_x %}
            G28.1 X
        {% endif %}
    {% endif %}
"""


def updated_config(original: str) -> str:
    """Minimal, fail-closed upgrade from original or v0.9.2 homing override."""
    if re.search(r"(?m)^\[gcode_macro[ \t]+G28\][ \t]*$", original):
        raise ValueError("G28 macro already defined. No change; inspect existing homing.")
    blocks = list(re.finditer(
        r"(?ms)^\[homing_override\][ \t]*(?:\r?\n)(?:(?!^\[).)*", original))
    if len(blocks) != 1:
        raise ValueError("Expected exactly one [homing_override] in printer.cfg")
    match = blocks[0]
    block = match.group(0)
    if not re.search(r"(?m)^set_position_z:[ \t]*0[ \t]*$", block):
        raise ValueError("Expected the known 'set_position_z: 0'. No change.")
    original_xyz = re.search(r"(?m)^axes:[ \t]*xyz[ \t]*$", block) is not None
    previous_z = re.search(r"(?m)^axes:[ \t]*z[ \t]*$", block) is not None
    if original_xyz and block.count(OLD_Y) == block.count(OLD_X) == 1:
        revised = re.sub(
            r"(?m)^axes:[ \t]*xyz[ \t]*$", "axes: z", block, count=1)
        revised = revised.replace(OLD_Y, NEW_Y).replace(OLD_X, NEW_X)
    elif previous_z and block.count(NEW_Y) == block.count(NEW_X) == 1:
        revised = block
    else:
        raise ValueError("Unknown homing override version or Y-first logic. No change.")
    for axis in "YXZ":
        # Requires exact standard G28 command lines; no exotic versions.
        pattern = r"(?m)^([ \t]*)G28[ \t]+" + axis + r"[ \t]*$"
        revised, count = re.subn(pattern, lambda m: m.group(1)+"G28.1 "+axis,
                                 revised)
        if count != 1:
            raise ValueError("Expected precisely one inner G28 "+axis+
                             " to rename. No change.")
    for required in ("G1 Z10 F300", "G1 X195 Y170 F6000",
                     "G1 Z5 F300", "set_position_z: 0"):
        if required not in revised:
            raise ValueError("Required Cartographer homing step missing: "+required)
    result = original[:match.start()] + revised + original[match.end():]
    return result.rstrip() + "\n\n" + PUBLIC_G28.strip() + "\n"

def check_other_macros(path: Path) -> None:
    """Prevent obvious duplicate G28 definitions in other active .cfg files."""
    for other in path.parent.glob("*.cfg"):
        if other == path or re.fullmatch(r"printer-\d{8}_\d{6}\.cfg",other.name):
            continue
        try:
            data=other.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError("Cannot inspect nearby config: "+str(other)) from exc
        if re.search(r"(?im)^\[gcode_macro[ \t]+G28\][ \t]*$",data):
            raise ValueError("Possible conflicting [gcode_macro G28] in "+str(other))

def idle_confirmed() -> bool:
    """Configuration changes only allowed when Moonraker confirms idle."""
    base = "http://127.0.0.1:7125/"
    def read(url):
        with urllib.request.urlopen(base + url, timeout=3) as response:
            return json.load(response)["result"]
    try:
        if read("printer/info")["state"] != "ready":
            return False
        names = read("printer/objects/list")["objects"]
        if "idle_timeout" not in names:
            return False
        query = ["idle_timeout"]
        if "print_stats" in names:
            query.append("print_stats")
        state = read("printer/objects/query?" + "&".join(query))["status"]
        if state["idle_timeout"]["state"] not in ("Idle", "Ready"):
            return False
        return "print_stats" not in names or state["print_stats"]["state"] in (
            "standby", "complete", "cancelled", "error")
    except (OSError, ValueError, KeyError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="CXM V0.9.3 enforced Y-before-X homing — preflight by default")
    parser.add_argument("--apply", action="store_true", help="Back up and apply the reviewed change")
    parser.add_argument("--file", type=Path,
                        default=Path.home() / "printer_data/config/printer.cfg")
    args = parser.parse_args(argv)
    path = args.file.expanduser()
    if not path.is_file() or path.is_symlink():
        raise SystemExit("Expected a regular, non-symlink printer.cfg: " + str(path))
    before = path.read_text(encoding="utf-8")
    try:
        check_other_macros(path)
        after = updated_config(before)
    except ValueError as exc:
        raise SystemExit("PRECHECK FAILED: " + str(exc)) from exc
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="printer.cfg (current)", tofile="printer.cfg (proposed)"))
    print("CXM HOMING FIX PREFLIGHT\n" + diff)
    print("ENFORCED: G28 X -> native Y home -> native X home (no Z reset/lift).")
    print("G28 Y -> native Y home. G28 -> original Z10, Y, X, Cartographer Z, Z5.")
    print("G28 Z -> original Z routine, which homes missing X/Y if needed.")
    print("XY-only homing has NO Z hop: independently confirm full-path clearance.")
    print("NEVER issue G28.1 directly as an operator command; it is a private alias.")
    if not args.apply:
        print("\nDRY RUN ONLY. No files changed. Apply with --apply when Klipper is idle.")
        return 0
    if not idle_confirmed():
        raise SystemExit("APPLY BLOCKED: Klipper not positively confirmed ready and idle.")
    # Protect against conflicting edits between read and write.
    if path.read_text(encoding="utf-8") != before:
        raise SystemExit("APPLY BLOCKED: printer.cfg changed during preflight.")
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name("printer.cfg.cxm-before-homing-" + suffix + ".bak")
    if backup.exists():
        raise SystemExit("APPLY BLOCKED: backup path already exists.")
    shutil.copy2(path, backup)
    fd, tmp = tempfile.mkstemp(prefix=".cxm-homing-", suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(fd, stat.S_IMODE(path.stat().st_mode))
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            output.write(after)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if path.read_text(encoding="utf-8") != after:
        raise SystemExit("POSTCHECK FAILED: file content mismatch; restore backup " + str(backup))
    print("\nAPPLIED TO DISK AND VERIFIED. BACKUP: " + str(backup))
    print("Klipper is STILL running the prior configuration until you perform ONE")
    print("intentional RESTART in Mainsail while safely parked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
