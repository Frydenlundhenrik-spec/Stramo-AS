"""Outside-corner room placement, project persistence and the assembly controls."""
from copy import deepcopy
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from construction import floor_outline
from dimensions import inside_from_outside
from kalkulasjon import ProjectInput
from montasje import figur_som_pdf
from project_file import (make_room, form_points, snap_room, wall_segment,
                          placement_points, encode_project, decode_project, world_input)
from project_ui import assembly_plan


def room(name, length, width, turns=0, mirrored=False, sloping=False):
    form = dict(kind='Femkant – avskåret hjørne' if sloping else 'Rektangel',
                length_mm=length, width_mm=width, turns=turns, mirrored=mirrored,
                dimension_basis='external', cut_x_mm=1100, cut_y_mm=800)
    points = inside_from_outside(form_points(form), .08)
    inp = ProjectInput(name, '138', 'A101', '30.10.2026', 'Ikke målfast',
                       'Kjølerom', 'PIR 80 mm', points, 2.4, 1.1, [], [])
    return make_room(inp, form, {})


for sloping in (False, True):
    for turns in range(4):
        for mirrored in (False, True):
            target = room('Hovedrom', 6000, 4000, turns, mirrored, sloping)
            moving = room('Rom 2', 3000, 2000, (turns+2)%4 if sloping else turns,
                          mirrored, sloping)
            target_wall, wall = (2, 2) if sloping else (1, 3)
            original = deepcopy(moving['input'])
            for from_end in (False, True):
                moving['position_mm'] = snap_room(moving, wall, target, target_wall, 1000, from_end)
                exterior = np.asarray(floor_outline(world_input(moving).pts, .08))
                reference = np.asarray(floor_outline(world_input(target).pts, .08))
                start, end = reference[target_wall], reference[(target_wall+1)%len(reference)]
                if from_end:
                    start, end = end, start
                direction = (end-start)/np.linalg.norm(end-start)
                stations = [(exterior[i]-start)@direction for i in (wall, (wall+1)%len(exterior))]
                assert np.isclose(min(stations), 1, atol=1e-6)
                # Keep the moving inside wall in contact with the retained outside wall.
                a,b,_ = wall_segment(moving, wall)
                c,d,normal = wall_segment(target, target_wall, outside=True)
                assert max(abs((a-c)@normal), abs((b-c)@normal)) < 1e-6
                assert moving['input'] == original
                p,q,_ = placement_points(moving, target, wall, target_wall, from_end)
                assert np.isclose(np.linalg.norm(q-p), 1, atol=1e-6)

target = room('Hovedrom', 6000, 4000)
moving = room('Rom 2', 2000, 2000)
moving['position_mm'] = snap_room(moving, 3, target, 1, 1000, True)
moving['placement'] = dict(target_id=target['id'], wall=3, target_wall=1,
                            from_end=True, distance_mm=1000)
moving['excluded_walls'] = [3]
rooms = [target, moving]
raw = encode_project(rooms, moving, moving['id'])
project = decode_project(raw)
assert project['rooms'][1]['placement'] == moving['placement']
assert encode_project(project['rooms'], project['draft'], project['active_id']) == raw
for distance, own_wall in ((-1, 3), (4000, 3), (1000, 1)):
    try:
        snap_room(moving, own_wall, target, 1, distance)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid placement accepted')

fig = assembly_plan(rooms)
text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(figur_som_pdf(fig))).pages)
assert '1000 mm' in text
fig.canvas.draw()
names = [t for t in fig.axes[0].texts if t.get_gid() == 'room-name']
for name in names:
    assert not any(name.get_window_extent().overlaps(t.get_window_extent())
                   for t in fig.axes[0].texts if t is not name and t.get_text().startswith('Vegg '))
plt.close(fig)

app = AppTest.from_file('app.py', default_timeout=90).run()
app.session_state['pending_project'] = project
app.run()
app.radio(key='ed_module').set_value('Sammenstilling').run()
assert not app.exception
app.selectbox(key='snap_moving').set_value(moving['id']).run()
assert app.selectbox(key='snap_target_wall').value == 1
assert app.selectbox(key='snap_own_wall').value == 3
assert app.selectbox(key='snap_from_end').value is True
assert app.number_input(key='snap_distance').value == 1000
assert app.number_input(key=f"pos_{moving['id']}_x").label == 'Venstre / høyre (mm)'
assert app.number_input(key=f"pos_{moving['id']}_y").label == 'Opp / ned (mm)'
assert any(e.label == 'Manuell plassering' for e in app.expander)
assert any(e.label == 'Fellesvegger' for e in app.expander)
before = deepcopy(app.session_state['project_rooms'])
app.number_input(key='snap_distance').set_value(500.).run()
assert app.session_state['project_rooms'] == before  # Explicit placement button applies edits.
app.button(key='snap_apply').click().run()
assert not app.exception and not app.error
placed = deepcopy(app.session_state['project_rooms'][1])
assert placed['placement']['distance_mm'] == 500
assert np.allclose(placed['position_mm'], snap_room(moving, 3, target, 1, 500, True))
saved = decode_project(encode_project(app.session_state['project_rooms'], placed, placed['id']))
app.session_state['pending_project'] = saved
app.run()
app.radio(key='ed_module').set_value('Sammenstilling').run()
assert not app.exception
assert app.session_state['project_rooms'][1]['placement'] == placed['placement']
app.number_input(key=f"pos_{moving['id']}_y").set_value(7000.).run()
assert not app.exception
assert 'placement' not in app.session_state['project_rooms'][1]
print('PASS: 32 outside-corner placements, shared-wall contact, project/PDF round trip, controls and manual edits')
