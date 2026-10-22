#!/usr/bin/env python3
"""Generate correctness CSV from captured stdout/stderr, not speed claims."""
import csv
import json
from pathlib import Path
import re
import sys

directory=Path(sys.argv[1])
rows=[json.loads(s) for s in (directory/"repeated/diagnostic.jsonl").read_text().splitlines()]
out=[]
for row in rows:
    result=json.loads(row["stdout"]) if row.get("stdout") else None
    watchdog=re.search(r"received=(\d+) EOF=(\d+)/(\d+)",row.get("stderr",""))
    out.append(dict(run=row["run"],mode=row["mode"],exit=row["exit"],
        received=result["received"] if result else int(watchdog[1]) if watchdog else "unknown",
        eof=result["counters"]["eof"] if result else int(watchdog[2]) if watchdog else "unknown",
        expected_eof=64,status="PASS" if row["exit"]==0 else "FAIL"))
with (directory/"correctness-summary.csv").open("w") as f:
    w=csv.DictWriter(f,list(out[0]));w.writeheader();w.writerows(out)
print(json.dumps(out,indent=2))
