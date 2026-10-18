#!/usr/bin/env python3
"""Sync the Adaptive page with the primary (warmup-first) saved analysis."""
import csv,json,re
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/'results/audit-v2';deck=root.parent.parent/'slides.md'
d=json.loads((out/'analysis.json').read_text());assert d['dynamic_source'].startswith('dynamic-warmed')
by={x['high_ms']:x for x in d['dynamic_comparisons']}
short=lambda high:f"{(by[high]['ratio']-1)*100:+.2f}%"
interval=lambda x:f"{(x['ci95'][0]-1)*100:+.2f}〜{(x['ci95'][1]-1)*100:+.2f}%"
confirmed=all(by[h]['ci95'][0]>1 for h in [1000,5000])
status='固定モデルのまま、改善を確認した。' if confirmed else '効果は条件ごとに確認する必要がある。'
left='各200 ms：系列間でも小差が変動'
s=deck.read_text();start=s.index('<div class="eyebrow">10 / ADAPTIVE?</div>');end=s.index('\n---\n',start)
body=s[start:end]
body=re.sub(r'<strong>各200 ms[^<]*</strong>',f'<strong>{left}</strong>',body)
body=re.sub(r'中央値2回・計[0-9.]+ ms',f"中央値{by[200]['switches']:.0f}回・計{by[200]['switch_ns']/1e6:.2f} ms",body)
body=re.sub(r'1秒：<b class="ref-result">[^<]*</b> ／ 5秒：<b class="ref-result">[^<]*</b>',f'1秒：<b class="ref-result">{short(1000)}</b> ／ 5秒：<b class="ref-result">{short(5000)}</b>',body)
body=body.replace('固定モデルのまま、改善を確認した。',status).replace('高Ready区間で利益、復帰区間で損失。',f'今回の中央値{short(200)}。過去は改善未確認。')
ph=list(csv.DictReader((out/'phase-summary.csv').open()))
phase_description=[]
for b in ['poll','epoll','adaptive']:
 g=[x for x in ph if x['backend']==b and int(x['high_ms'])==200]
 phase_description.append(b+' '+ ' / '.join(x['phase']+' '+f"{float(x['messages_s'])/1e6:.3f}" for x in g))
comparison=' / '.join(f"{h}ms：{short(h)} [{interval(by[h])}], Holm p={by[h]['holm_p']:.5g}" for h in [200,1000,5000])
notes=f'''<!--
目安35秒。200msの既存結果を起点に、長ければ利益を回収できるかを調べた。モデル・EMA・係数は既存のまま固定、追加データを見て調整していない。B200/1000/5000msは事前指定、A/C各200ms固定、各10回。主解析は全9warmupを先に終えてから本測定したdynamic-warmed.jsonl。初回runnerにはwarmupの並べ替え不備があり、初回dynamic.jsonlとその分析も別に保存して修正前後を比較した。
Adaptive/固定epollの完了速度改善率のペア中央値、95%percentile bootstrap区間（10000回）、3条件の正確符号検定Holm補正：{comparison}。少数の同VM追試であり他環境の保証ではない。初期setupは別記、実行中の切替費用は含む。
200msのPhase別速度中央値（M msg/s）：{'; '.join(phase_description)}。Phase中央値は足し算できないため、同一run/seedごとの速度差を時間比とPhase速度の寄与へ分解した。全体速度差へ足し上がるのは各ペアの寄与の平均であり、中央値ではない。phase-contributions.csvには過去と追加の全ペアを保存。差の発生区間を示すものでkernel関数への因果分解ではない。全27条件の速度・CPU時間・完了バースト・切替はphase-summary.csv。
図は性能sampleと別の診断run（seed20261101、B200ms）の実測。epoll→pollはB第5バースト、実験開始232.883msで完了（実費0.463ms）。poll→epollはC第3バースト、409.258msで完了（実費1.702ms）。Phase境界と切替完了は一致しない。理想的なPhase境界切替の図を実挙動として描いていない。64バーストごとと全切替を事前確保メモリへ記録し終了後出力。診断の性能値は通常測定へ混ぜない。
切替合計中央値ms：200ms {by[200]['switch_ns']/1e6:.3f} / 1秒 {by[1000]['switch_ns']/1e6:.3f} / 5秒 {by[5000]['switch_ns']/1e6:.3f}。closeと再登録は非対称だがControllerは直近費用を方向別に区別せず使う。初期見積はsetup。EMAは完了fd数を入力とし、generatorのPhaseを直接入力しない。最低16バースト継続、32バースト先までの推定利益と切替費用見積の1.1倍を比較する。
旧Oracle約0.80%は前半runで選び後半で評価した等時間近似、切替費用なし。追加は固定方式Phase中央値に時間重みを付けて推定しANALYSIS.mdに全条件掲載。別runの中央値からの記述的近似で、同一sampleの厳密な上限ではない。切替時間だけの回収見積は追随遅延・復帰損失を無視する楽観値。Oracleは将来の負荷を知る比較基準であり実運用アルゴリズムではない。
切替はバースト完全drain後、poll期間はepollをclose、復帰時は全fd再登録。全sampleで内容・byte数・メッセージ数が一致。任意の同時到着の正しさまでは証明しない。
benchmarks/poll-epoll/ANALYSIS.md
benchmarks/poll-epoll/results/audit-v2/dynamic-warmed.jsonl / diagnostics.jsonl / analysis.json / phase-summary.csv
-->'''
body=body[:body.index('<!--')]+notes+'\n'
s=s[:start]+body+s[end:];deck.write_text(s)
