#!/usr/bin/env python3
"""Rebuild the audit from preserved raw rows; no sample is discarded except warmup."""
import argparse, collections, csv, hashlib, json, math, random, statistics as st
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('directory',nargs='?',type=Path,default=root/'results/audit-v2');out=parser.parse_args().directory
med=st.median
colors={'poll':'#1d4ed8','poll-watched':'#64748b','epoll':'#b45309','adaptive':'#7e22ce'}
def load(p): return [json.loads(s) for s in p.read_text().splitlines()]
def samples(name): return [x for x in load(out/(name+'.jsonl')) if not x.get('warmup',False)]
def csvwrite(name,rows):
 with (out/(name+'.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def paired(a,b,cost):
 def index(rows):
  d={(x['run'],x['seed']):x for x in rows};assert len(d)==len(rows), 'duplicate pair';return d
 a,b=index(a),index(b);assert a.keys()==b.keys() and a, 'missing pairs'
 ratios=[cost(a[k])/cost(b[k]) for k in sorted(a)]
 rng=random.Random(271828);boots=sorted(med(rng.choices(ratios,k=len(ratios))) for _ in range(10000))
 wins=sum(r<1 for r in ratios);losses=sum(r>1 for r in ratios); n=wins+losses
 p=min(1,2*sum(math.comb(n,i) for i in range(min(wins,losses)+1))/2**n)
 return dict(n=len(ratios),ratio=med(ratios),ci95=[boots[250],boots[9749]],numerator_wins=wins,sign_p=p)
def holm(rows):
 last=0
 for i,x in enumerate(sorted(rows,key=lambda r:r['sign_p'])):
  last=max(last,min(1,x['sign_p']*(len(rows)-i)));x['holm_p']=last
# Historical files remain byte-for-byte intact.
manifest=json.loads((out/'historical-manifest.json').read_text())
assert all(hashlib.sha256((root/'results'/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
historical=[];hist_rows=0
for directory in ['fixed','replication','end-to-end','end-to-end-replication','crossover-check']:
 meta=json.loads((root/'results'/directory/'environment.json').read_text());rows=load(root/'results'/directory/'raw.jsonl');hist_rows+=len(rows)
 groups=collections.defaultdict(list)
 for x in rows:
  if not x['warmup']:groups[(x['benchmark'],x['fds'],x['requested_ready_percent'],x['payload'])].append(x)
 for k,g in groups.items():
  def cost(x):return x['acquisition_ns']/x['wait_calls'] if k[0]=='readiness' else x['e2e_duration_ns' if meta.get('includes_producer_timing') else 'duration_ns']/x['messages']
  r=paired([x for x in g if x['backend']=='poll'],[x for x in g if x['backend']=='epoll'],cost)
  r.update(dataset=directory,condition=list(k));historical.append(r)
holm(historical)
probe=samples('probe');assert len(probe)==800
ps=[]
for n,r in [(1024,10),(1024,1024),(4096,41),(4096,4096)]:
 for b in ['poll','epoll']:
  for mode in ['combined','syscall','scan','validate','clocks']:
   g=[x for x in probe if (x['fds'],x['ready_fds'],x['backend'],x['mode'])==(n,r,b,mode)];assert len(g)==20
   assert all(x['checksum']==r*x['iterations'] for x in g)
   v=[x['duration_ns']/x['iterations'] for x in g]
   ps.append(dict(fds=n,ready_fds=r,backend=b,mode=mode,n=len(g),ns_median=med(v),ns_min=min(v),ns_max=max(v),ns_per_event=med(v)/r))
csvwrite('probe-summary',ps)
controls=samples('controls');assert len(controls)==360
cs=[];comparisons=[]
for ready in [41,4096]:
 for order in ['shuffled','ascending']:
  g=[x for x in controls if x['ready_fds']==ready and x['order']==order]
  for b in ['poll','epoll','poll-watched']:
   rows=[x for x in g if x['backend']==b];assert len(rows)==30
   for x in rows:
    assert x['errors']==0 and x['bytes_sent']==x['bytes_received']==x['messages']*1024
    assert x['messages']==ready*x['iterations'] and x['e2e_duration_ns']>=x['producer_ns']+x['duration_ns']
   item=dict(ready_fds=ready,order=order,backend=b,n=30)
   for label,key in [('producer','producer_ns'),('consumer','duration_ns'),('acquisition','acquisition_ns'),('e2e','e2e_duration_ns')]:item[label+'_us_per_burst']=med(x[key]/x['iterations']/1000 for x in rows)
   item['user_us_per_burst']=med(x['e2e_user_us']/x['iterations'] for x in rows);item['system_us_per_burst']=med(x['e2e_system_us']/x['iterations'] for x in rows)
   item['messages_s']=med(x['messages']*1e9/x['e2e_duration_ns'] for x in rows);cs.append(item)
  r=paired([x for x in g if x['backend']=='poll'],[x for x in g if x['backend']=='epoll'],lambda x:x['e2e_duration_ns']/x['messages']);r.update(ready_fds=ready,order=order,pinned=True);comparisons.append(r)
rep=samples('replication');assert len(rep)==60
for x in rep:assert x['errors']==0 and x['bytes_sent']==x['bytes_received']==x['messages']*1024
r=paired([x for x in rep if x['backend']=='poll'],[x for x in rep if x['backend']=='epoll'],lambda x:x['e2e_duration_ns']/x['messages']);r.update(ready_fds=4096,order='shuffled',pinned=False);comparisons.append(r);
confirmation=samples('confirmation');assert len(confirmation)==120
for order in ['shuffled','ascending']:
 g=[x for x in confirmation if x['order']==order]
 r=paired([x for x in g if x['backend']=='poll'],[x for x in g if x['backend']=='epoll'],lambda x:x['e2e_duration_ns']/x['messages']);r.update(ready_fds=4096,order=order,pinned=True,series='second-pinned-seed');comparisons.append(r)
holm(comparisons);csvwrite('controls-summary',cs)
dynamic=samples('dynamic-warmed');assert len(dynamic)==90
ph=[];dyn=[];oracle=[]
rate=lambda x:x['messages']*1e9/x['duration_ns']
for high in [200,1000,5000]:
 d={b:[x for x in dynamic if x['high_ms']==high and x['backend']==b] for b in ['poll','epoll','adaptive']}
 for b,g in d.items():
  assert len(g)==10
  for x in g:
   assert x['errors']==0 and x['messages']==sum(p['messages'] for p in x['phases']) and x['duration_ns']==sum(p['duration_ns'] for p in x['phases'])
   assert x['switches']==sum(p['switches'] for p in x['phases']) and x['switch_ns']==sum(p['switch_ns'] for p in x['phases'])
   for i,p in enumerate(x['phases']):assert p['messages']==p['ready_fds']*p['batches'] and p['bytes']==p['messages']*1024 and p['duration_ns']>=([200,high,200][i])*1e6
  for i in range(3):
   p=[x['phases'][i] for x in g];ph.append(dict(high_ms=high,phase='ABC'[i],backend=b,n=10,messages_s=med(map(rate,p)),cpu_us=med(x['user_us']+x['system_us'] for x in p),batches=med(x['batches'] for x in p),switches=med(x['switches'] for x in p),switch_ns=med(x['switch_ns'] for x in p)))
 r=paired(d['adaptive'],d['epoll'],rate);r.update(high_ms=high,switch_ns=med(x['switch_ns'] for x in d['adaptive']),switches=med(x['switches'] for x in d['adaptive']));dyn.append(r)
 # Phase choice fixed from the old independent experiment; no new tuning.
 rates={b:[med(rate(x['phases'][i]) for x in d[b]) for i in range(3)] for b in ['poll','epoll']};seconds=[.2,high/1000,.2]
 ideal=sum(max(rates[b][i] for b in rates)*seconds[i] for i in range(3));fixed=max(sum(rates[b][i]*seconds[i] for i in range(3)) for b in rates)
 diff=rates['poll'][1]-rates['epoll'][1]; switchcost=r['switch_ns']/1e9
 oracle.append(dict(high_ms=high,phase_rates=rates,retrospective_choices=[max(rates,key=lambda b:rates[b][i]) for i in range(3)],retrospective_no_cost_upper_gain_percent=100*(ideal/fixed-1),frozen_choices=['epoll','poll','epoll'],frozen_gain_percent=100*((rates['epoll'][0]*.2+rates['poll'][1]*high/1000+rates['epoll'][2]*.2)/fixed-1),high_phase_extra_messages=diff*high/1000,approx_break_even_high_ms=switchcost*rates['epoll'][1]/diff*1000 if diff>0 else None,interpretation='retrospective descriptive upper bound, not deployable or confirmatory; fixed-duration message accounting'))
holm(dyn);csvwrite('phase-summary',ph)
old=load(root/'results/adaptive/raw.jsonl'); oldph=[]
for b in ['poll','epoll','adaptive']:
 for i in range(3):
  g=[x['phases'][i] for x in old if not x['warmup'] and x['backend']==b]
  oldph.append(dict(backend=b,phase='ABC'[i],messages_s=med(map(rate,g)),cpu_us=med(p['user_us']+p['system_us'] for p in g),batches=med(p['batches'] for p in g)))
csvwrite('historical-phase-summary',oldph)
diag=load(out/'diagnostics.jsonl'); switches=[x for x in diag if x.get('actual_ns',0)>0]
for high in [200,1000,5000]:
 sample=next(x for x in diag if x.get('high_ms')==high and 'phases'in x)
 rows=[x for x in switches if x['high_ms']==high];assert len(rows)==sample['switches'] and sum(x['actual_ns'] for x in rows)==sample['switch_ns']
# Exact per-pair rate/phase-weight identity; means add, medians need not.
contribution_rows=[];contribution_means=[]
for series,high,source in [('historical',200,[x for x in old if not x['warmup']])]+[('audit',h,[x for x in dynamic if x['high_ms']==h]) for h in [200,1000,5000]]:
 by={b:{(x['run'],x['seed']):x for x in source if x['backend']==b} for b in ['epoll','adaptive']}
 assert by['epoll'].keys()==by['adaptive'].keys()
 local=[]
 for key,e in by['epoll'].items():
  a=by['adaptive'][key];re=rate(e);ra=rate(a);parts=[]
  for phase in range(3):
   pe=e['phases'][phase];pa=a['phases'][phase];we=pe['duration_ns']/e['duration_ns'];wa=pa['duration_ns']/a['duration_ns']
   rate_effect=100*we*(rate(pa)-rate(pe))/re;weight_effect=100*(wa-we)*rate(pa)/re
   row=dict(series=series,high_ms=high,run=key[0],seed=key[1],phase='ABC'[phase],rate_effect_pp=rate_effect,weight_effect_pp=weight_effect,total_pair_gain_percent=100*(ra/re-1));local.append(row);parts.append(rate_effect+weight_effect)
  assert abs(sum(parts)-100*(ra/re-1))<1e-8
 contribution_rows.extend(local)
 contribution_means.append(dict(series=series,high_ms=high,rate_effect_pp=[st.mean(x['rate_effect_pp'] for x in local if x['phase']==p) for p in 'ABC'],weight_effect_pp=st.mean(sum(x['weight_effect_pp'] for x in local if x['run']==r) for r in range(1,11)),mean_gain_percent=st.mean(x['total_pair_gain_percent'] for x in local),median_gain_percent=med(x['total_pair_gain_percent'] for x in local)))
csvwrite('phase-contributions',contribution_rows)
report=dict(baseline='09cbca5',dynamic_source='dynamic-warmed.jsonl; all warmups first; dynamic.jsonl is a preserved preliminary series with interleaved warmup',historical_files_unchanged=len(manifest),historical_rows_validated=hist_rows+len(old),historical_comparisons=historical,controls_comparisons=comparisons,dynamic_comparisons=dyn,oracle=oracle,diagnostic_switches=switches,phase_contribution_means=contribution_means,policy='Frozen historical model; all samples retained; diagnostics separate; 95% paired median percentile bootstrap 10000 draws; exact sign tests with Holm within declared family; exploratory VM results, not population guarantees.')
(out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':17,'svg.fonttype':'none','svg.hashsalt':'poll-audit-v2','axes.spines.top':False,'axes.spines.right':False})
def save(fig,name):
 fig.savefig(out/(name+'.svg'),metadata={'Date':None});plt.close(fig)
 svg=out/(name+'.svg');svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
# Regenerate historical graphs directly from raw, preserving the previous scale and palette.
fig,axes=plt.subplots(1,2,figsize=(13,4.5),layout='constrained')
for ax,filename,mode in [(axes[0],'fixed','readiness'),(axes[1],'end-to-end','receive')]:
 rows=load(root/'results'/filename/'raw.jsonl')
 for b in ['poll','epoll']:
  points=[]
  for pct in [1,10,50,100]:
   g=[x for x in rows if not x['warmup'] and x['backend']==b and x['benchmark']==mode and x['fds']==1024 and x['payload']==64 and x['requested_ready_percent']==pct]
   v=[x['acquisition_ns']/x['wait_calls']/1000 if mode=='readiness' else rate(dict(messages=x['messages'],duration_ns=x['e2e_duration_ns']))/1e6 for x in g];q=st.quantiles(v,n=4);points.append((g[0]['ready_fds']/1024*100,med(v),q[0],q[2]))
  ax.plot([p[0] for p in points],[p[1] for p in points],'-o',color=colors[b],label=b);ax.fill_between([p[0] for p in points],[p[2] for p in points],[p[3] for p in points],color=colors[b],alpha=.15)
 ax.set(xlabel='Ready (%)',ylabel='Acquisition (µs/call)' if mode=='readiness' else 'Throughput (M msg/s)',ylim=(0,None),title='A: readiness only' if mode=='readiness' else 'B: send + receive');ax.legend();ax.grid(alpha=.2)
fig.supxlabel('OrbStack / Linux 7.0.14 aarch64 / Zig 0.17.0 ReleaseFast | 1024 fds, 64 B | median n=10, IQR',fontsize=10);save(fig,'measured')
fig,axes=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
for ax,high in zip(axes,[200,1000,5000]):
 for b in ['poll','epoll','adaptive']:
  rows=[x for x in ph if x['high_ms']==high and x['backend']==b];ax.plot(['A: 1%','B: 100%','C: 1%'],[x['messages_s']/1e6 for x in rows],'-o',color=colors[b],label=b)
 ax.set(title=f'High-ready phase: {high} ms',ylabel='M msg/s',ylim=(0,None));ax.grid(alpha=.2)
axes[0].legend(fontsize=12);fig.supxlabel('4096 fds, 1 KiB | A/C 200 ms | CPU 2 | median n=10; switching included; model frozen',fontsize=10);save(fig,'phases')
fig,ax=plt.subplots(figsize=(11,2.9),layout='constrained')
high=200;sample=next(x for x in diag if x.get('high_ms')==high and 'phases'in x);elapsed=0
for i,p in enumerate(sample['phases']):
 end=elapsed+p['duration_ns']/1e6;ax.axvspan(elapsed,end,color=['#ddd','#eee','#ddd'][i],alpha=.5);ax.text((elapsed+end)/2,1.12,['A: 1%','B: 100%','C: 1%'][i],ha='center');elapsed=end
xs=[0];ys=[1]
for d in switches:
 if d['high_ms']==high:xs.append(d['elapsed_ns']/1e6);ys.append(1 if d['after_epoll'] else 0)
xs.append(elapsed);ys.append(ys[-1]);ax.step(xs,ys,where='post',color=colors['adaptive'],linewidth=3)
ax.set(yticks=[0,1],yticklabels=['poll','epoll'],xlabel='Elapsed (ms)',ylim=(-.3,1.45),xlim=(0,elapsed));fig.supxlabel('Actual diagnostic run, seed 20261101 | 4096 fds, 1 KiB | separate from performance samples',fontsize=10);save(fig,'timeline')
print(json.dumps({k:report[k] for k in ['historical_files_unchanged','controls_comparisons','dynamic_comparisons','oracle','diagnostic_switches']},indent=2))
