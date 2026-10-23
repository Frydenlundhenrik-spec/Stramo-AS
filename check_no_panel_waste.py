from copy import deepcopy
from pathlib import Path
import pandas as pd
from project_file import decode_project
from purchase_summary import panel_summary
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
base=panel_summary(rooms)
for pct in (0,10,50,100):
    changed=deepcopy(rooms)
    for room in changed: room['form']['waste_pct']=pct
    current=panel_summary(changed)
    pd.testing.assert_frame_equal(base,current)
    assert (current.Bestill_hele_elementer==current.Elementer_stk).all()
print('PASS: panel quantities, lengths, area and weight unchanged for 0–100% allowance')
