#!/usr/bin/env python3
"""Update the existing comparison page and notes from measured data; no new pages."""
import csv,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1];repo=root.parents[2];out=root/'results/main'
d=json.loads((out/'analysis.json').read_text());srows=list(csv.DictReader((out/'summary.csv').open()))
assert d['validation']['primary']['measured']==216
pairs=d['backend_pairs'];reverse=any(x['poll_over_epoll_median']<1 for x in pairs)
result='一部条件でpoll優位も観測。' if reverse else '今回の条件ではepoll優位。'
values=[]
for language in ['c','zig']:
 for backend in ['poll','epoll']:
  x=next(x for x in srows if x['suite']=='A' and x['language']==language and int(x['fds'])==1000 and int(x['ready_fds'])==1000 and x['backend']==backend)
  values.append(f"{language}/{backend} {float(x['million_units_seconds']):.3f}s [{float(x['ci95_low'])/1000:.3f},{float(x['ci95_high'])/1000:.3f}]")
body=f'''<div class="eyebrow">09 / MEASURED COST</div>

# Kerrisk氏の測定を、CとZigで追試

<img class="audit-measured" src="/benchmarks/kerrisk-density.svg" alt="過去の表と現在のC/Zig再構成を別パネルで比較。1,000 fd、100万回。過去の高Ready率ではpollが優位。現在の結果は保存済み実測から生成。" />

<div class="benchmark-numbers"><span>過去は高Ready率で<b class="bench-poll">poll優位</b>。{result}</span><small>元Cは未入手。公開仕様から再構成し、過去と現在を別の実験として比較した。</small></div>

<div class="takeaway">I/O APIの性能は、何をどこまで測るかによっても変わる</div>
<p class="fine">今回：1,000 pipe fd・低位連続・100万回×各3回。timeout=-1、容量N、走査なしは仮定。OrbStack / Zig 0.17.0。</p>

<!--
目安55秒。Kerrisk氏の講義で「高Ready率ではpollが逆転した」表を見つけ、現在のLinuxで同じような現象が出るかを調べた。過去の参考値・現在のC再構成・現在のZig再構成を別パネルに分け、異なる環境/未知の条件を同一系列の線で結ばない。selectも本実験には含むが、LTの図は主題のpoll/epollだけに絞る。
元のaltio/altio_speed.cは公式TLPIのdist/book版20260523や公開候補で入手できなかった。講義の仕様に基づく独立したCとZigの再構成であり、オリジナルの無改変実行ではない。pipeや低位連続fdを使う考え方は確認したが、表が実際に使ったfd種、timeout、maxevents、イベント走査等の詳細は未確認。主比較のpipe、timeout=-1、容量N、走査なしには仮定を含む。図の未知条件の注意を省略しない。
図はReady検出のみ、データは読まず、1 byteを入れたReady状態を繰り返し取得する。新規I/Oメッセージを100万回受信した実験ではない。CはGCC -O2、Zig0.17.0 ReleaseFast、Linux7.0.14-orbstack aarch64、M2 MacBook Air上のFedora VM、CPU2固定。VM affinityは物理CPU専有を保証しない。初期登録・Ready生成・事前集合検証は計時外。
全Ready/1000fd/100万回の秒数、各3sampleの中央値と名目95%bootstrap区間：{'; '.join(values)}。原典はpoll12.7s/epoll47.3s。元の測定日時・CPU・kernel・sample数は不明。n=3の区間は粗く、確認的有意性の証拠にはしない。
Ready10/20/50/100%とN100/1000、N1/10/100/1000の中間1Ready、K0/1/5/10のDEL+ADDを全条件保存。C/ZigのReady集合・fd範囲・件数は一致し、条件を揃えた比較だがラッパーや最適化が完全に同じではない。言語性能の優劣と結論しない。
別対照ではpipe→socket→通常fd配置→timeout0→索引走査と一要因ずつ変えた。maxevents1/16/64/Nの単発費用と、全1000Ready fdを集める費用も分けた。返すイベントが少ない1回を、全Readyを取得する1回と同じ仕事とはしない。追加の登録/投入順対照（各5sample）では、ADD後にランダム投入した場合の返却順hashを独立に確認した。全Ready/socket/連続fdのZigは投入後ADD14.769µs、投入前ADD15.619µs/回。順序による費用差はあるが、kernel内のcache miss等の直接証拠ではなく、過去の逆転の完全な原因は未特定。原典と現在の差の完全な原因は未特定。元ソース・旧環境が不明なので、CPUやkernelの改善だけに帰属させない。
既存のN1024 socketpair Aは取得API+索引変換、送信込みBはProducer開始から内容照合までを含む別実験。既存の4096fd/全Ready/1KiBの小さなpoll優位とも、範囲・fd数・データ量が異なる。既存rawとAdaptive結果は変更していない。
https://man7.org/training/download/lusp_epoll_slides-mkerrisk-man7.org.pdf （January2026 rev d49d0b54be95、物理17/18ページ）
https://man7.org/tlpi/code/index.html
benchmarks/poll-epoll/kerrisk-reproduction/REPORT.md / SOURCES.md / results/main
benchmarks/poll-epoll/ANALYSIS.md
-->
'''
p=repo/'slides.md';text=p.read_text();start=text.index('<div class="eyebrow">09 / MEASURED COST</div>');end=text.index('\n---\n',start);text=text[:start]+body+text[end:]
# Add the reference once, keeping the existing deck structure.
needle='- [Linux v7.0.14: eventpoll.c](https://github.com/gregkh/linux/blob/v7.0.14/fs/eventpoll.c)'
reference='- [Kerrisk: epoll講義](https://man7.org/training/download/lusp_epoll_slides-mkerrisk-man7.org.pdf)'
if reference not in text:text=text.replace(needle,needle+'\n'+reference)
# The Adaptive slide retains its prior, independently measured numbers.
start=text.index('<div class="eyebrow">10 / ADAPTIVE?</div>');end=text.index('\n---\n',start);page=text[start:end]
if 'Kerrisk再構成の登録費用' not in page:
 ctl=[x for x in srows if x['suite']=='C' and x['language']=='zig'];v=' / '.join(f"K{x['changes']} {float(x['ns_per_unit_median']):.1f}ns/反復" for x in sorted(ctl,key=lambda x:int(x['changes'])))
 note=f'\nKerrisk再構成の登録費用：N100/R1/100万回のZigで{v}。各反復K組のDEL+ADDを含み、1件は2syscall。既存Adaptiveの4096fd close/再生成/全ADDとは違う処理なので、単純に1件費用を4096倍して切替費用を説明しない。今回の追試のためにAdaptive実装・保存結果は変更していない。詳細はkerrisk-reproduction/REPORT.md。\n'
 page=page.replace('-->',note+'-->');text=text[:start]+page+text[end:]
p.write_text(text)
dest=repo/'public/benchmarks/kerrisk-density.svg';shutil.copy2(out/'lt-density.svg',dest)
print('Existing slide 10, Adaptive notes and references updated; slide count unchanged.')
