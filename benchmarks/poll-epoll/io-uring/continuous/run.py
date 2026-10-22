#!/usr/bin/env python3
"""Frozen-plan runner. Correctness, exploration and confirmation never share raw files."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MODES = ("epoll", "oneshot", "multishot")

def command(args, **kwargs):
    return subprocess.run(list(map(str, args)), text=True, capture_output=True, **kwargs)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def conditions():
    base = dict(fds=256, percent=10, payload=256, pattern="uniform", rate=50000, batch=32)
    result = {}
    def add(c):
        c = dict(c, active=max(1, math.ceil(c["fds"] * c["percent"] / 100)))
        key = json.dumps(c, sort_keys=True)
        result[key] = c
    for key, values in dict(fds=[64,256,1024,4096], percent=[1,10,50,100], payload=[64,256,1024,4096], pattern=["burst","uniform","randomized"], rate=[10000,50000,200000,1000000]).items():
        for value in values:
            add(dict(base, **{key: value}))
    for n, percent in itertools.product([64,256,1024,4096], [1,10,50,100]):
        add(dict(base, fds=n, percent=percent, payload=1024, rate=200000))
    return [result[key] for key in sorted(result)]

def metadata(args, out, zig):
    def read(path):
        try: return Path(path).read_text().strip()
        except OSError: return None
    sources = {str(p.relative_to(ROOT)): digest(p) for p in HERE.rglob("*") if p.is_file() and "results" not in p.parts and p.suffix in (".zig", ".py")}
    for p in [HERE.parent/"ring.zig", HERE.parent.parent/"workload.zig", HERE.parent.parent/"metrics.zig"]:
        sources[str(p.relative_to(ROOT))] = digest(p)
    env = dict(start_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()), uname=platform.uname()._asdict(), os_release=read("/etc/os-release"),
        zig=command([zig,"version"]).stdout.strip(), git=command(["git","rev-parse","HEAD"],cwd=ROOT).stdout.strip(),
        virt=command(["systemd-detect-virt"]).stdout.strip(), affinity=sorted(os.sched_getaffinity(0)),
        consumer_cpu=args.consumer_cpu, producer_cpu=args.producer_cpu,
        siblings={str(c):read(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list") for c in (args.consumer_cpu,args.producer_cpu)},
        cpuinfo=read("/proc/cpuinfo"), cmdline=list(map(str,os.sys.argv)), sources=sources,
        optimization="ReleaseFast", libc=False, byteorder="little (x86_64/aarch64)", timing="strace excluded")
    import resource
    env["nofile"] = resource.getrlimit(resource.RLIMIT_NOFILE)
    (out/"environment.json").write_text(json.dumps(env,indent=2)+"\n")
    if env["zig"] != "0.17.0": raise RuntimeError("Zig 0.17.0 required")
    if str(args.producer_cpu) in (env["siblings"][str(args.consumer_cpu)] or "").replace("-",",").split(","):
        raise RuntimeError("Producer/Consumer may share physical core")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("stage",choices=["correctness","exploration","confirmation","batch","representative"])
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--zig",default="zig")
    ap.add_argument("--consumer-cpu",type=int,default=2)
    ap.add_argument("--producer-cpu",type=int,default=3)
    ap.add_argument("--confirmation-plan",type=Path)
    args=ap.parse_args()
    out=args.output.resolve()
    if out.exists(): raise RuntimeError("Refuse to overwrite existing series")
    out.mkdir(parents=True)
    metadata(args,out,args.zig)
    binary=out/"bench"
    build=command([args.zig,"build-exe",ROOT/"benchmarks/poll-epoll/continuous-main.zig","-O","ReleaseFast",f"-femit-bin={binary}"])
    (out/"build.log").write_text(build.stdout+build.stderr)
    build.check_returncode()
    (out/"binary-sha256.txt").write_text(digest(binary)+"\n")
    if args.stage == "correctness":
        test=command([args.zig,"test",ROOT/"benchmarks/poll-epoll/continuous-tests.zig","-O","ReleaseFast"],timeout=180)
        (out/"tests.log").write_text(test.stdout+test.stderr)
        test.check_returncode()
        cases=[]
        for n,active,payload,pattern in [(1,0,64,"uniform"),(1,1,64,"burst"),(64,1,4096,"randomized"),(64,64,64,"burst"),(256,26,256,"uniform"),(1024,1024,1024,"burst"),(4096,41,1024,"uniform")]:
            cases.append(dict(fds=n,active=active,payload=payload,pattern=pattern,rate=10000,batch=32,percent=100*active/n))
        runs, duration, seed = 1, 200, 2026102200
    elif args.stage == "exploration":
        cases=conditions(); runs,duration,seed=3,500,2026102201
    elif args.stage == "confirmation":
        if not args.confirmation_plan: raise RuntimeError("Frozen confirmation plan required")
        plan=json.loads(args.confirmation_plan.read_text()); cases=plan["conditions"]
        (out/"confirmation-plan.json").write_text(args.confirmation_plan.read_text())
        runs,duration,seed=20,1000,2026102301
    elif args.stage == "batch":
        cases=[dict(fds=256,active=26,percent=10,payload=256,pattern="uniform",rate=200000,batch=b) for b in (1,8,32,256)]
        runs,duration,seed=10,500,2026102401
    else:
        cases=[conditions()[0], dict(fds=256,active=26,percent=10,payload=256,pattern="uniform",rate=50000,batch=32)]
        runs,duration,seed=10,500,2026102501
    (out/"plan.json").write_text(json.dumps(dict(stage=args.stage,cases=cases,runs=runs,duration_ms=duration,seed=seed),indent=2)+"\n")
    schedule=[]
    for warmup in ([False] if args.stage=="correctness" else [True,False]):
        groups=[(i,run) for i in range(len(cases)) for run in range(1 if warmup else runs)]
        random.Random(seed+int(warmup)).shuffle(groups)
        for i,run in groups:
            modes=list(MODES)
            random.Random(seed+i*1000+run+int(warmup)*100000).shuffle(modes)
            for mode in modes: schedule.append(dict(case=i,run=run,mode=mode,warmup=warmup,seed=seed+run+(100000 if warmup else 0)))
    (out/"schedule.json").write_text(json.dumps(schedule,indent=2)+"\n")
    with (out/"raw.jsonl").open("x") as raw:
        for number,item in enumerate(schedule):
            c=cases[item["case"]]
            times=out/f"send-{number:05}.u64le"
            cmd=[binary,item["mode"],c["fds"],c["active"],c["payload"],c["rate"],duration,item["seed"],c["pattern"],c["batch"],args.consumer_cpu,args.producer_cpu,times]
            before=dict(loadavg=Path("/proc/loadavg").read_text().strip(), utc=time.time())
            proc=command(cmd,timeout=40)
            row=dict(item,condition=c,sequence=number,command=list(map(str,cmd)),before=before,exit=proc.returncode)
            if proc.returncode:
                row.update(status="FAILED",stderr=proc.stderr,stdout=proc.stdout)
                raw.write(json.dumps(row)+"\n");raw.flush()
                raise RuntimeError(f"Correctness failure; no further performance runs: {row}")
            result=json.loads(proc.stdout)
            if result["sent"]!=result["received"] or result["bytes_received"]!=result["received"]*c["payload"]: raise RuntimeError("Data mismatch")
            if times.stat().st_size!=8*result["sent"]: raise RuntimeError("send-time count mismatch")
            data=times.read_bytes()
            with gzip.open(str(times)+".gz","wb",compresslevel=1) as f: f.write(data)
            times.unlink()
            row.update(status="OK",result=result,send_times=times.name+".gz",send_times_sha256=hashlib.sha256(data).hexdigest())
            raw.write(json.dumps(row)+"\n");raw.flush()
            print(f"{number+1}/{len(schedule)} {item['mode']} case={item['case']} run={item['run']} warmup={item['warmup']}",flush=True)
    (out/"COMPLETE").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())+"\n")

if __name__=="__main__":main()
