#!/usr/bin/env python3
"""Rebuild all-condition summaries; never remove outliers or select raw rows."""
import argparse
import csv
import json
from pathlib import Path
import random
from statistics import median

def interval(values):
    rng=random.Random(20261022)
    sims=sorted(median(rng.choices(values,k=len(values))) for _ in range(10000))
    return [sims[249],sims[9749]]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("directory",type=Path)
    ap.add_argument("--select",type=Path);ap.add_argument("--plots",action="store_true")
    args=ap.parse_args();d=args.directory
    if not (d/"COMPLETE").exists():raise RuntimeError("Incomplete or failed series")
    rows=[json.loads(s) for s in (d/"raw.jsonl").read_text().splitlines()]
    expected=json.loads((d/"schedule.json").read_text())
    if len(rows)!=len(expected) or any(r["status"]!="OK" for r in rows):raise RuntimeError("Row integrity failure")
    for r in rows:
        v=r["result"]
        if v["sent"]!=v["received"] or v["bytes_received"]!=v["received"]*r["condition"]["payload"]:raise RuntimeError("Counts")
        if v["counters"]["eof"]!=r["condition"]["fds"]:raise RuntimeError("EOF mismatch")
    measured=[r for r in rows if not r["warmup"]]
    groups={}
    for r in measured:groups.setdefault((r["case"],r["mode"]),[]).append(r)
    summaries=[]
    for (case,mode), rs in sorted(groups.items()):
        summary=dict(case=case,mode=mode,n=len(rs),condition=rs[0]["condition"])
        for key in ["messages_s","p50_ns","p95_ns","p99_ns","drain_ns","backend_init_ns","backend_destroy_ns","enters","sqes","producer_eagain","producer_late_max_ns"]:
            values=[r["result"][key] for r in rs]
            summary[key]=dict(median=median(values),min=min(values),max=max(values))
        for who in ["producer","consumer"]:
            values=[sum(r["result"][who+"_cpu"].values())*1000/max(1,r["result"]["received"]) for r in rs]
            summary[who+"_cpu_ms_per_million"]=dict(median=median(values),min=min(values),max=max(values))
        summary["target_achieved_ratio"]=median(r["result"]["messages_s"]/r["condition"]["rate"] for r in rs)
        summaries.append(summary)
    pairs=[]
    for case in sorted({r["case"] for r in measured}):
        base={(r["seed"],r["run"]):r for r in groups[(case,"epoll")]}
        for mode in ("oneshot","multishot"):
            ratios=[];cpu=[];latency=[]
            for r in groups[(case,mode)]:
                e=base[(r["seed"],r["run"])]["result"];v=r["result"]
                if e["received"]!=v["received"]:raise RuntimeError("Paired sent-count mismatch")
                ratios.append(v["messages_s"]/e["messages_s"] if e["messages_s"] else 1)
                ecpu=sum(e["consumer_cpu"].values());vcpu=sum(v["consumer_cpu"].values())
                cpu.append(ecpu/max(1,vcpu))
                latency.append(e["p99_ns"]/max(1,v["p99_ns"]))
            pairs.append(dict(case=case,mode=mode,n=len(ratios),condition=groups[(case,mode)][0]["condition"],
                throughput_ratio=median(ratios),throughput_ci=interval(ratios),
                consumer_cpu_efficiency_ratio=median(cpu),consumer_cpu_ci=interval(cpu),
                p99_improvement_ratio=median(latency),p99_ci=interval(latency)))
    analysis=dict(raw_count=len(rows),measured_count=len(measured),summaries=summaries,pairs=pairs,
        interpretation="Ratios >1 favor io_uring. Descriptive paired bootstrap, no outlier removal; exploration is not confirmation.")
    (d/"analysis.json").write_text(json.dumps(analysis,indent=2)+"\n")
    with (d/"summary.csv").open("w") as f:
        fields=["case","mode","n","fds","active","payload","pattern","rate","batch","messages_s","p50_ns","p95_ns","p99_ns","consumer_cpu_ms_per_million","producer_cpu_ms_per_million","target_achieved_ratio"]
        writer=csv.DictWriter(f,fields);writer.writeheader()
        for s in summaries:
            flat={k:v for k,v in s.items() if k in fields and not isinstance(v,dict)}
            flat.update({k:v for k,v in s["condition"].items() if k in fields})
            flat.update({k:v["median"] for k,v in s.items() if k in fields and isinstance(v,dict) and "median" in v})
            writer.writerow(flat)
    if args.select:
        if args.select.exists():raise RuntimeError("Refuse to replace a frozen confirmation plan")
        candidates=[p for p in pairs if p["mode"]=="multishot"]
        key=lambda p:json.dumps(p["condition"],sort_keys=True)
        winners=sorted(candidates,key=lambda p:(-p["throughput_ratio"],key(p)))
        ties=sorted(candidates,key=lambda p:(abs(p["throughput_ratio"]-1),key(p)))
        losers=sorted(candidates,key=lambda p:(p["throughput_ratio"],key(p)))
        baseline=next(p for p in candidates if all(p["condition"][k]==v for k,v in dict(fds=256,percent=10,payload=256,pattern="uniform",rate=50000,batch=32).items()))
        selected=[];reasons=[]
        for reason,p in zip(["largest throughput ratio","closest to parity","smallest throughput ratio","preregistered baseline"],[winners[0],ties[0],losers[0],baseline]):
            if p["condition"] not in selected:selected.append(p["condition"])
            reasons.append(dict(reason=reason,candidate=p))
        plan=dict(exploration=str(d),conditions=selected,selection=reasons,all_candidates=candidates,
            seed=2026102301,runs=20,duration_ms=1000,warning="Post-exploration selection; only new independent runs can confirm direction.")
        args.select.write_text(json.dumps(plan,indent=2)+"\n")
    if args.plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        colors=dict(epoll="#b45309",oneshot="#7e22ce",multishot="#0f766e")
        cases=sorted({s["case"] for s in summaries})
        fig,axes=plt.subplots(1,3,figsize=(15,max(5,len(cases)*.28)),sharey=True)
        for mode,offset in zip(colors,[-.2,0,.2]):
            ss=[s for s in summaries if s["mode"]==mode]
            yy=[s["case"]+offset for s in ss]
            for ax,metric,scale in zip(axes,["messages_s","p99_ns","consumer_cpu_ms_per_million"],[1e-3,1e-3,1]):
                ax.scatter([s[metric]["median"]*scale for s in ss],yy,label=mode,color=colors[mode],s=14)
        for ax,label in zip(axes,["Complete messages / s (thousands)","p99 latency (µs)","Consumer CPU ms / million messages"]):
            ax.set_xlabel(label);ax.set_xlim(left=0);ax.grid(alpha=.2);ax.legend()
        axes[0].set_yticks(cases,[str(c) for c in cases]);axes[0].set_ylabel("Condition ID (all conditions; details in summary.csv)")
        env=json.loads((d/"environment.json").read_text())
        fig.suptitle(f"{env['uname']['machine']} / {env['uname']['release']} / Zig 0.17.0 / n={summaries[0]['n']} per condition\nMedians; fixed offered loads, receive + complete validation; not a Web-server benchmark")
        fig.tight_layout();fig.savefig(d/"all-conditions.svg");plt.close(fig)
    print(json.dumps(dict(rows=len(rows),measurements=len(measured),conditions=len(pairs)//2)))

if __name__=="__main__":main()
