"""Regression: price, full blanks, IFC levels and channel dimensions agree."""
from dataclasses import replace
from pathlib import Path
import numpy as np
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
from construction import CHANNEL_HEIGHT, CHANNEL_FLANGE, wall_base, finished_floor, fixing_screw_count
from database import PANEL_DB
from project_file import decode_project, world_input, make_room
from kalkulasjon import beregn_prosjekt, ProjectInput
from kappliste import panel_order_rows
from purchase_summary import grouped_panels, panel_summary
from ifc_export import gen_ifc
from transport import packages


def check_quantities(room):
    inp = world_input(room)
    result = beregn_prosjekt(inp)
    ordered = panel_summary([room])
    materials = result['df_mat']
    walls = materials[materials.Post.str.startswith('Vegg ')]
    wall_orders = ordered[ordered.Del.str.startswith('Vegg ')]
    assert result['ant_veggpanel'] == wall_orders.Bestill_hele_elementer.sum()
    assert np.isclose(walls.Mengde.sum(), wall_orders.Bestill_m2.sum())
    for zone, mask in [('Tak', materials.Post.eq('Tak (panel)')),
                       ('Gulv', materials.Post.str.startswith('Gulv – PIR'))]:
        assert np.isclose(materials.loc[mask, 'Mengde'].sum(), ordered.loc[ordered.Del.eq(zone), 'Bestill_m2'].sum())
    screw_row = materials.loc[materials.Post.eq('Skruer')].iloc[0]
    assert screw_row.Mengde == fixing_screw_count(inp.pts,inp.hoyde_m,inp.rom_type,
                                                PANEL_DB[inp.panel_key]['t']/1000,inp.excluded_walls)
    assert 'Skruer' in result['missing_prices'] and not result['pricing_complete']
    priced = beregn_prosjekt(inp, {'skruer':.5})
    assert 'Skruer' not in priced['missing_prices']
    assert priced['df_mat'].loc[priced['df_mat'].Post.eq('Skruer'),'Totalpris (kr)'].iloc[0] == screw_row.Mengde*.5
    return result


rooms = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
assert [check_quantities(room)['ant_veggpanel'] for room in rooms] == [28,24]
grouped = grouped_panels(rooms)
assert grouped.Bestill_hele_elementer.sum() == 75
assert np.isclose(grouped.Bestill_m2.sum(),274.593)
assert np.isclose(grouped.Bestill_vekt_kg.sum(),3339.0566)
assert sum(beregn_prosjekt(world_input(r))['df_mat'].query("Post=='Skruer'").Mengde.sum() for r in rooms)==444
freight=packages(rooms)
for _, order in grouped.iterrows():
    name=f'{order.Panel} · {order.Leveringslengde_mm:g} × {order.Bredde_mm:g}'
    loads=freight[freight.Innhold.eq(name)]
    assert loads.Antall.sum()==order.Bestill_hele_elementer
    assert np.isclose(loads.Vekt_kg.sum(),order.Bestill_vekt_kg)
    # Approved packing: panel footprint stays at element size; 150 mm is added in height.
    assert (loads.Lengde_mm==order.Leveringslengde_mm).all()
    assert (loads.Bredde_mm==order.Bredde_mm).all()
    assert (loads.Høyde_mm==loads.Antall*order.Tykkelse_mm+150).all()
fiber=freight[freight.Innhold.str.contains('Gulvplate')]
assert len(fiber)==1 and fiber.iloc[0].Antall==7
assert '1500 × 3000 mm' in fiber.iloc[0].Innhold
assert (fiber.iloc[0].Lengde_mm,fiber.iloc[0].Bredde_mm,fiber.iloc[0].Høyde_mm)==(3040,1540,134)

# A wall opening changes cut sub-pieces, never the number of purchased full blanks.
inp = world_input(rooms[1])
no_opening = beregn_prosjekt(replace(inp,dorer=[],apninger=[]))
opening = beregn_prosjekt(replace(inp,dorer=[],apninger=[(0,.5,.5,.5,.5,'Teståpning')]))
for result in (no_opening,opening):
    assert len(panel_order_rows(result['df_kapp'],2400,1100)) == 38
    assert result['sam']['tot_panel'] == result['ant_veggpanel'] == 24

# Matrix includes sloping and concave boundaries and all three supported test thicknesses.
shapes = [[(0,0),(5,0),(5,4),(0,4)],
          [(0,0),(5,0),(5,2),(3,2),(3,4),(0,4)],
          [(0,0),(5,0),(5,3),(4,4),(0,4)]]
for pts in shapes:
    for kind in ('Kjølerom','Fryserom'):
        for panel in ('PIR 80 mm','PIR 100 mm','PIR 150 mm'):
            project = ProjectInput('Test','QA','1','2026-10-22','1:50',kind,panel,pts,2.4,1.1,[],[])
            check_quantities(make_room(project,{'kind':'Egendefinert polygon','points_mm':[[round(x*1000),round(y*1000)] for x,y in pts]},{}))

settings=ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS,True)
for room in rooms:
    i=world_input(room)
    model=ifcopenshell.file.from_string(gen_ifc(i.pts,i.hoyde_m,i.navn,i.panel_key,i.dorer,
        i.rom_type,i.panelbredde_m,excluded_walls=i.excluded_walls).decode())
    roof_bounds=[]; floor_bounds=[]
    for product in model.by_type('IfcProduct'):
        if not product.Representation: continue
        geometry=ifcopenshell.geom.create_shape(settings,product)
        vertices=np.array(geometry.geometry.verts).reshape(-1,3)
        if product.is_a('IfcWall') or product.is_a('IfcWallStandardCase'):
            assert np.isclose(vertices[:,2].min(),wall_base(i.rom_type,i.panel_key))
        if (product.Name or '').startswith('U-kanal'):
            assert np.isclose(np.ptp(vertices[:,2]),.05)
            horizontal=np.sort(np.ptp(vertices[:,:2],axis=0))
            assert np.isclose(horizontal[0],PANEL_DB[i.panel_key]['t']/1000+.0012)
            expected_area=(PANEL_DB[i.panel_key]['t']/1000+2*.0006)*.0006+2*(.05-.0006)*.0006
            volume=ifcopenshell.util.shape.get_volume(geometry.geometry)
            assert np.isclose(volume,expected_area*horizontal[1])
        if product.is_a('IfcSlab') and (product.Name or '')[:1] in ('T','G') and (product.Name or '')[1:2].isdigit():
            bounds=tuple(np.round(np.r_[vertices[:,:2].min(axis=0),vertices[:,:2].max(axis=0)],6))
            (roof_bounds if product.Name.startswith('T') else floor_bounds).append(bounds)
    if i.rom_type=='Fryserom':
        assert roof_bounds and sorted(roof_bounds)==sorted(floor_bounds)
        assert np.isclose(wall_base(i.rom_type,i.panel_key),.122)
        assert np.isclose(finished_floor(i.rom_type,i.panel_key),.134)
    else:
        assert wall_base(i.rom_type,i.panel_key)==finished_floor(i.rom_type,i.panel_key)==0
assert CHANNEL_HEIGHT==.05 and CHANNEL_FLANGE==.0006
print('PASS: 18 cases; price/order parity; Tasty 75 panels, 274.593 m2, 3339.0566 kg; 444 screws; IFC levels and 0.6 mm channels')
