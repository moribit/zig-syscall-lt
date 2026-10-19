#!/usr/bin/env python3
"""Post-measurement traces for both frozen primary and corrected controls."""
import hashlib,json,subprocess as sp
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'results/main';records=[]
for version,bindir in [('primary','/tmp/kerrisk-primary-bin'),('controls','/tmp/kerrisk-reproduction-bin')]:
 env=json.loads((out/(version+'-environment.json')).read_text())
 for language in ['c','zig']:
  binary=Path(bindir)/language;assert hashlib.sha256(binary.read_bytes()).hexdigest()==env['binary_sha256'][language]
  for backend in ['select','poll','epoll']:
   for timeout in [-1,0]:
    command=['strace','-e','trace=ppoll,pselect6,epoll_pwait,epoll_ctl,dup2,dup3,pipe2,fcntl','-s','32',str(binary),backend,'pipe','8','4','5',str(timeout),'8','random','contiguous','api','0','17']
    r=sp.run(command,text=True,capture_output=True,timeout=30,check=True);x=json.loads(r.stdout);assert x['wait_calls']==5
    records.append(dict(version=version,language=language,backend=backend,timeout=timeout,command=command,stdout=x,trace=r.stderr,excluded_from_performance=True))
  command=['strace','-c','-e','trace=epoll_ctl,epoll_pwait',str(binary),'epoll','pipe','100','1','10','-1','100','middle','contiguous','api','5','17']
  r=sp.run(command,text=True,capture_output=True,timeout=30,check=True);x=json.loads(r.stdout);assert x['wait_calls']==10 and x['ctl_calls']==100
  records.append(dict(version=version,language=language,command=command,stdout=x,trace=r.stderr,excluded_from_performance=True,expected_total_epoll_ctl=200,note='100 initial ADD + 10 * 5 * (DEL+ADD); one preflight wait is outside timed counters'))
(out/'observations.json').write_text(json.dumps(records,indent=2)+'\n')
print('Separate traces saved for both exact binary hashes; performance data unchanged.')
