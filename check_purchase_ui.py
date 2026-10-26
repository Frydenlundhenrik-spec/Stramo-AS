from streamlit.testing.v1 import AppTest
a=AppTest.from_file('app.py',default_timeout=60).run()
keys={n.key for n in a.number_input}
assert 'ed_waste_pct' not in keys and 'ed_panel_weight' not in keys
a.radio(key='ed_module').set_value('Elementer').run()
assert not a.exception,[e.message for e in a.exception]
assert any('Antall (stk)' in d.value.columns for d in a.dataframe)
a.button(key='add_finished_room').click().run()
assert a.session_state['project_rooms'][0]['form']['waste_pct']==10
assert a.session_state['project_rooms'][0]['form']['panel_kg_m2']==0
a.button(key='calculate_finishing').click().run()
assert not a.exception,[e.message for e in a.exception]
assert any('innvendig 50×50:' in m.value and 'stenger' in m.value for m in a.markdown)
assert any(b.label=='Detaljert beslagsliste – PDF' for b in a.get('download_button'))
print('PASS: fixed trim allowance, automatic panel weight and purchase tables')
