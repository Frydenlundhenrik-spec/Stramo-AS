from pathlib import Path
import numpy as np
from project_file import decode_project
from purchase_summary import panel_summary,with_totals,PANEL_TOTAL_COLUMNS,estimated_panel_weight
assert estimated_panel_weight('PIR 80 mm')==11.8
assert estimated_panel_weight('PIR 100 mm')==12.6
p=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
for r in p['rooms']:r['form'].update(panel_kg_m2=0,panel_stock_mm=1000)
f=panel_summary(p['rooms'])
assert (f.Vektgrunnlag=='Balex produktdatablad').all()
assert np.allclose(f.Vekt_netto_kg,f.Areal_m2*f.Kg_pr_m2)
assert np.allclose(f.Bestill_vekt_kg,f.Bestill_m2*f.Kg_pr_m2)
assert (f[f.Del.str.startswith('Vegg')].Leveringslengde_mm==2400).all()
assert f.Leveringslengde_mm.max()>7000
p['rooms'][0]['form']['panel_kg_m2']=14
u=panel_summary(p['rooms']);assert (u[u.Panel=='PIR 80 mm'].Kg_pr_m2==11.8).all()
t=with_totals(f,PANEL_TOTAL_COLUMNS,'Rom');t.to_csv('qa/elementer-vektestimat.csv',index=False,encoding='utf-8-sig')
print(t.iloc[-1][['Areal_m2','Vekt_netto_kg','Bestill_hele_elementer','Bestill_m2','Bestill_vekt_kg']].to_dict())
print('PASS: exact lengths ignore legacy stock length; estimated and supplied weight; CSV totals')
