"""Regression cases from the 22 October audit: invalid drafts never replace saves."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

from geometry import validate_polygon, validate_wall_openings
from kalkulasjon import ProjectInput
from project_file import make_room, form_points, encode_project, decode_project, validate_room
import project_ui


def rejected(action, match=None):
    try:
        action()
    except ValueError as exc:
        assert match is None or match in str(exc), str(exc)
    else:
        raise AssertionError("Invalid geometry/project was accepted")


def check():
    form = dict(kind="Rektangel", length_mm=6000, width_mm=4000)
    inp = ProjectInput("Kjølerom 1", "138", "A1", "22.10.2026", "1:50", "Kjølerom",
                       "PIR 80 mm", form_points(form), 2.5, 1.1,
                       [("Enkel kjøledør 900×2100 mm", 1, 0, .35, "Venstre")], [])
    room = make_room(inp, form, {})
    validate_room(room)
    raw = encode_project([room], room, room["id"])
    assert encode_project(**{k: v for k, v in decode_project(raw).items()
                             if k in ("rooms", "draft", "active_id")}) == raw
    for points in (
        [(0,0),(5,4),(0,4),(4,0)],  # crossing with nonzero signed area
        [(0,0),(3,0),(1,0),(1,2),(0,2)],  # adjacent retraced edge
        [(0,0),(4,0),(4,4),(2,0),(0,4)],  # touching nonadjacent edge
        [(0,0),(4,0),(4,0),(0,4)],
        [(0,0),(float("nan"),0),(0,4)],
    ):
        rejected(lambda: validate_polygon(points))
    # Collinear boundary subdivisions and either winding remain supported.
    valid = [(0,0),(2,0),(4,0),(4,4),(0,4)]
    validate_polygon(valid)
    validate_polygon(valid[::-1])
    for mutation in (
        dict(apninger=[(0,10,1,1,.3,"Outside")]),
        dict(apninger=[(0,2,1,1,2,"Above ceiling")]),
        dict(dorer=inp.dorer*2),
        dict(dorer=[(inp.dorer[0][0],8,0,.35,"Venstre")]),
        dict(dorer=[(inp.dorer[0][0],-1,0,.35,"Venstre")]),
        dict(apninger=[(0,.5,1,1,.3,"Inside door")]),
        dict(apninger=[(1,.5,1,1,.3,"A"),(1,.9,1,1,.5,"B")]),
    ):
        bad = copy.deepcopy(room)
        bad["input"].update(mutation)
        rejected(lambda: validate_room(bad))
        rejected(lambda: encode_project([], bad))
        tampered = json.loads(raw)
        tampered["draft"] = bad
        rejected(lambda: decode_project(json.dumps(tampered).encode()))
    # Openings can share a wall when their rectangles do not overlap vertically.
    validate_wall_openings(inp.pts, 3, inp.dorer, [(0,.4,.5,.5,2.3,"Over door")])
    validate_wall_openings(inp.pts, 3, [], [(0,.5,1,1,.1,"A"),(0,1.5,1,1,.1,"B")])

    state = dict(project_rooms=[copy.deepcopy(room)], active_room_id=room["id"],
                 last_valid_editor=copy.deepcopy(room), ed_pnr="138", ed_date=inp.dato,
                 ed_scale="1:50", ed_tnr="A1", do0=6100, n_apninger=1,
                 pris_override={"skruer": 2.5, "gulv_finer": 450})
    with patch.object(project_ui.st, "session_state", state):
        bad_input = ProjectInput(**dict(room["input"], apninger=[(0,10,1,1,.3,"Outside")]))
        rejected(lambda: project_ui.capture_room(bad_input, form, None))
        assert state["last_valid_editor"] == room and state["project_rooms"] == [room]
        project_ui.start_new_room("Kjølerom")
        assert state["project_rooms"] == [room]
        assert state["ed_pnr"] == "138" and state["ed_date"] == inp.dato and state["ed_scale"] == "1:50"
        assert state["pris_override"] == {"skruer": 2.5, "gulv_finer": 450}
        assert state["ed_doors"] == 0 and "do0" not in state and "n_apninger" not in state
        assert "ed_tnr" not in state
    # The actual Tasty project remains valid with shared-wall choices.
    project = decode_project(Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes())
    decode_project(encode_project(project["rooms"], project["draft"], project["active_id"]))
    print("PASS: save/load validation parity, wall/height/count/collision bounds, simple polygons, last-valid recovery, project identity and Tasty compatibility")


def check_ui():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py", default_timeout=30).run()
    assert not app.exception and not app.error
    app.text_input(key="ed_pnr").set_value("138").run()
    app.number_input(key="ed_price_skruer_eske").set_value(2.5).run()
    before = copy.deepcopy(app.session_state["last_valid_editor"])
    app.number_input(key="n_apninger").set_value(1).run()
    app.number_input(key="ap_off0").set_value(10000).run()
    assert app.error and not app.exception
    assert app.session_state["last_valid_editor"] == before
    app.button(key="new_cool_room").click().run()
    assert not app.exception and not app.error
    assert app.text_input(key="ed_pnr").value == "138"
    assert app.number_input(key="ed_price_skruer_eske").value == 2.5
    assert app.number_input(key="n_apninger").value == 0
    assert app.session_state["project_rooms"] == [before]
    decode_project(encode_project(app.session_state["project_rooms"], app.session_state["last_valid_editor"]))
    app.number_input(key="ed_doors").set_value(2).run()
    assert app.error and not app.exception
    assert any("overlapper" in e.value for e in app.error)
    app.number_input(key="do1").set_value(2000).run()
    assert not app.exception and not app.error
    app.button(key="add_finished_room").click().run()
    saved = copy.deepcopy(app.session_state["project_rooms"])
    app.number_input(key="do1").set_value(350).run()
    assert app.error and not app.exception
    assert app.session_state["project_rooms"] == saved
    print("PASS: UI rejects invalid openings/overlapping doors, preserves draft and saved room, retains project 138 and reopens downloads")


if __name__ == "__main__":
    check()
    check_ui()
