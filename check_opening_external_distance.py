"""Opening dimensions use outside corners without moving the actual opening."""
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from database import FORM_MALER
from dimensions import inside_from_outside, corner_shift
from drawing_2d import tegn_veggoppstalt, stramo_plan
from geometry import transform_polygon, wall_lengths
from montasje import figur_som_pdf
from project_file import decode_project, encode_project


outer = FORM_MALER['Femkant – avskåret hjørne']['func'](5.85, 4.45, 4.8, 3.45)
info = dict(navn='Avstandskontroll', ttype='Plantegning', pnr='138', tnr='A101',
            dato='30.10.2026', A=17.75, P=18.26)
for thickness in (.08, .1):
    for turns in range(4):
        for mirrored in (False, True):
            points = inside_from_outside(transform_polygon(outer, turns, mirrored), thickness)
            distance = .1-corner_shift(points, thickness, 2)
            if thickness == .08:
                assert round(distance*1000) == 59  # Reported old inside measurement.
            opening = (2, distance, 4.5, 1.855, .1, 'Utsparing 1')
            with patch('drawing_2d._dh') as dims:
                fig = tegn_veggoppstalt(points, 2.4, 1.1, [], info, 2,
                    apninger=[opening], wall_thickness=thickness)
                call = next(c for c in dims.call_args_list if c.args[4] == '100 mm')
                assert np.isclose(call.args[2]-call.args[1], .1)
                assert np.isclose(call.args[2], distance)
                assert np.isclose(call.args[1], distance-.1)
                end_mm = round((wall_lengths(outer)[2]-.1-4.5)*1000)
                assert any(c.args[4] == f'{end_mm} mm' for c in dims.call_args_list)
                # The measured opening is still drawn at the same internal station.
                assert any(np.isclose(p.get_x(), distance) and np.isclose(p.get_width(), 4.5)
                           for p in fig.axes[0].patches if hasattr(p, 'get_width'))
                plt.close(fig)
            with patch('drawing_2d._door_dim') as dims:
                fig = stramo_plan(points, 2.4, 1.1, [], info,
                    apninger=[opening], wall_thickness=thickness)
                call = dims.call_args
                assert np.isclose(call.args[3], .1)
                assert np.isclose(call.args[4], 4.5)
                assert np.isclose(call.args[6], wall_lengths(outer)[2])
                assert np.allclose(call.args[1], transform_polygon(outer, turns, mirrored)[2])
                plt.close(fig)

# The PDF is produced from the same corrected drawing, not a separate set of labels.
points = inside_from_outside(outer, .08)
distance = .1-corner_shift(points, .08, 2)
fig = tegn_veggoppstalt(points, 2.4, 1.1, [], info, 2,
    apninger=[(2, distance, 4.5, 1.855, .3, 'Utsparing 1')], wall_thickness=.08)
text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(figur_som_pdf(fig))).pages)
plt.close(fig)
assert '100 mm' in text and '59 mm' not in text
fig = stramo_plan(points, 2.4, 1.1, [], info,
    apninger=[(2, distance, 4.5, 1.855, .3, 'Utsparing 1')], wall_thickness=.08)
text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(figur_som_pdf(fig))).pages)
assert all(label in text for label in ('100 mm', '4500', '1855', '1311 mm'))
assert '59 mm' not in text
plt.close(fig)

app = AppTest.from_file('app.py', default_timeout=90).run()
app.button(key='new_cool_room').click().run()
app.selectbox(key='ed_shape').set_value('Femkant – avskåret hjørne').run()
app.number_input(key='ed_pentagon_side_1').set_value(1000.).run()
app.number_input(key='ed_pentagon_side_3').set_value(1050.).run()
app.number_input(key='n_apninger').set_value(1).run()
app.number_input(key='ap_w0').set_value(3)
app.number_input(key='ap_off0').set_value(100)
app.number_input(key='ap_bw0').set_value(4500)
app.number_input(key='ap_bh0').set_value(1855)
app.number_input(key='ap_sill0').set_value(100).run()
assert not app.exception and not app.error
assert app.number_input(key='ap_off0').label == 'Avstand fra utvendig hjørne (mm)'
assert not any('Offset' in item.label for item in app.number_input)
assert not any(item.key == 'ed_pentagon_side_2' for item in app.number_input)
assert next(item for item in app.text_input if item.label == 'Vegg 3 – skråvegg (mm)').value == '5911'
saved = deepcopy(app.session_state['last_valid_editor'])
assert np.isclose(saved['input']['apninger'][0][1], distance)
app.session_state['pending_project'] = decode_project(encode_project([], saved, None))
app.run()
assert not app.exception and not app.error
assert app.number_input(key='ap_off0').value == 100
assert app.session_state['last_valid_editor']['input']['apninger'] == saved['input']['apninger']

# A 100 mm outside distance on an ordinary 80 mm wall stores 20 mm internally.
# This is valid and must survive saving and loading, rather than a legacy 50 mm limit.
app.number_input(key='n_apninger').set_value(0).run()
app.selectbox(key='ed_shape').set_value('Rektangel').run()
app.number_input(key='n_apninger').set_value(1).run()
app.number_input(key='ap_w0').set_value(1)
app.number_input(key='ap_off0').set_value(100).run()
assert not app.exception and not app.error
saved = deepcopy(app.session_state['last_valid_editor'])
assert np.isclose(saved['input']['apninger'][0][1], .02)
app.session_state['pending_project'] = decode_project(encode_project([], saved, None))
app.run()
assert not app.exception and not app.error
assert app.number_input(key='ap_off0').value == 100
print('PASS: outside opening distances in wall/PDF, 16 orientations/thicknesses, no geometry shift, read-only diagonal and project round trips')
