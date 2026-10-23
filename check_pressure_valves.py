from pathlib import Path
from copy import deepcopy
from project_file import decode_project,world_input
from kalkulasjon import beregn_prosjekt
from cutlist_pdf import project_materials,cutting_pdf
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
for room in rooms:
 for count in (0,1,4):
  r=deepcopy(room)
  r['input']['dorer']=[] if count==0 else [list(r['input']['dorer'][0])]
  if count:
   r['input']['dorer'][0][1]=count
   r['input']['dorer'][0][2]=1
   r['input']['dorer'][0][3]=.2
  for selection in ([],r['input']['beslag_valg']):
   r['input']['beslag_valg']=selection
   f=beregn_prosjekt(world_input(r))['df_mat']
   assert f.loc[f.Type=='Trykkventil','Mengde'].sum()==(1 if r['input']['rom_type']=='Fryserom' else 0)
f=project_materials(rooms)
assert f.loc[f.Produkt=='Trykkventil','Stk'].sum()==1
f2=project_materials(rooms+[deepcopy(rooms[1])])
assert f2.loc[f2.Produkt=='Trykkventil','Stk'].sum()==2
Path('output/pdf/materialliste-prosjekt.pdf').write_bytes(cutting_pdf(rooms,'materialer'))
f.to_csv('output/pdf/materialliste-prosjekt.csv',index=False,encoding='utf-8-sig')
print('PASS: zero per cooler, one per freezer, independent of doors and selection; PDF/CSV updated')
