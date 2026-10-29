"""Visible wall/door dimensions must terminate at actual freezer junctions."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import numpy as np
import matplotlib.pyplot as plt
from pypdf import PdfReader
from branding import project_name
from construction import floor_outline, wall_polygon
from dimensions import exterior_wall, exterior_door
from project_file import decode_project, world_input
from kalkulasjon import beregn_prosjekt
from montasje import tegn_plantegning, figur_som_pdf
from cutlist_pdf import cutting_pdf, project_materials
from geometry import transform_polygon

rooms = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
for room in rooms:
    room['input']['navn'] += ' – bildetest'
cool, freezer = map(world_input, rooms)
assert 'bildetest' not in cool.navn
assert rooms[0]['input']['navn'].endswith('bildetest')  # display cleanup does not alter saved data
assert project_name('Tasty Fredrikstad') == 'Tasty Fredrikstad'
assert project_name('Tasty - BILDETEST') == 'Tasty'

freezer_outline = np.array(floor_outline(freezer.pts, .1))
assert np.isclose(exterior_wall(cool.pts,.08,2,cool.excluded_walls)[1][0], freezer_outline[:,0].max())
assert np.isclose(exterior_wall(cool.pts,.08,5,cool.excluded_walls)[0][1], freezer_outline[:,1].min())
assert np.isclose(np.linalg.norm(np.subtract(*exterior_wall(cool.pts,.08,2,cool.excluded_walls))),6.33)
assert np.isclose(np.linalg.norm(np.subtract(*exterior_wall(cool.pts,.08,5,cool.excluded_walls))),3.78)

# Free wall endpoints must remain on the actual panel for rotations and mirrors.
for turns in range(4):
    for mirrored in (False, True):
        pts = transform_polygon(cool.pts, turns, mirrored)
        for wall, endpoint in ((2,1),(5,0)):
            p = exterior_wall(pts,.08,wall,cool.excluded_walls)[endpoint]
            polygon = wall_polygon(pts,wall,.08,cool.excluded_walls)
            assert min(np.linalg.norm(p-v) for v in polygon) < 1e-8
        start,length,offset = exterior_door(pts,.08,2,2.63,cool.excluded_walls)
        a,b = np.asarray(pts[2]),np.asarray(pts[3])
        direction = (b-a)/np.linalg.norm(b-a)
        # The opening stays at its original station; only its measurement origin changes.
        assert np.isclose((start+direction*offset-a)@direction,2.63)

with patch('drawing_2d._dim_along_wall') as measure:
    fig = tegn_plantegning(cool,beregn_prosjekt(cool))
    for wall,label in ((2,'6330 mm'),(5,'3780 mm')):
        call = next(c for c in measure.call_args_list if c.args[3] == label)
        a,b = exterior_wall(cool.pts,.08,wall,cool.excluded_walls)
        assert np.allclose(call.args[1],a) and np.allclose(call.args[2],b)
    plt.close(fig)

fig = tegn_plantegning(cool,beregn_prosjekt(cool))
pdf = figur_som_pdf(fig)
plt.close(fig)
text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
assert '6330 mm' in text and '3780 mm' in text and 'bildetest' not in text.lower()
assert 'Vegg 1' in text and 'V1' in text  # wall name and physical element ID are different
for kind in ('kalkulasjon','bestilling','bestilling_tilbehor'):
    text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(cutting_pdf(rooms,kind))).pages)
    assert 'bildetest' not in text.lower(), kind
assert not project_materials(rooms).Produkt.str.contains('bildetest').any()
print('PASS: wall and door endpoints match actual junctions, rotations/mirrors, PDF and clean names')
