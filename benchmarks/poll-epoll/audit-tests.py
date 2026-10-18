#!/usr/bin/env python3
"""Exercise pairing/statistical guards without asserting performance outcomes."""
import ast, math, random, statistics as st, unittest
from pathlib import Path
source=ast.parse(Path(__file__).with_name('audit-analyze.py').read_text())
namespace=dict(math=math,random=random,med=st.median)
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ['paired','holm']],type_ignores=[]),'audit-statistics','exec'),namespace)
paired=namespace['paired'];holm=namespace['holm']
class StatisticsTests(unittest.TestCase):
 def test_identical_pairs(self):
  a=[dict(run=i,seed=i,value=10) for i in range(10)]
  r=paired(a,a,lambda x:x['value']);self.assertEqual(r['ratio'],1);self.assertEqual(r['ci95'],[1,1]);self.assertEqual(r['sign_p'],1)
 def test_pairing_guards(self):
  a=[dict(run=1,seed=7,value=1)];cost=lambda x:x['value']
  for bad in [[],a+a,[dict(run=1,seed=8,value=1)]]:
   with self.assertRaises(AssertionError):paired(a,bad,cost)
 def test_exact_sign_and_holm(self):
  a=[dict(run=i,seed=i,value=1) for i in range(10)];b=[dict(x,value=2) for x in a]
  r=paired(a,b,lambda x:x['value']);self.assertEqual(r['sign_p'],2/1024)
  rows=[dict(sign_p=.01),dict(sign_p=.03),dict(sign_p=.2)];holm(rows)
  self.assertEqual([x['holm_p'] for x in rows],[.03,.06,.2])
if __name__=='__main__':unittest.main()
