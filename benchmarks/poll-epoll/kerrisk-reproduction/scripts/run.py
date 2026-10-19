#!/usr/bin/env python3
"""Frozen reconstruction experiment. No existing data is overwritten."""
import argparse,datetime,hashlib,json,os,platform,random,resource,shutil,subprocess as sp,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=root/'results/main');p.add_argument('--suite',choices=['primary','controls'],default='primary');a=p.parse_args();out=a.output
if platform.system()!='Linux' or sp.check_output(['zig','version'],text=True).strip()!='0.17.0':raise SystemExit('Linux and Zig 0.17.0 are required')
if 2 not in os.sched_getaffinity(0):raise SystemExit('CPU 2 unavailable; record a new affinity protocol before running')
if resource.getrlimit(resource.RLIMIT_NOFILE)[0]<5000:raise SystemExit('Need RLIMIT_NOFILE >= 5000 for relocation headroom')
out.mkdir(parents=True,exist_ok=True)
if (out/(a.suite+'.jsonl')).exists():raise SystemExit('Output exists: choose a new directory; no overwrite/resume')
source_hash={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [root/'c/reconstructed.c',root/'zig/main.zig']}
primary=[];controls=[]
def condition(suite,label,n,r,backend,kind='pipe',timeout=-1,cap=None,placement='random',layout='contiguous',work='api',changes=0,loops=1_000_000):
 return dict(suite=suite,label=label,fds=n,ready_fds=r,backend=backend,kind=kind,timeout=timeout,capacity=n if cap is None else cap,placement=placement,layout=layout,work=work,changes=changes,iterations=loops,unit='ready_set' if work=='full' else 'prepared_scan' if work in ['scan-only','verify-only'] else 'ctl_iteration' if work=='ctl-only' else 'wait_call')
for n in [100,1000]:
 for pct in [10,20,50,100]:
  for b in ['select','poll','epoll']:primary.append(condition('A',f'{pct}% ready',n,n*pct//100,b))
for n in [1,10,100,1000]:
 for b in ['poll','epoll']:primary.append(condition('B','one middle ready',n,1,b,placement='middle'))
for k in [0,1,5,10]:primary.append(condition('C','DEL+ADD per iteration',100,1,'epoll',placement='middle',changes=k))
# Fixed path from reconstructed baseline toward the existing benchmark. Each edge
# changes one factor. Extra direct controls isolate timeout and scan/validation.
variants=[('baseline',{}),('socket',dict(kind='socket')),('socket-normal',dict(kind='socket',layout='normal')),('existing-api',dict(kind='socket',layout='normal',timeout=0)),('existing-scan',dict(kind='socket',layout='normal',timeout=0,work='scan')),('pipe-timeout0',dict(timeout=0)),('pipe-scan',dict(work='scan')),('pipe-verify',dict(work='verify')),('scan-only',dict(work='scan-only')),('verify-only',dict(work='verify-only'))]
for ready in [10,1000]:
 for label,kw in variants:
  for b in ['poll','epoll']:controls.append(condition('factors',label,1000,ready,b,loops=100_000 if kw.get('work') in ['scan-only','verify-only'] else 20_000,**kw))
for cap in [1,16,64,1000]:
 for work,loops in [('api',100_000),('full',1000)]:controls.append(condition('capacity',f'capacity {cap}',1000,1000,'epoll',cap=cap,work=work,loops=loops))
for placement in ['first','middle','last']:
 for timeout in [-1,0]:
  for b in ['poll','select']:controls.append(condition('position',placement,1000,1,b,placement=placement,timeout=timeout,loops=20_000))
for k in [1,5,10]:controls.append(condition('ctl-only','DEL+ADD only',100,1,'epoll',placement='middle',work='ctl-only',changes=k,loops=100_000))
plan=dict(primary=primary,controls=controls,primary_runs=3,control_runs=5,warmup_iterations=2000,primary_iterations=1_000_000,affinity=[2],ordering_seed=20261105,workload_seed_base=20261105,assumptions=['original source unavailable','baseline timeout -1, capacity N, no event scan are reconstruction assumptions'],languages=['c','zig'])
if (out/'plan.json').exists():assert json.loads((out/'plan.json').read_text())==plan
else:(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
hashfile=out/('source-hashes.json' if a.suite=='primary' else 'controls-source-hashes.json')
snapshot_name='source-snapshot' if a.suite=='primary' else 'controls-source-snapshot'
if hashfile.exists():assert json.loads(hashfile.read_text())==source_hash,'source changed within this suite'
else:
 hashfile.write_text(json.dumps(source_hash,indent=2)+'\n')
 for f in source_hash:
  dest=out/snapshot_name/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/f,dest)
if a.suite=='controls':sp.run(['python3',str(root/'scripts/test.py')],check=True)
binpath=Path('/tmp/kerrisk-reproduction-bin');binpath.mkdir(exist_ok=True)
if a.suite=='controls' and (out/'primary-environment.json').exists():
 primary_env=json.loads((out/'primary-environment.json').read_text());backup=Path('/tmp/kerrisk-primary-bin');backup.mkdir(exist_ok=True)
 for b,h in primary_env['binary_sha256'].items():
  assert hashlib.sha256((binpath/b).read_bytes()).hexdigest()==h,'Primary binary changed before controls'
  shutil.copy2(binpath/b,backup/b)
builds=[['gcc','-O2','-std=c11','-Wall','-Wextra','-Werror',str(root/'c/reconstructed.c'),'-o',str(binpath/'c')],['zig','build-exe','-O','ReleaseFast',str(root/'zig/main.zig'),'-femit-bin='+str(binpath/'zig')]]
for command in builds:sp.run(command,check=True)
def output(*cmd):return sp.check_output(cmd,text=True).strip()
env=dict(date_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),uname=output('uname','-a'),cpu=output('lscpu'),os=Path('/etc/os-release').read_text(),host='M2 MacBook Air (user supplied; host sysctl: Apple M2)',virtualization='OrbStack/Fedora VM',allowed_affinity=sorted(os.sched_getaffinity(0)),measurement_affinity=[2],fd_limit=resource.getrlimit(resource.RLIMIT_NOFILE),gcc=output('gcc','--version'),zig=output('zig','version'),git_sha=output('git','rev-parse','HEAD'),git_status=output('git','status','--short'),build_commands=builds,binary_sha256={b:hashlib.sha256((binpath/b).read_bytes()).hexdigest() for b in ['c','zig']},source_sha256=source_hash,source_snapshot=snapshot_name,index_bytes_c=8,index_bytes_zig=8,verification_barrier=True,plan_sha256=hashlib.sha256((out/'plan.json').read_bytes()).hexdigest(),start_load=Path('/proc/loadavg').read_text(),start_stat=Path('/proc/stat').read_text(),affinity_caveat='VM affinity does not reserve a physical host CPU')
(out/(a.suite+'-environment.json')).write_text(json.dumps(env,indent=2)+'\n')
conditions=plan[a.suite];runs=plan['primary_runs' if a.suite=='primary' else 'control_runs'];rng=random.Random(20261105+(a.suite=='controls'))
# Every condition/language warms before the FIRST measured sample. Source and
# schedule are fixed before observing timings. Identical seed pairs across C/Zig.
warm=[(0,i,b) for i in range(len(conditions)) for b in ['c','zig']];rng.shuffle(warm)
measured=[]
for run,i in rng.sample([(run,i) for run in range(1,runs+1) for i in range(len(conditions))],runs*len(conditions)):
 measured.extend((run,i,b) for b in rng.sample(['c','zig'],2))
(out/(a.suite+'-schedule.json')).write_text(json.dumps(warm+measured)+'\n')
with (out/(a.suite+'.jsonl')).open('w',buffering=1) as f:
 for seq,(run,i,language) in enumerate(warm+measured,1):
  c=conditions[i];loops=plan['warmup_iterations'] if run==0 else c['iterations'];seed=20261105+run
  command=['taskset','-c','2',str(binpath/language),c['backend'],c['kind'],str(c['fds']),str(c['ready_fds']),str(loops),str(c['timeout']),str(c['capacity']),c['placement'],c['layout'],c['work'],str(c['changes']),str(seed)]
  begin=time.time_ns();result=sp.run(command,text=True,capture_output=True,timeout=300)
  if result.returncode:
   (out/(a.suite+'-failure.json')).write_text(json.dumps(dict(command=command,stdout=result.stdout,stderr=result.stderr,returncode=result.returncode),indent=2));raise SystemExit('Child failed; see failure.json. No sample skipped.')
  x=json.loads(result.stdout);x.update(c);x.update(language=language,condition=i,run=run,seed=seed,warmup=run==0,iterations=loops,sequence=seq,command=command,start_unix_ns=begin,end_unix_ns=time.time_ns(),loadavg=Path('/proc/loadavg').read_text())
  assert x['errors']==0 and x['preflight_ready']==c['ready_fds'];f.write(json.dumps(x)+'\n')
  if run:print(f'{a.suite} {seq-len(warm)}/{len(measured)} {language} {c["suite"]} N={c["fds"]} R={c["ready_fds"]} {c["backend"]}: {x["duration_ns"]/1e9:.3f}s',flush=True)
env.update(end_load=Path('/proc/loadavg').read_text(),end_stat=Path('/proc/stat').read_text());(out/(a.suite+'-environment.json')).write_text(json.dumps(env,indent=2)+'\n')
