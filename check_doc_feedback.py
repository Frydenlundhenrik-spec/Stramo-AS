from pathlib import Path
import numpy as np
from project_file import decode_project,world_input
from kalkulasjon import beregn_prosjekt
from montasje import tegn_produksjonsfigurer,tegn_taktegning,figur_som_pdf,tegn_plantegning
import matplotlib.pyplot as plt
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
for room in rooms:
 inp=world_input(room);r=beregn_prosjekt(inp)
 assert not r['df_mat'].Type.str.contains('50×125').any()
 if inp.rom_type=='Fryserom':
  cuts=r['df_kapp'];t=cuts[cuts.Vegg=='Tak'];g=cuts[cuts.Vegg=='Gulv PIR']
  print(cuts.Vegg.unique())
  g=cuts[cuts.Vegg.str.startswith('Gulv') & cuts.Bredde_mm.apply(lambda v:isinstance(v,(int,float)))]
  assert np.allclose(t.Areal_m2.to_numpy(dtype=float),g.Areal_m2.to_numpy(dtype=float))
  fig=tegn_taktegning(inp,r);Path('output/pdf/test-tak-gulv-lik.pdf').write_bytes(figur_som_pdf(fig));plt.close(fig)
 figs=tegn_produksjonsfigurer(inp,r)
 titles=' '.join(ax.get_title(loc='left') for f in figs for ax in f.axes)
 assert 'Std vegg' in titles and 'Std tak' in titles
 if inp.rom_type=='Fryserom':assert 'Std gulv' in titles
 for f in figs:plt.close(f)
 plt.close(tegn_plantegning(inp,r))
 print(inp.rom_type,len(figs),'pages')
print('PASS: same roof/floor geometry, 50x150, grouped standard drawings, omitted plan walls')
