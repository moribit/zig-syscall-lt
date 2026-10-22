#!/usr/bin/env python3
"""Replace the existing speed page; retain all 23 slides and semantic colors."""
import argparse,csv,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parent;repo=root.parents[2]
p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=root/'results/main');out=p.parse_args().directory
env=json.loads((out/'environment.json').read_text());physical=env.get('virtualization_detected')=='none'
pairs=list(csv.DictReader((out/'paired.csv').open()));baseline=[x for x in pairs if x['backend']=='uring' and x['label']=='baseline'];wins=sum(float(x['speed_over_epoll_median'])>1 for x in baseline)
result=f'実機では6/32条件でRECVがepollを上回った（ペア速度比の中央値）。' if physical else 'バッチ投入でenterは減った。今回のRECVは、全32条件でepollを上回らなかった。'
result=result.replace('6/32',f'{wins}/{len(baseline)}')
foot='実機 i7-3615QM / Linux 6.18.9 / Zig 0.17.0。1 KiB・32バースト×10回。初期化/終了は別計時。' if physical else '1 KiB / 32バースト×10回。送信〜内容検証・再投入。初期化/終了は別計時。OrbStack / Zig 0.17.0。'
rows=list(csv.DictReader((out/'summary.csv').open()))
def row(backend,label='baseline'):return next(x for x in rows if x['fds']=='4096' and x['payload']=='1024' and x['ready_percent_requested']=='100' and x['backend']==backend and x['label']==label)
values={b:float(row(b)['msg_s_median'])/1e6 for b in ['poll','epoll','uring']}
text=f"""<div class="eyebrow">12 / WHY IT CAN HELP</div>

# 同じ受信処理を、3方式で実測

<img class="audit-measured" src="/benchmarks/uring-recv-e2e.svg" alt="送信・内容検証・再投入を含む32バーストの処理速度。poll、epoll、io_uring RECVを同じ系列で各10回測定。" />

<div class="benchmark-numbers"><span>全Ready / 4,096 fd：<b class="bench-poll">poll {values['poll']:.3f}</b> / <b class="bench-epoll">epoll {values['epoll']:.3f}</b> / <b class="ref-result">RECV {values['uring']:.3f}</b> 百万件/秒</span><small>{result}</small></div>

<div class="takeaway">syscallの削減と、処理全体の速さを分けて確かめる</div>
<p class="fine">{foot}</p>

<!--
目安50秒。仕組みを説明したので、同じ受信処理を実際に書いて比べた。新規の同一系列でpoll+recv、epoll LT+recv、io_uring RECVを測定し、過去のrawと混ぜていない。Zig0.17.0 ReleaseFast、M2 MacBook Air / OrbStack Fedora、Linux7.0.14 aarch64、CPU2。affinityは物理CPU専有を保証しない。
N64/256/1024/4096、Ready1/10/50/100%、payload64/1024B。Ready個数はceil(N*pct/100)。全32基本条件のRECV/epollペア速度比中央値は1を超えず、初期化・終了込みでも同様。10sample、名目95%percentile bootstrap10000回、外れ値除外なし。これは今回の有限・送信先行の合成負荷とVMに限り、WebサーバやLinux全般の勝敗ではない。
単一スレッドでProducer全送信後にConsumerが全受信・内容検証し、次回rearm/flush完了までがE2E。既存workloadのProducerとreceiveを再利用した。Consumerは件数とpayloadを共通プロトコルとして知るが、将来のReady fdのidentityを受け取らない。RECVは全fdに初期要求を用意し、inactive要求をバースト間で保持する。32バーストの再投入境界は31回。最後は未完了をcancelし、受付CQEだけでなく対象終端CQEまで確認してからbufferを解放する。
全Ready/4096fd/1024B、最大バッチの中央値：poll {values['poll']:.3f}、epoll {values['epoll']:.3f}、RECV {values['uring']:.3f} Mmsg/s。別のバッチ1→最大の対照では、E2Eのenterが126976→31回、0.590→0.680 Mmsg/s、プロセスCPU222.447→192.825ms。初期enterは別で4096→1回。バッチは効果があったが、最大batchが全variantで最速ではなく、epollにも届かなかった。CQ回収1/64、SQ64/Nも別対照とし、SQ64はbatch64を揃えた追加系列で監査した。
仕組みとして、複数要求のバッチ投入、ユーザー/カーネルの共有リング、登録bufferによる繰り返し準備削減には余地がある。共有リングは全データのzero-copyを意味せず、syscallとcontext switchも同義ではない。今回registered buffers/files、SQPOLL、multishotは使っていない。SQPOLLは専用threadのCPUも評価する必要がある。PostgreSQLの最大3倍をこの実験やio_uring単独の効果へ結び付けない。
POLL_ADD oneshot+recvも測定したが、再武装を含む通知→排出サイクルで、既存Aのデータ非消費LT再通知とは異なるため専用図へ分離した。図はRECVの実受信Bを主指標としている。実測はstd.os.linuxのABIであり、std.Io.Eventedの性能ではない。Eventedビルド問題とは独立して実行できている。
初期化、mmap、専用buffer確保、初期要求、終了cancel/破棄は別記し、backend初期化+E2E+終了込みもレポートへ掲載した。CPUはgetrusageのプロセス時間で、kernel worker/ホスト全体を含む保証はない。Producerのsend中にRECV処理が進む費用もE2Eに含む。区間時計の費用を含み、中央値を単純加算しない。原因をkernel内cache等だけへ帰属していない。
https://man7.org/linux/man-pages/man2/io_uring_enter.2.html
https://man7.org/linux/man-pages/man2/io_uring_register.2.html
benchmarks/poll-epoll/io-uring/ANALYSIS.md / BENCHMARK_DESIGN.md / results/main
-->
"""
if physical:
 start=text.index('<!--');end=text.index('-->',start)
 note=f"""<!--
目安50秒。VMで比較した後、同じZig実装・条件・seed・順序でIntel実機へ追試した。ここに示すのは実機だけの送信・内容検証・再投入込みB。過去のVM結果とは混ぜていない。
Intel Core i7-3615QM、物理Mac mini、EndeavourOS、Linux6.18.9-arch1-2 x86_64、Zig0.17.0 ReleaseFast/native、libc/liburingなし。systemd-detect-virt=none。CPU2に固定するがSMT sibling6を専有しない。governor=schedutilで周波数・温度・他負荷は固定していない。fd上限はセッション内だけ16384。
N64/256/1024/4096、要求Ready1/10/50/100%、64/1024B、32バースト、全warmup後に各10sample。同じrun/seedを対応付け、方式順をランダム化。全32基本条件のうち{wins}条件でRECV/epollペア速度比中央値が1を超えたが、うち3条件の区間は1を跨ぎ小差。探索後の確認的な有意差とは呼ばない。backend初期化・終了込みも6条件で中央値1超えだが、同じ条件とは限らない。
全Ready/4096fd/1024B、速度中央値：poll {values['poll']:.3f}、epoll {values['epoll']:.3f}、RECV {values['uring']:.3f} Mmsg/s。RECV/epollペア比中央値1.040、記述的95%percentile bootstrap区間1.024–1.051。初期化・終了込み比は1.045、1.028–1.054。速度中央値同士の商とペア比中央値は異なる。4096fd/Ready約1%ではsteady比中央値1.021だが区間は1を跨ぎ、初期化込みでは0.945だった。処理量・接続寿命・計測範囲で変わる。
同じProducerを使い、単一スレッドで全送信後に全受信・内容検証・次回rearm/flushまでを測る。RECV側は将来のReady identityを知らず全fdへ初期要求を用意し、inactive要求はバースト間で維持する。32バーストの再投入境界は31回。最後はcancel受付と対象終端CQEまで排出し、bufferを解放する。
batch1→最大の全Ready/4096fd/1KiB対照では、E2E enter126976→31、0.209→0.243 Mmsg/s、プロセスCPU626.223→536.008ms。最大batchが常に最速ではない。CQ回収上限の変更は端数flush頻度も変え、コピー単体の費用ではない。batch64を揃えたSQ64/N対照80件も実機で追試し、区間はいずれも1を跨いだ。
POLL_ADD oneshot+recvは再武装込みの通知→排出サイクルであり、非消費LT再通知とは契約が違うため専用図へ分離。主図はRECVのB。straceは別の12実行で件数を検証し、tracer下の時間を性能値に混ぜない。x86_64のpoll/epoll_wait経路を実測した。std.os.linux.IoUringのABI実装であり、std.Io.Eventedの性能ではない。
仕組みとして共有リング、要求のまとめ投入、registered buffer等で準備を償却する余地はある。ただし今回SQPOLL/multishot/registered resourcesは使わない。共有リングは全データzero-copyを意味せず、syscallとcontext switchも同義ではない。CPUはgetrusageのプロセス時間で、kernel worker/ホスト全体のCPUとは違う。時計オーバーヘッドを含む。区間中央値を単純加算しない。
VMでは基本32条件でepollが速い中央値だったが、実機では上回る条件もあった。同時にCPU、aarch64/x86_64、kernel版、native target、SMT、周波数制御が違うため「仮想化のオーバーヘッド」だけを測ったとは言えない。別日の独立系列や継続到着/TCP/TLS/Web処理は未検証。Kerrisk/Adaptiveページは過去のVM系列のままで、この追試で実機に移したと説明しない。
benchmarks/poll-epoll/io-uring/PHYSICAL_ANALYSIS.md / results/physical-20261022
https://man7.org/linux/man-pages/man2/io_uring_enter.2.html
https://man7.org/linux/man-pages/man2/io_uring_register.2.html
-->"""
 text=text[:start]+note+text[end+3:]
p=repo/'slides.md';deck=p.read_text();start=deck.index('<div class="eyebrow">12 / WHY IT CAN HELP</div>');end=deck.index('\n---\n',start);deck=deck[:start]+text+deck[end:]
needle='- [epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html) / [io_uring(7)](https://man7.org/linux/man-pages/man7/io_uring.7.html)'
if '[enter(2)]' not in deck:deck=deck.replace(needle,needle+' / [enter(2)](https://man7.org/linux/man-pages/man2/io_uring_enter.2.html)')
note='今回のRECV/POLL_ADD実測はstd.os.linux.IoUringを使い、std.Io.Eventedを使っていない。低レベルではRECVの最小実行・三方式比較・未完了要求の終了まで確認済み。Eventedのビルド失敗という結論は変更しない。'
start=deck.index('<div class="eyebrow">16 / OBSERVED RESULT</div>');end=deck.index('\n---\n',start);page=deck[start:end]
if note not in page:page=page.replace('-->',note+'\n-->');deck=deck[:start]+page+deck[end:]
p.write_text(deck);shutil.copy2(out/'e2e-1024.svg',repo/'public/benchmarks/uring-recv-e2e.svg')
print('Updated slide 13 and notes; no slides added.')
