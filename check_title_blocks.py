"""Project labels stay in their own fields in every drawing title block."""
from pathlib import Path
import matplotlib.pyplot as plt
from project_file import decode_project,world_input
from kalkulasjon import beregn_prosjekt
from montasje import tegn_plantegning,tegn_taktegning,tegn_snitt,tegn_veggoppstaltt,tegn_produksjonsfigurer

count=0
for room in decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']:
    inp=world_input(room);result=beregn_prosjekt(inp)
    figs=[tegn_plantegning(inp,result),tegn_taktegning(inp,result),*tegn_produksjonsfigurer(inp,result)]
    for i in range(len(inp.pts)):
        if i not in inp.excluded_walls:
            figs.extend([tegn_snitt(inp,result,i),tegn_veggoppstaltt(inp,result,i)])
    for fig in figs:
        fig.canvas.draw();renderer=fig.canvas.get_renderer()
        for ax in fig.axes:
            if not any(t.get_text()=='Prosjekt' for t in ax.texts):continue
            box=ax.get_window_extent();count+=1
            for text in ax.texts:
                b=text.get_window_extent(renderer)
                assert b.x0>=box.x0-1 and b.x1<=box.x1+1,(text.get_text(),b,box)
                assert b.y0>=box.y0-1 and b.y1<=box.y1+1,(text.get_text(),b,box)
        plt.close(fig)
print('PASS:',count,'title blocks; every label and value inside its box')
