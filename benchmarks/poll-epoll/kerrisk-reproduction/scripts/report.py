#!/usr/bin/env python3
"""Publish all primary results and selected predeclared controls, without winner filtering."""
import csv,json,re,statistics as st
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'results/main';data=json.loads((out/'analysis.json').read_text());summary=list(csv.DictReader((out/'summary.csv').open()));history=list(csv.DictReader((root/'results/historical.csv').open()))
def current(suite,language):return [x for x in summary if x['suite']==suite and x['language']==language]
def number(x,key):return float(x[key])
def table(rows,columns):
 text='| '+' | '.join(label for label,_ in columns)+' |\n| '+' | '.join('---' for _ in columns)+' |\n'
 for row in rows:text+='| '+' | '.join(str(fn(row)) for _,fn in columns)+' |\n'
 return text
historical='原典の秒数（いずれも100万監視操作）。信頼区間・sample数は未確認。\n\n'
historical+=table(history,[('比較',lambda x:x['suite']),('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),('K',lambda x:x['changes']),('過去の秒数',lambda x:x['seconds'])])
blocks={'HISTORICAL_RESULTS':historical}
for lang,marker in [('c','C_RESULTS'),('zig','ZIG_RESULTS')]:
 text='原典相当のA/B/C、100万反復、中央値と名目95% bootstrap区間（秒）、各3 sample。\n\n'
 rows=[x for x in summary if x['language']==lang and x['suite'] in ['A','B','C']]
 text+=table(rows,[('比較',lambda x:x['suite']),('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),('K',lambda x:x['changes']),('秒 中央値',lambda x:f"{number(x,'million_units_seconds'):.3f}"),('95%区間',lambda x:f"{number(x,'ci95_low')/1000:.3f}–{number(x,'ci95_high')/1000:.3f}")])
 if lang=='c':text+='\n![過去・現在C・現在Zigは別の実験](results/main/density-1000.svg)\n\n![100 fdの比較も全点を掲載](results/main/density-100.svg)\n'
 else:
  pairs=data['backend_pairs'];pollwins=[x for x in pairs if x['poll_over_epoll_median']<1]
  text+='\n### Q1：高Ready率の逆転\n\n'
  if not pollwins:text+='今回の主比較Aでは、両言語・全N/Ready率でpollの費用中央値がepollを上回り、原典の高Ready率でのpoll逆転を再現しなかった。これは再構成と今回のVMの範囲に限る。元ソース未入手なので、厳密な原典再現の成功/失敗とは別である。\n'
  else:text+='poll費用中央値がepollを下回った条件も、下回らなかった条件も、次の全表で示す。条件探索後の小差を一般的な逆転とは断定しない。\n'
  text+=table(pairs,[('言語',lambda x:x['language']),('N',lambda x:x['fds']),('Ready',lambda x:x['ready_fds']),('poll/epoll費用比',lambda x:f"{x['poll_over_epoll_median']:.3f}"),('95%区間',lambda x:f"{x['ci95_low']:.3f}–{x['ci95_high']:.3f}"),('pollが速いrun',lambda x:f"{x['poll_faster_runs']}/{x['n']}")])
  text+='\n原典の公表点では50%と100%でpollが逆転しているが、正確な閾値を連続的に測った表ではない。全Readyでは100 fdでpoll/epoll=0.214、1000 fdで0.268。今回の全点の比と上表で比較する。逆転の有無だけでなく、Ready率に対する曲線と差の規模も異なり得る。\n\n### Q2：CとZigの傾向\n\n'
  agreement=all((next(p for p in pairs if p['language']=='c' and p['fds']==z['fds'] and p['ready_fds']==z['ready_fds'])['poll_over_epoll_median']<1)==(z['poll_over_epoll_median']<1) for z in pairs if z['language']=='zig')
  text+=('主比較Aのpoll対epollの優劣方向は全条件でCとZigが一致した。現行のこの条件では、Zig化だけを過去との差の原因とする説明を支持しない。' if agreement else 'CとZigで一致しない優劣方向もあった。全条件を上表へ残した。')+'各条件のZig/Cペア比はanalysis.jsonのlanguage_pairsに全件保存した。APIラッパー・コンパイラ最適化・検査コードが完全同一ではなく、これを言語の優位性の測定としない。\n\n![中間の1 Ready、データ消費なし](results/main/sparse.svg)\n'
 blocks[marker]=text
factor=''
if any(x['suite']=='factors' for x in summary):
 factor='### Q3：一要因ずつの橋渡し対照\n\nN=1000、短いループを各5回。下表はZig側の全橋渡し点で、µs/待機呼び出し。同じN/Ready集合で比較し、C側もsummary.csvへ全件保存した。\n\n'
 rows=[x for x in summary if x['suite']=='factors' and x['language']=='zig' and x['label'] in ['baseline','socket','socket-normal','existing-api','existing-scan']]
 factor+=table(rows,[('Ready',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),('段階',lambda x:x['label']),('µs/回',lambda x:f"{number(x,'ns_per_unit_median')/1000:.3f}"),('95%区間',lambda x:f"{number(x,'ci95_low')/1000:.3f}–{number(x,'ci95_high')/1000:.3f}")])
 factor+='\n順序はpipe/contiguous/-1/API → socket/contiguous/-1/API → socket/normal/-1/API → socket/normal/0/API → socket/normal/0/scan。各隣接点は1条件だけ変更する。これだけで元の既存実装と完全一致したとはしない。直接のtimeout/走査/検証対照もsummary.csvに残す。\n\n### maxevents：異なる量の仕事を区別\n\n'
 rows=[x for x in summary if x['suite']=='capacity']
 factor+=table(rows,[('言語',lambda x:x['language']),('work',lambda x:x['work']),('容量',lambda x:x['capacity']),('µs/単位',lambda x:f"{number(x,'ns_per_unit_median')/1000:.3f}"),('待機回数/単位',lambda x:f"{number(x,'waits_per_unit'):.1f}"),('イベント数/単位',lambda x:f"{number(x,'events_per_unit'):.1f}")])
 factor+='\n単発APIでは容量1と1000で返すイベント数が違う。fullは1000個すべてのReady対象を集める同量の仕事であり、単位・繰り返し回数が異なる。単発の低コストを全Ready集合の高速化と誤認しない。\n\n![呼び出し単位と全Ready集合単位を分離](results/main/capacity.svg)\n\n### 走査と集合検証\n\n'
 rows=[x for x in summary if x['suite']=='factors' and x['language']=='zig' and x['label'] in ['baseline','pipe-scan','pipe-verify','scan-only','verify-only']]
 factor+=table(rows,[('Ready',lambda x:x['ready_fds']),('方式',lambda x:x['backend']),('work',lambda x:x['work']),('ns/その区間の1反復',lambda x:f"{number(x,'ns_per_unit_median'):.1f}"),('反復',lambda x:x['iterations'])])
 factor+='\napi/scan/verifyはそれぞれ待機を含む。scan-only/verify-onlyは事前取得結果を繰り返す別ループで、キャッシュ状態も異なる。独立した中央値の差を厳密な加法分解にしない。\n'
registration_file=out/'registration-summary.csv'
if registration_file.exists():
 rows=list(csv.DictReader(registration_file.open()))
 factor+='\n### 登録と投入の順序：追加の一要因対照\n\n主測定と上の対照ではデータ投入後にADDするため、Ready Listの初期順序は登録順となる。既存の実装はADD後にランダムに投入する。この差を静的監査で発見したため、別planを固定し、登録/投入の順だけを変える追加対照を行った。元のCがどちらかは未確認。各20,000反復・5 sample、両言語の全条件を示す。\n\n'
 factor+=table(rows,[('言語',lambda x:x['language']),('条件',lambda x:x['label']),('Ready',lambda x:x['ready_fds']),('ADDの時点',lambda x:x['registration']),('µs/回',lambda x:f"{number(x,'median_ns')/1000:.3f}"),('名目95%区間',lambda x:f"{number(x,'ci95_low')/1000:.3f}–{number(x,'ci95_high')/1000:.3f}")])
 factor+='\nafter-fillは投入後ADD（登録順）、before-fillは投入前ADD（ランダム通知順）。計時外の事前取得列のhashを独立したPython実装で照合し、集合は同じだが列の順序が変わることも確認した。生成したC/Zigソース・差分・SHAとコマンドはregistration-source/とregistration-environment.jsonへ保存した。\n\n全Readyのsocket/bridgeではランダム通知順の中央値が上昇した。pipeでは差が小さく区間も重なる。キャッシュmissを直接測ったものではないため内部原因までは特定しない。この介入はepollのみの短い対照で、過去のpoll逆転や既存End-to-End全体の差を説明し切ったものではない。\n\n![登録と投入の順序を変えた追加対照](results/main/registration.svg)\n'
blocks['FACTOR_RESULTS']=factor
confirmed='### Ready配置とtimeout\n\n'
if any(x['suite']=='position' for x in summary):
 rows=[x for x in summary if x['suite']=='position']
 confirmed+=table(rows,[('言語',lambda x:x['language']),('方式',lambda x:x['backend']),('位置',lambda x:x['placement']),('timeout',lambda x:x['timeout']),('µs/回',lambda x:f"{number(x,'ns_per_unit_median')/1000:.3f}")])
 confirmed+='\nこの介入で位置/timeoutによる費用差を直接比較する。ただし待機登録件数をprobeで直接数えたものではなく、上流kernel実装と整合するかを判断する。\n'
confirmed+='\n### Q4：監視対象の更新費用\n\n'
ctl=[x for x in summary if x['suite']=='C'];confirmed+=table(ctl,[('言語',lambda x:x['language']),('K',lambda x:x['changes']),('ns/反復',lambda x:f"{number(x,'ns_per_unit_median'):.1f}"),('DEL+ADD増分ns/組',lambda x:'—' if int(x['changes'])==0 else f"{(number(x,'ns_per_unit_median')-number(next(y for y in ctl if y['language']==x['language'] and int(y['changes'])==0),'ns_per_unit_median'))/int(x['changes']):.1f}")])
confirmed+='\n増分はK=0とK>0の独立中央値からの記述的推定であり、純粋な1 syscallのレイテンシではない。\n\n![監視操作と2K回の更新を含む](results/main/ctl.svg)\n'
if any(x['suite']=='ctl-only' for x in summary):
 confirmed+=table([x for x in summary if x['suite']=='ctl-only'],[('言語',lambda x:x['language']),('K',lambda x:x['changes']),('登録変更のみns/反復',lambda x:f"{number(x,'ns_per_unit_median'):.1f}"),('ns/DEL+ADD組',lambda x:f"{number(x,'ns_per_unit_median')/int(x['changes']):.1f}")])
blocks['CONFIRMED_RESULTS']=confirmed
p=root/'REPORT.md';text=p.read_text()
for marker,body in blocks.items():
 start='<!-- '+marker+' -->';end='<!-- /'+marker+' -->';replacement=start+'\n'+body+'\n'+end
 if end in text:text=re.sub(re.escape(start)+'.*?'+re.escape(end),lambda _:replacement,text,flags=re.S)
 else:text=text.replace(start,replacement)
p.write_text(text)
print('Report tables regenerated from all saved measurements; historical/current remain separated.')
