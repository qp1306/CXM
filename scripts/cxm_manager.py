#!/usr/bin/env python3
"""CXM Control Centre v0.1 installer. Dry-run by default; never edits Klipper."""
import argparse
import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

REPO = "qp1306/CXM"
URL = "https://github.com/qp1306/CXM.git"
INCLUDE = "    include /etc/nginx/snippets/cxm.conf;"
SECTION = "[update_manager CXM]"

def run(*args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True,
                          text=True, timeout=90).stdout.strip()

def save(path, content, privileged=False):
    """Write config atomically on its own filesystem; sudo install copies nginx snippets.

    A temp file under /tmp cannot be atomically renamed into a different mount,
    including a bind-mounted printer_data/config directory (errno.EXDEV).
    """
    target = Path(path)
    temp_dir = None if privileged else target.parent
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=temp_dir,
        prefix=f".{target.name}.cxm-", delete=False
    ) as f:
        temp = f.name
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    try:
        if privileged:
            run("sudo", "install", "-m", "644", temp, target)
        else:
            mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
            os.chmod(temp, mode)
            os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)

def repository_check(root):
    if not (root / ".git").is_dir():
        raise RuntimeError("Existing CXM path is not a Git clone")
    if run("git", "-C", root, "remote", "get-url", "origin") not in (URL, URL[:-4]):
        raise RuntimeError("CXM Git remote does not match qp1306/CXM")
    if run("git", "-C", root, "branch", "--show-current") != "main":
        raise RuntimeError("CXM clone is not on main")
    if run("git", "-C", root, "status", "--porcelain"):
        raise RuntimeError("CXM Git clone has local modifications")
    if not (root / "web" / "index.html").is_file():
        raise RuntimeError("Missing web/index.html in CXM clone")

def snippet_text(root):
    path = str(root / "web")
    if not re.fullmatch(r"[/A-Za-z0-9_.-]+", path):
        raise RuntimeError("Unsupported installation path characters")
    return (f"# CXM Control Centre v0.1\n"
            f"location /cxm/ {{\n    alias {path}/;\n    index index.html;\n}}\n"
            f"location = /cxm/index.html {{\n    alias {path}/index.html;\n"
            f"    add_header Cache-Control \"no-store\";\n}}\n")

def main():
    p = argparse.ArgumentParser(description="Install CXM dashboard and updater; Klipper untouched")
    p.add_argument("action", choices=("install", "verify"))
    p.add_argument("--apply", action="store_true", help="Approve changes after dry run")
    p.add_argument("--path", default=str(Path.home() / "CXM"))
    p.add_argument("--config-dir", default=str(Path.home() / "printer_data/config"))
    p.add_argument("--nginx-site", default="/etc/nginx/sites-available/mainsail")
    args = p.parse_args()
    root = Path(args.path).expanduser().resolve()
    config = Path(args.config_dir).expanduser().resolve()
    moon = config / "moonraker.conf"
    nginx = Path(args.nginx_site)
    snippet = Path("/etc/nginx/snippets/cxm.conf")
    if not moon.is_file() or not nginx.is_file():
        raise RuntimeError("Expected Moonraker config and Mainsail nginx site not found; no changes made")
    if root.exists():
        repository_check(root)
    m = moon.read_text(encoding="utf-8")
    n = nginx.read_text(encoding="utf-8")
    existing = re.search(r"(?ms)^\[update_manager CXM\]\s*$(.*?)(?=^\[|\Z)", m)
    if existing and (URL not in existing.group(1) or str(root) not in existing.group(1)):
        raise RuntimeError("Existing CXM update manager targets a different repository/path")
    add_moon = not existing
    add_nginx = INCLUDE.strip() not in n
    new_snippet = snippet_text(root)
    if snippet.exists() and snippet.read_text(encoding="utf-8") != new_snippet:
        raise RuntimeError("An unrelated CXM nginx snippet exists; refusing to overwrite")
    if add_nginx:
        marker = list(re.finditer(r"(?m)^ {4}location /websocket\s*\{", n))
        if len(marker) != 1:
            raise RuntimeError("Unknown Mainsail nginx layout; expected one websocket location")
        n = n[:marker[0].start()] + INCLUDE + "\n\n" + n[marker[0].start():]
    if add_moon:
        m = m.rstrip() + ("" if "[update_manager]\n" in m else "\n\n[update_manager]\n") + (
            "\n[update_manager CXM]\n"
            "type: git_repo\nchannel: dev\n"
            f"path: {root}\norigin: {URL}\nprimary_branch: main\n"
            "is_system_service: False\n")
    if args.action == "verify":
        checks = {
            "Git clone": root.exists(),
            "CXM update manager": bool(existing),
            "CXM nginx include": not add_nginx,
            "CXM nginx snippet": snippet.exists(),
        }
        for key, ok in checks.items():
            print(("OK" if ok else "MISSING") + ": " + key)
        return 0 if all(checks.values()) else 1
    print(f"Repository: {URL}")
    print(f"Git checkout: {root} ({'existing' if root.exists() else 'clone on apply'})")
    print("Moonraker update manager:", "already configured" if not add_moon else "add CXM")
    print("Nginx route:", "already configured" if not add_nginx else "add /cxm/")
    print("Changes never edit printer.cfg or restart Klipper.")
    if not args.apply:
        print("DRY RUN: use --apply after reviewing this plan.")
        return 0
    if not root.exists():
        run("git", "clone", "--branch", "main", "--single-branch", URL, root)
    else:
        # The first attempt may have cloned CXM before failing on a config write.
        # Move a clean existing clone forward without discarding local edits.
        repository_check(root)
        run("git", "-C", root, "pull", "--ff-only", "origin", "main")
    repository_check(root)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backups = []
    try:
        if add_moon:
            dest = moon.with_name(moon.name + ".before-cxm-" + stamp)
            shutil.copy2(moon, dest)
            backups.append((moon, dest, False))
            save(moon, m)
        if not snippet.exists():
            save(snippet, new_snippet, privileged=True)
            backups.append((snippet, None, True))
        if add_nginx:
            dest = nginx.with_name(nginx.name + ".before-cxm-" + stamp)
            run("sudo", "cp", nginx, dest)
            backups.append((nginx, dest, False))
            save(nginx, n, privileged=True)
        run("sudo", "nginx", "-t")
        if add_nginx:
            run("sudo", "systemctl", "reload", "nginx")
        if add_moon:
            run("sudo", "systemctl", "restart", "moonraker")
    except Exception:
        for target, previous, created in reversed(backups):
            try:
                if created:
                    run("sudo", "rm", "-f", target)
                elif target == moon:
                    shutil.copy2(previous, target)
                else:
                    run("sudo", "cp", previous, target)
            except Exception as err:
                print("WARNING: restore failed for", target, err)
        raise
    print("Installed. Open http://YOUR-PRINTER-IP/cxm/ (no Klipper restart).")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("CXM install/verify failed:", exc)
        raise SystemExit(1)
