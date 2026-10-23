from pathlib import Path
from dataclasses import replace
import numpy as np
from project_file import decode_project,encode_project,make_room,form_points,freezer_shared_walls,world_input
from kalkulasjon import ProjectInput,beregn_prosjekt
from construction import wall_base,finished_floor,floor_outline
from geometry import poly_area,beslag_beregning
from finishing import plywood_cuts
from project_ui import assembly_plan
from montasje import tegn_snitt
import matplotlib.pyplot as plt
p=decode_project(Path('tasty-original.json').read_bytes())
cool=p['rooms'][0]
form=dict(kind='Rektangel',length_mm=3910,width_mm=7460,plywood_width_mm=1220,plywood_length_mm=2440)
base=ProjectInput(**cool['input'])
freezer=make_room(replace(base,navn='Tasty Fredrikstad Fryserom',rom_type='Fryserom',panel_key='PIR 100 mm',pts=form_points(form),dorer=[],apninger=[]),form,{})
# Cooler's re-entrant corner is (2.410,3.860). Align both external freezer faces.
freezer['position_mm']=[-1600,3960]
rooms=[cool,freezer]
matches=freezer_shared_walls(rooms)
assert {m[1] for m in matches}=={3,4},matches
cool['excluded_walls']=[3,4]
assert cool['input']['dorer']==p['draft']['input']['dorer']
raw=encode_project(rooms,cool,cool['id']);decode_project(raw)
Path('Tasty-Rom4-og-fryserom.json').write_bytes(raw)
fig=assembly_plan(rooms);fig.savefig('qa/tasty-sammenstilling.png',dpi=120);plt.close(fig)
for room in rooms:
 inp=world_input(room);result=beregn_prosjekt(inp)
 print(inp.navn,result['beslag']['stk_inn'],result['beslag']['stk_ut'])
 if inp.rom_type=='Fryserom':
  assert np.isclose(wall_base(inp.rom_type,inp.panel_key),.122)
  assert np.isclose(finished_floor(inp.rom_type,inp.panel_key),.134)
  # This fixture intentionally exercises the supported custom 1220 x 2440 format.
  cuts=plywood_cuts(inp.pts,room['form']['plywood_width_mm'],room['form']['plywood_length_mm'])
  assert abs(sum(r['Areal_m2'] for r in cuts)-poly_area(inp.pts))<.00001
  assert all(r['Bredde_mm']<=2440 and r['Lengde_mm']<=2440 for r in cuts)
  assert poly_area(floor_outline(inp.pts,.1))>poly_area(inp.pts)
  fig=tegn_snitt(inp,result);fig.savefig('qa/tasty-gulvsnitt.png',dpi=110);plt.close(fig)
  print('Finer sheets:',len(cuts))
  assert result['beslag']['n_inn']==result['beslag']['n_ut']==4
assert len(plywood_cuts(cool['input']['pts']))>0
print('PASS: two shared walls, preserved doors, floor levels, trim counts and plywood coverage')
