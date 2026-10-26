from pathlib import Path
from copy import deepcopy
from project_file import decode_project
from transport import packages,pack_floor,load_figure
import pandas as pd
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
f=packages(rooms);p,m=pack_floor(f,13600,2450,2700)
assert len(p)+len(m)==len(f)
assert f[f.Innhold.str.startswith('PIR')].Antall.sum()==75
for thickness, per_package in ((80,14),(100,11)):
 panel = f[f.Innhold.str.startswith(f'PIR {thickness} mm')]
 assert panel.Antall.between(1,per_package).all()
 assert (panel.Høyde_mm == panel.Antall*thickness+150).all()
 assert panel.Bredde_mm.eq(1100).all()
 assert panel[panel.Lengde_mm.eq(2400)].Antall.max()==per_package
 # User's example: four full packages, two across and two high, use 2400 mm.
 example=pd.DataFrame([dict(Kolli=f'E{i}',Innhold=f'PIR {thickness} mm',Antall=per_package,
     Lengde_mm=2400,Bredde_mm=1100,Høyde_mm=per_package*thickness+150) for i in range(4)])
 loaded,unloaded=pack_floor(example,2400,2450,2700)
 assert len(loaded)==4 and unloaded.empty
 assert (loaded.X_mm+loaded.Lastelengde_mm).max()==2400
 assert set(loaded.Z_mm)=={0,per_package*thickness+150}
 assert len(pack_floor(example,2400,2450,2700,stack_panels=False)[0])==2
 # Even a tall trailer must never receive a third package on top.
 third=pd.concat([example.iloc[:2],example.iloc[:1].assign(Kolli='E4')],ignore_index=True)
 assert len(pack_floor(third,2400,1100,5000)[0])==2
fiber=f[f.Innhold.str.startswith('Gulvplate')].iloc[0]
assert fiber.Antall==7 and '1500 × 3000 mm' in fiber.Innhold
assert (fiber.Lengde_mm,fiber.Bredde_mm,fiber.Høyde_mm)==(3040,1540,134)
screws=f[f.Innhold.eq('22 mm hvite skruer')].iloc[0]
assert screws.Antall==444 and (screws.Lengde_mm,screws.Bredde_mm,screws.Høyde_mm)==(400,300,200)
# Unspecified accessories must not become invented one-piece cargo.
manual=deepcopy(rooms)
for room in manual:
 room['form']['accessory_quantities']={key:None for key in ('fugemasse','skum','pakninger','alarm')}
assert not packages(manual).Innhold.str.match('Fugemasse|Skum|Pakninger|Alarm').any()
for room in manual:
 room['form']['accessory_quantities']=dict(fugemasse=2,skum=3,pakninger=4.25,alarm=1)
entered=packages(manual)
assert entered.loc[entered.Innhold.eq('Fugemasse'),'Antall'].sum()==4
assert entered.loc[entered.Innhold.eq('Skum'),'Antall'].sum()==6
assert entered.loc[entered.Innhold.eq('Alarm'),'Antall'].sum()==2
gaskets=entered[entered.Innhold.eq('Pakninger · 8.5 m')]
assert len(gaskets)==1 and gaskets.iloc[0].Antall==1
assert 'kolli' in gaskets.iloc[0].Grunnlag
for i,a in enumerate(p.to_dict('records')):
 assert a['X_mm']>=0 and a['Y_mm']>=0 and a['X_mm']+a['Lastelengde_mm']<=13600 and a['Y_mm']+a['Lastebredde_mm']<=2450 and a['Z_mm']+a['Høyde_mm']<=2700
 for b in p.to_dict('records')[i+1:]:
  assert a['X_mm']+a['Lastelengde_mm']<=b['X_mm'] or b['X_mm']+b['Lastelengde_mm']<=a['X_mm'] or a['Y_mm']+a['Lastebredde_mm']<=b['Y_mm'] or b['Y_mm']+b['Lastebredde_mm']<=a['Y_mm'] or a['Z_mm']+a['Høyde_mm']<=b['Z_mm'] or b['Z_mm']+b['Høyde_mm']<=a['Z_mm']
assert len(pack_floor(f,1000,500,500)[1])>0
rot=pd.DataFrame([dict(Kolli='X',Lengde_mm=500,Bredde_mm=1500,Høyde_mm=100)])
assert len(pack_floor(rot,1600,600,500)[0])==1
Path('output/transport').mkdir(parents=True,exist_ok=True)
load_figure(p,13600,2450,2700).write_html('output/transport/lasteforslag.html')
p.to_csv('output/transport/plassert.csv',index=False,encoding='utf-8-sig')
print('PASS: quantities, boundary/overlap checks, rotation, oversize. Placed',len(p),'of',len(f))
print(m[['Kolli','Innhold']].to_string(index=False) if not m.empty else 'All packages fit')

from transport import transport_manifest
manifest=transport_manifest(f,p)
assert len(manifest)==len(f) and manifest.Kolli.is_unique
assert set(manifest.loc[manifest.Status.eq("Ikke plassert"),"Kolli"])==set(m.Kolli)
assert manifest[manifest.Status.eq("Ikke plassert")].X_mm.isna().all()
assert len(transport_manifest(f,p.iloc[:0]))==len(f)
