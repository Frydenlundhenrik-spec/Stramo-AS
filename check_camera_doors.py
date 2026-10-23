from pathlib import Path
import numpy as np
import ifcopenshell, ifcopenshell.geom
from project_file import decode_project,encode_project,world_input
from montasje import tegn_3d_modell
from ifc_export import gen_ifc
from project_ui import assembly_plan
p=decode_project(Path('Tasty-Rom4-og-fryserom.json').read_bytes())
f=next(r for r in p['rooms'] if r['input']['rom_type']=='Fryserom')
f['input']['dorer']=[['Fryserom enkel 1000×2100 mm',1,0,2.1,'Høyre'],['Fryserom enkel 1000×2100 mm',1,1,5.7,'Venstre']]
raw=encode_project(p['rooms'],p['draft'],p['active_id']);decode_project(raw)
Path('Tasty-Rom4-og-fryserom-med-dorer.json').write_bytes(raw)
inp=world_input(f)
fig=tegn_3d_modell(inp)
assert fig.layout.scene.camera.projection.type=='orthographic'
assert fig.layout.scene.camera.up.z==1
assert fig.layout.scene.dragmode=='turntable'
doors=[t for t in fig.data if (t.name or '').startswith('Dør –')]
assert len(doors)==2
m=ifcopenshell.file.from_string(gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,inp.dorer,inp.rom_type,inp.panelbredde_m).decode())
assert len(m.by_type('IfcDoor'))==2
settings=ifcopenshell.geom.settings();settings.set(settings.USE_WORLD_COORDS,True)
for door in m.by_type('IfcDoor'):
 v=np.array(ifcopenshell.geom.create_shape(settings,door).geometry.verts).reshape(-1,3)
 assert np.isclose(v[:,2].max()-v[:,2].min(),2.1)
plan=assembly_plan(p['rooms']);plan.savefig('qa/tasty-med-fryseromsdorer.png',dpi=120)
print('PASS: two 1000 mm freezer doors, parsed IFC, orthographic camera and turntable')
