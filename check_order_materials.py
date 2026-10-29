"""Order dimensions, calculation prices, PDF and room selection must agree."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import math
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest
from project_file import decode_project, world_input
from kalkulasjon import beregn_prosjekt
from kappliste import panel_order_rows
from materialer import materialliste_med_sum
from purchase_summary import grouped_panels
from cutlist_pdf import cutting_pdf, project_materials

rooms = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
for room in rooms:
    inp = world_input(room)
    result = beregn_prosjekt(inp)
    panel_rows = result['df_mat'].query("Post == 'Panel'")
    orders = grouped_panels([room])
    assert not panel_rows.duplicated(['Type', 'Leveringslengde_mm', 'Bredde_mm', 'Tykkelse_mm']).any()
    assert panel_rows.Bestill_hele_elementer.sum() == 35
    for order in orders.itertuples():
        row = panel_rows[panel_rows.Leveringslengde_mm.eq(order.Leveringslengde_mm)].iloc[0]
        assert row.Type == order.Panel
        assert row.Bredde_mm == order.Bredde_mm and row.Tykkelse_mm == order.Tykkelse_mm
        assert row.Bestill_hele_elementer == order.Bestill_hele_elementer
        assert math.isclose(row.Mengde, order.Bestill_m2)
        assert math.isclose(row['Totalpris (kr)'], round(order.Bestill_m2 * result['panel']['pris'], 2))
    shown = materialliste_med_sum(result['df_mat'])
    assert shown.iloc[-1].Post == 'SUM'
    assert shown.iloc[-1]['Totalpris (kr)'] == round(result['tot_pris'], 2)
    assert not shown.Post.str.startswith(('Vegg ', 'Tak (panel)', 'Gulv – PIR')).any()
    assert not shown.Type.str.contains('PRIS MANGLER').any()
    assert len(shown[shown.Post.eq('Dør')]) == 2
    pdf = cutting_pdf([room], 'kalkulasjon')
    text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    assert 'Leveringslengde' in text and 'Antall (stk)' in ' '.join(text.split()) and 'SUM' in text
    assert 'Vegg 1\n' not in text

    # Historical per-wall/roof/floor prices must still apply to their allocated material.
    overrides = {'vegg_0': 700, 'vegg_1': 1200, 'tak': 850, 'gulv_pir': 1100}
    priced = beregn_prosjekt(inp, overrides)['df_mat'].query("Post == 'Panel'")
    blanks = panel_order_rows(result['df_kapp'], round(inp.hoyde_m*1000), round(inp.panelbredde_m*1000))
    expected = 0
    for _, group in blanks.groupby(['Leveringslengde_mm', 'Bredde_mm']):
        cost = 0
        for allocation in group.Fordeling_m2:
            for zone, area in allocation.items():
                key = f"vegg_{int(zone.split()[1])-1}" if zone.startswith('Vegg ') else {'Tak':'tak', 'Gulv':'gulv_pir'}[zone]
                cost += area * overrides.get(key, result['panel']['pris'])
        expected += round(cost, 2)
    assert math.isclose(priced['Totalpris (kr)'].sum(), expected)
    incomplete = beregn_prosjekt(inp, {'vegg_0': 0})
    assert not incomplete['pricing_complete']
    assert inp.panel_key in incomplete['missing_prices']

combined = project_materials(rooms)
assert combined.query("Gruppe == 'Elementer'").Stk.sum() == 70
assert not combined.query("Gruppe == 'Tilbehør'").Produkt.str.startswith('PIR').any()
order_pdf = cutting_pdf(rooms, 'bestilling')
text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(order_pdf)).pages)
assert 'Bestillingsliste elementer' in text and 'PIR 80 mm' in text and 'PIR 100 mm' in text
assert 'Elementliste\n' not in text

# The separate order PDF contains all non-panel products and no element pages.
for selection in (rooms, rooms[:1], rooms[1:]):
    accessory_pdf = PdfReader(BytesIO(cutting_pdf(selection, 'bestilling_tilbehor')))
    assert len(accessory_pdf.pages) == 1
    text = '\n'.join(p.extract_text() for p in accessory_pdf.pages)
    assert 'Bestillingsliste – beslag, dører og tilbehør' in text
    assert all(label in text for label in ('Beslag', 'Dører', 'Tilbehør', '22 mm hvite skruer'))
    assert 'PIR 80 mm' not in text and 'PIR 100 mm' not in text
    assert 'Bestillingsliste elementer' not in text and 'Leveringslengde' not in text
    assert ('Fryseromsdør' in text) == any(r['input']['rom_type'] == 'Fryserom' for r in selection)
    assert ('Kjøleromsdør' in text) == any(r['input']['rom_type'] == 'Kjølerom' for r in selection)
    assert 'Slagretning' in text

# run_checks.py supplies an isolated copy with a test-only login stub.
app = AppTest.from_file('app.py', default_timeout=90).run()
app.session_state['project_rooms'] = deepcopy(rooms)
app.session_state['pending_editor'] = deepcopy(rooms[0])
app.run()
app.radio(key='ed_module').set_value('Bestilling').run()
assert not app.exception, [e.message for e in app.exception]
assert any(b.key == 'panel_order_pdf' for b in app.get('download_button'))
assert any(b.key == 'accessory_order_pdf' for b in app.get('download_button'))
assert any('Beslag' in d.value.columns for d in app.dataframe)
doors = next(d.value for d in app.dataframe if 'Dører' in d.value.columns)
assert len(doors) == 4 and doors.Antall.sum() == 4
accessories = next(d.value for d in app.dataframe if 'Tilbehør' in d.value.columns)
assert accessories.loc[accessories['Tilbehør'].eq('Alarm'), 'Antall'].iloc[0] == 1
frame = next(d.value for d in app.dataframe if 'Bestilling (stk)' in d.value.columns)
assert frame.iloc[-1]['Bestilling (stk)'] == 70
app.selectbox(key='order_room_choice').set_value(rooms[1]['id']).run()
assert not app.exception, [e.message for e in app.exception]
frame = next(d.value for d in app.dataframe if 'Bestilling (stk)' in d.value.columns)
assert frame.iloc[-1]['Bestilling (stk)'] == 35
assert 'PIR 80 mm' not in frame.Panel.values and 'PIR 100 mm' in frame.Panel.values
doors = next(d.value for d in app.dataframe if 'Dører' in d.value.columns)
assert len(doors) == 2 and doors['Dører'].str.startswith('Fryseromsdør').all()
app.selectbox(key='order_room_choice').set_value(rooms[0]['id']).run()
assert not app.exception, [e.message for e in app.exception]
accessories = next(d.value for d in app.dataframe if 'Tilbehør' in d.value.columns)
assert 'Alarm' not in accessories['Tilbehør'].values
app.radio(key='ed_module').set_value('Kalkulasjon').run()
assert not app.exception, [e.message for e in app.exception]
assert any('Leveringslengde (mm)' in d.value.columns for d in app.dataframe)
app.radio(key='ed_module').set_value('Elementer').run()
assert not app.exception, [e.message for e in app.exception]
assert not any('Bestilling (stk)' in d.value.columns for d in app.dataframe)
assert len(app.session_state['project_rooms']) == 2
print('PASS: Tasty order dimensions and quantities, prices, doors, PDF, all/single room and navigation')
