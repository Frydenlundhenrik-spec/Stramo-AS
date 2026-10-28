"""«Nytt prosjekt» på oversikten skal slette rom, priser og prosjektdata."""
import faulthandler
from streamlit.testing.v1 import AppTest

faulthandler.dump_traceback_later(120, exit=True)
app = AppTest.from_file("app.py", default_timeout=60).run()


def checked():
    assert not app.exception, [e.message for e in app.exception]


checked()
app.text_input(key="ed_pnr").set_value("777")
app.text_input(key="ed_name").set_value("Gammelt rom").run()
app.number_input(key="ed_price_skruer_eske").set_value(9.0).run()
app.button(key="add_finished_room").click().run()
app.button(key="new_freezer_room").click().run()
checked()
assert len(app.session_state["project_rooms"]) == 1
app.radio(key="ed_module").set_value("Oversikt").run()
checked()
app.button(key="ov_new_project").click().run()
checked()
assert app.session_state["project_rooms"] == []
assert "active_room_id" not in app.session_state or not app.session_state["active_room_id"]
assert app.radio(key="ed_module").value == "Oversikt"
assert app.text_input(key="ed_pnr").value == "1001"
assert app.text_input(key="ed_name").value == ""
assert app.radio(key="ed_room_type").value == "Kjølerom"
assert app.number_input(key="ed_price_skruer_eske").value != 9.0
faulthandler.cancel_dump_traceback_later()
print("PASS: Nytt prosjekt clears rooms, prices and project fields and returns to a blank overview")
