from streamlit.testing.v1 import AppTest
a=AppTest.from_file('app.py',default_timeout=60).run()
keys={n.key for n in a.number_input}
assert 'ed_waste_pct' not in keys and 'ed_panel_weight' not in keys
a.radio(key='ed_module').set_value('Produksjon').run()
assert not a.exception,[e.message for e in a.exception]
assert any('Antall (stk)' in d.value.columns for d in a.dataframe)
a.button(key='add_finished_room').click().run()
assert a.session_state['project_rooms'][0]['form']['waste_pct']==10
assert a.session_state['project_rooms'][0]['form']['panel_kg_m2']==0
a.selectbox(key='doc_production_preview').set_value('Bestillingslister').run()
assert not a.exception,[e.message for e in a.exception]
assert any('50×50' in str(d.value) for d in a.dataframe)
assert a.checkbox(key='doc_production_profiles').value
assert a.button(key='doc_production_build').disabled is False
print('PASS: fixed trim allowance, automatic panel weight and purchase tables')
