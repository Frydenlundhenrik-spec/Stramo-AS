"""Exercise real upload-button handling, room switching and module navigation."""
import copy
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import streamlit as st
from streamlit.testing.v1 import AppTest

from database import PANEL_DB
from project_file import decode_project, encode_project


def check():
    data = Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes()
    project = decode_project(data)
    actual_uploader = st.file_uploader

    def uploader(*args, **kwargs):
        # AppTest has no file-upload input. Only supply its bytes here; the real
        # upload button, decoder and editor restoration still execute in the app.
        if kwargs.get("key") == "project_upload":
            return BytesIO(data)
        return actual_uploader(*args, **kwargs)

    def checked(app, expected):
        assert not app.exception, [e.message for e in app.exception]
        assert not app.error, [e.value for e in app.error]
        assert app.text_input(key="ed_name").value == expected["input"]["navn"]
        assert app.selectbox(key="ed_shape").value == expected["form"]["kind"]
        if expected["form"]["kind"] == "L-form":
            assert [app.number_input(key=f"l_side_{i}").value for i in range(6)] == expected["form"]["sides_mm"]
        else:
            assert app.number_input(key="ed_length").value == expected["form"]["length_mm"]
            assert app.number_input(key="ed_width").value == expected["form"]["width_mm"]
        current = app.session_state["last_valid_editor"]
        np.testing.assert_allclose(current["input"]["pts"], expected["input"]["pts"])
        assert [tuple(door) for door in current["input"]["dorer"]] == [tuple(door) for door in expected["input"]["dorer"]]
        assert current["excluded_walls"] == expected["excluded_walls"]
        assert current["position_mm"] == expected["position_mm"]
        assert current["input"]["maalestokk"] == "Ikke målfast"

    with patch.object(st, "file_uploader", side_effect=uploader):
        app = AppTest.from_file("app.py", default_timeout=90).run()
        # Import over an already rendered L editor, including old widget IDs.
        app.selectbox(key="ed_shape").set_value("L-form").run()
        app.button(key="open_project").click().run()
        checked(app, project["draft"])
        modules = app.radio(key="ed_module").options
        assert modules == ["Oversikt", "Rom", "Tegninger", "Kalkulasjon", "Bestilling", "Elementer", "FDV", "Transport", "Sammenstilling"]
        assert PANEL_DB["PIR 80 mm"]["pris"] == 900
        assert PANEL_DB["PIR 100 mm"]["pris"] == 1000
        assert not any("NS 3420" in str(column) or "NS3420" in str(column)
                       for frame in app.dataframe for column in frame.value.columns)
        assert any("U-verdi" in str(expander.label) for expander in app.expander)

        for module in ["Transport", "Kalkulasjon", "Bestilling", "Oversikt", "Rom", "Transport", "Elementer", "Tegninger", "Sammenstilling"]:
            app.radio(key="ed_module").set_value(module).run()
            checked(app, project["draft"])

        # Import again after UI/navigation state already exists.
        app.button(key="open_project").click().run()
        checked(app, project["draft"])
        app.radio(key="ed_module").set_value("Transport").run()
        checked(app, project["draft"])

        for room in (project["rooms"][1], project["rooms"][0]):
            app.selectbox(key="room_picker").set_value(room["id"]).run()
            checked(app, room)
            app.radio(key="ed_module").set_value("Transport").run()
            checked(app, room)

        # Validate export/reimport preserves both rooms, geometry and doors.
        rooms = copy.deepcopy(app.session_state["project_rooms"])
        current = copy.deepcopy(app.session_state["last_valid_editor"])
        active = app.session_state["active_room_id"]
        data = encode_project(rooms, current, active)
        exported = decode_project(data)
        assert exported["rooms"] == json.loads(json.dumps(rooms))
        app.button(key="open_project").click().run()
        checked(app, current)
        assert json.loads(json.dumps(app.session_state["project_rooms"])) == json.loads(json.dumps(rooms))

        # Invalid input must leave the current project intact.
        data = b"{invalid JSON"
        app.button(key="open_project").click().run()
        assert not app.exception
        assert any("Kunne ikke åpne prosjektet" in error.value for error in app.error)
        assert json.loads(json.dumps(app.session_state["project_rooms"])) == json.loads(json.dumps(rooms))

    print("PASS: actual upload button over an existing L editor; Tasty dimensions and doors survive module navigation, repeated import, room switching and export/reimport; invalid import preserves both rooms")


if __name__ == "__main__":
    check()
