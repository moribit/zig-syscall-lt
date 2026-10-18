#!/usr/bin/env python3
"""Rebuild tables, uncertainty, held-out oracle assessment, and SVG figures."""
import argparse, collections, csv, json, random, statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(); p.add_argument('directory',type=Path,nargs='?',default=Path(__file__).parent/'results/fixed'); a=p.parse_args()
rows=[json.loads(x) for x in (a.directory/'raw.jsonl').read_text().splitlines()]
meta=json.loads((a.directory/'environment.json').read_text())
measured=[x for x in rows if not x['warmup']]
groups=collections.defaultdict(list)
for x in measured: groups[(x['benchmark'],x['fds'],x['requested_ready_percent'],x['payload'],x['backend'])].append(x)
assert all(len(g)==meta['runs'] for g in groups.values())
assert len(measured)==len(meta['conditions'])*2*meta['runs']
def metrics(x):
 return dict(wait_ns=x['acquisition_ns']/x['wait_calls'],event_ns=x['acquisition_ns']/x['events_observed'] if x['events_observed'] else 0,duration_ns=x['duration_ns'],messages_s=x['messages']*1e9/x['duration_ns'],bytes_s=x['bytes_received']*1e9/x['duration_ns'],ns_per_message=x['duration_ns']/x['messages'] if x['messages'] else 0,user_us=x['user_us'],system_us=x['system_us'],wait_calls=x['wait_calls'],recv_calls=x['recv_calls'],events=x['events_observed'],setup_ns=x['setup_ns'])
summary=[]
for key,g in sorted(groups.items()):
 item=dict(zip(['benchmark','fds','ready_percent','payload','backend'],key)); item['n']=len(g); item['actual_ready_percent']=g[0]['ready_ratio']*100
 for metric in metrics(g[0]):
  v=[metrics(x)[metric] for x in g]
  item[metric+'_median']=statistics.median(v); item[metric+'_min']=min(v); item[metric+'_max']=max(v)
  item[metric+'_q1']=statistics.quantiles(v,n=4)[0]; item[metric+'_q3']=statistics.quantiles(v,n=4)[2]
 summary.append(item)
with (a.directory/'summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
rng=random.Random(271828)
comparisons=[]
for mode,n,ratio,payload in sorted({k[:4] for k in groups}):
 d={b:{x['run']:x for x in groups[(mode,n,ratio,payload,b)]} for b in ['poll','epoll']}
 metric='wait_ns' if mode=='readiness' else 'ns_per_message'
 ratios=[metrics(d['poll'][i])[metric]/metrics(d['epoll'][i])[metric] for i in range(1,meta['runs']+1)]
 boots=sorted(statistics.median(rng.choices(ratios,k=len(ratios))) for _ in range(4000))
 lo,hi=boots[100],boots[3899]
 comparisons.append(dict(benchmark=mode,fds=n,ready_percent=ratio,payload=payload,paired_ratio_median=statistics.median(ratios),ci95_low=lo,ci95_high=hi,poll_faster_runs=sum(r<1 for r in ratios),epoll_faster_runs=sum(r>1 for r in ratios),winner='epoll' if lo>1 else 'poll' if hi<1 else 'uncertain'))
# Training runs 1..5 choose a backend per condition; remaining runs evaluate it.
# Also show the optimistic in-sample oracle; neither includes switching costs.
oracles={}
for mode in ['readiness','receive']:
 metric='wait_ns' if mode=='readiness' else 'ns_per_message'
 costs={b:0.0 for b in ['poll','epoll','oracle_in_sample','oracle_held_out']}
 choices=[]
 for k in sorted({key[:4] for key in groups if key[0]==mode}):
  g={b:groups[(*k,b)] for b in ['poll','epoll']}
  split=meta['runs']//2
  train={b:statistics.median(metrics(x)[metric] for x in g[b] if x['run']<=split) for b in g}
  test={b:statistics.median(metrics(x)[metric] for x in g[b] if x['run']>split) for b in g}
  choice=min(train,key=train.get)
  choices.append(dict(condition=k,chosen_from_training=choice))
  for b in g: costs[b]+=test[b]
  costs['oracle_in_sample']+=min(test.values()); costs['oracle_held_out']+=test[choice]
 best=min(costs['poll'],costs['epoll'])
 oracles[mode]=dict(costs=costs,unit='sum of equally weighted condition medians: '+metric,optimistic_gain_percent=100*(1-costs['oracle_in_sample']/best),held_out_gain_percent=100*(1-costs['oracle_held_out']/best),choices=choices,switch_cost_included=False)
receive_winners={x['winner'] for x in comparisons if x['benchmark']=='receive'}
assessment=dict(criterion='Paired bootstrap 95% interval of median poll/epoll cost ratio excludes 1, in both directions for receive workloads. No speed-based pass/fail test.',comparisons=comparisons,oracle=oracles,adaptive_implemented=False,decision='No robust reversal in receive conditions; dynamic switching not justified.' if not {'poll','epoll'}<=receive_winners else 'Reversal detected: evaluate adaptive before drawing conclusions.')
(a.directory/'analysis.json').write_text(json.dumps(assessment,indent=2)+'\n')
# One stable palette throughout the deck.
colors={'poll':'#1d4ed8','epoll':'#b45309'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':20,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
caption=f'OrbStack VM / Linux 7.0.14 aarch64 / Zig 0.17.0 ReleaseFast | median, n={meta["runs"]}; shaded IQR | 64 B'
def plot(name,title,xlabel,ylabel,select,xfield,yfield,scale=1):
 fig,ax=plt.subplots(figsize=(9,4.4),layout='constrained')
 for b in colors:
  g=sorted([s for s in summary if s['backend']==b and select(s)],key=lambda s:s[xfield]); xs=[s[xfield] for s in g]
  ax.plot(xs,[s[yfield+'_median']/scale for s in g],marker='o',label=b,color=colors[b],linewidth=2)
  ax.fill_between(xs,[s[yfield+'_q1']/scale for s in g],[s[yfield+'_q3']/scale for s in g],color=colors[b],alpha=.15)
 ax.set(xlabel=xlabel,ylabel=ylabel,title=title,ylim=(0,None)); ax.grid(alpha=.2); ax.legend(); fig.supxlabel(caption,fontsize=10)
 fig.savefig(a.directory/(name+'.svg')); plt.close(fig)
plot('A-fds','A: requested 1% ready (rounded)','Monitored fds','Acquisition (µs/call)',lambda s:s['benchmark']=='readiness' and s['ready_percent']==1 and s['payload']==64,'fds','wait_ns',1000)
plot('B-ready','A: readiness, 1024 fds','Ready (%)','Acquisition (µs/call)',lambda s:s['benchmark']=='readiness' and s['fds']==1024 and s['payload']==64,'actual_ready_percent','wait_ns',1000)
plot('C-throughput','B: prefilled receive, 1024 fds','Ready (%)','Receive (M msg/s)',lambda s:s['benchmark']=='receive' and s['fds']==1024 and s['payload']==64,'actual_ready_percent','messages_s',1e6)
print(json.dumps(dict(rows=len(rows),measured=len(measured),winners=dict(collections.Counter(x['winner'] for x in comparisons)),decision=assessment['decision'],oracle={k:{x:v[x] for x in ['optimistic_gain_percent','held_out_gain_percent']} for k,v in oracles.items()}),indent=2))
