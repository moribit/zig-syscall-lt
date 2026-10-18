#!/usr/bin/env python3
"""Re-run historical analysis in a temporary directory and compare numbers."""
import json, subprocess, tempfile, shutil
from pathlib import Path
root=Path(__file__).resolve().parent
report={}
with tempfile.TemporaryDirectory(prefix='poll-reaggregate-') as temp:
 for name in ['fixed','replication','end-to-end','end-to-end-replication','crossover-check','adaptive']:
  src=root/'results'/name;dst=Path(temp)/name;dst.mkdir()
  for f in ['raw.jsonl','environment.json']:
   if (src/f).exists():shutil.copy2(src/f,dst/f)
  subprocess.run(['python3',str(root/('analyze-adaptive.py' if name=='adaptive' else 'analyze.py')),str(dst)],check=True,stdout=subprocess.DEVNULL)
  old=json.loads((src/'analysis.json').read_text());new=json.loads((dst/'analysis.json').read_text());new.pop('inference_scope',None)
  assert old==new, f'numerical analysis changed: {name}'
  assert (src/'summary.csv').read_bytes()==(dst/'summary.csv').read_bytes(),f'summary changed: {name}'
  report[name]={'analysis_numbers_unchanged':True,'summary_csv_identical':True}
(root/'results/audit-v2/reaggregation.json').write_text(json.dumps(report,indent=2)+'\n')
print('All six historical analyses reproduce unchanged numbers; originals untouched.')
