from pathlib import Path
from copy import deepcopy
from project_file import decode_project,world_input
from kalkulasjon import beregn_prosjekt
from cutlist_pdf import project_materials,cutting_pdf
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
for room in rooms:
 for count in (0,1,3):
  r=deepcopy(room)
  r['input']['dorer']=[] if not count else [list(r['input']['dorer'][0])]
  if count:
   r['input']['dorer'][0][1]=count
   r['input']['dorer'][0][3]=.2
  f=beregn_prosjekt(world_input(r))['df_mat']
  assert f.loc[f.Type=='Terskel rustfritt','Mengde'].sum()==(count if r['input']['rom_type']=='Fryserom' else 0)
f=project_materials(rooms)
assert f.loc[f.Produkt=='Terskel rustfritt','Stk'].sum()==2
assert f.loc[f.Produkt=='Trykkventil','Stk'].sum()==1
Path('output/pdf/materialliste-prosjekt.pdf').write_bytes(cutting_pdf(rooms,'materialer'))
f.to_csv('output/pdf/materialliste-prosjekt.csv',index=False,encoding='utf-8-sig')
print('PASS: thresholds only for freezer doors; current project 2 thresholds and 1 pressure valve')
