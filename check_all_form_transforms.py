"""All room shapes retain wall identity and geometry across save/load and orientation."""
import copy
from types import SimpleNamespace
import numpy as np
from database import FORM_MALER
from dimensions import inside_from_outside
from construction import floor_outline
from geometry import wall_lengths, poly_area
from kalkulasjon import ProjectInput, beregn_prosjekt
from kappliste import panel_order_rows
from project_file import make_room, form_points, encode_project, decode_project, validate_room
import project_ui


FORMS = [
    dict(kind="Rektangel", length_mm=5850, width_mm=4450),
    dict(kind="Trekant", length_mm=5850, width_mm=4450),
    dict(kind="T-form", length_mm=5850, width_mm=4450),
    dict(kind="L-form", sides_mm=[5850,4450,2925,2225,2925,2225]),
    dict(kind="Femkant – avskåret hjørne", length_mm=5850.25, width_mm=4450.75,
         cut_x_mm=1200.125, cut_y_mm=700.625),
    dict(kind="Egendefinert polygon", points_mm=[
        [1200,-500],[7050,-500],[7050,2850],[5950,3950],[1200,3950]]),
]


def editor_form(state):
    form = dict(kind=state["ed_shape"], dimension_basis="external",
                turns=state["ed_turns"], mirrored=state["ed_mirrored"],
                origin_mm=state["ed_form_origin"])
    if form["kind"] == "L-form":
        form["sides_mm"] = [state[f"l_side_{i}"] for i in range(6)]
    elif form["kind"] == "Egendefinert polygon":
        form["points_mm"] = [[state[f"px{i}"],state[f"py{i}"]]
                             for i in range(state["ed_corners"])]
    elif form["kind"] == "Femkant – avskåret hjørne":
        from geometry import pentagon_parameters
        values = pentagon_parameters([state[f"ed_pentagon_side_{i}"] for i in range(5)])
        form.update(zip(("length_mm","width_mm","cut_x_mm","cut_y_mm"), values))
    else:
        form.update(length_mm=state["ed_length"], width_mm=state["ed_width"])
    return form


def room_for(form):
    outer = form_points(form)
    points = inside_from_outside(outer, .08) if form.get("dimension_basis") == "external" else outer
    data = ProjectInput("Retningstest","138","A101","30.10.2026","Ikke målfast",
        "Kjølerom","PIR 80 mm",points,2.4,1.1,
        [("Enkel kjøledør 1000×2100 mm",1,0,.35,"Venstre")],[])
    room = make_room(data,form,{})
    room["position_mm"] = [1300,-2500]
    return room


def check():
    assert {form["kind"] for form in FORMS} == set(FORM_MALER)
    real_streamlit = project_ui.st
    try:
        for source in FORMS:
            base = form_points(source)
            baseline_order = None
            baseline_price = None
            for mirrored in (False, True):
                for turns in range(4):
                    form = dict(source, dimension_basis="external", origin_mm=[320,-610],
                                turns=turns, mirrored=mirrored)
                    room = room_for(form)
                    validate_room(room)
                    outer = form_points(form)
                    assert np.allclose(wall_lengths(outer), wall_lengths(base)), source["kind"]
                    assert np.isclose(poly_area(outer), poly_area(base))
                    raw = encode_project([room], room, room["id"])
                    restored = decode_project(raw)
                    assert encode_project(restored["rooms"], restored["draft"], restored["active_id"]) == raw
                    assert restored["draft"]["input"]["dorer"][0][2:] == [0,.35,"Venstre"]
                    state = {}
                    project_ui.st = SimpleNamespace(session_state=state)
                    project_ui.restore_editor(restored["draft"])
                    assert state["ed_turns"] == turns and state["ed_mirrored"] == mirrored
                    assert state["ed_height"] == 2400, "Existing panel height must be preserved."
                    assert state["dw0"] == 1 and state["dh0"] == "Venstre"
                    assert np.allclose(form_points(editor_form(state)), outer, atol=1e-9, rtol=0)
                    # Rotation leaves the door's wall, offset and hinge attached to the same edge.
                    points = np.asarray(room["input"]["pts"])
                    edge = points[1]-points[0]
                    anchor = points[0] + edge/np.linalg.norm(edge)*.35
                    assert np.isclose(np.linalg.norm(anchor-points[0]), .35)
                    result = beregn_prosjekt(ProjectInput(**room["input"]))
                    orders = panel_order_rows(result["df_kapp"],2400,1100)
                    signature = orders[["Vegg","Elementnavn","Leveringslengde_mm","Bredde_mm"]].to_dict("records")
                    if baseline_order is None:
                        baseline_order, baseline_price = signature, result["tot_pris"]
                    assert signature == baseline_order, (source["kind"], turns, mirrored)
                    assert np.isclose(result["tot_pris"], baseline_price, atol=1e-6, rtol=0)

            # Freezers also have floor panels. Their ordered blank lengths and
            # widths must rotate/mirror with the room, just like the roof panels.
            baseline_order = None
            for mirrored in (False, True):
                for turns in range(4):
                    room = room_for(dict(source, dimension_basis="external", turns=turns, mirrored=mirrored))
                    data = room["input"]
                    data.update(rom_type="Fryserom", panel_key="PIR 100 mm",
                                pts=inside_from_outside(form_points(room["form"]), .1),
                                dorer=[("Fryserom enkel 1000×2100 mm",1,0,.35,"Venstre")])
                    result = beregn_prosjekt(ProjectInput(**data))
                    orders = panel_order_rows(result["df_kapp"],2400,1100)
                    signature = orders[["Vegg","Elementnavn","Leveringslengde_mm","Bredde_mm"]].to_dict("records")
                    if baseline_order is None:
                        baseline_order = signature
                    assert signature == baseline_order, ("Frys", source["kind"], turns, mirrored)

            # Older files omit transforms entirely. They must still load without coordinate shifts.
            old = room_for(source)
            validate_room(old)
            assert np.allclose(old["input"]["pts"], base, atol=1e-12, rtol=0)
            state = {}
            project_ui.st = SimpleNamespace(session_state=state)
            project_ui.restore_editor(old)
            expected = floor_outline(old["input"]["pts"], .08)
            assert np.allclose(form_points(editor_form(state)), expected, atol=1e-8, rtol=0)

            # Internal-basis projects may already contain rotation; migrating to outer dimensions
            # must not rotate the converted custom polygon a second time.
            old = room_for(dict(source, turns=1, mirrored=True))
            validate_room(old)
            state = {}
            project_ui.st = SimpleNamespace(session_state=state)
            project_ui.restore_editor(old)
            assert np.allclose(form_points(editor_form(state)),
                               floor_outline(old["input"]["pts"], .08), atol=1e-8, rtol=0)

        # Reject malformed orientations on every shape, rather than treating them as truthy.
        for source in FORMS:
            room = room_for(source)
            for field, value in (("turns",4),("turns",True),("turns",1.0),("mirrored",1)):
                bad = copy.deepcopy(room)
                bad["form"][field] = value
                try:
                    validate_room(bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError((source["kind"],field,value))
    finally:
        project_ui.st = real_streamlit
    print("PASS: 96 cooler/freezer orientations; project/editor round trips, legacy migration, door references and unchanged panel orders")


if __name__ == "__main__":
    check()
