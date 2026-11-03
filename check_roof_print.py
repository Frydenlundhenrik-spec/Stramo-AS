"""Cut roof blanks, order widths and A4 print bounds."""
import io
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from shapely.geometry import Polygon
from shapely.ops import unary_union

from dimensions import inside_from_outside
from drawing_2d import stramo_tak
from kappliste import lag_kappliste
from montasje import figur_som_pdf, figurer_som_samlet_pdf
from panel_engine import generate_roof_floor_panels


triangle = np.array([(0, 9), (4, 9), (4, 0)], float)
pentagon = np.array([(0, 0), (8, 0), (8, 2), (1, 5), (0, 5)], float)
for pts, span in ((triangle, [1, 0]), (pentagon, [0, 1])):
    for rotation in (0, 37, 90, 270):
        t = np.radians(rotation)
        rot = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        for mirror in (1, -1):
            transform = rot @ np.diag([mirror, 1])
            exterior = pts @ transform.T + [3.123, -8.25]
            panels = generate_roof_floor_panels(exterior, 1100)
            assert Polygon(exterior).symmetric_difference(unary_union([Polygon(p.polygon) for p in panels])).area < 1e-7
            blanks = [p for p in panels if p.blank]
            assert blanks
            for p in blanks:
                blank = np.asarray(p.blank)
                span_edge = blank[2] - blank[1]
                assert abs(np.dot(span_edge/np.linalg.norm(span_edge), transform @ span)) > .9999999
                assert Polygon(p.blank).buffer(1e-8).covers(Polygon(p.polygon))
                assert round(1000*np.linalg.norm(span_edge)) == p.span_mm
            cutlist = lag_kappliste(inside_from_outside(exterior, .08), 2400, 1100, "Kjølerom", floor_panel_mm=80)
            rows = cutlist[cutlist["Vegg"] == "Tak"]
            assert list(zip(rows.Elementnavn,rows.Bredde_mm,rows.Høyde_mm)) == [(p.name,p.width_mm,p.span_mm) for p in panels]
            if pts is triangle:
                assert len(panels) == len(blanks) == 9 and panels[-1].width_mm == 200

room = Polygon(triangle)
info = dict(navn="Skråtak – utskriftskontroll", ttype="Taktegning", pnr="Kontroll",
            tnr="T01", dato="", A=room.area, P=room.length)
fig = stramo_tak(inside_from_outside(triangle,.08),2.4,1.1,[],info)
pdf = figur_som_pdf(fig,"Taktegning")
if len(sys.argv) == 2:
    Path(sys.argv[1]).write_bytes(pdf)
# Exercise automatic portrait and landscape on the shared multi-page path.
wide, ax = plt.subplots(figsize=(10,3))
ax.text(.5,.5,"Kontroll",ha="center")
doc = PdfReader(io.BytesIO(figurer_som_samlet_pdf([fig, wide])))
for n,page in enumerate(doc.pages):
    assert np.allclose(sorted([float(page.mediabox.width),float(page.mediabox.height)]),A4,atol=.01)
    assert (page.mediabox.width > page.mediabox.height) == (n == 1)
    text = page.extract_text()
    assert f"Side {n+1} av 2" in text
    if not n:
        for token in ("Råelement før kapp","9 elementer","0 hele","9 kapp","T9","9000 mm","T01"):
            assert token in text, token
plt.close("all")
print("PASS: clipped roofs, rotation and mirror invariance, roof cut list, blanks and A4 PDF")
