#!/usr/bin/env python3
"""Validate counts and transport invariants without testing relative speed."""
import collections, hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parent
report={}
for group in ['fixed','replication']:
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
   assert x['bytes_received']==x['bytes_sent']==x['messages']*x['payload']
  else:
   assert x['events_observed']==x['ready_fds']*x['iterations']
 for n,ratio,payload,mode in meta['conditions']:
  for backend in ['poll','epoll']:
   assert counts[(mode,n,ratio,payload,backend,False)]==meta['runs']
   assert counts[(mode,n,ratio,payload,backend,True)]==meta['warmups']
 assert len(rows)==len(meta['conditions'])*2*(meta['runs']+meta['warmups'])
 report[group]=dict(rows=len(rows),measured=sum(not x['warmup'] for x in rows),warmups=sum(x['warmup'] for x in rows),raw_sha256=hashlib.sha256((directory/'raw.jsonl').read_bytes()).hexdigest())
report['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.zig')}
(root/'results/validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('All saved samples satisfy count, byte, message, and event invariants.')
