from pathlib import Path
import numpy as np
import ifcopenshell
import ifcopenshell.geom
from project_file import decode_project,world_input
from ifc_export import gen_ifc
from drawing_3d import tegn_3d_med_panelbredde
r=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms'][1];i=world_input(r)
data=gen_ifc(i.pts,i.hoyde_m,i.navn,i.panel_key,i.dorer,i.rom_type,i.panelbredde_m)
m=ifcopenshell.file.from_string(data.decode());setting=ifcopenshell.geom.settings();setting.set(setting.USE_WORLD_COORDS,True)
roof=[];floor=[]
for item in m.by_type('IfcSlab'):
 name=item.Name or ''
 if __import__('re').match(r'^[TG]\d',name):
  shape=ifcopenshell.geom.create_shape(setting,item);v=np.array(shape.geometry.verts).reshape(-1,3)
  bounds=tuple(np.round(np.r_[v[:,:2].min(axis=0),v[:,:2].max(axis=0)],6))
  (roof if name.startswith('T') else floor).append(bounds)
assert roof and sorted(roof)==sorted(floor),(roof,floor)
print('PASS: IFC roof and floor panel bounds match')

