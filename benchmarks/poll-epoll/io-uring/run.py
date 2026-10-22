#!/usr/bin/env python3
"""Single-process sequential, paired seeded runs. Refuses to overwrite raw data."""
import argparse,datetime,hashlib,json,os,platform,random,re,resource,subprocess as sp,time
from pathlib import Path
root=Path(__file__).resolve().parent;base=root.parent;repo=base.parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=root/'results/main');p.add_argument('--prepare-only',action='store_true');p.add_argument('--machine-label');p.add_argument('--plot-environment');p.add_argument('--binary-dir',type=Path,default=Path('/tmp'));a=p.parse_args();out=a.output
assert platform.system()=='Linux' and sp.check_output(['zig','version'],text=True).strip()=='0.17.0'
assert 2 in os.sched_getaffinity(0) and resource.getrlimit(resource.RLIMIT_NOFILE)[0]>=10000
out.mkdir(parents=True,exist_ok=True)
assert not (out/'raw.jsonl').exists(), 'Refusing to overwrite existing samples'
def cmd(*args):return sp.check_output(args,text=True).strip()
a.binary_dir.mkdir(parents=True,exist_ok=True)
binary=a.binary_dir/'zig-uring-bench';probe=a.binary_dir/'zig-uring-probe'
for source,target in [('io-uring-probe.zig',probe),('io-uring-main.zig',binary)]:sp.run(['zig','build-exe',str(base/source),'-O','ReleaseFast','-femit-bin='+str(target)],check=True)
pre=sp.run([str(probe)],text=True,capture_output=True)
phase0=dict(command=[str(probe)],returncode=pre.returncode,stdout=pre.stdout,stderr=pre.stderr,uname=cmd('uname','-a'),zig=cmd('zig','version'),libc_linked=False,io_uring_disabled=Path('/proc/sys/kernel/io_uring_disabled').read_text().strip(),process_status=Path('/proc/self/status').read_text(),date_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
if pre.returncode:phase0['status']='UNSUPPORTED';(out/'phase0.json').write_text(json.dumps(phase0,indent=2)+'\n');raise SystemExit('UNSUPPORTED: see phase0.json, no benchmark numbers generated')
phase0.update(json.loads(pre.stdout));assert all(phase0[k] for k in ['recv_supported','poll_add_supported','cancel_supported']);(out/'phase0.json').write_text(json.dumps(phase0,indent=2)+'\n')
checks=[]
def check_command(command):
 c=sp.run(command,text=True,capture_output=True,timeout=180);checks.append(dict(command=command,returncode=c.returncode,stdout=c.stdout,stderr=c.stderr));assert c.returncode==0, c.stderr
check_command(['zig','test',str(base/'io-uring-tests.zig')]);check_command(['zig','test',str(base/'tests.zig')]);check_command(['zig','test',str(base/'io-uring-fault-tests.zig')])
# End-to-end parity with no/one/all Ready, changing Ready sets, repeated receives,
# small SQ versus many outstanding requests, and each batch/CQ size.
scenarios=0
for n,ready in [(1,0),(1,1),(8,0),(8,1),(8,8),(64,1),(64,64)]:
 for payload in [64,1024]:
  records=[]
  for backend in ['poll','epoll','uring','uring-poll']:
   command=[str(binary),backend,str(n),str(ready),str(payload),'5','29','1','8','1'];x=json.loads(sp.check_output(command,text=True,timeout=30));records.append(x)
  for key in ['messages','bytes_sent','bytes_received','errors']:assert len({x[key] for x in records})==1
  assert records[0]['messages']==ready*5;scenarios+=1
checks.append(dict(end_to_end_scenarios=scenarios,backends_per_scenario=4,status='PASS'))
(out/'tests.json').write_text(json.dumps(checks,indent=2)+'\n')
conditions=[]
def add(n,pct,payload,backend,batch=None,capacity=None,cq_batch=None,label='baseline'):
 c=dict(fds=n,ready_percent_requested=pct,ready_fds=(n*pct+99)//100,payload=payload,backend=backend,batch=n if batch is None else batch,capacity=n if capacity is None else capacity,cq_batch=n if cq_batch is None else cq_batch,label=label)
 if c not in conditions:conditions.append(c)
for n in [64,256,1024,4096]:
 for pct in [1,10,50,100]:
  for payload in [64,1024]:
   for backend in ['poll','epoll','uring','uring-poll']:add(n,pct,payload,backend)
for n in [1024,4096]:
 for pct in [1,100]:
  for batch in [1,8,32]:add(n,pct,1024,'uring',batch=batch,label='batch-'+str(batch))
  for cq_batch in [1,64]:add(n,pct,1024,'uring',cq_batch=cq_batch,label='cq-'+str(cq_batch))
  add(n,pct,1024,'uring',batch=64,capacity=64,label='sq-64')
plan=dict(conditions=conditions,runs=10,bursts=32,warmup_bursts=4,affinity=[2],seed_base=20261021,ordering_seed=20261021,registered_files=False,multishot=False,sqpoll=False)
(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
sources=[base/'workload.zig',base/'metrics.zig',base/'poll.zig',base/'epoll.zig',base/'io-uring-main.zig',base/'io-uring-probe.zig',base/'io-uring-tests.zig',base/'io-uring-fault-tests.zig',*root.glob('*.zig'),root/'BENCHMARK_DESIGN.md',Path(__file__)]
hashes={str(f.relative_to(base)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}
for f in sources:
 target=out/'source-snapshot'/f.relative_to(base);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
zig_environment=cmd('zig','env')
match=re.search(r'\.std_dir\s*=\s*"([^"]+)"',zig_environment)
assert match, 'Cannot locate the Zig 0.17.0 standard library from zig env'
lib=Path(match.group(1))/'os/linux'
virt_result=sp.run(['systemd-detect-virt'],text=True,capture_output=True)
virtualization_detected=virt_result.stdout.strip() or 'unknown'
def sys_read(path):
 try:return Path(path).read_text().strip()
 except OSError:return None
machine_label=a.machine_label or (platform.node()+' / '+virtualization_detected+' / '+platform.machine())
plot_environment=a.plot_environment or f'{machine_label} / Linux {platform.release().split("-")[0]} / Zig 0.17.0 ReleaseFast / CPU 2'
env=dict(date_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),uname=cmd('uname','-a'),cpu=cmd('lscpu'),os=Path('/etc/os-release').read_text(),zig_env=cmd('zig','env'),virtualization=machine_label,virtualization_detected=virtualization_detected,plot_environment=plot_environment,hostname=platform.node(),architecture=platform.machine(),dmi_product=sys_read('/sys/class/dmi/id/product_name'),cpu2_siblings=sys_read('/sys/devices/system/cpu/cpu2/topology/thread_siblings_list'),cpu2_governor=sys_read('/sys/devices/system/cpu/cpu2/cpufreq/scaling_governor'),affinity=[2],affinity_caveat='Affinity does not reserve the CPU or its SMT sibling; governor and host load are not fixed',binary_path=str(binary),probe_path=str(probe),fd_limit=resource.getrlimit(resource.RLIMIT_NOFILE),git_sha=cmd('git','rev-parse','HEAD'),git_status=cmd('git','status','--short'),optimization='ReleaseFast',libc_linked=False,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),source_sha256=hashes,std_source_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [lib/'IoUring.zig',lib.parent/'linux.zig']},binary_headers=cmd('readelf','-l',str(binary)),start_stat=Path('/proc/stat').read_text(),start_load=Path('/proc/loadavg').read_text())
(out/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
if a.prepare_only:
 print('Prepared and tested, no performance data generated');raise SystemExit(0)
rng=random.Random(plan['ordering_seed']);warm=[(0,i) for i in range(len(conditions))];rng.shuffle(warm)
groups={}
for i,c in enumerate(conditions):groups.setdefault((c['fds'],c['ready_percent_requested'],c['payload']),[]).append(i)
schedule=warm[:]
for run,key in rng.sample([(run,key) for run in range(1,11) for key in groups],10*len(groups)):
 schedule.extend((run,i) for i in rng.sample(groups[key],len(groups[key])))
(out/'schedule.json').write_text(json.dumps(schedule)+'\n')
with (out/'raw.jsonl').open('w',buffering=1) as f:
 for sequence,(run,i) in enumerate(schedule,1):
  c=conditions[i];bursts=plan['warmup_bursts'] if run==0 else plan['bursts'];seed=plan['seed_base']+run
  command=['taskset','-c','2',str(binary),c['backend'],str(c['fds']),str(c['ready_fds']),str(c['payload']),str(bursts),str(seed),str(c['batch']),str(c['capacity']),str(c['cq_batch'])]
  start=time.time_ns();child=sp.run(command,text=True,capture_output=True,timeout=120)
  if child.returncode:
   (out/'failure.json').write_text(json.dumps(dict(command=command,returncode=child.returncode,stdout=child.stdout,stderr=child.stderr),indent=2));raise SystemExit('Benchmark failed, no sample silently skipped')
  x=json.loads(child.stdout);assert x['status']=='OK' and x['errors']==0 and x['messages']==c['ready_fds']*bursts and x['bytes_sent']==x['bytes_received']==x['messages']*c['payload']
  x.update(c,condition=i,run=run,warmup=run==0,bursts=bursts,seed=seed,sequence=sequence,command=command,start_unix_ns=start,end_unix_ns=time.time_ns(),loadavg=Path('/proc/loadavg').read_text());f.write(json.dumps(x)+'\n')
  if run and (sequence-len(warm))%40==0:print(f'Measured {sequence-len(warm)}/{len(schedule)-len(warm)}',flush=True)
assert all(hashlib.sha256((base/f).read_bytes()).hexdigest()==h for f,h in hashes.items()), 'Sources changed during measurement'
env.update(end_stat=Path('/proc/stat').read_text(),end_load=Path('/proc/loadavg').read_text(),raw_sha256=hashlib.sha256((out/'raw.jsonl').read_bytes()).hexdigest());(out/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
print('All paired measurements complete',flush=True)
