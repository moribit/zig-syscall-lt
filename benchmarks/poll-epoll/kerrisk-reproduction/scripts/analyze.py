#!/usr/bin/env python3
"""Validate raw samples, generate tables and separated historical/current plots."""
import argparse,collections,csv,hashlib,json,random,statistics as st,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('directory',nargs='?',type=Path,default=root/'results/main');out=p.parse_args().directory
plan=json.loads((out/'plan.json').read_text());colors={'poll':'#1d4ed8','epoll':'#b45309','select':'#64748b'}
def load(name):return [json.loads(s) for s in (out/(name+'.jsonl')).read_text().splitlines()]
def interval(values):
 rng=random.Random(271828);b=sorted(st.median(rng.choices(values,k=len(values))) for _ in range(10000));return b[250],b[9749]
def csvwrite(name,rows):
 with (out/(name+'.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def expected_hash(n,r,placement,seed):
 mask=(1<<64)-1;state=seed or 1;order=list(range(n))
 if placement=='random':
  for i in range(n-1,0,-1):
   state^=(state<<13)&mask;state^=state>>7;state^=(state<<17)&mask
   j=state%(i+1);order[i],order[j]=order[j],order[i]
 elif placement=='middle':order[0]=n//2
 elif placement=='last':order[0]=n-1
 bitmap=set(order[:r]);h=1469598103934665603
 for i in range(n):h=((h^(i in bitmap))*1099511628211)&mask
 return h
source_hashes=json.loads((out/'source-hashes.json').read_text())
assert all(hashlib.sha256((out/'source-snapshot'/f).read_bytes()).hexdigest()==h for f,h in source_hashes.items())
control_hashfile=out/'controls-source-hashes.json'
if control_hashfile.exists():
 assert all(hashlib.sha256((out/'controls-source-snapshot'/f).read_bytes()).hexdigest()==h for f,h in json.loads(control_hashfile.read_text()).items())
allrows=[];validation={}
for suite in ['primary','controls']:
 if not (out/(suite+'.jsonl')).exists():continue
 rows=load(suite);conditions=plan[suite];runs=plan['primary_runs' if suite=='primary' else 'control_runs'];assert len(rows)==len(conditions)*2*(runs+1)
 assert max(x['sequence'] for x in rows if x['warmup'])<min(x['sequence'] for x in rows if not x['warmup'])
 groups=collections.defaultdict(list)
 for x in rows:
  assert 0<=x['condition']<len(conditions)
  expected=conditions[x['condition']]
  assert all(x[k]==v for k,v in expected.items() if k!='iterations')
  assert x['iterations']==(plan['warmup_iterations'] if x['warmup'] else expected['iterations'])
  assert x['ready_hash']==expected_hash(x['fds'],x['ready_fds'],x['placement'],x['seed'])
  groups[x['condition'],x['language']].append(x)
  assert x['errors']==0 and x['preflight_ready']==x['ready_fds']
  assert x['warmup']==(x['run']==0) and x['ctl_calls']==2*x['changes']*x['iterations']
  if x['layout']=='contiguous':assert x['min_fd']==3 and x['max_fd']==x['fds']+2
  if x['work'] in ['scan-only','verify-only','ctl-only']:assert x['wait_calls']==0 and x['events_observed']==0
  elif x['work']=='full':assert x['wait_calls']>=x['iterations'] and x['events_observed']>=x['ready_fds']*x['iterations']
  else:assert x['wait_calls']==x['iterations'] and x['events_observed']==x['iterations']*(min(x['ready_fds'],x['capacity']) if x['backend']=='epoll' else x['ready_fds'])
  if suite=='primary' and not x['warmup']:assert x['iterations']==1_000_000
 assert set(groups)=={(i,b) for i in range(len(conditions)) for b in ['c','zig']}
 for (i,b),g in groups.items():
  assert len(g)==runs+1 and {x['run'] for x in g}==set(range(runs+1))
  for x in g:
   other=next(y for y in groups[i,'zig' if b=='c' else 'c'] if y['run']==x['run'])
   for k in ['seed','ready_hash','iterations','min_fd','max_fd','preflight_ready','wait_calls','events_observed','checksum','ctl_calls']:assert x[k]==other[k],(suite,i,k)
 validation[suite]=dict(rows=len(rows),measured=sum(not x['warmup'] for x in rows),conditions=len(conditions),sha256=hashlib.sha256((out/(suite+'.jsonl')).read_bytes()).hexdigest());allrows.extend(x for x in rows if not x['warmup'])
old=root.parent/'results';manifest=json.loads((root/'results/existing-manifest.json').read_text())
assert all(hashlib.sha256((old/f).read_bytes()).hexdigest()==h for f,h in manifest.items());validation['existing_files_unchanged']=len(manifest)
summary=[];by=collections.defaultdict(list)
for x in allrows:by[x['suite'],x['condition'],x['language']].append(x)
for (suite,i,language),g in sorted(by.items()):
 x=g[0];v=[row['duration_ns']/row['iterations'] for row in g];lo,hi=interval(v)
 item={k:x[k] for k in ['suite','condition','label','fds','ready_fds','backend','kind','timeout','capacity','placement','layout','work','changes','unit']};item.update(language=language,n=len(g),iterations=x['iterations'],ns_per_unit_median=st.median(v),ci95_low=lo,ci95_high=hi,min=min(v),max=max(v),million_units_seconds=st.median(v)/1000 if suite in ['A','B','C'] else '',measured_duration_s_median=st.median(row['duration_ns'] for row in g)/1e9,waits_per_unit=st.median(row['wait_calls']/row['iterations'] for row in g),events_per_unit=st.median(row['events_observed']/row['iterations'] for row in g),user_us_per_unit=st.median(row['user_us']/row['iterations'] for row in g),system_us_per_unit=st.median(row['system_us']/row['iterations'] for row in g));summary.append(item)
csvwrite('summary',summary)
# Matching seeds/runs pair implementation costs; no language-performance claim.
language_pairs=[];backend_pairs=[]
for suite in ['primary','controls']:
 for i in range(len(plan[suite])):
  g=[x for x in allrows if x['condition']==i and (x['suite'] in ['A','B','C'])==(suite=='primary')]
  if not g:continue
  d={b:{(x['run'],x['seed']):x for x in g if x['language']==b} for b in ['c','zig']};assert d['c'].keys()==d['zig'].keys()
  ratios=[(d['zig'][k]['duration_ns']/d['zig'][k]['iterations'])/(d['c'][k]['duration_ns']/d['c'][k]['iterations']) for k in d['c']];lo,hi=interval(ratios);language_pairs.append(dict(suite=suite,condition=i,n=len(ratios),zig_over_c_median=st.median(ratios),ci95_low=lo,ci95_high=hi))
for lang in ['c','zig']:
 for n in [100,1000]:
  for ready in [n//10,n//5,n//2,n]:
   d={b:{(x['run'],x['seed']):x for x in allrows if x['suite']=='A' and x['language']==lang and x['fds']==n and x['ready_fds']==ready and x['backend']==b} for b in ['poll','epoll']}
   if not d['poll']:continue
   assert d['poll'].keys()==d['epoll'].keys();ratios=[d['poll'][k]['duration_ns']/d['epoll'][k]['duration_ns'] for k in d['poll']];lo,hi=interval(ratios);backend_pairs.append(dict(language=lang,fds=n,ready_fds=ready,n=len(ratios),poll_over_epoll_median=st.median(ratios),ci95_low=lo,ci95_high=hi,poll_faster_runs=sum(v<1 for v in ratios)))
assessment=dict(validation=validation,language_pairs=language_pairs,backend_pairs=backend_pairs,interval_method='Paired or per-group median percentile bootstrap, 10000 resamples; descriptive, very small n; no outliers removed; historical n unknown',source_status='Independent reconstruction; original source unavailable; assumptions in SOURCES.md')
(out/'analysis.json').write_text(json.dumps(assessment,indent=2)+'\n');(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':17,'svg.fonttype':'none','svg.hashsalt':'kerrisk-reconstruction-20261019','axes.spines.top':False,'axes.spines.right':False})
def save(fig,name):
 fig.savefig(out/(name+'.svg'),metadata={'Date':None});plt.close(fig);path=out/(name+'.svg');path.write_text('\n'.join(s.rstrip() for s in path.read_text().splitlines())+'\n')
history=list(csv.DictReader((root/'results/historical.csv').open()))
# Separate panels: old source assumptions/hardware are not identical to ours.
for n in [100,1000]:
 fig,axes=plt.subplots(1,3,figsize=(15,4.4),layout='constrained',sharey=True)
 for ax,language in zip(axes,['historical','c','zig']):
  for backend in ['select','poll','epoll']:
   if language=='historical':
    rows=sorted([x for x in history if x['suite']=='A' and int(x['fds'])==n and x['backend']==backend],key=lambda x:int(x['ready_fds']));xs=[int(x['ready_fds'])/n*100 for x in rows];ys=[float(x['seconds']) for x in rows];ax.plot(xs,ys,'-o',color=colors[backend],label=backend)
   else:
    rows=sorted([x for x in summary if x['suite']=='A' and x['fds']==n and x['backend']==backend and x['language']==language],key=lambda x:x['ready_fds']);xs=[x['ready_fds']/n*100 for x in rows];ys=[x['million_units_seconds'] for x in rows];ax.plot(xs,ys,'-o',color=colors[backend],label=backend);ax.fill_between(xs,[x['ci95_low']/1000 for x in rows],[x['ci95_high']/1000 for x in rows],color=colors[backend],alpha=.15)
  ax.set(title={'historical':'Kerrisk: past measurements','c':'C reconstruction (GCC -O2)','zig':'Zig reconstruction (ReleaseFast)'}[language],xlabel='Ready (%)',ylim=(0,None));ax.grid(alpha=.2)
 axes[0].set_ylabel('Seconds / 1,000,000 waits');axes[0].legend(fontsize=12)
 fig.supxlabel(f'{n} fds | separate experiments; original details unknown | current: pipe, contiguous, timeout=-1, maxevents=N, API-only\nOrbStack / Linux 7.0.14 aarch64 / Zig 0.17.0 ReleaseFast / GCC -O2 / CPU 2 | median n=3, nominal 95% bootstrap',fontsize=9);save(fig,'density-'+str(n))
if any(x['suite']=='B' for x in summary):
 fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained',sharey=True)
 for ax,lang in zip(axes,['c','zig']):
  for b in ['poll','epoll']:
   rows=sorted([x for x in summary if x['suite']=='B' and x['language']==lang and x['backend']==b],key=lambda x:x['fds']);ax.plot([x['fds'] for x in rows],[x['million_units_seconds'] for x in rows],'-o',color=colors[b],label=b)
  ax.set(xscale='log',xlabel='Monitored fds',title=lang,ylim=(0,None));ax.grid(alpha=.2);ax.legend()
 axes[0].set_ylabel('Seconds / 1,000,000 waits');fig.supxlabel('1 middle ready | current reconstruction | median n=3 | CPU 2 / OrbStack / Linux 7.0.14 / Zig 0.17.0',fontsize=10);save(fig,'sparse')
if any(x['suite']=='C' for x in summary):
 fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
 for ax,language in zip(axes,['c','zig']):
  rows=sorted([x for x in summary if x['suite']=='C' and x['language']==language],key=lambda x:x['changes']);ax.plot([x['changes'] for x in rows],[x['million_units_seconds'] for x in rows],'-o',color=colors['epoll']);ax.fill_between([x['changes'] for x in rows],[x['ci95_low']/1000 for x in rows],[x['ci95_high']/1000 for x in rows],color=colors['epoll'],alpha=.15);ax.set(xlabel='DEL+ADD pairs per iteration',ylabel='Seconds / 1,000,000 iterations',title=language,ylim=(0,None));ax.grid(alpha=.2)
 fig.supxlabel('100 fds, 1 middle ready | wait + 2K epoll_ctl | median n=3, nominal bootstrap band\nOrbStack / Linux 7.0.14 aarch64 / CPU 2 / GCC -O2 / Zig 0.17.0 ReleaseFast',fontsize=10);save(fig,'ctl')
if 'controls' in validation:
 # Full Ready-set completion is explicitly separated from one bounded call.
 fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
 for ax,work in zip(axes,['api','full']):
  for language,color in [('c','#171717'),('zig','#7e22ce')]:
   rows=sorted([x for x in summary if x['suite']=='capacity' and x['work']==work and x['language']==language],key=lambda x:x['capacity']);ax.plot([x['capacity'] for x in rows],[x['ns_per_unit_median']/1000 for x in rows],'-o',color=color,label=language)
  ax.set(xscale='log',xlabel='maxevents',ylabel='µs / bounded call' if work=='api' else 'µs / complete Ready set',title='One call: different returned event counts' if work=='api' else 'Collect all 1000 unique ready fds',ylim=(0,None));ax.legend();ax.grid(alpha=.2)
 fig.supxlabel('Pipe, 1000/1000 ready | call and full-set units differ | LT re-notifications, no consuming I/O | median n=5\nOrbStack / Linux 7.0.14 aarch64 / CPU 2 / GCC -O2 / Zig 0.17.0 ReleaseFast',fontsize=10);save(fig,'capacity')
(out/'analysis-environment.json').write_text(json.dumps(dict(python=sys.version,matplotlib=matplotlib.__version__,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
print(json.dumps(validation,indent=2))
# LT: omit the secondary select line for clarity, retain it in the full report.
fig,axes=plt.subplots(1,3,figsize=(14,4.2),layout='constrained',sharey=True)
for ax,language in zip(axes,['historical','c','zig']):
 for backend in ['poll','epoll']:
  if language=='historical':
   rows=sorted([x for x in history if x['suite']=='A' and int(x['fds'])==1000 and x['backend']==backend],key=lambda x:int(x['ready_fds']));xs=[int(x['ready_fds'])/10 for x in rows];ys=[float(x['seconds']) for x in rows]
  else:
   rows=sorted([x for x in summary if x['suite']=='A' and x['fds']==1000 and x['backend']==backend and x['language']==language],key=lambda x:x['ready_fds']);xs=[x['ready_fds']/10 for x in rows];ys=[x['million_units_seconds'] for x in rows]
  ax.plot(xs,ys,'-o',color=colors[backend],label=backend,linewidth=2)
  if language!='historical':ax.fill_between(xs,[x['ci95_low']/1000 for x in rows],[x['ci95_high']/1000 for x in rows],color=colors[backend],alpha=.15)
 ax.set(title={'historical':'Kerrisk (past)','c':'C (reconstructed)','zig':'Zig (reconstructed)'}[language],xlabel='Ready (%)',ylim=(0,None));ax.grid(alpha=.2);ax.legend(fontsize=13)
axes[0].set_ylabel('Seconds / 1,000,000 waits')
fig.supxlabel('1000 fds | historical/current are separate experiments; original details unknown\nCurrent: pipe / contiguous / timeout=-1 / maxevents=N / API-only | OrbStack / Linux 7.0.14 / GCC -O2 / Zig 0.17.0 ReleaseFast / CPU 2 / median n=3',fontsize=8.5);save(fig,'lt-density')
if 'controls' in validation:
 fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
 for ax,backend in zip(axes,['poll','select']):
  for timeout,style in [(-1,'-o'),(0,'--s')]:
   rows=[next(x for x in summary if x['suite']=='position' and x['language']=='zig' and x['backend']==backend and x['timeout']==timeout and x['placement']==where) for where in ['first','middle','last']]
   ax.plot(['first','middle','last'],[x['ns_per_unit_median']/1000 for x in rows],style,label=f'timeout={timeout}',color=colors[backend] if timeout==-1 else '#171717')
  ax.set(title=backend,xlabel='Position of the single ready fd',ylabel='µs / wait',ylim=(0,None));ax.legend();ax.grid(alpha=.2)
 fig.supxlabel('1000 pipe fds / Zig 0.17.0 ReleaseFast / OrbStack Linux 7.0.14 aarch64 / CPU 2 | median n=5',fontsize=10);save(fig,'position')
