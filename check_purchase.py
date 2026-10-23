from pathlib import Path
from copy import deepcopy
import pandas as pd
from project_file import decode_project,encode_project
from purchase_summary import panel_summary
p=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
base=panel_summary(p['rooms'])
for waste in (0,10,99):
 q=deepcopy(p)
 for r in q['rooms']:r['form'].update(waste_pct=waste,panel_kg_m2=99,panel_stock_mm=1000)
 f=panel_summary(q['rooms'])
 pd.testing.assert_frame_equal(base,f)
 assert (f.Bestill_hele_elementer==f.Elementer_stk).all()
 assert (f.Bestill_m2>=f.Areal_m2-1e-8).all()
 assert ((f.Bestill_vekt_kg-f.Bestill_m2*f.Kg_pr_m2).abs()<1e-8).all()
 decode_project(encode_project(q['rooms'],q['draft'],q['active_id']))
print('PASS: automatic weights, made-to-length, no panel allowance and roundtrip')
