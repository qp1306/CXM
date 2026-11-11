#!/usr/bin/env python3
"""CXM native toolchange installer. Read-only preflight unless --apply."""
import argparse
import glob
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import tempfile

INCLUDE = '[include cxm_native_toolchange.cfg]'
MACROS = ('CXM_CAMERA', 'CXM_SPEED_REPORT', 'CXM_MANUAL_DOCK_JOG', 'CXM_CALIBRATION_RELEASE', 'CXM_SELECT_TOOL', '_CXM_NATIVE', '_CXM_PREPARE_CLEARANCE', '_CXM_STAGE_TEST',
          'CXM_DECLARE_CARRIAGE', 'CXM_RECOVER', '_CXM_CLEAR_TRANSFER', '_CXM_CHECK_TOOL',
          '_CXM_PICKUP_MOTION', '_CXM_RELEASE_MOTION',
          '_CXM_VERIFY', '_CXM_COMMIT_STATE', 'CXM_CONFIRM_EMPTY',
          '_CXM_TEST_STATE', 'CXM_TEST_START', 'CXM_TEST_STOP',
          'CXM_SET_PROFILE', 'CXM_TEST_RESET', '_CXM_TEST_ADVANCE')


def atomic_write(path, contents):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(contents)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def included_macro_collisions(printer, names):
    """Detect native macro collisions in printer.cfg and local includes."""
    visited = set()
    collisions = []

    def visit(path):
        path = path.resolve()
        if path in visited:
            return
        visited.add(path)
        if not path.is_file():
            raise RuntimeError('Missing Klipper include: ' + str(path))
        raw = path.read_text('utf8')
        for name in names:
            pattern = r'(?mi)^\s*\[gcode_macro\s+' + re.escape(name) + r'\s*\]\s*$'
            if re.search(pattern, raw):
                collisions.append((name, str(path)))
        include_pattern = r'(?mi)^\s*\[include\s+([^\]]+)\s*\]\s*$'
        for pattern in re.findall(include_pattern, raw):
            pattern = pattern.strip()
            if pattern == 'cxm_native_toolchange.cfg':
                continue
            matches = glob.glob(str(path.parent / pattern))
            if not matches:
                raise RuntimeError('Unresolved Klipper include: ' + pattern)
            for match in matches:
                visit(Path(match))

    visit(printer)
    return collisions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--repo', type=Path, default=Path.home() / 'CXM')
    ap.add_argument('--printer-config', type=Path,
                    default=Path.home() / 'printer_data/config/printer.cfg')
    args = ap.parse_args()
    source = (args.repo / 'vendor/cxm/cxm_native_toolchange.cfg').expanduser().resolve()
    printer = args.printer_config.expanduser().resolve()
    target = printer.parent / 'cxm_native_toolchange.cfg'
    if not source.is_file() or not printer.is_file():
        raise RuntimeError('Missing native source or printer.cfg')
    content = source.read_bytes()
    original = printer.read_text('utf8')
    for name in MACROS:
        if content.count(('[gcode_macro ' + name + ']').encode()) != 1:
            raise RuntimeError('Missing or duplicate native macro: ' + name)
    if content.count(b'[delayed_gcode CXM_NATIVE_TEST_STEP]') != 1:
        raise RuntimeError('Missing delayed native test controller')
    if content.count(b'[delayed_gcode CXM_ACCEL_RESTORE]') != 1:
        raise RuntimeError('Missing acceleration restoration watchdog')
    collisions = included_macro_collisions(printer, MACROS)
    if collisions:
        raise RuntimeError('Existing macro definitions collide with native CXM: ' +
                           ', '.join(name + ' in ' + location
                                     for name, location in collisions))
    if not re.search(r'(?mi)^\s*\[include\s+cxm_fast_guard\.cfg\s*\]\s*$', original):
        raise RuntimeError('Existing CXM_FAST_VERIFY guard include is required')
    installed = re.findall(r'(?mi)^\s*\[include\s+cxm_native_toolchange\.cfg\s*\]\s*$', original)
    if len(installed) > 1:
        raise RuntimeError('Duplicate native include')
    upgrading = target.exists() and target.read_bytes() != content
    if installed and target.exists() and not upgrading:
        print('Already installed and identical. No changes.')
        return
    if upgrading and not installed:
        raise RuntimeError('Native macro file exists but is not included: review manually')
    if installed and not target.exists():
        raise RuntimeError('Native macro is included but missing from disk: review manually')
    if upgrading:
        import difflib
        old_lines = target.read_text('utf8').splitlines(keepends=True)
        new_lines = content.decode('utf8').splitlines(keepends=True)
        delta = ''.join(difflib.unified_diff(old_lines, new_lines,
                        fromfile='installed native macro',
                        tofile='updated native macro', n=3))
        print('UPGRADE REVIEW — native Klipper macro differences:')
        print(delta)
        if len(delta) > 15000:
            raise RuntimeError('Macro upgrade diff too large for automatic review')
    marker = '#*# <---------------------- SAVE_CONFIG'
    if not installed:
        revised = (original.replace(marker, INCLUDE + '\n\n' + marker, 1)
                   if marker in original
                   else original.rstrip() + '\n\n' + INCLUDE + '\n')
    else:
        revised = original
    print('Printer:', printer)
    print('Source:', source)
    print('Destination:', target)
    print('New include required:', not bool(installed))
    print('Update installed macro required:', upgrading)
    print('No printer motion, no restart, no accepted XY changes.')
    if not args.apply:
        print('DRY RUN. Review before rerunning with --apply.')
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = printer.parent / 'cxm_backups' / ('native-' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(printer, backup / 'printer.cfg')
    if target.exists():
        shutil.copy2(target, backup / target.name)
    created = not target.exists()
    try:
        if created or upgrading:
            atomic_write(target, content)
        if revised != original:
            atomic_write(printer, revised.encode('utf8'))
    except BaseException:
        atomic_write(printer, (backup / 'printer.cfg').read_bytes())
        if created:
            target.unlink(missing_ok=True)
        elif upgrading:
            atomic_write(target, (backup / target.name).read_bytes())
        raise
    print('Installed. Backups:', backup)
    print('One deliberate Klipper RESTART is required after inspection.')
    print('Rehome XYZ, synchronize accepted XY in Control Centre, then confirm EMPTY.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print('CXM NATIVE INSTALL REFUSED:', exc)
        raise SystemExit(2)
