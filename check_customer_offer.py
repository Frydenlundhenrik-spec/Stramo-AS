"""Exercise Tasty's customer offer through the menu and its actual download callback."""
import io
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest
from project_file import decode_project, world_input, OFFER_ATTACHMENTS
from kalkulasjon import beregn_prosjekt
from cutlist_pdf import project_materials, offer_materials

p = decode_project(Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes())
rooms = p["rooms"]
downloads = {}
real_download = st.download_button

def capture(label, data, *args, **kwargs):
    if label == "Last ned samlet tilbud (PDF)":
        downloads["offer"] = data
    if kwargs.get("key") == "download_project":
        downloads["project"] = data
    return real_download(label, data, *args, **kwargs)

def run_ok(app):
    app.run()
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]

with patch.object(st, "download_button", side_effect=capture):
    app = AppTest.from_file("app.py", default_timeout=90).run()
    app.session_state["pending_project"] = deepcopy(p)
    run_ok(app)
    app.radio(key="ed_module").set_value("Tilbud")
    run_ok(app)
    prefix = "offer_Alle rom_"
    expected = round(sum(beregn_prosjekt(world_input(r), pris_override=r["prices"])["tot_pris"] for r in rooms),2)
    assert app.number_input(key=prefix+"price").value == expected
    material_prices = [r["prices"] for r in decode_project(downloads["project"])["rooms"]]
    app.number_input(key=prefix+"price").set_value(425000.)
    app.text_input(key=prefix+"title").set_value("Kjøle- og fryserom til Tasty Fredrikstad")
    app.text_input(key=prefix+"customer").set_value("Tasty Fredrikstad")
    app.date_input(key=prefix+"date").set_value(date(2026,11,5))
    app.text_area(key=prefix+"note").set_value("Eksempeltilbud til gjennomgang.")
    run_ok(app)
    stored = decode_project(downloads["project"])
    assert stored["offers"]["Alle rom"]["price"] == 425000.
    assert stored["offers"]["Alle rom"]["customer"] == "Tasty Fredrikstad"
    assert [r["prices"] for r in stored["rooms"]] == material_prices
    pdf_bytes = downloads["offer"]()
    pdf = PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() for page in pdf.pages]
    text = " ".join(" ".join(pages).split())
    assert text.count("425 000,00 kr") == 1 and "05.12.2026" in pages[0]
    assert "Takk for forespørselen." in pages[0] and "Med vennlig hilsen" in pages[0]
    assert len(pdf.pages[0].images) == 1  # Logo only; the room/model block has been removed.
    assert "Dette inngår i tilbudet" not in text
    assert "Tilbudsdato 05.11.2026 | Prosjekt 138 | Tasty Fredrikstad Kjølerom" in " ".join(pages[0].split())
    assert "Materialliste · Plantegning · Snittegning" in " ".join(pages[0].split())
    for term in ["Montasje i Østfold er inkludert", "eks. mva.", "gyldig i 30 dager", "PROSJEKT 138",
                 "Plantegning – alle valgte rom", "Materialliste", "Leveringslengde", "Mengde"]:
        assert term in text, term
    for removed in ("Beslagsliste", "Kappfordeling", "3D-bilde", "Bestilling kg", "Vektgrunnlag", "Totalpris"):
        assert removed not in text, removed
    assert "enhetspris" not in text.lower() and "stykkpris" not in text.lower() and "pris mangler" not in text.lower()
    for item in project_materials(rooms).Produkt:
        assert " ".join(item.split()) in text, item
    # A single table must carry the order quantities, including globally rounded accessories.
    shown = offer_materials(rooms)
    assert list(shown.columns) == ["Post", "Type", "Leveringslengde (mm)", "Bredde (mm)",
                                   "Tykkelse (mm)", "Antall (stk)", "Enhet", "Mengde"]
    assert any(d.value.equals(shown) for d in app.dataframe)
    ordered = project_materials(rooms)
    for item in ordered.itertuples():
        match = shown[shown.Type.eq(item.Produkt)]
        if item.Gruppe == "Elementer":
            match = match[match["Leveringslengde (mm)"].eq(item.Høyde_mm)]
            assert match.iloc[0]["Antall (stk)"] == item.Stk
            assert match.iloc[0].Mengde == item.Areal_m2
        else:
            assert match.iloc[0].Mengde == item.Stk
    expected_outline = ["Tilbudsbrev", "Materialliste", "Plantegning – alle valgte rom"]
    expected_outline += ["Plantegning – " + world_input(r).navn for r in rooms]
    expected_outline += ["Snitt A–A · Vegg 1 – " + world_input(r).navn for r in rooms]
    assert [item.title for item in pdf.outline] == expected_outline
    for r in rooms:
        name = world_input(r).navn
        for label in ("Plantegning – ", "Snitt A–A · Vegg 1 – "):
            assert label + name in text
    for n, page in enumerate(pages, 1):
        assert page.count("Side ") == 1 and f"Side {n} av {len(pages)}" in page
    app.selectbox(key="offer_room_choice").set_value(rooms[1]["id"])
    run_ok(app)
    key = "offer_"+rooms[1]["id"]+"_"
    assert app.number_input(key=key+"price").value != 425000
    app.multiselect(key=key+"attachments").set_value([])
    run_ok(app)
    single_pdf = PdfReader(io.BytesIO(downloads["offer"]()))
    assert len(single_pdf.pages[0].images) == 1
    assert [item.title for item in single_pdf.outline] == ["Tilbudsbrev", "Materialliste"]
    single = " ".join(page.extract_text() for page in single_pdf.pages)
    assert "Fryseromsdør" in single and "Kjøleromsdør" not in single
    assert "Snitt A–A" not in single and "3D-bilde –" not in single
    # Offers saved by the old version reopen with only the allowed attachments.
    legacy = deepcopy(stored)
    legacy["offers"]["Alle rom"]["attachments"] = ["3D-bilde", "Snittegning", "Kappfordeling", "Plantegning"]
    loaded = decode_project(json.dumps(legacy).encode())
    assert loaded["offers"]["Alle rom"]["attachments"] == list(OFFER_ATTACHMENTS)
    app.session_state["pending_project"] = loaded
    run_ok(app)
    app.radio(key="ed_module").set_value("Tilbud")
    run_ok(app)
    assert app.number_input(key=prefix+"price").value == 425000
    assert app.multiselect(key=prefix+"attachments").options == list(OFFER_ATTACHMENTS)
    assert app.multiselect(key=prefix+"attachments").value == list(OFFER_ATTACHMENTS)
    app.session_state["pending_project"] = p  # An older project must open cleanly.
    run_ok(app)
    app.radio(key="ed_module").set_value("Tilbud")
    run_ok(app)
    assert app.number_input(key=prefix+"price").value == expected and not app.text_input(key=prefix+"customer").value
print("PASS: scoped offers, unchanged order quantities, one total price, cover, attachment order, legacy save/reopen")
