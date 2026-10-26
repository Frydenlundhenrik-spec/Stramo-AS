from pathlib import Path
from copy import deepcopy
from project_file import decode_project
from transport import packages,pack_floor,load_figure,forward_support
from cutlist_pdf import project_materials
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
 assert len(loaded[loaded.Z_mm.eq(0)])==2 and len(loaded[loaded.Z_mm.gt(0)])==2
 assert set(loaded.Y_mm)=={0,1100}
 # With only two packages, fill the width before placing a package on top.
 across,remainder=pack_floor(example.iloc[:2],4800,2450,2700)
 assert remainder.empty and across.Z_mm.eq(0).all() and across.X_mm.eq(0).all()
 assert set(across.Y_mm)=={0,1100}
 # Four packages must stay together at the front, not spread down a long trailer.
 front,remainder=pack_floor(example,13600,2450,2700)
 assert remainder.empty and front.X_mm.eq(0).all()
 assert set(front.Y_mm)=={0,1100} and len(front[front.Z_mm.gt(0)])==2
 # Successive rows touch: no artificial gaps laterally or lengthwise.
 eight=pd.concat([example,example.assign(Kolli=[f'F{i}' for i in range(4)])],ignore_index=True)
 touching,left=pack_floor(eight,4800,2200,2700)
 assert left.empty and len(touching)==8
 assert set(touching.X_mm)=={0,2400} and set(touching.Y_mm)=={0,1100}
 assert len(pack_floor(example,2400,2450,2700,stack_panels=False)[0])==2
 # Trailer height limits the stack, not a fixed number of packages.
 third=pd.concat([example.iloc[:2],example.iloc[:1].assign(Kolli='E4')],ignore_index=True)
 assert len(pack_floor(third,2400,1100,2700)[0])==2
 assert len(pack_floor(third,2400,1100,5000)[0])==3
 # Small packages may form three or more layers, each including its own 150 mm strø.
 partial=example.iloc[:1].copy()
 partial['Antall']=2
 partial['Høyde_mm']=2*thickness+150
 partial=pd.concat([partial.assign(Kolli=f'P{i}') for i in range(10)],ignore_index=True)
 tall,left=pack_floor(partial,2400,1100,2700)
 capacity=2700//(2*thickness+150)
 assert len(tall)==capacity and len(left)==10-capacity
 assert tall.Z_mm.tolist()==[i*(2*thickness+150) for i in range(capacity)]
 assert (tall.Z_mm+tall.Høyde_mm).max()<=2700
 assert len(pack_floor(partial,2400,1100,2700,stack_panels=False)[0])==1
# Only elements and trims are cargo, even when accessories have quantities.
materials=project_materials(rooms)
trims=materials[materials.Gruppe.eq('Beslag')]
trim_cargo=f[~f.Innhold.str.startswith('PIR')]
assert set(trim_cargo.Innhold)==set(trims.Produkt)
assert trim_cargo.Antall.sum()==trims.Stk.sum()==94
assert f.Vekt_kg.isna().sum()==len(trim_cargo)==3
assert not f.Innhold.str.contains('dør|Gulvplate|skruer|Trykkventil|Terskel',case=False).any()
manual=deepcopy(rooms)
for room in manual:
 room['form']['accessory_quantities']={key:None for key in ('fugemasse','skum','pakninger','alarm')}
assert not packages(manual).Innhold.str.match('Fugemasse|Skum|Pakninger|Alarm').any()
for room in manual:
 room['form']['accessory_quantities']=dict(fugemasse=2,skum=3,pakninger=4.25,alarm=1)
entered=packages(manual)
pd.testing.assert_frame_equal(entered,f)
assert p.X_mm.is_monotonic_increasing
assert p.Lastenr.tolist()==list(range(1,len(p)+1))
assert len(p)==len(f) and m.empty
assert p.Sammenheng_til_front.all() and p.Frontkontakt_pct.eq(100).all()
front_panels=p[p.Innhold.str.startswith('PIR') & p.X_mm.eq(0) & p.Z_mm.eq(0)]
assert len(front_panels)==2 and set(front_panels.Y_mm)=={0,1100}
for upper in p[p.Z_mm.gt(0)].to_dict('records'):
 assert any(base['Z_mm']+base['Høyde_mm']==upper['Z_mm']
     and base['X_mm']<=upper['X_mm'] and base['Y_mm']<=upper['Y_mm']
     and base['X_mm']+base['Lastelengde_mm']>=upper['X_mm']+upper['Lastelengde_mm']
     and base['Y_mm']+base['Lastebredde_mm']>=upper['Y_mm']+upper['Lastebredde_mm']
     for base in p.to_dict('records'))
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
assert set(manifest.loc[manifest.Status.eq("Ikke plassert"),"Kolli"])==set(m.get('Kolli',[]))
assert manifest.X_mm.is_monotonic_increasing and manifest.Lastenr.is_monotonic_increasing
assert manifest[manifest.Status.eq("Ikke plassert")].X_mm.isna().all()
assert len(transport_manifest(f,p.iloc[:0]))==len(f)
small,missing=pack_floor(f,1000,500,500)
unloaded=transport_manifest(f,small)
assert unloaded.Status.eq('Ikke plassert').all() and unloaded.Lastenr.isna().all()
assert unloaded.Sammenheng_til_front.isna().all()
assert manifest.Sammenheng_til_front.all() and manifest.Anlegg_mot.notna().all()

# Independent front-face cases: contact is checked in both Y and Z, not merely X.
def item(k,x,y=0,z=0,w=1000,h=1000):
 return dict(Kolli=k,X_mm=x,Y_mm=y,Z_mm=z,Lastelengde_mm=1000,Lastebredde_mm=w,Høyde_mm=h)
def audit(*rows):return forward_support(pd.DataFrame(rows)).set_index('Kolli')
chain=audit(item('C',2000),item('B',1000),item('A',0))
assert chain.Sammenheng_til_front.all() and chain.loc['C','Anlegg_mot']=='B'
gap=audit(item('A',1),item('B',1001))
assert not gap.Sammenheng_til_front.any()  # Touching an unblocked package is not a chain to front.
rear_gap=audit(item('A',0),item('B',1001))
assert not rear_gap.loc['B','Sammenheng_til_front']
low=audit(item('A',0,h=800),item('B',1000))
assert low.loc['B','Frontkontakt_pct']==80 and not low.loc['B','Sammenheng_til_front']
offset=audit(item('A',0),item('B',1000,y=500))
assert offset.loc['B','Frontkontakt_pct']==50
upper=audit(item('A',0),item('B',1000,z=1000))
assert upper.loc['B','Frontkontakt_pct']==0
# Adjacent front packages can jointly cover a face, without counting edges as support.
joint=audit(item('A',0,w=500),item('B',0,y=500,w=500),item('C',1000))
assert joint.loc['C','Sammenheng_til_front']
stacked=audit(item('A',0,h=500),item('B',0,z=500,h=500),item('C',1000))
assert stacked.loc['C','Sammenheng_til_front']
edge=audit(item('A',0),item('B',1000,y=1000))
assert edge.loc['B','Frontkontakt_pct']==0
# Do not silently place a rear package without contact, even when physical space remains.
two=pd.DataFrame([dict(Kolli=k,Innhold='PIR 80 mm',Lengde_mm=2400,Bredde_mm=1100,Høyde_mm=1270) for k in ('A','B')])
loaded,left=pack_floor(two,5000,1100,1270,clearance=10)
assert len(loaded)==1 and len(left)==1
# Different lengths, widths and heights exercise floor-space joins and stacked packing.
import random
rng=random.Random(26)
for _ in range(30):
 cargo=pd.DataFrame([dict(Kolli=f'R{i}',Innhold='PIR 80 mm' if i<7 else 'Beslag',
     Lengde_mm=rng.choice((1200,2400,3910,6000)),Bredde_mm=rng.choice((400,700,1100)),
     Høyde_mm=rng.choice((310,450,710,1250,1270))) for i in range(10)])
 loaded,left=pack_floor(cargo,13600,2450,2700)
 assert len(loaded)+len(left)==10 and loaded.Sammenheng_til_front.all()
 boxes=loaded.to_dict('records')
 for i,a in enumerate(boxes):
  assert 0<=a['X_mm']<a['X_mm']+a['Lastelengde_mm']<=13600
  assert 0<=a['Y_mm']<a['Y_mm']+a['Lastebredde_mm']<=2450
  assert 0<=a['Z_mm']<a['Z_mm']+a['Høyde_mm']<=2700
  if a['Z_mm']:
   assert any(b['Z_mm']+b['Høyde_mm']==a['Z_mm'] and b['X_mm']<=a['X_mm'] and b['Y_mm']<=a['Y_mm']
       and b['X_mm']+b['Lastelengde_mm']>=a['X_mm']+a['Lastelengde_mm']
       and b['Y_mm']+b['Lastebredde_mm']>=a['Y_mm']+a['Lastebredde_mm'] for b in boxes)
  for b in boxes[i+1:]:
   assert any(a[pos]+a[size]<=b[pos] or b[pos]+b[size]<=a[pos]
       for pos,size in (('X_mm','Lastelengde_mm'),('Y_mm','Lastebredde_mm'),('Z_mm','Høyde_mm')))
print('PASS: full front-face contact, upper layers, lateral offsets, gaps and complete chain to bulkhead')
