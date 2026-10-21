#!/usr/bin/env python3
import csv,json,re
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/'results/main'
s=list(csv.DictReader((out/'summary.csv').open()));v=json.loads((out/'validation.json').read_text());obs=json.loads((out/'observations.json').read_text())
def f(x,k):return float(x[k])
def table(rows,cols):
 text='| '+' | '.join(k for k,_ in cols)+' |\n| '+' | '.join('---' for _ in cols)+' |\n'
 return text+''.join('| '+' | '.join(str(fn(x)) for _,fn in cols)+' |\n' for x in rows)
cols=[('N',lambda x:x['fds']),('Ready個数',lambda x:x['ready_fds']),('B/msg',lambda x:x['payload']),('方式',lambda x:x['backend']),('msg/s',lambda x:f"{f(x,'msg_s_median'):,.0f}"),('名目95%区間',lambda x:f"{f(x,'msg_s_ci95_low'):,.0f}–{f(x,'msg_s_ci95_high'):,.0f}"),('backend初期化/終了込みmsg/s',lambda x:f"{f(x,'lifecycle_msg_s_median'):,.0f}")]
blocks={}
blocks['BASELINE']=table([x for x in s if x['label']=='baseline' and x['backend']!='uring-poll'],cols)
blocks['NOTIFY']=table([x for x in s if x['label']=='baseline' and x['backend']=='uring-poll'],cols)
rows=[x for x in s if x['fds']=='4096' and x['payload']=='1024' and x['ready_percent_requested'] in ['1','100'] and x['label']=='baseline']
blocks['CPU']=table(rows,[('Ready',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),('Producer ms',lambda x:f"{f(x,'producer_ns_median')/1e6:.3f}"),('Consumer ms',lambda x:f"{f(x,'consumer_ns_median')/1e6:.3f}"),('投入 ms',lambda x:f"{f(x,'submit_ns_median')/1e6:.3f}"),('待機/CQ回収 ms',lambda x:f"{f(x,'wait_ns_median')/1e6:.3f}"),('CPU user ms',lambda x:f"{f(x,'user_us_median')/1000:.3f}"),('CPU system ms',lambda x:f"{f(x,'system_us_median')/1000:.3f}"),('CPU合計 ms',lambda x:f"{f(x,'cpu_us_median')/1000:.3f}")])
blocks['SYSCALL']=table(obs['observations'],[('方式',lambda x:x['backend']),('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('batch上限',lambda x:x['batch']),('enter',lambda x:x['syscall_counts'].get('io_uring_enter',0)),('wait',lambda x:x['syscall_counts'].get('ppoll',0)+x['syscall_counts'].get('epoll_pwait',0)),('recvfrom',lambda x:x['syscall_counts'].get('recvfrom',0)),('sendto',lambda x:x['syscall_counts'].get('sendto',0)),('全syscall',lambda x:sum(x['syscall_counts'].values()))])
keys=[('backend初期化','backend_init_ns_median'),('setup','ring_setup_ns_median'),('mmap','mmap_ns_median'),('buffer確保','buffer_allocation_ns_median'),('初期投入','initial_submit_ns_median'),('cancel/排出','cancel_ns_median'),('破棄','destroy_ns_median')]
blocks['INIT']=table(rows,[('Ready',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),*[(label,lambda x,k=k:f"{f(x,k)/1e6:.3f}") for label,k in keys]])
contexts={(x['fds'],x['ready_percent_requested'],x['payload']) for x in s if x['label']!='baseline'};crows=[x for x in s if x['backend']=='uring' and (x['fds'],x['ready_percent_requested'],x['payload']) in contexts]
blocks['BATCH']=table(crows,[('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('variant',lambda x:x['label']),('SQ',lambda x:x['capacity']),('CQ回収上限',lambda x:x['cq_batch']),('batch上限',lambda x:x['batch']),('msg/s',lambda x:f"{f(x,'msg_s_median'):,.0f}"),('E2E enter',lambda x:f"{f(x,'enter_calls_median'):.0f}"),('CPU合計 ms',lambda x:f"{f(x,'cpu_us_median')/1000:.3f}")])
blocks['VALIDATION']=f"検証済みraw {v['rows']}行（本測定{v['measured']}、warmup{v['rows']-v['measured']}）、{v['conditions']}条件。開始時から存在した{v['existing_files_unchanged']}ファイルのSHAが一致し、既存poll/epoll/Adaptive/Kerrisk結果を変更していない。"
capacity=out/'capacity-summary.csv'
if capacity.exists():
 crows=list(csv.DictReader(capacity.open()));pr=list(csv.DictReader((out/'capacity-paired.csv').open()))
 blocks['CAPACITY']=table(crows,[('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('SQ',lambda x:x['capacity']),('batch上限',lambda x:x['batch']),('msg/s',lambda x:f"{f(x,'msg_s_median'):,.0f}"),('enter',lambda x:x['enter_calls_median'])])+'\n'+table(pr,[('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('SQ64/N速度比中央値',lambda x:f"{f(x,'sq64_over_sqN_speed'):.4f}"),('名目95%区間',lambda x:f"{f(x,'ci95_low'):.4f}–{f(x,'ci95_high'):.4f}")])
p=root/'ANALYSIS.md';text=p.read_text()
for marker,body in blocks.items():
 start='<!-- '+marker+' -->';end='<!-- /'+marker+' -->';replacement=start+'\n'+body+'\n'+end
 if end in text:text=re.sub(re.escape(start)+'.*?'+re.escape(end),lambda _:replacement,text,flags=re.S)
 else:text=text.replace(start,replacement)
p.write_text(text)
print('Regenerated complete report from all baseline and optimization conditions.')
