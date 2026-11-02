"""Outside-corner opening limits, new defaults, saved projects and solid exports."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import matplotlib.pyplot as plt
import numpy as np
from pypdf import PdfReader
from shapely.geometry import Polygon
from streamlit.testing.v1 import AppTest

from construction import wall_polygon, wall_span
from database import FORM_MALER
from dimensions import inside_from_outside, corner_shift
from drawing_2d import stramo_plan
from geometry import l_polygon, transform_polygon, validate_wall_openings, wall_lengths
from ifc_export import gen_ifc
from kalkulasjon import beregn_prosjekt
from montasje import figur_som_pdf, tegn_3d_modell
from project_file import decode_project, encode_project, world_input


shapes = [FORM_MALER['Rektangel']['func'](8.96, 8.91, 0, 0),
          l_polygon([8960, 8910, 6410, 5050, 2550, 3860]),
          FORM_MALER['Femkant – avskåret hjørne']['func'](8.96, 8.91, 2.5, 2.)]
for outer in shapes:
    for thickness in (.08, .1):
        for turns in range(4):
            for mirrored in (False, True):
                points = inside_from_outside(transform_polygon(outer, turns, mirrored), thickness)
                for wall, length in enumerate(wall_lengths(outer)):
                    offset = -corner_shift(points, thickness, wall)
                    opening = (wall, offset, length, 1.855, .1, 'Hel veggbredde')
                    validate_wall_openings(points, 2.4, [], [opening], thickness)
                    for bad in ((wall, offset-.001, length, 1.855, .1, 'Utenfor'),
                                (wall, offset, length+.001, 1.855, .1, 'For bred')):
                        try:
                            validate_wall_openings(points, 2.4, [], [bad], thickness)
                        except ValueError:
                            pass
                        else:
                            raise AssertionError('Opening outside exterior wall accepted')

project = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
room = deepcopy(project['rooms'][0])
points = room['input']['pts']
opening = (1, -corner_shift(points, .08, 1), 8.91, 1.855, .1, 'Hel veggbredde')
room['input']['apninger'] = [opening]
loaded = decode_project(encode_project([room], room, room['id']))
assert np.allclose(loaded['draft']['input']['apninger'][0][:5], opening[:5])
inp = world_input(room)
result = beregn_prosjekt(inp)
assert result['df_kapp'].loc[result['df_kapp'].Vegg.eq('Vegg 2'), 'Type'].eq('Utsparing').any()

info = dict(navn=inp.navn, ttype='Plantegning', pnr='138', tnr='A101',
            dato='02.11.2026', A=66.96, P=35.74)
fig = stramo_plan(inp.pts, inp.hoyde_m, inp.panelbredde_m, inp.dorer, info,
                 apninger=inp.apninger, wall_thickness=.08, excluded_walls=inp.excluded_walls)
pdf = figur_som_pdf(fig)
plt.close(fig)
assert '8910' in '\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
Path('output/pdf/full-vegg-aapning.pdf').write_bytes(pdf)

# IFC must contain the full opening instead of silently dropping it at the inside limit.
model = ifcopenshell.file.from_string(gen_ifc(inp.pts, inp.hoyde_m, inp.navn,
    inp.panel_key, inp.dorer, inp.rom_type, inp.panelbredde_m,
    apninger=inp.apninger, excluded_walls=inp.excluded_walls).decode())
assert len(model.by_type('IfcOpeningElement')) == 3  # two doors and the new opening
wall = next(w for w in model.by_type('IfcWall') if w.Name == 'Vegg 2')
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)
solid = ifcopenshell.geom.create_shape(settings, wall)
expected_volume = Polygon(wall_polygon(inp.pts, 1, .08)).area * (inp.hoyde_m-1.855)
assert np.isclose(ifcopenshell.util.shape.get_volume(solid.geometry), expected_volume)
trace = next(t for t in tegn_3d_modell(inp, apninger=inp.apninger).data if t.name == 'Vegg 2 – panel')
direction = np.subtract(inp.pts[2], inp.pts[1])
direction /= np.linalg.norm(direction)
projected = np.column_stack([np.column_stack([trace.x, trace.y]) @ direction, trace.z])
triangles = projected[np.column_stack([trace.i, trace.j, trace.k])]
a, b = triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0]
area = np.abs(a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0]).sum()/2
lo, hi = wall_span(inp.pts, 1, .08)
assert np.isclose(area, 2*(hi-lo)*(inp.hoyde_m-1.855))

app = AppTest.from_file('app.py', default_timeout=90).run()
for button in ('new_cool_room', 'new_freezer_room'):
    app.button(key=button).click().run()
    app.number_input(key='n_apninger').set_value(1).run()
    assert not app.exception and not app.error
    assert app.number_input(key='ap_sill0').value == 100
    assert app.number_input(key='ap_off0').value == 100
    assert app.number_input(key='ap_bh0').value == 1855

# The exact Tasty wall from the screenshot accepts 6500 mm and the full 8910 mm.
app.session_state['pending_project'] = project
app.run()
app.number_input(key='n_apninger').set_value(1).run()
app.number_input(key='ap_w0').set_value(2)
app.number_input(key='ap_off0').set_value(300)
app.number_input(key='ap_bw0').set_value(6500).run()
assert not app.exception and not app.error, [e.value for e in app.error]
app.number_input(key='ap_off0').set_value(0)
app.number_input(key='ap_bw0').set_value(8910).run()
assert not app.exception and not app.error, [e.value for e in app.error]
saved = deepcopy(app.session_state['last_valid_editor'])
assert np.isclose(saved['input']['apninger'][0][1], -.08)
app.number_input(key='ap_bw0').set_value(8911).run()
assert app.error and not app.exception
assert app.session_state['last_valid_editor'] == saved
app.session_state['pending_project'] = decode_project(encode_project([], saved, None))
app.run()
assert not app.exception and not app.error
assert app.number_input(key='ap_bw0').value == 8910
assert app.number_input(key='ap_off0').value == 0
app.number_input(key='ap_off0').set_value(200)
app.number_input(key='ap_bw0').set_value(6500)
app.number_input(key='ap_sill0').set_value(150)
app.number_input(key='ap_bh0').set_value(1800).run()
saved = deepcopy(app.session_state['last_valid_editor'])
app.session_state['pending_project'] = decode_project(encode_project([], saved, None))
app.run()
assert not app.exception and not app.error
assert [app.number_input(key=k).value for k in ('ap_off0','ap_bw0','ap_sill0','ap_bh0')] == [200,6500,150,1800]
print('PASS: full exterior wall openings, 48 orientations/types, outside limits, Tasty 6500/8910 mm, defaults, preserved edits, project round trip, PDF, 3D and IFC solids')
