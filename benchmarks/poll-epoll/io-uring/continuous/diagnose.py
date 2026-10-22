#!/usr/bin/env python3
"""Correctness-only EOF diagnosis. Never labels these timings performance data."""
import argparse
import json
from pathlib import Path
import subprocess
import time

def main():
    p=argparse.ArgumentParser();p.add_argument("binary",type=Path);p.add_argument("output",type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    with (args.output/"diagnostic.jsonl").open("x") as f:
        for run in range(3):
            for mode in ("epoll","oneshot","multishot"):
                cmd=[str(args.binary),mode,"64","64","64","10000","200",str(2026102200+run),"burst","32","2","3","-"]
                before=time.time()
                try:
                    proc=subprocess.run(cmd,text=True,capture_output=True,timeout=20)
                    row=dict(run=run,mode=mode,command=cmd,utc=before,exit=proc.returncode,stdout=proc.stdout,stderr=proc.stderr)
                except subprocess.TimeoutExpired as err:
                    row=dict(run=run,mode=mode,command=cmd,utc=before,exit=None,error=str(err))
                row["purpose"]="correctness diagnosis only; not performance measurement"
                f.write(json.dumps(row)+"\n");f.flush()
                print(f"run={run} {mode} exit={row['exit']}",flush=True)

if __name__=="__main__":main()
