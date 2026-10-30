"""Title fields must fit and drawing exports must work on vector and raster canvases."""
from dataclasses import replace
import io
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import RendererAgg
from pypdf import PdfReader

from drawing_2d import _tegn_fig_title_block
from kalkulasjon import beregn_prosjekt
from montasje import tegn_plantegning, tegn_snitt, tegn_taktegning, figur_som_pdf
from project_file import decode_project, world_input


NAME = "Tasty Fredrikstad kjølerom og fryserom med en lang prosjektbetegnelse"
info = dict(navn=NAME, ttype="Plantegning", pnr="138", tnr="A101",
            dato="30.10.2026", A=25.43, P=19.96)
room = decode_project(Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes())["rooms"][0]
inp = replace(world_input(room), navn=NAME)
result = beregn_prosjekt(inp)

for backend in ("agg", "svg", "pdf"):
    plt.switch_backend(backend)
    fig = plt.figure(figsize=(12, 8))
    original_canvas = fig.canvas
    _tegn_fig_title_block(fig, info)
    assert fig.canvas is original_canvas, "Measuring text must not replace the export canvas."
    ax = fig.axes[0]
    text = next(t for t in ax.texts if t.get_text() == NAME)
    renderer = RendererAgg(fig.bbox.width, fig.bbox.height, fig.dpi)
    bounds = text.get_window_extent(renderer)
    left = ax.transData.transform((.14, 0))[0]
    right = ax.transData.transform((3.2-.14, 0))[0]
    assert bounds.x0 >= left-.1 and bounds.x1 <= right+1, (backend, bounds, left, right)
    for output_format in ("png", "svg", "pdf"):
        buffer = io.BytesIO()
        fig.savefig(buffer, format=output_format)
        assert len(buffer.getvalue()) > 1000
        assert fig.canvas is original_canvas
    plt.close(fig)

    for draw in (tegn_plantegning, tegn_snitt, tegn_taktegning):
        drawing = draw(inp, result)
        canvas = drawing.canvas
        document = PdfReader(io.BytesIO(figur_som_pdf(drawing)))
        assert len(document.pages) == 1
        assert "Tasty Fredrikstad" in document.pages[0].extract_text()
        assert drawing.canvas is canvas
        plt.close(drawing)

print("PASS: title-block fit and canvas identity on Agg/SVG/PDF; 9 plan, section and roof PDF exports")
