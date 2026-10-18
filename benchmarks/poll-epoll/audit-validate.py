#!/usr/bin/env python3
"""Validate every new row, including warmup and diagnostic runs, independent of speed."""
import argparse,collections,hashlib,json,math
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('directory',nargs='?',type=Path,default=root/'results/audit-v2');out=parser.parse_args().directory
report={}
for name,total,keys,runs in [('probe',840,['fds','ready_fds','backend','mode'],21),('controls',372,['ready_fds','backend','order'],31),('replication',62,['backend'],31),('dynamic',99,['high_ms','backend'],11),('dynamic-warmed',99,['high_ms','backend'],11),('confirmation',124,['backend','order'],31)]:
 if name=='dynamic' and not (out/'dynamic.jsonl').exists():continue
 rows=[json.loads(s) for s in (out/(name+'.jsonl')).read_text().splitlines()];assert len(rows)==total
 groups=collections.defaultdict(list)
 for x in rows:
  groups[tuple(x[k] for k in keys)].append(x)
  assert x['warmup']==(x['run']==0)
  assert x['end_unix_ns']>=x['start_unix_ns'] and x['duration_ns']>0
  if name=='probe':assert x['checksum']==x['ready_fds']*x['iterations']
  else:
   assert x['errors']==0
   if name in ['dynamic','dynamic-warmed']:
    assert x['messages']==sum(p['messages'] for p in x['phases']) and x['duration_ns']==sum(p['duration_ns'] for p in x['phases'])
    assert x['switches']==sum(p['switches'] for p in x['phases']) and x['switch_ns']==sum(p['switch_ns'] for p in x['phases'])
    for i,p in enumerate(x['phases']):assert p['ready_fds']==[41,4096,41][i] and p['messages']==p['ready_fds']*p['batches'] and p['bytes']==p['messages']*1024
   else:
    assert x['messages']==x['ready_fds']*x['iterations'] and x['bytes_sent']==x['bytes_received']==x['messages']*x['payload']
    assert x['e2e_duration_ns']>=x['producer_ns']+x['duration_ns']>=x['acquisition_ns']
 if name=='dynamic-warmed':assert max(x['sequence'] for x in rows if x['warmup']) < min(x['sequence'] for x in rows if not x['warmup'])
 for g in groups.values():
  assert len(g)==runs and {x['run'] for x in g}==set(range(runs))
  assert len({(x['run'],x['seed']) for x in g})==runs
 report[name]=dict(rows=len(rows),groups=len(groups),warmups=sum(x['warmup'] for x in rows),sha256=hashlib.sha256((out/(name+'.jsonl')).read_bytes()).hexdigest())
rows=[json.loads(s) for s in (out/'diagnostics.jsonl').read_text().splitlines()]
for high in [200,1000,5000]:
 sample=[x for x in rows if x['high_ms']==high and 'phases'in x];assert len(sample)==1
 sample=sample[0];log=[x for x in rows if x['high_ms']==high and 'phases'not in x]
 assert [x['elapsed_ns'] for x in log]==sorted(x['elapsed_ns'] for x in log)
 assert sample['switches']==sum(x['actual_ns']>0 for x in log) and sample['switch_ns']==sum(x['actual_ns'] for x in log)
 for x in log:
  assert (x['actual_ns']>0)==(x['before_epoll']!=x['after_epoll'])
  assert all(math.isfinite(x[k]) for k in ['ema','poll_ns','epoll_ns','estimate_ns'])
 report['diagnostics_'+str(high)]=dict(decisions=len(log),switches=sample['switches'])
env=json.loads((out/'environment.json').read_text())
for name,h in env['sources'].items():assert hashlib.sha256((out/'source-snapshot'/name).read_bytes()).hexdigest()==h
warmed_env=out/'dynamic-warmed-environment.json'
if warmed_env.exists():
 info=json.loads(warmed_env.read_text());assert hashlib.sha256((out/'warmed-source-snapshot/adaptive.zig').read_bytes()).hexdigest()==info['source_sha256']
manifest=json.loads((out/'historical-manifest.json').read_text())
for p,h in manifest.items():assert hashlib.sha256((root/'results'/p).read_bytes()).hexdigest()==h
report['historical_files_unchanged']=len(manifest);report['measured_source_snapshot_matches']=True
(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
