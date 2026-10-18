#!/usr/bin/env python3
"""Validate counts and transport invariants without testing relative speed."""
import collections, hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parent
report={}
for group in ['fixed','replication','end-to-end','end-to-end-replication','crossover-check']:
 directory=root/'results'/group
 meta=json.loads((directory/'environment.json').read_text())
 rows=[json.loads(x) for x in (directory/'raw.jsonl').read_text().splitlines()]
 counts=collections.Counter()
 for x in rows:
  counts[(x['benchmark'],x['fds'],x['requested_ready_percent'],x['payload'],x['backend'],x['warmup'])]+=1
  assert 0<=x['acquisition_ns']<=x['duration_ns']
  assert x['errors']==0 and x['ready_ratio']==x['ready_fds']/x['fds']
  if x['benchmark']=='receive':
   assert x['messages']==x['ready_fds']*x['iterations']
   if 'e2e_duration_ns' in x:
    assert x['e2e_duration_ns']>=x['duration_ns']+x['producer_ns']
    assert x['e2e_user_us']>=x['user_us'] and x['e2e_system_us']>=x['system_us']
   assert x['bytes_received']==x['bytes_sent']==x['messages']*x['payload']
  else:
   assert x['events_observed']==x['ready_fds']*x['iterations']
 for n,ratio,payload,mode in meta['conditions']:
  for backend in ['poll','epoll']:
   assert counts[(mode,n,ratio,payload,backend,False)]==meta['runs']
   assert counts[(mode,n,ratio,payload,backend,True)]==meta['warmups']
 assert len(rows)==len(meta['conditions'])*2*(meta['runs']+meta['warmups'])
 report[group]=dict(rows=len(rows),measured=sum(not x['warmup'] for x in rows),warmups=sum(x['warmup'] for x in rows),raw_sha256=hashlib.sha256((directory/'raw.jsonl').read_bytes()).hexdigest())
adaptive=root/'results/adaptive/raw.jsonl'
if adaptive.exists():
 rows=[json.loads(x) for x in adaptive.read_text().splitlines()]
 assert len(rows)==33
 for x in rows:
  assert x['errors']==0 and x['messages']==sum(p['messages'] for p in x['phases'])
  for p,ready in zip(x['phases'],[41,4096,41]):
   assert p['ready_fds']==ready and p['duration_ns']>=200_000_000
   assert p['messages']==ready*p['batches'] and p['bytes']==p['messages']*1024
 report['adaptive']=dict(rows=33,measured=30,warmups=3,raw_sha256=hashlib.sha256(adaptive.read_bytes()).hexdigest())
report['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.zig')}
(root/'results/validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('All saved samples satisfy count, byte, message, and event invariants.')
