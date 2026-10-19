#!/usr/bin/env python3
"""Correctness checks only: never assert which implementation is faster."""
import json,subprocess as sp
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sp.run(['gcc','-O2','-Wall','-Wextra','-Werror',str(root/'c/reconstructed.c'),'-o','/tmp/kerrisk-test-c'],check=True)
sp.run(['zig','build-exe','-O','Debug',str(root/'zig/main.zig'),'-femit-bin=/tmp/kerrisk-test-zig'],check=True)
sp.run(['gcc','-O1','-g','-fsanitize=address,undefined',str(root/'c/reconstructed.c'),'-o','/tmp/kerrisk-test-san'],check=True)
count=0
for kind in ['pipe','socket']:
 for backend in ['select','poll','epoll']:
  for n,r in [(1,0),(1,1),(8,0),(8,1),(8,8)]:
   for work in ['api','scan','verify','scan-only','verify-only']:
    args=[backend,kind,str(n),str(r),'5','0',str(n),'first','contiguous',work,'0','17'];rows=[]
    for binary in ['c','zig','san']:
     x=json.loads(sp.check_output(['/tmp/kerrisk-test-'+binary,*args],text=True,stderr=sp.PIPE));assert x['errors']==0 and x['preflight_ready']==r;rows.append(x)
    for key in ['ready_hash','wait_calls','events_observed','checksum','ctl_calls','min_fd','max_fd','preflight_ready']:assert len({x[key] for x in rows})==1,(args,key,rows)
    count+=1
for cap in [1,3,8]:
 for work in ['api','full','verify']:
  args=['epoll','pipe','8','8','5','-1',str(cap),'random','contiguous',work,'0','77'];rows=[json.loads(sp.check_output(['/tmp/kerrisk-test-'+b,*args],text=True)) for b in ['c','zig','san']]
  for key in ['ready_hash','wait_calls','events_observed','checksum','ctl_calls']:assert len({x[key] for x in rows})==1,(args,key)
  count+=1
for k in [0,1,5,8]:
 for work in ['api','ctl-only']:
  args=['epoll','socket','8','1','5','-1','8','middle','normal',work,str(k),'17'];rows=[json.loads(sp.check_output(['/tmp/kerrisk-test-'+b,*args],text=True)) for b in ['c','zig','san']]
  assert all(x['ctl_calls']==2*k*5 for x in rows);assert len({x['ready_hash'] for x in rows})==1;count+=1
for b in ['c','zig']:
 for args in [['poll','pipe','1','0','1','-1','1','first','normal','api','0','17'],['select','pipe','1000','1','1','0','1000','middle','normal','api','0','17']]:
  r=sp.run(['/tmp/kerrisk-test-'+b,*args],capture_output=True,timeout=10);assert r.returncode!=0;count+=1
print(f'{count} scenarios passed: C/Zig parity, C ASan/UBSan, Zig Debug, zero/all-ready, bounded/full sets, mutations, fd_set limits and non-blocking test termination.')
