"""Check the actual folded section and order drawings for non-square corners."""
import io
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
from matplotlib.text import Text
import numpy as np
from pypdf import PdfReader

from beslag_profiles import profile_png, profile_rows
from cutlist_pdf import cutting_pdf, project_materials
from finishing import format_trim_angle
from project_file import decode_project


# A tipped section must show its actual opening, two 100 mm wings, and two 10 mm hems.
for degrees in (1, 36, 116, 135, 153, 177):
    for kind in ('skew_inner', 'skew_outer'):
        profile_png.cache_clear()
        with patch.object(plt, 'close'):
            profile_png(kind, 100, degrees)
            fig = plt.gcf()
        ax = fig.axes[0]
        outlines = [line.get_xydata() for line in ax.lines if len(line.get_xydata()) == 4]
        left, right = outlines
        left_tip, right_tip = left[1], right[1]
        assert np.isclose(np.linalg.norm(left_tip), 100) and np.isclose(np.linalg.norm(right_tip), 100)
        assert np.isclose(np.degrees(np.arccos(np.dot(left_tip, right_tip) / 100**2)), degrees)
        for wing in outlines:
            assert np.isclose(np.linalg.norm(wing[-1] - wing[-2]), 10)
            assert (wing[-2][1] < wing[1][1]) == (kind == 'skew_inner')
        labels = [artist.get_text() for artist in ax.texts]
        assert labels.count('10 mm') == 2 and labels.count('100 mm') == 2
        assert format_trim_angle(degrees) in labels and 'RAL 9010 · lakkert side' in labels
        fig.canvas.draw()
        degree_text = next(t for t in ax.texts if t.get_text() == format_trim_angle(degrees))
        paint = next(t for t in ax.texts if t.get_text().startswith('RAL 9010'))
        assert not degree_text.get_window_extent().overlaps(Text.get_window_extent(paint)), (kind, degrees)
        plt.close(fig)

with patch.object(plt, 'close'):
    profile_png('skew_inner', 100, 0)
    fig = plt.gcf()
labels = [artist.get_text() for artist in fig.axes[0].texts]
assert 'Ferdig vinkel 0°' in labels and 'Knekk fra flat plate 180°' in labels
assert any('avklares med verkstedet' in label for label in labels)
plt.close(fig)

room = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms'][0]
room['input'].update(navn='Skrårom', dorer=[], apninger=[])
room['excluded_walls'] = []
for pts, corners in (
    ([(0,0),(4,0),(4,2),(2,4),(0,4)], {135: ('H3', 'H4')}),
    ([(0,0),(5,0),(5,2),(1,4),(0,4)], {116: ('H3',), 153: ('H4',)}),
):
    room['input']['pts'] = pts
    profiles = [row for row in profile_rows(project_materials([room])) if 'angle' in row]
    assert len(profiles) == 2 * len(corners)
    assert {row['kind'] for row in profiles} == {'skew_inner', 'skew_outer'}
    for row in profiles:
        expected = row['angle']
        assert all(h in row['corners'] for h in corners[expected])
        assert row['angles'] == f"Ferdig vinkel {expected:.0f}° · Knekk fra flat plate {180-expected:.0f}°"
        assert row['lm'] == row['qty'] * 2.5
    for export in ('beslagprofiler', 'bestilling_tilbehor'):
        document = PdfReader(io.BytesIO(cutting_pdf([room], export)))
        text = '\n'.join(p.extract_text() for p in document.pages)
        for row in profiles:
            assert row['name'] in text and row['angles'] in text
            assert f"{row['qty']} stk" in text and row['corners'] in text
print('PASS: actual 100/100 geometry, hems, face, angles, references and quantities in profile/order PDFs')
