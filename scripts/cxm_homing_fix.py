#!/usr/bin/env python3
"""CXM homing override correction — read-only preflight unless --apply.

Only the known CXM [homing_override] in printer.cfg is modified.
A hardware change is NOT made automatically and Klipper is never restarted
by this script. Use one deliberate FIRMWARE_RESTART after reviewing the diff.
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


def updated_config(original: str) -> str:
    """Produce a minimal update, or fail closed on an unfamiliar macro."""
    blocks = list(re.finditer(r"(?ms)^\[homing_override\][ \t]*(?:\r?\n)(?:(?!^\[).)*", original))
    if len(blocks) != 1:
        raise ValueError("Expected exactly one [homing_override] in printer.cfg")
    match = blocks[0]
    block = match.group(0)
    if not re.search(r"(?m)^axes:[ \t]*xyz[ \t]*$", block):
        raise ValueError("Expected the known 'axes: xyz' setting. No change.")
    if not re.search(r"(?m)^set_position_z:[ \t]*0[ \t]*$", block):
        raise ValueError("Expected the known 'set_position_z: 0' setting. No change.")
    if block.count(OLD_Y) != 1 or block.count(OLD_X) != 1:
        raise ValueError("Unexpected Y-first/X homing logic. Review config manually.")
    for required in ("G1 Z10 F300", "G28 Y", "G28 X", "G28 Z",
                     "G1 X195 Y170 F6000", "G1 Z5 F300"):
        if required not in block:
            raise ValueError("Expected homing command is missing: " + required)
    revised = re.sub(r"(?m)^axes:[ \t]*xyz[ \t]*$", "axes: z", block, count=1)
    revised = revised.replace(OLD_Y, NEW_Y).replace(OLD_X, NEW_X)
    return original[:match.start()] + revised + original[match.end():]


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
    parser = argparse.ArgumentParser(description="CXM Y-first homing correction — preflight by default")
    parser.add_argument("--apply", action="store_true", help="Back up and apply the reviewed change")
    parser.add_argument("--file", type=Path,
                        default=Path.home() / "printer_data/config/printer.cfg")
    args = parser.parse_args(argv)
    path = args.file.expanduser()
    if not path.is_file() or path.is_symlink():
        raise SystemExit("Expected a regular, non-symlink printer.cfg: " + str(path))
    before = path.read_text(encoding="utf-8")
    try:
        after = updated_config(before)
    except ValueError as exc:
        raise SystemExit("PRECHECK FAILED: " + str(exc)) from exc
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="printer.cfg (current)", tofile="printer.cfg (proposed)"))
    print("CXM HOMING FIX PREFLIGHT\n" + diff)
    print("Effect: G28 Y and G28 X now use native XY homing WITHOUT resetting/lifting Z.")
    print("Full G28 still uses the existing 10 mm lift, Y, X, Cartographer Z and 5 mm raise.")
    print("G28 X alone NO LONGER automatically homes Y first. For calibration use")
    print("two separate commands in order: G28 Y, then G28 X.")
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
    print("intentional FIRMWARE_RESTART in Mainsail while safely parked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
