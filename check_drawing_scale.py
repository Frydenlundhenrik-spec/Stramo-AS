"""Auto-fitted drawing figures and PDFs must not claim a fixed print scale."""
import io
from pathlib import Path

import matplotlib.pyplot as plt
from pypdf import PdfReader

from drawing_2d import stramo_plan
from kalkulasjon import beregn_prosjekt
from montasje import (
    figur_som_pdf, lag_tegningsinfo, tegn_plantegning, tegn_snitt,
    tegn_taktegning, tegn_veggoppstaltt,
)
from project_file import decode_project, world_input
from project_ui import assembly_plan


def check_scale_label(fig):
    text = '\n'.join(item.get_text() for ax in fig.axes for item in ax.texts)
    assert 'Ikke målfast' in text, text
    assert '1:10' not in text and '1:50' not in text, text


project = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
for room in project['rooms']:
    inp = world_input(room)
    result = beregn_prosjekt(inp)
    # Older saved projects contain a requested ratio. Geometry is auto-fitted,
    # so neither that value nor a direct caller's metadata may label the output.
    info = lag_tegningsinfo(inp, result, 'Plantegning')
    assert info['maal'] == 'Ikke målfast'
    legacy_info = dict(info, maal='1:50')
    fig = stramo_plan(inp.pts, inp.hoyde_m, inp.panelbredde_m, inp.dorer,
                      legacy_info, wall_thickness=.1 if 'Fryserom' in inp.rom_type else .08,
                      excluded_walls=inp.excluded_walls)
    check_scale_label(fig)
    plt.close(fig)
    for draw in (tegn_plantegning, tegn_snitt, tegn_taktegning, tegn_veggoppstaltt):
        fig = draw(inp, result)
        check_scale_label(fig)
        if draw is tegn_plantegning:
            text = PdfReader(io.BytesIO(figur_som_pdf(fig))).pages[0].extract_text()
            assert 'Ikke målfast' in text and '1:10' not in text and '1:50' not in text
            for expected in (('3910', '7460') if 'Fryserom' in inp.rom_type else ('8960', '8910', '6410')):
                assert expected in text
        plt.close(fig)

fig = assembly_plan(project['rooms'])
check_scale_label(fig)
plt.close(fig)
print('PASS: plans, sections, elevations, roof/floor and assembly use honest auto-fit scale labels; PDF dimension values preserved')
