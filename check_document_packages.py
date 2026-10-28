"""Tasty integration checks for selectable PDFs, saved settings and navigation."""
import copy
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader
from document_package import (DEFAULTS, DOCUMENTS, available_documents, build_package,
                              package_fingerprint, validate_document_settings)
from project_file import decode_project, encode_project


def check():
    source = Path(os.environ.get("STRAMO_TEST_PROJECT", "Tasty-Rom4-og-fryserom-med-dorer.json"))
    project = decode_project(source.read_bytes())
    rooms = project["rooms"]
    original = copy.deepcopy(rooms)
    offer = dict(project_name="Tasty Fredrikstad – funksjonstest", customer="TEST – ikke et kundetilbud",
                 contact="", reference="TEST-138", date="2026-10-28", valid_until="",
                 amount=123456.78, description="Kontrolleksempel. Pris og kundedata er testverdier.", terms="",
                 room_ids=[r["id"] for r in rooms], parts=list(DEFAULTS["Tilbud"]))
    production = dict(project_name="Tasty Fredrikstad – funksjonstest", date="2026-10-28",
                      description="Kontroll av samlet produksjonsunderlag.", room_ids=offer["room_ids"],
                      parts=list(DEFAULTS["Produksjon"]))
    out = Path("output/pdf");out.mkdir(parents=True, exist_ok=True)
    for mode, settings in (("Tilbud", offer), ("Produksjon", production)):
        data = build_package(mode,rooms,settings)
        (out/f"Tasty-{mode}-TEST.pdf").write_bytes(data)
        pdf = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert f"Side {len(pdf.pages)} av {len(pdf.pages)}" in text
        assert all(r["input"]["navn"] in text for r in rooms)
        assert len(pdf.outline) > len(settings["parts"])
        if mode == "Tilbud":
            assert "123 456,78 kr" in text
            assert "Bestillingsliste" not in text and "Enhetspris" not in text and "Kappfordeling" not in text
            assert "Vektgrunnlag" not in text
        else:
            assert "Bestillingsliste elementer" in text and "Kappfordeling" in text
            assert "Enhetspris" not in text and "123 456" not in text
        print(f"PASS {mode}: {len(pdf.pages)} pages, {len(data)} bytes", flush=True)
        # Contents page references match real outline destinations, including a
        # multi-page production cover and mixed page sizes.
        for bookmark in pdf.outline[1:]:
            if isinstance(bookmark, dict):
                index = pdf.get_destination_page_number(bookmark)
                assert index >= 1 and index < len(pdf.pages)
                assert bookmark.title in text
                first = pdf.get_destination_page_number(pdf.outline[1])
                contents_text = " ".join(" ".join(p.extract_text() for p in pdf.pages[:first]).split())
                assert f"{bookmark.title} {index+1}" in contents_text
    assert rooms == original
    for room in rooms:
        only = dict(production, room_ids=[room["id"]], parts=["panel_order"])
        pdf = PdfReader(io.BytesIO(build_package("Produksjon",[room],only)))
        assert len(pdf.pages) == 2
        assert "Bestillingsliste elementer" in pdf.pages[-1].extract_text()
        other = next(r for r in rooms if r["id"] != room["id"])
        assert other["input"]["navn"] not in "\n".join(p.extract_text() for p in pdf.pages)
    for wrong in (dict(offer,amount=None), dict(offer,amount=float("nan")), dict(offer,parts=["panel_order"]),
                  dict(offer,parts=[]), dict(offer,customer="")):
        try:
            build_package("Tilbud",rooms,wrong)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid offer must be rejected")
    settings = {"Tilbud":offer,"Produksjon":production}
    restored = decode_project(encode_project(rooms,project["draft"],project.get("active_id"),documents=settings))
    assert restored["documents"] == settings
    assert "documents" not in decode_project(encode_project(rooms,project["draft"],project.get("active_id")))
    assert package_fingerprint("Tilbud",rooms,offer) != package_fingerprint("Tilbud",rooms,dict(offer,amount=1))
    print("PASS selection, exact price, validation, unchanged geometry and project-file compatibility",flush=True)
    long_cover = PdfReader(io.BytesIO(build_package("Produksjon",rooms,dict(production,
        description="Arbeidsbeskrivelse med flere sider.\n"*80,parts=["panel_order"]))))
    first_attachment = long_cover.get_destination_page_number(long_cover.outline[1])
    assert first_attachment > 1
    toc = " ".join(" ".join(p.extract_text() for p in long_cover.pages[:first_attachment]).split())
    assert f"Bestillingsliste elementer {first_attachment+1}" in toc

    # Exercise optional renderers as well; their errors must not be hidden in a combined package.
    extras = [key for key in available_documents("Produksjon",rooms) if key not in production["parts"]]
    for key in extras:
        data = build_package("Produksjon", rooms, dict(production,parts=[key]))
        assert len(PdfReader(io.BytesIO(data)).pages) >= 2
        if key == "fdv":
            (out/"Tasty-FDV-samlet-TEST.pdf").write_bytes(data)
        print(f"PASS optional appendix: {key}",flush=True)

    import streamlit as st
    from streamlit.testing.v1 import AppTest
    with patch("login.require_login",return_value=None):
        app = AppTest.from_file("app.py",default_timeout=120)
        app.session_state["pending_project"] = project
        app.session_state["ed_module"] = "Tilbud"
        app.run()
        app.radio(key="ed_module").set_value("Tilbud").run()
        assert not app.exception,[e.message for e in app.exception]
        assert {"Tilbud","Produksjon"}.issubset(app.radio(key="ed_module").options)
        assert "Elementer" not in app.radio(key="ed_module").options
        assert app.button(key="doc_offer_build").disabled
        app.text_input(key="doc_offer_customer").set_value("Testkunde")
        app.number_input(key="doc_offer_amount").set_value(125000.0)
        app.run()
        app.button(key="doc_offer_build").click().run()
        assert not app.exception,[e.message for e in app.exception]
        assert not app.error,[e.value for e in app.error]
        assert any("Last ned tilbud PDF" == b.label for b in app.get("download_button"))
        app.text_input(key="doc_offer_customer").set_value("Endret kunde").run()
        assert not any("Last ned tilbud PDF" == b.label for b in app.get("download_button"))
        app.radio(key="ed_module").set_value("Produksjon").run()
        assert not app.exception,[e.message for e in app.exception]
        selected = rooms[0]
        app.multiselect(key="doc_production_rooms").set_value([selected["id"]]).run()
        for checkbox in app.checkbox:
            if checkbox.key.startswith("doc_production_"):
                checkbox.set_value(checkbox.key == "doc_production_panel_order")
        app.run()
        app.button(key="doc_production_build").click().run()
        assert not app.exception,[e.message for e in app.exception]
        assert not app.error,[e.value for e in app.error]
        assert len(PdfReader(io.BytesIO(app.session_state["doc_production_generated"][1])).pages) == 2
        app.radio(key="ed_module").set_value("Kalkulasjon").run()
        assert not any(b.label == "Last ned materialliste PDF" for b in app.get("download_button"))
        app.radio(key="ed_module").set_value("Tilbud").run()
        assert app.text_input(key="doc_offer_customer").value == "Endret kunde"
        assert app.number_input(key="doc_offer_amount").value == 125000.0
        app.radio(key="ed_module").set_value("Produksjon").run()
        assert app.multiselect(key="doc_production_rooms").value == [selected["id"]]
        assert app.session_state["document_settings"]["Produksjon"]["parts"] == ["panel_order"]
        assert not app.exception,[e.message for e in app.exception]
        assert len(app.session_state["project_rooms"]) == 2
        app.session_state["pending_project"] = restored
        app.run()
        app.radio(key="ed_module").set_value("Tilbud").run()
        assert app.text_input(key="doc_offer_customer").value == offer["customer"]
        assert app.number_input(key="doc_offer_amount").value == offer["amount"]
        assert not any("Last ned tilbud PDF" == b.label for b in app.get("download_button"))
        app.session_state["pending_project"] = project
        app.run()
        app.radio(key="ed_module").set_value("Tilbud").run()
        assert app.text_input(key="doc_offer_customer").value == ""
        assert app.number_input(key="doc_offer_amount").value is None
    print("PASS real app navigation, generation, single room, preserved selections and stale-file removal",flush=True)


if __name__ == "__main__":
    check()
