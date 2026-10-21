#!/usr/bin/env python3
"""Validate complete raw data and regenerate CSV/SVG and the analysis report."""
import argparse,collections,csv,hashlib,json,random,statistics as st,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent;p=argparse.ArgumentParser();p.add_argument('directory',nargs='?',type=Path,default=root/'results/main');out=p.parse_args().directory
plan=json.loads((out/'plan.json').read_text());env=json.loads((out/'environment.json').read_text());assert 'end_stat' in env
raw=[json.loads(line) for line in (out/'raw.jsonl').read_text().splitlines()]
assert len(raw)==len(plan['conditions'])*(plan['runs']+1)
assert max(x['sequence'] for x in raw if x['warmup'])<min(x['sequence'] for x in raw if not x['warmup'])
assert len({x['sequence'] for x in raw})==len(raw)
assert hashlib.sha256((out/'raw.jsonl').read_bytes()).hexdigest()==env['raw_sha256']
assert all(hashlib.sha256((out/'source-snapshot'/f).read_bytes()).hexdigest()==h for f,h in env['source_sha256'].items())
manifest=json.loads((root/'results/existing-manifest.json').read_text());assert all(hashlib.sha256((root.parent/f).read_bytes()).hexdigest()==h for f,h in manifest.items())
groups=collections.defaultdict(list)
for x in raw:
 c=plan['conditions'][x['condition']];assert all(x[k]==v for k,v in c.items())
 assert x['seed']==plan['seed_base']+x['run'] and x['warmup']==(x['run']==0)
 assert x['bursts']==(plan['warmup_bursts'] if x['warmup'] else plan['bursts'])
 assert x['messages']==x['ready_fds']*x['bursts'] and x['bytes_received']==x['bytes_sent']==x['messages']*x['payload']
 assert x['errors']==0 and x['status']=='OK' and x['e2e_ns']>0
 assert x['e2e_ns']==x['producer_ns']+x['consumer_ns']
 if x['backend']=='uring':assert x['recv_calls']==0 and x['cqes']>=x['messages']
 if x['backend'] in ['poll','epoll']:assert x['enter_calls']==0 and x['cqes']==0
 if x['backend']=='uring-poll':assert x['cqes']>=x['messages']
 groups[x['condition']].append(x)
assert set(groups)==set(range(len(plan['conditions'])))
for i,g in groups.items():assert len(g)==11 and {x['run'] for x in g}==set(range(11))
def ci(v):
 rng=random.Random(314159);med=sorted(st.median(rng.choices(v,k=len(v))) for _ in range(10000));return med[250],med[9749]
def csvwrite(name,rows):
 with (out/(name+'.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
summary=[]
for i,g in sorted(groups.items()):
 g=[x for x in g if not x['warmup']];c=plan['conditions'][i];rate=[x['messages']*1e9/x['e2e_ns'] for x in g];lo,hi=ci(rate)
 row=dict(c,condition=i,n=len(g),bursts=g[0]['bursts'],actual_ready_ratio=c['ready_fds']/c['fds'],messages=g[0]['messages'],bytes_received=g[0]['bytes_received'],msg_s_median=st.median(rate),msg_s_ci95_low=lo,msg_s_ci95_high=hi,msg_s_min=min(rate),msg_s_max=max(rate))
 for key in ['e2e_ns','producer_ns','consumer_ns','submit_ns','wait_ns','first_completion_ns','backend_init_ns','workload_setup_ns','ring_setup_ns','mmap_ns','buffer_allocation_ns','initial_submit_ns','cancel_ns','destroy_ns','user_us','system_us','lifetime_user_us','lifetime_system_us','wait_calls','recv_calls','send_calls','enter_calls','initial_enter_calls','finish_enter_calls','cq_copy_calls','sqes_submitted_including_initial','eagain','eintr']:
  row[key+'_median']=st.median(x[key] for x in g)
 row['cpu_us_median']=st.median(x['user_us']+x['system_us'] for x in g)
 row['lifetime_cpu_us_median']=st.median(x['lifetime_user_us']+x['lifetime_system_us'] for x in g)
 row['bytes_s_median']=st.median(x['bytes_received']*1e9/x['e2e_ns'] for x in g)
 inclusive=[x['backend_init_ns']+x['e2e_ns']+x['cancel_ns']+x['destroy_ns'] for x in g]
 row['lifecycle_ns_median']=st.median(inclusive)
 row['lifecycle_msg_s_median']=st.median(x['messages']*1e9/v for x,v in zip(g,inclusive))
 row['all_including_socket_ns_median']=st.median(x['workload_setup_ns']+v for x,v in zip(g,inclusive))
 row['selected_io_calls_median']=st.median(x['send_calls']+x['recv_calls']+x['wait_calls']+x['enter_calls'] for x in g)
 summary.append(row)
csvwrite('summary',summary)
# Paired ratios: identical run/seed/condition, no outlier removal.
pairs=[]
for c in summary:
 if c['backend']=='epoll':continue
 ref=next(x for x in summary if x['backend']=='epoll' and all(x[k]==c[k] for k in ['fds','ready_fds','payload']))
 left={x['run']:x for x in groups[c['condition']] if not x['warmup']};right={x['run']:x for x in groups[ref['condition']] if not x['warmup']};assert left.keys()==right.keys()
 ratios=[];life=[]
 for run,x in left.items():
  y=right[run];assert x['seed']==y['seed'] and x['messages']==y['messages'] and x['bytes_received']==y['bytes_received']
  ratios.append(y['e2e_ns']/x['e2e_ns'])
  life.append((y['backend_init_ns']+y['e2e_ns']+y['cancel_ns']+y['destroy_ns'])/(x['backend_init_ns']+x['e2e_ns']+x['cancel_ns']+x['destroy_ns']))
 lo,hi=ci(ratios);llo,lhi=ci(life)
 pairs.append(dict(condition=c['condition'],backend=c['backend'],label=c['label'],fds=c['fds'],ready_fds=c['ready_fds'],payload=c['payload'],n=len(ratios),speed_over_epoll_median=st.median(ratios),ci95_low=lo,ci95_high=hi,lifecycle_speed_over_epoll_median=st.median(life),lifecycle_ci95_low=llo,lifecycle_ci95_high=lhi))
csvwrite('paired',pairs)
validation=dict(rows=len(raw),measured=sum(not x['warmup'] for x in raw),conditions=len(groups),existing_files_unchanged=len(manifest),source_hashes_match=True,raw_sha256=env['raw_sha256'],interval='Paired or per-group median percentile bootstrap 10000 resamples; descriptive, no outliers removed',python=sys.version,matplotlib=matplotlib.__version__)
(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':14,'svg.fonttype':'none','svg.hashsalt':'zig-uring-20261021','axes.spines.top':False,'axes.spines.right':False})
colors={'poll':'#1d4ed8','epoll':'#b45309','uring':'#7e22ce','uring-poll':'#047857'}
def save(fig,name):
 fig.savefig(out/(name+'.svg'),metadata={'Date':None});plt.close(fig);path=out/(name+'.svg');path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
for payload in [64,1024]:
 fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
 for ax,n in zip(axes,[1024,4096]):
  for backend in ['poll','epoll','uring']:
   rows=sorted([x for x in summary if x['label']=='baseline' and x['fds']==n and x['payload']==payload and x['backend']==backend],key=lambda x:x['ready_fds'])
   xs=[x['actual_ready_ratio']*100 for x in rows];ax.plot(xs,[x['msg_s_median']/1e6 for x in rows],'-o',color=colors[backend],label=backend);ax.fill_between(xs,[x['msg_s_ci95_low']/1e6 for x in rows],[x['msg_s_ci95_high']/1e6 for x in rows],color=colors[backend],alpha=.15)
  ax.set(title=f'{n} fds / {payload} B',xlabel='Actual Ready (%)',ylabel='Million messages / s',ylim=(0,None));ax.grid(alpha=.2);ax.legend(fontsize=11)
 fig.supxlabel('Send + receive + content validation + rearm | 32 bursts | median n=10, nominal 95% bootstrap\nM2 / OrbStack Fedora / Linux 7.0.14 aarch64 / Zig 0.17.0 ReleaseFast / CPU 2 | setup/teardown excluded',fontsize=9);save(fig,'e2e-'+str(payload))
fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
for ax,n in zip(axes,[1024,4096]):
 for backend in ['poll','epoll','uring-poll']:
  rows=sorted([x for x in summary if x['label']=='baseline' and x['fds']==n and x['payload']==1024 and x['backend']==backend],key=lambda x:x['ready_fds']);ax.plot([x['actual_ready_ratio']*100 for x in rows],[x['msg_s_median']/1e6 for x in rows],'-o',color=colors[backend],label=backend)
 ax.set(title=f'{n} fds / 1024 B',xlabel='Actual Ready (%)',ylabel='Million notification+drain cycles / s',ylim=(0,None));ax.legend(fontsize=11);ax.grid(alpha=.2)
fig.supxlabel('Oneshot POLL_ADD + recv + rearm, not repeated non-consuming LT | 32 bursts | median n=10\nM2 / OrbStack Fedora / Linux 7.0.14 aarch64 / Zig 0.17.0 ReleaseFast / CPU 2',fontsize=9);save(fig,'poll-add')
fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
for ax,n in zip(axes,[1024,4096]):
 for pct,style in [(1,'-o'),(100,'--s')]:
  rows=[next(x for x in summary if x['fds']==n and x['ready_percent_requested']==pct and x['payload']==1024 and x['backend']=='uring' and x['label']==label) for label in ['batch-1','batch-8','batch-32','baseline']]
  ax.plot([1,8,32,n],[x['msg_s_median']/1e6 for x in rows],style,label=f'Ready {pct}%')
 ax.set(title=f'{n} fds / 1024 B',xscale='log',xlabel='Submission batch limit',ylabel='Million messages / s',ylim=(0,None));ax.legend();ax.grid(alpha=.2)
fig.supxlabel('32 bursts | same work, tail batches flushed after each CQ batch | median n=10\nM2 / OrbStack Fedora / Linux 7.0.14 aarch64 / Zig 0.17.0 ReleaseFast / CPU 2',fontsize=9);save(fig,'batch')
fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
for ax,pct in zip(axes,[1,100]):
 rows=[next(x for x in summary if x['fds']==4096 and x['ready_percent_requested']==pct and x['payload']==1024 and x['backend']==backend and x['label']=='baseline') for backend in ['poll','epoll','uring']]
 xs=list(range(3));ax.bar([x-.18 for x in xs],[x['e2e_ns_median']/1e6 for x in rows],width=.36,label='Burst window');ax.bar([x+.18 for x in xs],[x['lifecycle_ns_median']/1e6 for x in rows],width=.36,label='Backend lifecycle');ax.set(xticks=xs,xticklabels=['poll','epoll','uring'],ylabel='ms / 32 bursts',title=f'4096 fds / Ready {pct}% / 1024 B',ylim=(0,None));ax.legend(fontsize=10)
fig.supxlabel('Lifecycle = backend init + measured window + cancel/drain + destroy (socket creation separate)\nMedian n=10 / M2 OrbStack Linux 7.0.14 / Zig 0.17.0 ReleaseFast / CPU 2',fontsize=9);save(fig,'lifecycle')
print(json.dumps(validation,indent=2))
