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

from branding import LOGO_PATH, logo_finnes, logo_sideforhold, project_name
from cutlist_pdf import cutting_pdf, offer_materials
from export_pdf import _registrer_font, draw_pdf_footer
from kalkulasjon import beregn_prosjekt
from montasje import figur_som_pdf, tegn_plantegning, tegn_snitt
from oversikt import rom_tall, tall
from project_file import OFFER_ATTACHMENTS, world_input
from project_ui import assembly_plan

INK = colors.HexColor("#07384c")
MUTED = colors.HexColor("#526b78")
LIME = colors.HexColor("#d5e600")


def offer_cover(rooms, title, customer, issued, price, note, attachments):
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=48, rightMargin=48,
                            topMargin=41, bottomMargin=60, title="Tilbud", author="Stramo AS")
    font, bold = _registrer_font()

    def paragraph(text, size=11, face=font, color=INK, after=8):
        style = ParagraphStyle("offer", fontName=face, fontSize=size, leading=size*1.4,
                               textColor=color, spaceAfter=after)
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    date_text = issued.strftime("%d.%m.%Y")
    expiry = (issued + timedelta(days=30)).strftime("%d.%m.%Y")
    references = ", ".join(dict.fromkeys(r["input"]["pnr"] for r in rooms if r["input"]["pnr"]))
    names = ", ".join(dict.fromkeys(project_name(r["input"]["navn"]) or r["input"]["rom_type"] for r in rooms))
    width = doc.width - 12  # The document frame adds 6 pt of padding on either side.
    logo = Image(str(LOGO_PATH), width=77, height=77/logo_sideforhold()) if logo_finnes() else ""
    masthead = Table([[paragraph("TILBUD", 11, bold, MUTED, 0), logo]], colWidths=[width-77, 77])
    masthead.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                                 ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0)]))
    gaps = [Spacer(1, 24) for _ in range(4)]
    story = [masthead, Spacer(1, 51), paragraph(title, 25, bold, after=11),
             paragraph(f"Tilbudsdato {date_text}" +
                       (f"   |   Prosjekt {references}" if references else "") +
                       f"   |   {names}", 10, font, MUTED),
             gaps[0]]
    if customer:
        story.append(paragraph(f"Kunde: {customer}", 13, bold))
    story.append(paragraph("Takk for forespørselen. Vi har gleden av å tilby levering og montasje som beskrevet i dette tilbudet."))
    if note.strip():
        story.extend([Spacer(1, 12), paragraph(note.strip())])
    story.append(gaps[1])
    price_box = Table([[paragraph("Tilbudspris eks. mva.", 11, bold, colors.white, 0)],
                       [paragraph(tall(price, 2) + " kr", 23, bold, colors.white, 0)]], colWidths=[width], splitByRow=0)
    price_box.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),INK), ("LINEBEFORE",(0,0),(0,-1),3,LIME),
        ("LEFTPADDING",(0,0),(-1,-1),14), ("TOPPADDING",(0,0),(-1,0),10),
        ("BOTTOMPADDING",(0,-1),(-1,-1),11)]))
    story.extend([price_box, gaps[2], paragraph("Montasje i Østfold er inkludert i tilbudsprisen.", after=3),
                  paragraph(f"Tilbudet er gyldig i 30 dager fra tilbudsdato, til og med {expiry}.", after=10)])
    story.extend([gaps[3], paragraph("Vedlegg", 12, bold),
                  paragraph(" · ".join(["Materialliste", *attachments]), 10)])
    # Share spare page space between the sections; long notes can still flow onto another page.
    content_height = sum(item.wrap(width, doc.height)[1] + item.getSpaceBefore() + item.getSpaceAfter()
                         for item in story if item not in gaps)
    gap_height = max(24, (doc.height - 16 - content_height) / len(gaps))
    for gap in gaps:
        gap.height = gap_height
    # Move the price nearer its terms without moving the surrounding sections.
    price_shift = min(48, gap_height - 12)
    gaps[1].height += price_shift
    gaps[2].height -= price_shift
    # Lower the price and terms together while leaving the attachments in place.
    block_shift = min(64, gap_height - 16)
    gaps[1].height += block_shift
    gaps[3].height -= block_shift
    def footer(c, document):
        draw_pdf_footer(c, document.page, A4[0], left=28, right=28, y=16, show_page_number=False)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def offer_pdf(rooms, title, customer, issued, price, note="", attachments=OFFER_ATTACHMENTS):
    """Produce one bookmarked A4 document; order costs never enter an attachment."""
    if not rooms:
        raise ValueError("Velg minst ett rom til tilbudet.")
    attachments = tuple(a for a in OFFER_ATTACHMENTS if a in attachments)
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

    inputs = [world_input(room) for room in rooms]
    add_pdf(offer_cover(rooms, title, customer, issued, price, note, attachments), "Tilbudsbrev")
    add_pdf(cutting_pdf(rooms, "tilbud"), "Materialliste")
    if "Plantegning" in attachments and len(rooms) > 1:
        add_drawing(assembly_plan(rooms), "Plantegning – alle valgte rom")
    # All plans precede all sections, including when several rooms are selected.
    for attachment in attachments:
        for room, inp in zip(rooms, inputs):
            result = beregn_prosjekt(inp, pris_override=room.get("prices", {}))
            name = inp.navn or inp.rom_type
            if attachment == "Plantegning":
                background = room.get("background")
                image = io.BytesIO(base64.b64decode(background["data"])) if background else None
                add_drawing(tegn_plantegning(inp, result, image, inp.apninger), f"Plantegning – {name}")
            elif attachment == "Snittegning":
                wall = next((i for i in range(len(inp.pts)) if i not in inp.excluded_walls), None)
                if wall is None:
                    raise ValueError(f"{name} har ingen egen vegg å vise snitt av. Fjern Snittegning eller velg et annet rom.")
                add_drawing(tegn_snitt(inp, result, wall, "A–A", inp.apninger),
                            f"Snitt A–A · Vegg {wall+1} – {name}")

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
    price = st.number_input("Tilbudspris eks. mva. (kr)", min_value=0., max_value=1e12,
                            value=float(draft["price"] if draft.get("price") is not None else base),
                            step=100., format="%.2f", key=key+"price")
    st.caption("Utgangspunktet er de prissatte postene i kalkulasjonen. Sett totalen slik at den dekker montasje i Østfold og eventuelle uprisede varer.")
    note = st.text_area("Presiseringer til kunden (valgfritt)", draft.get("note",""),
                        max_chars=1500, key=key+"note")
    selected = state.get(key+"attachments", draft.get("attachments", OFFER_ATTACHMENTS))
    selected = [a for a in OFFER_ATTACHMENTS if a in selected]
    if key+"attachments" in state and state[key+"attachments"] != selected:
        state[key+"attachments"] = selected
    attachments = st.multiselect("Vedlegg til tilbudet", OFFER_ATTACHMENTS,
                                 default=selected, key=key+"attachments")
    draft.update(title=title, customer=customer, date=issued.isoformat(), price=price if price != base else None,
                 note=note, attachments=list(attachments))
    st.caption("Materiallisten følger alltid med, deretter valgte plantegninger og snittegninger. Tilbudet er gyldig i 30 dager, til og med " +
               (issued + timedelta(days=30)).strftime("%d.%m.%Y") + ".")
    with st.expander("Materialer i tilbudet"):
        st.dataframe(offer_materials(rooms), hide_index=True, width="stretch")
    missing = [r for r in rooms if len(r["excluded_walls"]) == len(r["input"]["pts"])]
    if "Snittegning" in attachments and missing:
        st.warning("Kan ikke tegne snitt av " + ", ".join(world_input(r).navn for r in missing) +
                   " fordi alle veggene er utelatt. Fjern Snittegning eller velg et annet rom.")
        return
    st.download_button("Last ned samlet tilbud (PDF)",
        partial(offer_pdf, rooms, title.strip() or "Tilbud", customer, issued, price, note, tuple(attachments)),
        f"Tilbud-{pnr or 'Stramo'}-{issued.isoformat()}.pdf", "application/pdf",
        key=key+"pdf", on_click="ignore", icon=":material/picture_as_pdf:")
