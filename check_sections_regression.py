"""Selected-wall section dimensions and construction levels must match the model."""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from project_file import decode_project,world_input
from kalkulasjon import beregn_prosjekt
from montasje import tegn_snitt
from construction import wall_base, floor_outline
from geometry import wall_lengths
from database import PANEL_DB

rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
output=Path('qa/section-regression')
output.mkdir(parents=True,exist_ok=True)
for room in rooms:
    inp=world_input(room)
    result=beregn_prosjekt(inp)
    for wall,length in enumerate(wall_lengths(inp.pts)):
        fig=tegn_snitt(inp,result,wall)
        ax=fig.axes[0]
        labels=[text.get_text() for text in ax.texts]
        thickness=PANEL_DB[inp.panel_key]['t']/1000
        assert f'{round(wall_lengths(floor_outline(inp.pts,thickness))[wall]*1000)} mm' in labels,(wall,labels)
        assert not any('mm innv.' in label for label in labels),(wall,labels)
        assert any(text.startswith(f'Prinsippsnitt langs V{wall+1}') for text in labels)
        assert '80 mm U-kan.' not in labels
        assert f'Vegg\nV{(wall+2)%len(inp.pts)+1}' not in labels
        thickness=PANEL_DB[inp.panel_key]['t']/1000
        wall_rectangles=[patch for patch in ax.patches if isinstance(patch,Rectangle)
            and np.isclose(patch.get_width(),thickness) and np.isclose(patch.get_height(),inp.hoyde_m)]
        assert len(wall_rectangles)>=2
        assert all(np.isclose(patch.get_y(),wall_base(inp.rom_type,inp.panel_key)) for patch in wall_rectangles)
        total_mm=round((wall_base(inp.rom_type,inp.panel_key)+inp.hoyde_m+thickness)*1000)
        assert f'{total_mm} mm utvendig' in labels
        if inp.rom_type=='Kjølerom':
            assert '50 mm U-kanal' in labels
        else:
            assert '122 mm gulvoppbygging' in labels
            assert '2388 mm innvendig' in labels
        if (inp.rom_type=='Kjølerom' and wall in (2,5)) or (inp.rom_type=='Fryserom' and wall==0):
            fig.savefig(output/f'{inp.rom_type}-V{wall+1}.png',dpi=120)
        plt.close(fig)
assert np.isclose(wall_lengths(world_input(rooms[0]).pts)[2],6.25)
assert np.isclose(wall_lengths(world_input(rooms[0]).pts)[5],3.70)
print('PASS: 10 section views: selected wall lengths, honest titles, cooler0/freezer122 mm wall base and total heights')
