from pathlib import Path
from copy import deepcopy
import pandas as pd
from project_file import decode_project
from purchase_summary import grouped_panels,grouped_cuts,panel_summary
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
g=grouped_panels(rooms);raw=panel_summary(rooms)
assert not g.duplicated(['Panel','Leveringslengde_mm','Bredde_mm','Tykkelse_mm']).any()
for c in ('Bestill_hele_elementer','Bestill_lm','Bestill_m2','Bestill_vekt_kg'):
    assert abs(g[c].sum()-raw[c].sum())<1e-8
assert len(g)==5
assert g[g.Tykkelse_mm==80].Bestill_hele_elementer.sum()==38
assert g[g.Tykkelse_mm==100].Bestill_hele_elementer.sum()==39
cuts=grouped_cuts(rooms)
assert not cuts.duplicated(['Panel','Høyde_mm','Bredde_mm','Tykkelse_mm']).any()
assert grouped_panels(rooms+deepcopy(rooms)).Bestill_hele_elementer.sum()==154
print(g.to_string(index=False))
print('PASS: dimensions consolidated across walls and rooms, quantities/area/weight preserved')
