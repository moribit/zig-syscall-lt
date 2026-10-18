#!/usr/bin/env python3
"""Run perf/strace separately, never merge their timings with normal measurements."""
import hashlib,json,subprocess as sp
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/'results/audit-v2'
records=[]
for backend in ['poll','epoll']:
 command=['taskset','-c','2','/tmp/poll-audit',backend,'receive','4096','4096','1024','64','20261102']
 for tool,prefix in [('perf',['perf','stat','-e','cycles,instructions,task-clock,context-switches,cpu-migrations','--']),('strace',['strace','-c','-e','ppoll,epoll_pwait,epoll_ctl,sendto,recvfrom'])]:
  try:
   r=sp.run(prefix+command,text=True,capture_output=True,timeout=60)
   records.append(dict(tool=tool,backend=backend,command=prefix+command,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,excluded_from_performance_analysis=True))
  except FileNotFoundError as e:records.append(dict(tool=tool,error=str(e)))
(out/'observations.json').write_text(json.dumps(records,indent=2)+'\n')
(out/'binary-sha256.json').write_text(json.dumps({b:hashlib.sha256(Path('/tmp',b).read_bytes()).hexdigest() for b in ['poll-audit','poll-probe','adaptive-audit']},indent=2)+'\n')
