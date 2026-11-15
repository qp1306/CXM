#!/usr/bin/env python3
"""CXM 2026-11-15 source staging. Default: preflight only, no GitHub writes."""
import argparse, ast, pathlib, re, shutil, subprocess, sys, tempfile, zipfile

HOME=pathlib.Path.home()
BRANCH="docs/golden-baseline-2026-11-15"
REPO="https://github.com/qp1306/CXM.git"
SECRET=re.compile(r'(?i)(password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret|private[_-]?key|authorization)\s*[:=]\s*["\']?([^\s"\',}\]]{8,})')

def run(cmd,cwd=None):
    p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return p.returncode,p.stdout

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--source",type=pathlib.Path,default=HOME/"CXM_Golden_Backup/CXM_SOURCE_2026-11-15.zip")
    a=ap.parse_args()
    guard=HOME/"printer_data/config/cxm_fast_guard.cfg"
    if not a.source.is_file() or not guard.is_file():
        sys.exit("STOP: source ZIP and live cxm_fast_guard.cfg must be present on Pi")
    with tempfile.TemporaryDirectory(prefix="cxm-github-preflight-") as tmp:
        dest=pathlib.Path(tmp)/"repo"
        rc,out=run(["git","clone","--quiet","--single-branch","--branch",BRANCH,REPO,str(dest)])
        if rc: sys.exit("STOP: Git clone failed:\n"+out[-1000:])
        paths=[]
        with zipfile.ZipFile(a.source) as z:
            for e in z.infolist():
                if e.is_dir(): continue
                rel=pathlib.PurePosixPath(e.filename)
                if rel.is_absolute() or ".." in rel.parts or rel.parts[0] not in {"server","web","scripts","tests","klipper"}:
                    sys.exit("STOP: invalid ZIP path: "+e.filename)
                f=dest.joinpath(*rel.parts)
                f.parent.mkdir(parents=True,exist_ok=True)
                f.write_bytes(z.read(e))
                paths.append(f)
        macro=dest/"klipper/cxm_native_toolchange.cfg"
        if not macro.is_file(): sys.exit("STOP: live Klipper macro not in ZIP")
        v=dest/"vendor/cxm"
        v.mkdir(parents=True,exist_ok=True)
        shutil.copy2(macro,v/"cxm_native_toolchange.cfg")
        shutil.copy2(guard,v/"cxm_fast_guard.cfg")
        paths += [v/"cxm_native_toolchange.cfg",v/"cxm_fast_guard.cfg"]
        problems=[]
        for f in paths:
            try: s=f.read_text()
            except UnicodeError: problems.append(str(f.relative_to(dest))+": nontext");continue
            if f.suffix==".py":
                try: ast.parse(s)
                except SyntaxError as e: problems.append(f"{f.name}: {e}")
            if f.suffix in (".js",".cjs") and shutil.which("node"):
                rc,out=run(["node","--check",str(f)])
                if rc: problems.append(f"{f.name}: JS syntax failed")
            for i,line in enumerate(s.splitlines(),1):
                if SECRET.search(line):
                    problems.append(f"{f.relative_to(dest)}:{i}: possible embedded secret")
        if problems:
            print("\n".join(problems[:40]))
            sys.exit("STOP: source audit failed, no GitHub changes")
        rc,out=run(["git","add","--","server","web","scripts","tests","klipper/cxm_native_toolchange.cfg","vendor/cxm"],dest)
        if rc: sys.exit("STOP: git add failed: "+out)
        _,stat=run(["git","diff","--cached","--stat"],dest)
        print("=== PROPOSED SOURCE CHANGES ===\n"+stat[-10000:])
        rc,out=run([sys.executable,"-m","unittest","discover","-s","tests","-p","test_*.py","-q"],dest)
        print("=== TEST RESULTS ===\n"+"\n".join(out.splitlines()[-30:]))
        if rc: sys.exit("STOP: regression tests failed, no GitHub changes")
        if not a.apply:
            print("PASS: preflight finished; GitHub and printer are unchanged")
            return
        rc,out=run(["git","-c","user.name=CXM Baseline Publisher","-c","user.email=cxm-baseline@users.noreply.github.com","commit","-m","sync: 2026-11-15 CXM active source"],dest)
        if rc:
            if "nothing to commit" in out: print("No source changes to publish");return
            sys.exit("STOP: commit failed: "+out[-1000:])
        rc,out=run(["git","push","origin","HEAD:"+BRANCH],dest)
        if rc: sys.exit("STOP: push failed: "+out[-1000:])
        print("PUBLISHED: https://github.com/qp1306/CXM/pull/107")

if __name__=="__main__": main()
