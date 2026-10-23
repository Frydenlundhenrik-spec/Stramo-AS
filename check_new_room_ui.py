import copy, faulthandler
from streamlit.testing.v1 import AppTest
faulthandler.dump_traceback_later(50,exit=True)
a=AppTest.from_file('app.py',default_timeout=15).run()
a.text_input(key='ed_name').set_value('Fryserom 1')
a.radio(key='ed_room_type').set_value('Fryserom').run()
a.number_input(key='ed_doors').set_value(2).run()
a.number_input(key='do1').set_value(2000).run()
a.button(key='add_finished_room').click().run()
saved=copy.deepcopy(a.session_state['project_rooms'])
a.number_input(key='do0').set_value(6100).run()
assert a.error and not a.exception
assert a.button(key='new_cool_room')
a.button(key='new_cool_room').click().run()
assert not a.exception,[e.message for e in a.exception]
assert not a.error,[e.value for e in a.error]
assert a.radio(key='ed_room_type').value=='Kjølerom'
assert a.number_input(key='ed_doors').value==0
assert a.number_input(key='n_apninger').value==0
assert a.session_state['project_rooms']==saved
assert a.text_input(key='ed_name').value=='Kjølerom 1'
# Starting another room automatically retains the valid unsaved draft.
a.button(key='new_cool_room').click().run()
assert not a.exception
assert len(a.session_state['project_rooms'])==2
assert a.text_input(key='ed_name').value=='Kjølerom 2'
assert a.session_state['project_rooms'][0]==saved[0]
a.button(key='new_freezer_room').click().run()
assert len(a.session_state['project_rooms'])==3
assert a.text_input(key='ed_name').value=='Fryserom 2'
assert a.number_input(key='ed_doors').value==0
faulthandler.cancel_dump_traceback_later()
print('PASS: invalid 6100 mm door recovery, fresh fields, preserved rooms, automatic draft retention and numbering')
