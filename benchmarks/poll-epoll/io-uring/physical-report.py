#!/usr/bin/env python3
"""Publish the physical series separately; do not overwrite historical VM reports."""
import csv,hashlib,json,re
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/'results/physical-20261022';vm=root/'results/main'
s=list(csv.DictReader((out/'summary.csv').open()));ps=list(csv.DictReader((out/'paired.csv').open()));v=json.loads((out/'validation.json').read_text());env=json.loads((out/'environment.json').read_text());old=json.loads((vm/'environment.json').read_text())
assert env['virtualization_detected']=='none' and env['architecture']=='x86_64'
assert json.loads((out/'plan.json').read_text())==json.loads((vm/'plan.json').read_text())
assert json.loads((out/'schedule.json').read_text())==json.loads((vm/'schedule.json').read_text())
assert hashlib.sha256((out/'raw.jsonl').read_bytes()).hexdigest()==env['raw_sha256']
manifest=json.loads((out/'preserved-results.json').read_text());assert all(hashlib.sha256((root.parent/f).read_bytes()).hexdigest()==h for f,h in manifest.items())
core=['workload.zig','metrics.zig','poll.zig','epoll.zig','io-uring/main.zig','io-uring/recv.zig','io-uring/ring.zig']
assert all(env['source_sha256'][f]==old['source_sha256'][f] for f in core)
def f(x,k):return float(x[k])
def table(rows,cols):
 return '| '+' | '.join(k for k,_ in cols)+' |\n| '+' | '.join('---' for _ in cols)+' |\n'+''.join('| '+' | '.join(str(fn(x)) for _,fn in cols)+' |\n' for x in rows)
base=[x for x in ps if x['backend']=='uring' and x['label']=='baseline'];wins=[x for x in base if f(x,'speed_over_epoll_median')>1];lifewins=[x for x in base if f(x,'lifecycle_speed_over_epoll_median')>1]
body=f"io_uringの機能確認と14件のZigテスト（rootを含む）、14条件×4方式のE2E検査が成功した。主系列本測定{v['measured']}件・warmup152件、追加SQ容量対照80件・warmup8件。全方式で送受信byte数と内容を検証した。\n\nRECV/epollのペア速度比中央値は**{len(wins)}/32条件で1を上回った**。backend初期化・終了込みの速度比中央値も{len(lifewins)}/32条件で1を上回ったが、該当する条件は同一とは限らない。多条件を調べた後の小差を一般的な優位や確認的有意差と呼ばない。\n\n"
representative=[x for x in s if x['fds']=='4096' and x['payload']=='1024' and x['label']=='baseline' and x['ready_percent_requested'] in ['1','100']]
body+=table(representative,[('Ready個数',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),('msg/s中央値',lambda x:f"{f(x,'msg_s_median'):,.0f}"),('名目95%区間',lambda x:f"{f(x,'msg_s_ci95_low'):,.0f}–{f(x,'msg_s_ci95_high'):,.0f}"),('backend初期化/終了込みmsg/s',lambda x:f"{f(x,'lifecycle_msg_s_median'):,.0f}"),('プロセスCPU ms',lambda x:f"{f(x,'cpu_us_median')/1000:.3f}")])
body+='\n全Ready/4096fd/1024BでのRECV/epollペア速度比中央値は1.040（記述的95%区間1.024–1.051）、初期化・終了込みは1.045（1.028–1.054）。速度中央値同士の商とは異なる指標である。32条件を探索しており、一般的な勝敗へ拡張しない。低Ready4096fdではsteadyの比中央値は1.021だが区間は1を跨ぎ、初期化込みでは0.945となる。寿命や計測境界で結論が変わり得る。\n\n'
body+='![実機64BのE2E](results/physical-20261022/e2e-64.svg)\n\n![実機1024BのE2E](results/physical-20261022/e2e-1024.svg)\n\n### 全32条件のRECV/epoll比（同seed/run）\n\n'
body+=table(base,[('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('B/msg',lambda x:x['payload']),('E2E速度比中央値',lambda x:f"{f(x,'speed_over_epoll_median'):.4f}"),('名目95%区間',lambda x:f"{f(x,'ci95_low'):.4f}–{f(x,'ci95_high'):.4f}"),('初期化/終了込み比中央値',lambda x:f"{f(x,'lifecycle_speed_over_epoll_median'):.4f}")])
body+='\n比>1はRECVが速い方向。全方式の絶対値・最小最大・CPU user/system・区間時間はsummary.csvに全条件保存した。\n\n### 初期化と終了\n\n'
body+=table(representative,[('Ready',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),('backend初期化 ms',lambda x:f"{f(x,'backend_init_ns_median')/1e6:.3f}"),('setup ms',lambda x:f"{f(x,'ring_setup_ns_median')/1e6:.3f}"),('mmap ms',lambda x:f"{f(x,'mmap_ns_median')/1e6:.3f}"),('初期投入 ms',lambda x:f"{f(x,'initial_submit_ns_median')/1e6:.3f}"),('cancel/排出 ms',lambda x:f"{f(x,'cancel_ns_median')/1e6:.3f}"),('破棄 ms',lambda x:f"{f(x,'destroy_ns_median')/1e6:.3f}")])
body+='\n列は各区間の中央値であり、加算して総時間を復元しない。socket生成は共通の別区間。未到着要求は毎バーストキャンセルせず、最後に受付CQEと対象終端CQEを回収してからbufferを解放する。\n\n![初期化/終了込み](results/physical-20261022/lifecycle.svg)\n\n### バッチ・CQ・SQ対照\n\n'
opts=[x for x in s if x['backend']=='uring' and x['payload']=='1024' and x['fds'] in ['1024','4096'] and x['ready_percent_requested'] in ['1','100']]
body+=table(opts,[('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('variant',lambda x:x['label']),('msg/s',lambda x:f"{f(x,'msg_s_median'):,.0f}"),('E2E enter',lambda x:f"{f(x,'enter_calls_median'):.0f}"),('CPU ms',lambda x:f"{f(x,'cpu_us_median')/1000:.3f}")])
body+='\n全Ready/4096fd/1024B、batch1→最大でenter126976→31回、0.209→0.243 Mmsg/s、プロセスCPU626.223→536.008ms。投入削減とCPU/速度改善を確認したが、最大batchが常に最速という意味ではない。CQ回収上限は再投入の端数flush頻度にも影響するため、コピー単体の費用差とは解釈しない。\n\n![バッチ](results/physical-20261022/batch.svg)\n\n'
cp=list(csv.DictReader((out/'capacity-paired.csv').open()));body+=table(cp,[('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('batch64固定 SQ64/N速度比',lambda x:f"{f(x,'sq64_over_sqN_speed'):.4f}"),('名目95%区間',lambda x:f"{f(x,'ci95_low'):.4f}–{f(x,'ci95_high'):.4f}")])
body+='\nSQ容量だけを変えた対照の全区間は1を跨いだ。この系列では明確な優位を確認しない。SQより多数の未完了要求を保持する設計は実機4096fdでも通過した。\n\n### POLL_ADDとsyscall経路\n\n![通知→排出→再武装](results/physical-20261022/poll-add.svg)\n\noneshotの再投入込みであり、既存Aの非消費LT再通知とは比べない。別strace12実行で、x86_64のpoll/epoll_wait/recvfromとio_uring_enterの件数を内部カウンタと照合した。setup/mmap/registerの最小プログラムtraceも保存した。\n'
p=root/'PHYSICAL_ANALYSIS.md';text=p.read_text();start='<!-- RESULTS -->';end='<!-- /RESULTS -->';replacement=start+'\n'+body+'\n'+end
text=re.sub(re.escape(start)+'.*?'+re.escape(end),lambda _:replacement,text,flags=re.S) if end in text else text.replace(start,replacement)
p.write_text(text)
print('Physical report generated; frozen VM results and source hashes verified.')
