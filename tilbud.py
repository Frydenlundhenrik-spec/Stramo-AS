"""Customer offer for the same rooms and materials as the order module."""
import base64
import io
from datetime import date, datetime, timedelta
from functools import partial
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from branding import LOGO_PATH, logo_finnes, logo_sideforhold
from cutlist_pdf import cutting_pdf, material_tables, project_materials
from drawing_3d import static3d
from export_pdf import _registrer_font, draw_pdf_footer
from kalkulasjon import beregn_prosjekt
from montasje import figur_som_pdf, tegn_3d_modell, tegn_plantegning, tegn_snitt
from oversikt import rom_tall, tall
from project_file import OFFER_ATTACHMENTS, world_input
from project_ui import assembly_plan
from purchase_summary import panel_cutting_plan

INK = colors.HexColor("#07384c")
MUTED = colors.HexColor("#526b78")
LIME = colors.HexColor("#d5e600")


def offer_cover(rooms, title, customer, issued, price, note, attachments):
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=42, rightMargin=42,
                            topMargin=44, bottomMargin=44, title="Tilbud", author="Stramo AS")
    font, bold = _registrer_font()

    def paragraph(text, size=11, face=font, color=INK, after=8):
        style = ParagraphStyle("offer", fontName=face, fontSize=size, leading=size*1.4,
                               textColor=color, spaceAfter=after)
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    date_text = issued.strftime("%d.%m.%Y")
    expiry = (issued + timedelta(days=30)).strftime("%d.%m.%Y")
    references = ", ".join(dict.fromkeys(r["input"]["pnr"] for r in rooms if r["input"]["pnr"]))
    story = []
    if logo_finnes():
        story.append(Image(str(LOGO_PATH), width=86, height=86/logo_sideforhold(), hAlign="LEFT"))
    story.extend([Spacer(1, 21), paragraph("TILBUD", 11, bold, MUTED),
                  paragraph(title, 25, bold), paragraph(f"Tilbudsdato {date_text}" +
                    (f"   |   Prosjekt {references}" if references else ""), 10, font, MUTED)])
    if customer:
        story.append(paragraph(f"Til {customer}", 13, bold))
    story.extend([Spacer(1, 10), paragraph(
        "Stramo AS tilbyr levering og montasje av rommene nedenfor. Materiallisten og tegningene i dette dokumentet beskriver leveransen.")])
    for room in rooms:
        inp = world_input(room)
        story.append(paragraph(f"{inp.navn or inp.rom_type} · {inp.rom_type} · {inp.panel_key}", 10, after=3))
    story.append(Spacer(1, 15))
    price_box = Table([[paragraph("Samlet tilbudspris eks. mva.", 11, bold, colors.white, 0)],
                       [paragraph(tall(price, 2) + " kr", 23, bold, colors.white, 0)]], colWidths=[doc.width])
    price_box.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),INK), ("LINEBEFORE",(0,0),(0,-1),3,LIME),
        ("LEFTPADDING",(0,0),(-1,-1),14), ("TOPPADDING",(0,0),(-1,0),10),
        ("BOTTOMPADDING",(0,-1),(-1,-1),11)]))
    story.extend([price_box, Spacer(1, 13), paragraph("Montasje i Østfold er inkludert i tilbudsprisen."),
                  paragraph(f"Tilbudet er gyldig i 30 dager fra tilbudsdato, til og med {expiry}.")])
    if note.strip():
        story.extend([paragraph("Presiseringer", 12, bold), paragraph(note.strip(), 10)])
    story.extend([Spacer(1, 13), paragraph("Vedlegg", 12, bold),
                  paragraph(" · ".join(["Materialliste med beslagstegninger", *attachments]), 10),
                  Spacer(1, 15), paragraph("Med vennlig hilsen", 10, after=0), paragraph("Stramo AS", 11, bold)])
    def footer(c, document):
        draw_pdf_footer(c, document.page, A4[0], left=28, right=28, y=16, show_page_number=False)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def offer_pdf(rooms, title, customer, issued, price, note="", attachments=OFFER_ATTACHMENTS):
    """Produce one bookmarked A4 document; order costs never enter an attachment."""
    if not rooms:
        raise ValueError("Velg minst ett rom til tilbudet.")
    writer = PdfWriter()
    drawing_pages = set()

    def add_pdf(data, heading):
        writer.append(io.BytesIO(data), outline_item=heading)

    def add_drawing(fig, heading):
        try:
            drawing_pages.add(len(writer.pages))
            add_pdf(figur_som_pdf(fig, heading, show_page_number=False), heading)
        finally:
            plt.close(fig)

    add_pdf(offer_cover(rooms, title, customer, issued, price, note, attachments), "Tilbudsbrev")
    add_pdf(cutting_pdf(rooms, "tilbud", include_cutting_plan="Kappfordeling" in attachments),
            "Materialliste og beslagstegninger")
    if "Plantegning" in attachments and len(rooms) > 1:
        add_drawing(assembly_plan(rooms), "Plantegning – alle valgte rom")
    for room in rooms:
        inp = world_input(room)
        result = beregn_prosjekt(inp, pris_override=room.get("prices", {}))
        name = inp.navn or inp.rom_type
        if "Plantegning" in attachments:
            background = room.get("background")
            image = io.BytesIO(base64.b64decode(background["data"])) if background else None
            add_drawing(tegn_plantegning(inp, result, image, inp.apninger), f"Plantegning – {name}")
        if "Snittegning" in attachments:
            wall = next((i for i in range(len(inp.pts)) if i not in inp.excluded_walls), None)
            if wall is None:
                raise ValueError(f"{name} har ingen egen vegg å vise snitt av. Fjern Snittegning eller velg et annet rom.")
            add_drawing(tegn_snitt(inp, result, wall, "A–A", inp.apninger),
                        f"Snitt A–A · Vegg {wall+1} – {name}")
        if "3D-bilde" in attachments:
            model = tegn_3d_modell(inp, apninger=inp.apninger)
            add_drawing(static3d(model, name), f"3D-bilde – {name}")

    # Continuous numbering in each attachment's existing footer.
    font, _ = _registrer_font()
    total = len(writer.pages)
    for i, page in enumerate(writer.pages):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        overlay = io.BytesIO()
        c = canvas.Canvas(overlay, pagesize=(width,height))
        drawing = i in drawing_pages
        y = 35.35 if drawing else 16
        right = 38.35 if drawing else 28
        c.setFillColor(colors.white if drawing else MUTED)
        c.setFont(font, 8)
        c.drawRightString(width-right, y, f"Side {i+1} av {total}")
        c.save()
        page.merge_page(PdfReader(overlay).pages[0])
    writer.add_metadata({"/Title": f"Tilbud – {title}", "/Author": "Stramo AS"})
    output = io.BytesIO()
    writer.write(output)
    writer.close()
    return output.getvalue()


def tilbud_ui(rooms, scope):
    st.subheader("Tilbud")
    state = st.session_state
    draft = state.setdefault("offer_drafts", {}).setdefault(scope, {})
    key = f"offer_{scope}_"
    base = round(sum(rom_tall(r)["pris"] for r in rooms), 2)
    pnr = rooms[0]["input"]["pnr"]
    title = st.text_input("Tilbudstittel", draft.get("title", "Levering og montasje av " +
                          ("kjøle- og fryserom" if len({r["input"]["rom_type"] for r in rooms}) > 1
                           else rooms[0]["input"]["rom_type"].lower())), max_chars=300, key=key+"title")
    c1, c2 = st.columns(2)
    customer = c1.text_input("Kunde", draft.get("customer",""), max_chars=200, key=key+"customer")
    today = datetime.now(ZoneInfo("Europe/Oslo")).date()
    issued = c2.date_input("Tilbudsdato", date.fromisoformat(draft["date"]) if "date" in draft else today,
                           format="DD.MM.YYYY", key=key+"date")
    # An untouched suggestion follows the current calculation across room edits.
    if key+"price" in state and draft.get("price") is None and state.get(key+"base") != base:
        state[key+"price"] = base
    state[key+"base"] = base
    price = st.number_input("Samlet tilbudspris eks. mva. (kr)", min_value=0., max_value=1e12,
                            value=float(draft["price"] if draft.get("price") is not None else base),
                            step=100., format="%.2f", key=key+"price")
    st.caption("Utgangspunktet er de prissatte postene i kalkulasjonen. Sett totalen slik at den dekker montasje i Østfold og eventuelle uprisede varer.")
    note = st.text_area("Presiseringer til kunden (valgfritt)", draft.get("note",""),
                        max_chars=1500, key=key+"note")
    attachments = st.multiselect("Vedlegg til tilbudet", OFFER_ATTACHMENTS,
                                 default=draft.get("attachments", OFFER_ATTACHMENTS), key=key+"attachments")
    draft.update(title=title, customer=customer, date=issued.isoformat(), price=price if price != base else None,
                 note=note, attachments=list(attachments))
    st.caption("Materialliste og beslagstegninger følger alltid med. Tilbudet er gyldig i 30 dager, til og med " +
               (issued + timedelta(days=30)).strftime("%d.%m.%Y") + ".")
    with st.expander("Materialer i tilbudet"):
        for group, table in material_tables(project_materials(rooms)):
            st.write(group)
            st.dataframe(table.rename(columns={"Produkt":group, "Stk":"Antall", "Høyde_mm":"Lengde (mm)",
                "Bredde_mm":"Bredde (mm)", "Tykkelse_mm":"Tykkelse (mm)", "Areal_m2":"Areal (m²)"}),
                hide_index=True, width="stretch")
        if "Kappfordeling" in attachments:
            st.write("Kappfordeling på hele elementer")
            st.dataframe(panel_cutting_plan(rooms), hide_index=True, width="stretch")
    missing = [r for r in rooms if len(r["excluded_walls"]) == len(r["input"]["pts"])]
    if "Snittegning" in attachments and missing:
        st.warning("Kan ikke tegne snitt av " + ", ".join(world_input(r).navn for r in missing) +
                   " fordi alle veggene er utelatt. Fjern Snittegning eller velg et annet rom.")
        return
    st.download_button("Last ned samlet tilbud (PDF)",
        partial(offer_pdf, rooms, title.strip() or "Tilbud", customer, issued, price, note, tuple(attachments)),
        f"Tilbud-{pnr or 'Stramo'}-{issued.isoformat()}.pdf", "application/pdf",
        key=key+"pdf", on_click="ignore", icon=":material/picture_as_pdf:")
