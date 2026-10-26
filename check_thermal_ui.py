"""Thermal settings survive reruns, room changes and portable project files."""
import copy
import io
from pathlib import Path

from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from database import PANEL_DB
from project_file import decode_project, encode_project
from thermal import PANEL_U, calculate_project
from thermal_pdf import thermal_pdf


def check():
    for key, u in PANEL_U.items():
        assert PANEL_DB[key]["u"] == u
    project = decode_project(Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes())
    original_thermal = copy.deepcopy(project["rooms"][0]["form"]["thermal"])
    app = AppTest.from_file("app.py", default_timeout=120)
    # Seed the old choice before a new widget tree is built, as on a source reload.
    app.session_state["ed_module"] = "U-verdi og varmetap"
    app.run()

    def checked():
        assert not app.exception, [e.message for e in app.exception]
        assert not app.error, [e.value for e in app.error]

    checked()
    assert app.radio(key="ed_module").value == "Kalkulasjon"
    app.session_state["project_rooms"] = copy.deepcopy(project["rooms"])
    app.session_state["pending_editor"] = copy.deepcopy(project["rooms"][0])
    app.run()
    checked()
    assert app.radio(key="ed_module").value == "Kalkulasjon"
    assert "U-verdi og varmetap" not in app.radio(key="ed_module").options
    assert any(e.label == "U-verdi og varmetap" for e in app.expander)
    assert any(b.label == "Last ned U-verdi og varmetap PDF" for b in app.get("download_button"))
    assert app.number_input(key="ed_thermal_inside_c").value == 5
    assert app.number_input(key="ed_thermal_ambient_c").value == 18
    assert len(app.selectbox(key="thermal_scope").options) == 3
    assert app.get("download_button")
    app.number_input(key="ed_thermal_inside_c").set_value(4.0).run()
    app.number_input(key="ed_thermal_door_u").set_value(.8).run()
    app.number_input(key="ed_thermal_floor_u").set_value(.5).run()
    app.number_input(key="ed_thermal_heat_flux_limit").set_value(10.0).run()
    checked()
    saved = copy.deepcopy(app.session_state["project_rooms"])
    assert saved[0]["form"]["thermal"]["inside_c"] == 4
    assert saved[0]["form"]["thermal"]["door_u"] == .8
    assert project["rooms"][0]["form"]["thermal"] == original_thermal
    app.session_state["pending_editor"] = copy.deepcopy(saved[1])
    app.run()
    checked()
    assert app.number_input(key="ed_thermal_inside_c").value == -18
    assert app.number_input(key="ed_thermal_door_u").value == 0
    app.number_input(key="ed_thermal_door_u").set_value(.9).run()
    checked()
    app.session_state["pending_editor"] = copy.deepcopy(app.session_state["project_rooms"][0])
    app.run()
    checked()
    assert app.number_input(key="ed_thermal_inside_c").value == 4
    assert app.number_input(key="ed_thermal_door_u").value == .8
    app.radio(key="ed_module").set_value("Elementer").run()
    app.radio(key="ed_module").set_value("Kalkulasjon").run()
    checked()
    rooms = copy.deepcopy(app.session_state["project_rooms"])
    raw = encode_project(rooms, rooms[0], rooms[0]["id"])
    reopened = decode_project(raw)
    assert reopened["rooms"][0]["form"]["thermal"] == rooms[0]["form"]["thermal"]
    assert abs(calculate_project(rooms)["shared_net_w"]) < 1e-9
    for ids in (None, [rooms[0]["id"]], [rooms[1]["id"]]):
        pdf = thermal_pdf(rooms, ids)
        reader = PdfReader(io.BytesIO(pdf))
        text = "\n".join(p.extract_text() for p in reader.pages)
        assert "U-verdi" in text and "18" in text
        assert "0,29" in text or "0.29" in text
        assert len(reader.pages) >= 1
    bad = copy.deepcopy(rooms)
    bad[0]["form"]["thermal"]["ambient_c"] = float("nan")
    try:
        encode_project(bad, bad[0], bad[0]["id"])
    except ValueError:
        pass
    else:
        raise AssertionError("Non-finite thermal value accepted")
    app.button(key="new_freezer_room").click().run()
    checked()
    assert app.number_input(key="ed_thermal_inside_c").value == -18
    assert app.number_input(key="ed_thermal_ambient_c").value == 18
    assert app.number_input(key="ed_thermal_door_u").value == 0
    assert len(app.session_state["project_rooms"]) == 2
    print("PASS: U data, all/one-room PDF, UI reruns, room switching, new-room defaults, project round-trip and NaN rejection")


if __name__ == "__main__":
    check()
