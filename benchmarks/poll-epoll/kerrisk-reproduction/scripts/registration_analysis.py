#!/usr/bin/env python3
"""Regenerate registration control tables from immutable JSONL."""
import argparse,csv,hashlib,json,random,statistics
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('directory',nargs='?',type=Path,default=root/'results/main');out=p.parse_args().directory
plan=json.loads((root/'results/registration-plan.json').read_text())
rows=[json.loads(s) for s in (out/'registration.jsonl').read_text().splitlines()]
conditions=[]
for r in plan['ready']:
 for variant in plan['variants']:
  for order in plan['orders']:conditions.append(dict(variant,ready_fds=r,registration=order))
assert len(rows)==len(conditions)*2*(plan['runs']+1)
assert max(x['sequence'] for x in rows if x['warmup'])<min(x['sequence'] for x in rows if not x['warmup'])
for x in rows:
 assert all(x[k]==v for k,v in conditions[x['condition']].items())
 assert x['errors']==0 and x['events_observed']==x['iterations']*x['ready_fds'] and x['wait_calls']==x['iterations']
env=json.loads((out/'registration-environment.json').read_text())
assert all(hashlib.sha256((out/'registration-source'/name).read_bytes()).hexdigest()==h for name,h in env['source_sha256'].items())
# Independently reconstruct both expected membership and event sequence.
mask=(1<<64)-1
for x in rows:
 order=list(range(1000));state=x['seed'] or 1
 for i in range(999,0,-1):
  state^=(state<<13)&mask;state^=state>>7;state^=(state<<17)&mask
  j=state%(i+1);order[i],order[j]=order[j],order[i]
 ready=order[:x['ready_fds']];bitmap=set(ready);h=1469598103934665603
 for i in range(1000):h=((h^(i in bitmap))*1099511628211)&mask
 assert h==x['ready_hash']
 if x['registration']=='after-fill':ready.sort()
 h=1469598103934665603
 for i in ready:h=((h^i)*1099511628211)&mask
 assert h==x['preflight_order_hash'], ('event sequence mismatch',x['registration'])
# Same Ready bitmap, event/byte count and work for every paired language/order.
for x in rows:
 peers=[y for y in rows if (y['label'],y['ready_fds'],y['run'])==(x['label'],x['ready_fds'],x['run'])]
 assert len(peers)==4
 for y in peers:
  for k in ['ready_hash','events_observed','checksum','ctl_calls','min_fd','max_fd','iterations','seed']:assert x[k]==y[k],k
summary=[]
for i,c in enumerate(conditions):
 for language in plan['languages']:
  g=[x for x in rows if x['condition']==i and x['language']==language and not x['warmup']];assert len(g)==plan['runs']
  v=[x['duration_ns']/x['iterations'] for x in g];boot=random.Random(271828);samples=sorted(statistics.median(boot.choices(v,k=len(v))) for _ in range(10000))
  summary.append(dict(c,language=language,n=len(v),median_ns=statistics.median(v),ci95_low=samples[250],ci95_high=samples[9749],min_ns=min(v),max_ns=max(v)))
with (out/'registration-summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0]),lineterminator="\n");w.writeheader();w.writerows(summary)
print('Regenerated registration-summary.csv from',len(rows),'validated rows')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':14,'svg.fonttype':'none','svg.hashsalt':'kerrisk-registration','axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
for ax,r in zip(axes,plan['ready']):
 for language,color in [('c','#171717'),('zig','#7e22ce')]:
  for order,style in [('after-fill','-o'),('before-fill','--s')]:
   selected=[next(x for x in summary if x['label']==label and x['language']==language and x['registration']==order and x['ready_fds']==r) for label in ['pipe','socket','bridge']]
   ax.plot(['pipe','socket','bridge'],[x['median_ns']/1000 for x in selected],style,color=color,label=f'{language}: ADD {order}')
 ax.set(title=f'{r} / 1000 ready',ylabel='µs / epoll wait + selected work',ylim=(0,None));ax.grid(alpha=.2)
axes[0].legend(fontsize=8)
fig.supxlabel('Only registration/fill order differs within each pair | median n=5 | 20,000 waits / sample\nOrbStack / Linux 7.0.14 aarch64 / CPU 2 / GCC -O2 / Zig 0.17.0 ReleaseFast | bridge: socket, normal fds, timeout=0, scan',fontsize=9)
fig.savefig(out/'registration.svg',metadata={'Date':None});plt.close(fig)
p=out/'registration.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text().splitlines())+'\n')
