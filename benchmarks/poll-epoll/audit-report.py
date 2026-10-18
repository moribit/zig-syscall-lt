#!/usr/bin/env python3
"""Regenerate published report tables from audit-v2 raw-derived statistics."""
from pathlib import Path
import json,csv,re
root=Path(__file__).resolve().parent;out=root/'results/audit-v2'
d=json.loads((out/'analysis.json').read_text());probe=list(csv.DictReader((out/'probe-summary.csv').open()));controls=list(csv.DictReader((out/'controls-summary.csv').open()));ph=list(csv.DictReader((out/'phase-summary.csv').open()));old=list(csv.DictReader((out/'historical-phase-summary.csv').open()))
s='主解析は **1,430 sample**（warmup 67を別保存）。このほか、warmup順序に不備のあった初回動的90 sample＋warmup 9も保存・別掲。診断は別run。過去2,981行の整合性も確認した。\n\n### A：Readinessの区間別プローブ\n\n単位µs/回、各20回の中央値。64 Bを事前投入。APIはsyscall単体、取得はAPI+索引変換、走査・集合検証は準備済み結果を別ループで処理する。\n\n| fd / Ready | 方式 | API | 取得 | 走査 | 集合検証 | 取得 ns/event |\n|---|---|---:|---:|---:|---:|---:|\n'
for n,r in [(1024,10),(1024,1024),(4096,41),(4096,4096)]:
 for b in ['poll','epoll']:
  g={x['mode']:x for x in probe if int(x['fds'])==n and int(x['ready_fds'])==r and x['backend']==b}
  s+=f'| {n} / {r} | {b} | '+ ' | '.join(f"{float(g[m]['ns_median'])/1000:.3f}" for m in ['syscall','combined','scan','validate'])+f" | {float(g['combined']['ns_per_event']):.1f} |\n"
s+='\n時計ペアだけのループは約24ns/回。約225nsの最短epoll取得に対して無視できないため、数ns差を解釈したり機械的に引き算したりしない。APIの費用はユーザー走査より大きく、全Readyでもepoll取得が速い。\n\n### B：送受信の対照（4,096 fd / 1 KiB / 64バースト）\n\nCPU 2固定、各30回。時間はµs/バーストの中央値。各区間中央値は別々に計算するので和が総時間中央値に一致するとは限らない。\n\n| Ready | 送信順 | 方式 | Producer | Consumer | 取得（Consumer内） | End-to-End | CPU user / system |\n|---:|---|---|---:|---:|---:|---:|---:|\n'
for x in controls:
 s+=f"| {x['ready_fds']} | {x['order']} | {x['backend']} | "+' | '.join(f"{float(x[k]):.2f}" for k in ['producer_us_per_burst','consumer_us_per_burst','acquisition_us_per_burst','e2e_us_per_burst'])+f" | {float(x['user_us_per_burst']):.1f} / {float(x['system_us_per_burst']):.1f} |\n"
s+='\n| Ready / 送信順 / CPU | poll/epoll費用比中央値 | 95%区間 | pollが速いペア | Holm補正符号検定p |\n|---|---:|---|---:|---:|\n'
for x in d['controls_comparisons']:
 s+=f"| {x['ready_fds']} / {x['order']} / {('CPU 2・第2seed' if x.get('series') else 'CPU 2') if x['pinned'] else '未固定・別seed'} | {x['ratio']:.4f} | {x['ci95'][0]:.4f}–{x['ci95'][1]:.4f} | {x['numerator_wins']}/{x['n']} | {x['holm_p']:.5g} |\n"
s+='\nCPU固定・ランダム送信ではpollの費用がペア中央値で約4.33%小さい。一方、昇順送信は明確な差がなく、affinity未固定の別seed追試も区間が1をまたいだ。解析・描画終了後の別seed再測定ではランダム順の中央値は同方向（約2.67%短縮、pointwise bootstrap区間は1未満）だったが、Holm補正符号検定p=0.395で、優位性が強く再現したとは断定しない。昇順は区間が1をまたいだ（表の第2seed行）。負の結果も含め、普遍的なpoll優位とはしない。`poll-watched`ではProducer時間が増え、監視登録の存在が送信側にも影響し得ることを確認した。\n\n### C：Adaptiveの区間別結果\n\n過去200ms系列のPhase別中央値（各10回）。CPUはuser+systemのµs。過去rawにはPhase別切替情報がないため、切替時刻を後から捏造していない。\n\n| 方式 | Phase | M msg/s | CPU µs | 完了バースト |\n|---|---|---:|---:|---:|\n'
for x in old:s+=f"| {x['backend']} | {x['phase']} | {float(x['messages_s'])/1e6:.4f} | {float(x['cpu_us']):.1f} | {float(x['batches']):.1f} |\n"
s+='\n追加の固定モデル評価。A/C各200ms、Bのみ変更、CPU 2固定。各方式10回、通常測定は診断無効。\n\n| Bの長さ | Adaptive/epoll改善率 | 95%区間 | 切替回数中央値 | 合計切替ms | Holm補正p |\n|---|---:|---|---:|---:|---:|\n'
for x in d['dynamic_comparisons']:
 s+=f"| {x['high_ms']} ms | {(x['ratio']-1)*100:+.2f}% | {(x['ci95'][0]-1)*100:+.2f}–{(x['ci95'][1]-1)*100:+.2f}% | {x['switches']:.0f} | {x['switch_ns']/1e6:.3f} | {x['holm_p']:.5g} |\n"
s+='\n'+ ' / '.join(f"{x['high_ms']}ms："+('改善確認' if x['ci95'][0]>1 else '悪化側' if x['ci95'][1]<1 else '改善未確認') for x in d['dynamic_comparisons'])+'。全3条件を事前指定し、評価後のモデル調整はない。このVMと条件での結果であり、本番への保証ではない。\n\n| Bの長さ | Phase | 方式 | M msg/s | CPU µs | バースト | 切替回数 / ms |\n|---|---|---|---:|---:|---:|---:|\n'
for x in ph:s+=f"| {x['high_ms']} ms | {x['phase']} | {x['backend']} | {float(x['messages_s'])/1e6:.4f} | {float(x['cpu_us']):.1f} | {float(x['batches']):.1f} | {float(x['switches']):.0f} / {float(x['switch_ns'])/1e6:.3f} |\n"
s+='\nPhase別中央値は足し合わせられないため、同じrun/seedペアごとに全体速度差を分解した。全体速度R=Σ(Phase時間比w × Phase速度r)より、差はΣ[w_epoll×(r_adaptive−r_epoll) + (w_adaptive−w_epoll)×r_adaptive]。下表は各寄与をepoll全体速度で割った**ペア平均のpercentage point**。和は平均改善率に厳密に一致するが、上のペア中央値とは異なる。\n\n| 系列 / B長 | Aの速度差寄与 | Bの速度差寄与 | Cの速度差寄与 | 時間比の変化 | 平均改善率 |\n|---|---:|---:|---:|---:|---:|\n'
for x in d['phase_contribution_means']:
 s+=f"| {x['series']} / {x['high_ms']} ms | "+' | '.join(f'{v:+.3f} pp' for v in x['rate_effect_pp'])+f" | {x['weight_effect_pp']:+.3f} pp | {x['mean_gain_percent']:+.3f}% |\n"
s+='\nAには切替がないので、その差を切替費用とは解釈できず、VM変動等も含む。Bの利益とCの復帰区間の損失は表を対比する。分解は差の発生区間を示す恒等式であり、kernel関数やcacheに対する因果分解ではない。全ペアを`phase-contributions.csv`に保存した。\n'
s+='\n### D：Oracleの規模と回収時間（記述的推定）\n\n| Bの長さ | 後知恵の理想改善 | 既存選択固定の改善 | 固定選択の高Ready追加メッセージ | 切替時間だけの回収に必要なBの長さ |\n|---|---:|---:|---:|---:|\n'
for x in d['oracle']:s+=f"| {x['high_ms']} ms | {x['retrospective_no_cost_upper_gain_percent']:.2f}% | {x['frozen_gain_percent']:.2f}% | {x['high_phase_extra_messages']:.0f} | {(format(x['approx_break_even_high_ms'], '.1f')+' ms') if x['approx_break_even_high_ms'] is not None else '定義なし（poll優位なし）'} |\n"
s+='\n200msの固定方式系列ではBもepollを選ぶのが速く、後知恵の理想選択はepoll固定（費用なし改善0%）。表の200ms負値は既存の選択epoll→poll→epollを固定した評価で、両者を混同しない。1秒・5秒の理想選択はepoll→poll→epoll。固定方式の別runのPhase速度中央値からの近似で、同一runの数学的上限ではない。ノイズや中央値の非加法性により実測改善がこの推定を超える場合もある。回収時間は切替だけを考えた楽観値であり、Bへ追随する約26–33ms、Cでの復帰遅延・低下、CPU状態差を含まない。短い200msでは固定方式の小差自体が系列で変わり、利益が得られる前提も安定しない。\n\n![Readinessと送信込みは別実験](results/audit-v2/measured.svg)\n\n![全Phase別の完了速度](results/audit-v2/phases.svg)\n'
# Preserve and show the protocol-correction comparison, not just its preferred outcome.
initial=json.loads((out/'initial-dynamic-analysis/analysis.json').read_text())
s+='\n### warmup順序の修正前後\n\n初回runnerはrun=0を本測定と混ぜてシャッフルしていた。これはwarmup先行の要件を満たさないため、全9 warmupを先に完了する別系列を追加した。同じworkload seedと固定モデル、別実行順で、速度の結果を理由に除外したものではない。初回rawは`dynamic.jsonl`、その時点の分析は`initial-dynamic-analysis/`へ保持。最終の主解析は`dynamic-warmed.jsonl`。測定時刻と実行順も変わるため、修正前後の差をwarmupそのものの因果効果とは解釈しない。\n\n| Bの長さ | 初回改善率・95%区間 | warmup先行の改善率・95%区間 |\n|---|---|---|\n'
for before,after in zip(initial['dynamic_comparisons'],d['dynamic_comparisons']):
 def describe(x):return f"{(x['ratio']-1)*100:+.2f}% [{(x['ci95'][0]-1)*100:+.2f}, {(x['ci95'][1]-1)*100:+.2f}]"
 s+=f"| {after['high_ms']} ms | {describe(before)} | {describe(after)} |\n"
rows=[json.loads(x) for x in (out/'diagnostics.jsonl').read_text().splitlines()]
t='| Bの長さ | Phase / バースト | 実験開始からの完了時刻ms | 実切替 | EMA fd | 推定poll / epoll ms | 切替見積 / 実測ms |\n|---|---|---:|---|---:|---:|---:|\n'
for x in d['diagnostic_switches']:
 t+=f"| {x['high_ms']} ms | {'ABC'[x['phase']]} / {x['burst']} | {x['elapsed_ns']/1e6:.3f} | {'epoll→poll' if x['before_epoll'] else 'poll→epoll'} | {x['ema']:.1f} | {x['poll_ns']/1e6:.3f} / {x['epoll_ns']/1e6:.3f} | {x['estimate_ns']/1e6:.3f} / {x['actual_ns']/1e6:.3f} |\n"
t+='\nB開始後4〜5バーストでpollへ、C開始後3バーストでepollへ復帰した。closeは約0.45ms、再登録は約1.7msで非対称だった。Phase別集計でもBで利益、Cで復帰に伴う損失が見える。診断による追加記録の費用を通常性能の結果には混ぜていないが、診断の時刻にはその記録費用が含まれる。\n\n![実際の切替。理想的なPhase境界での切替ではない](results/audit-v2/timeline.svg)\n\nperfはcycles/instructionsが`<not supported>`。user限定のtask-clockとソフトウェア指標は出力されたが、単発のcontext-switches=0等から因果を断定しない。キャッシュの説明を実測済みにできるhardware counterは取得できなかった。strace別runでは双方sendto/recvfrom各262,144回、待機各64回、epollは初期登録4,096回を確認。tracer下の時間は性能集計から除外した。[観察ログ](results/audit-v2/observations.json)。\n'
p=root/'ANALYSIS.md';text=p.read_text()
for name,body in [('AUDIT_RESULTS',s),('DIAGNOSTIC_RESULTS',t)]:
 text=re.sub(r'<!-- '+name+r' -->.*?<!-- /'+name+r' -->',lambda _: '<!-- '+name+' -->\n'+body+'\n<!-- /'+name+' -->',text,flags=re.S)
p.write_text(text)
(out/'results.md').write_text(s+'\n'+t)
