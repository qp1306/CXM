"""Reconcile a revision 6 Pi checkout with an explicitly fetched CXM release."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

BASELINE = '4d179da59c16c2c34cc737a7fbc733a945b1f017'
TRACKED = ('server/cxm_native.py', 'web/cxm-multi.js', 'web/index.html')
OLD_BACKUP = 'web/index.html.bak-carriage-button'
MACRO = 'vendor/cxm/cxm_native_toolchange.cfg'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    home = Path.home()
    repo = home / 'CXM'
    config = home / 'printer_data/config'

    def git(*args):
        return subprocess.check_output(['git', '-C', repo, *args])

    def require(condition, why):
        if not condition:
            raise SystemExit(why)

    head = git('rev-parse', 'HEAD').decode().strip()
    target = git('rev-parse', '--verify', 'origin/main^{commit}').decode().strip()
    require(target == args.release, 'Fetch origin/main and use its reviewed full release SHA.')
    require(git('branch', '--show-current').strip() == b'main', 'Expected the main checkout.')
    git('merge-base', '--is-ancestor', head, target)
    require(not git('diff', '--cached', '--name-only'), 'Preserve staged work before proceeding.')
    dirty = git('diff', '--name-only').decode().splitlines()
    extra = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
    require(set(dirty) <= set(TRACKED) and set(extra) <= {OLD_BACKUP}, 'Other local changes need review.')
    for name in dirty:
        require((repo / name).read_bytes() in (git('show', BASELINE + ':' + name), git('show', target + ':' + name)),
                'Local edits differ from reviewed revision 6: ' + name)
    live = config / 'cxm_native_toolchange.cfg'
    calibration = config / 'CXM_variables.cfg'
    require(calibration.is_file(), 'Calibration file missing.')
    require(live.read_bytes() == git('show', target + ':' + MACRO),
            'Installed motion macro differs from GitHub. Keep the working copy and compare before updating.')
    def read(url):
        with urlopen('http://127.0.0.1' + url, timeout=8) as reply:
            return json.load(reply)
    status = read(':7125/printer/objects/query?gcode_macro%20_CXM_NATIVE=four_move_revision&print_stats=state&idle_timeout=state')['result']['status']
    require(status['gcode_macro _CXM_NATIVE']['four_move_revision'] == 6, 'Klipper must already be running revision 6.')
    require(status['print_stats']['state'] not in ('printing', 'paused') and status['idle_timeout']['state'] != 'Printing',
            'Wait for the printer to become idle.')
    state = read('/cxm/api/v1/native/status')
    require(state['running'] is False and state['sensor'] == 'RELEASED', 'Finish the test and confirm an empty carriage.')
    print('Preflight passed. Live and release macros are byte-identical.')
    if not args.apply or (target == head and not dirty and not extra):
        return
    backup = Path(tempfile.mkdtemp(prefix='cxm-rev6-', dir=home))
    print('Backup:', backup, flush=True)
    for name in (*TRACKED, *extra):
        path = backup / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / name, path)
    for path in (live, calibration):
        shutil.copy2(path, backup / path.name)
    if dirty or extra:
        git('stash', 'push', '--include-untracked', '-m', 'CXM revision 6 before ' + target, '--', *dirty, *extra)
    git('merge', '--ff-only', target)
    require(not git('status', '--porcelain'), 'Inspect remaining local changes before restarting.')
    require(calibration.read_bytes() == (backup / calibration.name).read_bytes(), 'Calibration changed during update.')
    print('Checkout reconciled. Restart cxm-config.service and refresh the Control Centre.')


if __name__ == '__main__':
    main()
