"""Exercise completed-room editing and final assembly through Streamlit."""
import copy
import faulthandler
from streamlit.testing.v1 import AppTest
from project_file import encode_project, decode_project

# This check renders the 3D assembly repeatedly. Allow CPU contention in the
# full suite; the watchdog detects hangs rather than imposing a 55 s total SLA.
faulthandler.dump_traceback_later(180, exit=True)
app = AppTest.from_file('app.py', default_timeout=45).run()

def checked():
    assert not app.exception, [e.message for e in app.exception]

checked()
app.text_input(key='ed_name').set_value('Frys test')
app.radio(key='ed_room_type').set_value('Fryserom').run()
checked()
app.button(key='add_finished_room').click().run()
checked()
assert len(app.session_state['project_rooms']) == 1
app.button(key='new_cool_room').click().run()
checked()
app.text_input(key='ed_name').set_value('Kjøl test').run()
app.button(key='add_finished_room').click().run()
checked()
assert len(app.session_state['project_rooms']) == 2
app.radio(key='ed_module').set_value('Sammenstilling').run()
checked()
rooms = app.session_state['project_rooms']
first, second = [r['id'] for r in rooms]
app.multiselect(key=f'omit_{second}').set_value([3]).run()
checked()
assert app.session_state['project_rooms'][1]['excluded_walls'] == [3]
app.number_input(key=f'pos_{second}_x').set_value(7000.).run()
checked()
assert app.session_state['project_rooms'][1]['position_mm'][0] == 7000
app.selectbox(key='room_picker').set_value(first).run()
checked()
assert app.text_input(key='ed_name').value == 'Frys test'
assert app.radio(key='ed_room_type').value == 'Fryserom'
app.text_input(key='ed_name').set_value('Frys endret').run()
checked()
rooms = copy.deepcopy(app.session_state['project_rooms'])
project = decode_project(encode_project(rooms,rooms[0],first))
app.session_state['pending_editor'] = project['rooms'][1]
app.run()
checked()
assert app.text_input(key='ed_name').value == 'Kjøl test'
app.radio(key='ed_module').set_value('Sammenstilling').run()
checked()
assert app.multiselect(key=f'omit_{second}').value == [3]
assert app.number_input(key=f'pos_{second}_x').value == 7000.
assert app.session_state['project_rooms'][0]['input']['navn'] == 'Frys endret'
faulthandler.cancel_dump_traceback_later()
print('PASS: UI add two rooms, omit wall, placement, edit saved room and restore project data')
