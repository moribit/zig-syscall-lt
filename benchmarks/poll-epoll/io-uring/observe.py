#!/usr/bin/env python3
"""Independent strace observations; tracer durations never join performance data."""
import argparse,hashlib,json,re,subprocess as sp
from pathlib import Path
root=Path(__file__).resolve().parent;p=argparse.ArgumentParser();p.add_argument('directory',nargs='?',type=Path,default=root/'results/main');out=p.parse_args().directory
env=json.loads((out/'environment.json').read_text());binary=Path('/tmp/zig-uring-bench');assert hashlib.sha256(binary.read_bytes()).hexdigest()==env['binary_sha256']
observations=[]
conditions=[(b,64,r,64,64) for b in ['poll','epoll','uring','uring-poll'] for r in [1,64]]+ [('uring',1024,1024,b,1024) for b in [1,8,32,1024]]
for backend,n,ready,batch,capacity in conditions:
 command=['taskset','-c','2','strace','-c',str(binary),backend,str(n),str(ready),'1024','4','31',str(batch),str(capacity),str(n)]
 child=sp.run(command,text=True,capture_output=True,check=True,timeout=120);x=json.loads(child.stdout);counts={}
 for line in child.stderr.splitlines():
  cols=line.split()
  if len(cols) in [5,6] and re.match(r'^[0-9.]+$',cols[0]) and cols[-1]!='total':
   counts[cols[-1]]=int(cols[3])
 if backend.startswith('uring'):assert counts.get('io_uring_enter',0)==x['initial_enter_calls']+x['enter_calls']+x['finish_enter_calls']
 if backend=='poll':assert counts.get('ppoll',0)==x['wait_calls']
 if backend=='epoll':assert counts.get('epoll_pwait',0)==x['wait_calls']
 assert counts.get('sendto',0)==x['send_calls'] and counts.get('recvfrom',0)==x['recv_calls']
 observations.append(dict(command=command,backend=backend,fds=n,ready_fds=ready,batch=batch,bursts=4,stdout=x,syscall_counts=counts,summary=child.stderr,excluded_from_performance=True))
command=['strace','-e','trace=io_uring_setup,io_uring_enter,io_uring_register,mmap,munmap,close','/tmp/zig-uring-probe']
child=sp.run(command,text=True,capture_output=True,check=True);probe=dict(command=command,stdout=json.loads(child.stdout),trace=child.stderr,excluded_from_performance=True)
(out/'observations.json').write_text(json.dumps(dict(observations=observations,probe=probe),indent=2)+'\n')
print('Validated separate strace counts for',len(observations),'runs; mmap/setup/enter/register trace saved.')
