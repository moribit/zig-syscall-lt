#!/usr/bin/env python3
import argparse, csv, json, random, statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
parser=argparse.ArgumentParser(); parser.add_argument('directory',nargs='?',type=Path,default=Path(__file__).resolve().parent/'results/adaptive'); root=parser.parse_args().directory
rows=[json.loads(x) for x in (root/'raw.jsonl').read_text().splitlines()]
assert len(rows)==33
sample=[x for x in rows if not x['warmup']]
for x in rows:
 assert x['errors']==0 and x['messages']==sum(p['messages'] for p in x['phases'])
 assert x['duration_ns']==sum(p['duration_ns'] for p in x['phases'])
 for p,r in zip(x['phases'],[41,4096,41]):
  assert p['ready_fds']==r and p['duration_ns']>=200_000_000
  assert p['messages']==r*p['batches'] and p['bytes']==p['messages']*1024
summary=[]
for b in ['poll','epoll','adaptive']:
 g=[x for x in sample if x['backend']==b]; assert len(g)==10
 rates=[x['messages']*1e9/x['duration_ns'] for x in g]
 q=statistics.quantiles(rates,n=4)
 summary.append(dict(backend=b,n=10,messages_s_median=statistics.median(rates),messages_s_min=min(rates),messages_s_max=max(rates),messages_s_q1=q[0],messages_s_q3=q[2],switches_median=statistics.median(x['switches'] for x in g),switch_ns_median=statistics.median(x['switch_ns'] for x in g),setup_ns_median=statistics.median(x['setup_ns'] for x in g),including_setup_messages_s_median=statistics.median(x['messages']*1e9/(x['duration_ns']+x['setup_ns']) for x in g)))
d={b:{x['run']:x for x in sample if x['backend']==b} for b in ['poll','epoll','adaptive']}
ratio=[(d['adaptive'][i]['messages']/d['adaptive'][i]['duration_ns'])/(d['epoll'][i]['messages']/d['epoll'][i]['duration_ns']) for i in range(1,11)]
rng=random.Random(314159)
boots=sorted(statistics.median(rng.choices(ratio,k=10)) for _ in range(10000))
# Offline phase oracle, trained on first 5 dynamic fixed-mode runs, then held out.
oracle=0; fixed={b:0 for b in ['poll','epoll']}; choices=[]
for phase in range(3):
 train={b:statistics.median(x['phases'][phase]['messages']*1e9/x['phases'][phase]['duration_ns'] for i,x in d[b].items() if i<=5) for b in fixed}
 test={b:statistics.median(x['phases'][phase]['messages']*1e9/x['phases'][phase]['duration_ns'] for i,x in d[b].items() if i>5) for b in fixed}
 choice=max(train,key=train.get); choices.append(choice); oracle+=test[choice]
 for b in fixed: fixed[b]+=test[b]
assessment=dict(comparison='adaptive throughput / fixed epoll throughput',paired_median_percent=(statistics.median(ratio)-1)*100,ci95_percent=[(boots[250]-1)*100,(boots[9749]-1)*100],switch_cost_included=True,initial_setup_in_primary_timing=False,controller='model calibrated only on crossover-check runs 1..5; no dynamic-result tuning',oracle=dict(phase_choices=choices,held_out_gain_percent=(oracle/max(fixed.values())-1)*100,switch_cost_included=False),conclusion='No demonstrated throughput improvement over fixed epoll' if boots[250]<=1 else 'Adaptive improved in this workload')
(root/'analysis.json').write_text(json.dumps(assessment,indent=2)+'\n')
with (root/'summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0]),lineterminator="\n");w.writeheader();w.writerows(summary)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':19,'svg.fonttype':'none','svg.hashsalt':'poll-epoll-20261019','axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(figsize=(9,4.4),layout='constrained')
v=[x['messages_s_median']/1e6 for x in summary]
ax.bar(['poll','epoll','Adaptive'],v,color=['#1d4ed8','#b45309','#7e22ce'],width=.6)
ax.errorbar(range(3),v,yerr=[[v[i]-x['messages_s_q1']/1e6 for i,x in enumerate(summary)],[x['messages_s_q3']/1e6-v[i] for i,x in enumerate(summary)]],fmt='none',ecolor='#171717',capsize=5)
ax.set(ylabel='Throughput (M msg/s)',ylim=(0,max(v)*1.3),title='1% -> 100% -> 1% ready')
for i,y in enumerate(v):ax.text(i,y+.06,f'{y:.3f}',ha='center')
fig.supxlabel('4096 fds / 1 KiB / 200 ms per phase / median, n=10; IQR / switching included',fontsize=10)
fig.savefig(root/'D-adaptive.svg',metadata={'Date':None});plt.close(fig)
svg=root/'D-adaptive.svg';svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
print(json.dumps(dict(summary=summary,assessment=assessment),indent=2))
