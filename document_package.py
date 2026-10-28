"""Selectable customer and production PDFs using the app's existing calculations."""
from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from xml.sax.saxutils import escape

# Order here is also the order of attachments in the downloaded PDF.
DOCUMENTS = {
    "assembly": ("Plantegning – sammenstilling", "Valgte rom med plassering og fellesvegger."),
    "plans": ("Plantegning per rom", "Utvendige mål, vegger og dørplasseringer."),
    "sections": ("Snittegninger", "Høyder og oppbygging av gulv, vegger og tak."),
    "roofs": ("Takplaner", "Plassering og mål på takelementene."),
    "customer_elements": ("Elementoversikt til kunden", "Ferdige mål, antall og m². Uten innkjøpspriser og råelementer."),
    "walls": ("Veggoppriss", "Alle vegger som skal leveres, med dører og åpninger."),
    "production_drawings": ("Produksjonstegninger – tilpassede elementer", "Detaljtegninger av elementer som skal kappes eller bearbeides."),
    "cuts": ("Elementkappliste", "Ferdige deler med referanser til tegningene."),
    "allocation": ("Kappfordeling", "Hvilke deler som kappes fra hvert hele element."),
    "panel_order": ("Bestillingsliste elementer", "Hele elementer, leveringsmål, antall og m²."),
    "accessory_order": ("Bestillingsliste – beslag, dører og tilbehør", "Bestillingsmengder og egen linje per dør med slagretning."),
    "profiles": ("Beslagstegninger", "Målsatte profiler og bestillingsantall."),
    "floor_plan": ("Gulvplateplan", "Plassering av gulvplatene inne i fryserommet."),
    "floor_cuts": ("Gulvplatekappliste", "Ferdige platemål og antall hele gulvplater."),
    "calculation": ("Kalkulasjon – internt underlag", "Materialmengder og registrerte priser. Kun i produksjonspakken."),
    "fdv": ("FDV-pakke", "Tilgjengelig produktdokumentasjon og oversikt over manglende vedlegg."),
}
OFFER_PARTS = ("assembly", "plans", "sections", "roofs", "customer_elements", "floor_plan", "fdv")
PRODUCTION_PARTS = tuple(key for key in DOCUMENTS if key != "customer_elements")
DEFAULTS = {
    "Tilbud": ("assembly", "plans", "customer_elements"),
    "Produksjon": ("assembly", "plans", "sections", "cuts", "allocation", "panel_order", "accessory_order", "profiles", "floor_plan", "floor_cuts"),
}
TEXT_FIELDS = ("project_name", "customer", "contact", "reference", "description", "terms", "date", "valid_until")


def validate_document_settings(settings):
    """Keep optional project-file settings bounded, finite and backward compatible."""
    if not isinstance(settings, dict) or set(settings) - {"Tilbud", "Produksjon"}:
        raise ValueError("Ugyldige dokumentvalg i prosjektfilen.")
    for mode, values in settings.items():
        if not isinstance(values, dict) or set(values) - set(TEXT_FIELDS) - {"amount", "room_ids", "parts"}:
            raise ValueError("Ugyldige dokumentfelt i prosjektfilen.")
        for key in TEXT_FIELDS:
            if key in values and (not isinstance(values[key], str) or len(values[key]) > 8000):
                raise ValueError("Dokumentteksten er ugyldig eller for lang.")
        amount = values.get("amount")
        if amount is not None and (type(amount) not in (float, int) or not math.isfinite(amount) or not 0 <= amount <= 1e9):
            raise ValueError("Tilbudssummen er ugyldig.")
        for field in ("parts", "room_ids"):
            if field in values and (not isinstance(values[field], list) or len(values[field]) > 31
                                   or any(not isinstance(v, str) or len(v) > 200 for v in values[field])):
                raise ValueError("Ugyldige dokument- eller romvalg.")
        allowed = OFFER_PARTS if mode == "Tilbud" else PRODUCTION_PARTS
        if set(values.get("parts", [])) - set(allowed):
            raise ValueError("Et dokumentvalg passer ikke til valgt pakke.")
    if len(json.dumps(settings, ensure_ascii=False)) > 64000:
        raise ValueError("Dokumentinnstillingene er for store.")
    return settings


def available_documents(mode, rooms):
    keys = OFFER_PARTS if mode == "Tilbud" else PRODUCTION_PARTS
    return [key for key in keys
            if (key != "assembly" or len(rooms) > 1)
            and (key not in ("floor_plan", "floor_cuts") or any(r["input"]["rom_type"] == "Fryserom" for r in rooms))]


def package_fingerprint(mode, rooms, settings):
    data = json.dumps([mode, rooms, settings], sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _figure_pdf(fig, title):
    import matplotlib.pyplot as plt
    from montasje import figur_som_pdf
    try:
        return figur_som_pdf(fig, title)
    finally:
        plt.close(fig)


def _attachments(rooms, parts, project_name):
    from project_file import world_input
    from kalkulasjon import beregn_prosjekt
    from cutlist_pdf import cutting_pdf
    from montasje import (tegn_plantegning, tegn_snitt, tegn_taktegning,
                          tegn_veggoppstaltt, tegn_produksjonsfigurer, figurer_som_samlet_pdf)
    import matplotlib.pyplot as plt
    inputs = [(room, world_input(room)) for room in rooms]
    results = {room["id"]: beregn_prosjekt(inp, pris_override=room.get("prices", {})) for room, inp in inputs}
    list_kinds = {"customer_elements": "tilbud_elementer", "cuts": "elementkapp", "allocation": "kappfordeling",
                  "panel_order": "bestilling_elementer", "accessory_order": "bestilling_tilbehor",
                  "profiles": "beslagprofiler", "floor_cuts": "finer", "calculation": "kalkulasjon"}
    for key in parts:
        title = DOCUMENTS[key][0]
        if key in list_kinds:
            yield title, cutting_pdf(rooms, list_kinds[key])
        elif key == "assembly":
            from project_ui import assembly_plan
            yield title, _figure_pdf(assembly_plan(rooms), "Plantegning")
        elif key == "fdv":
            from build_standard_fdv import lag_standard_fdv_pdf
            if any(not inp.panel_key.startswith("PIR") for _, inp in inputs):
                raise ValueError("FDV-pakken gjelder BALEX PIR STANDARD. Fjern FDV-valget for andre paneltyper.")
            yield title, lag_standard_fdv_pdf(project_name, inputs[0][1].pnr, tuple(inp.navn for _, inp in inputs))
        else:
            for room, inp in inputs:
                result = results[room["id"]]
                name = f"{title} – {inp.navn}"
                retained = [i for i in range(len(inp.pts)) if i not in inp.excluded_walls]
                if key == "plans":
                    yield name, _figure_pdf(tegn_plantegning(inp, result, apninger=inp.apninger), title)
                elif key == "sections":
                    if not retained:
                        raise ValueError(f"{inp.navn}: Ingen vegger igjen for snittegning.")
                    yield name, _figure_pdf(tegn_snitt(inp, result, retained[0], apninger=inp.apninger), title)
                elif key == "roofs":
                    yield name, _figure_pdf(tegn_taktegning(inp, result), title)
                elif key == "walls":
                    for wall in retained:
                        yield f"{inp.navn} – Vegg {wall+1}", _figure_pdf(tegn_veggoppstaltt(inp, result, wall, apninger=inp.apninger), "Veggoppriss")
                elif key == "production_drawings":
                    figs = tegn_produksjonsfigurer(inp, result, bare_tilpassede=True)
                    try:
                        if figs:
                            yield name, figurer_som_samlet_pdf(figs)
                        else:
                            from export_pdf import lag_enkel_pdf
                            yield name, lag_enkel_pdf(name, ["Ingen tilpassede elementer i dette rommet."])
                    finally:
                        for fig in figs:
                            plt.close(fig)
                elif key == "floor_plan" and inp.rom_type == "Fryserom":
                    from finishing import plywood_plan
                    from database import PANEL_DB
                    form = room["form"]
                    fig = plywood_plan(inp.pts, form.get("plywood_width_mm",1500), form.get("plywood_length_mm",3000), PANEL_DB[inp.panel_key]["t"]/1000)
                    yield name, _figure_pdf(fig, title)


def _cover(mode, rooms, settings, contents):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
    from branding import LOGO_PATH, logo_finnes, logo_sideforhold
    from export_pdf import _registrer_font
    from database import PANEL_DB
    from construction import floor_outline
    from geometry import poly_area
    from project_file import world_input
    font, bold = _registrer_font()
    ink, grey = colors.HexColor("#07384c"), colors.HexColor("#526b78")
    body = ParagraphStyle("body", fontName=font, fontSize=10, leading=15, textColor=ink, spaceAfter=8)
    heading = ParagraphStyle("heading", parent=body, fontName=bold, fontSize=13, leading=18, spaceBefore=14)
    def p(value, style=body):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=32, bottomMargin=40)
    story = []
    if logo_finnes():
        story.append(Image(str(LOGO_PATH), width=90, height=90/logo_sideforhold(), hAlign="RIGHT"))
    story.append(p("Tilbud" if mode == "Tilbud" else "Produksjonsunderlag", ParagraphStyle("title", parent=heading, fontSize=26, leading=32)))
    story.append(p(settings["project_name"], heading))
    numbers = ", ".join(dict.fromkeys(r["input"].get("pnr", "") for r in rooms))
    display_date = date.fromisoformat(settings["date"]).strftime("%d.%m.%Y")
    story.append(p(f"Prosjekt {numbers} · {display_date}"))
    if mode == "Tilbud":
        for label, key in (("Til", "customer"), ("Kontaktperson", "contact"), ("Tilbudsreferanse", "reference"), ("Gyldig til", "valid_until")):
            if settings.get(key):
                story.append(p(f"{label}: {settings[key]}"))
    if settings.get("description"):
        story.extend([p("Leveransen" if mode == "Tilbud" else "Arbeidsbeskrivelse", heading), p(settings["description"])])
    story.append(p("Rom i leveransen", heading))
    for room in rooms:
        inp = world_input(room)
        area = poly_area(floor_outline(inp.pts, PANEL_DB[inp.panel_key]["t"]/1000))
        area_text = f"{area:.2f}".replace(".", ",")
        story.append(p(f"{inp.navn} · {inp.panel_key} · avtrykk {area_text} m²"))
    if mode == "Tilbud":
        amount = Decimal(str(settings["amount"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        amount_text = f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " kr"
        white = ParagraphStyle("price", parent=heading, textColor=colors.white, spaceBefore=0, spaceAfter=0)
        total = Table([[p("Tilbudssum eks. mva", white), p(amount_text, white)]], colWidths=[doc.width*.57, doc.width*.43])
        total.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),ink),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                                  ("LINEBEFORE",(0,0),(0,0),3,colors.HexColor("#d5e600")),
                                  ("TOPPADDING",(0,0),(-1,-1),13),("BOTTOMPADDING",(0,0),(-1,-1),13)]))
        story.extend([Spacer(1,12), total])
        if settings.get("terms"):
            story.extend([p("Levering og vilkår", heading), p(settings["terms"])])
    if contents:
        rows = [[p("Vedlegg", heading), p("PDF-side", heading)]]
        rows += [[p(title), p(str(page))] for title, page in contents]
        toc = Table(rows, colWidths=[doc.width-80,80], repeatRows=1, hAlign="LEFT")
        toc.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),1,grey),
                                ("LEFTPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
        story.extend([Spacer(1,12), toc])
    doc.build(story)
    return out.getvalue()


def build_package(mode, rooms, settings):
    """All-or-nothing PDF build. Selected sections never silently disappear."""
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.generic import ArrayObject, FloatObject, NameObject
    from reportlab.pdfgen import canvas
    from export_pdf import draw_pdf_footer
    if mode not in DEFAULTS or not rooms:
        raise ValueError("Velg minst ett rom.")
    validate_document_settings({mode:settings})
    if not settings.get("project_name", "").strip() or not settings.get("date"):
        raise ValueError("Fyll inn prosjektnavn og dato.")
    if mode == "Tilbud" and (not settings.get("customer", "").strip() or settings.get("amount") is None):
        raise ValueError("Fyll inn kunde og tilbudssum eks. mva.")
    parts = settings.get("parts", [])
    if not parts:
        raise ValueError("Velg minst ett vedlegg.")
    if set(parts) - set(available_documents(mode, rooms)):
        raise ValueError("Et vedlegg er ikke tilgjengelig for de valgte rommene. Velg innhold på nytt.")
    # Stable ordering even after toggling checkboxes in a different sequence.
    parts = [key for key in DOCUMENTS if key in parts]
    sections = [(title, PdfReader(io.BytesIO(data))) for title, data in _attachments(rooms, parts, settings["project_name"])]
    cover_count = 1
    for _ in range(5):
        page, contents = cover_count + 1, []
        for title, pdf in sections:
            contents.append((title, page))
            page += len(pdf.pages)
        cover = PdfReader(io.BytesIO(_cover(mode, rooms, settings, contents)))
        if len(cover.pages) == cover_count:
            break
        cover_count = len(cover.pages)
    else:
        raise ValueError("Innholdsfortegnelsen kunne ikke ferdigstilles.")
    writer = PdfWriter()
    writer.append(cover, outline_item=mode, import_outline=False)
    preserved_pages = set()
    for title, pdf in sections:
        if title == DOCUMENTS["fdv"][0]:
            preserved_pages.update(range(len(writer.pages),len(writer.pages)+len(pdf.pages)))
        writer.append(pdf, outline_item=title, import_outline=False)
    # Our drawings/lists reserve 32 points. Supplier pages in FDV have no
    # guaranteed margin; add space rather than painting over their content.
    for index, page in enumerate(writer.pages, 1):
        footer = io.BytesIO()
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        if index-1 in preserved_pages:
            page.add_transformation(Transformation().translate(0,30))
            for ref in page.get("/Annots", []):
                annotation = ref.get_object()
                for field in ("/Rect", "/QuadPoints"):
                    if field in annotation:
                        annotation[NameObject(field)] = ArrayObject([
                            FloatObject(float(value)+(30 if i%2 else 0))
                            for i,value in enumerate(annotation[field])])
            height += 30
            page.mediabox.upper_right = (width,height)
            page.cropbox.upper_right = (width,height)
        c = canvas.Canvas(footer, pagesize=(width,height))
        c.setFillColorRGB(1,1,1)
        c.rect(0,0,width,30,stroke=0,fill=1)
        draw_pdf_footer(c,index,width,total_pages=len(writer.pages),y=16)
        c.save()
        page.merge_page(PdfReader(footer).pages[0])
    writer.add_metadata({"/Title": f"{mode} – {settings['project_name']}", "/Author": "Stramo AS"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def document_package_ui(mode, saved_rooms, current):
    import copy
    import streamlit as st
    all_rooms = [current if r["id"] == current["id"] else r for r in saved_rooms]
    if current["id"] not in {r["id"] for r in all_rooms}:
        all_rooms.append(current)
    settings_store = st.session_state.setdefault("document_settings", {})
    settings = copy.deepcopy(settings_store.get(mode, {}))
    prefix = "doc_offer_" if mode == "Tilbud" else "doc_production_"
    st.subheader(mode)
    st.caption("Velg rom og vedlegg til kundens tilbud." if mode == "Tilbud" else "Velg rom og underlag for bestilling og montasje.")
    labels = {r["id"]:r["input"]["navn"] or r["input"]["rom_type"] for r in all_rooms}
    default_ids = [r["id"] for r in saved_rooms] or [current["id"]]
    stored_ids = [rid for rid in settings.get("room_ids",default_ids) if rid in labels]
    ids = st.multiselect("Rom som skal med", list(labels), default=stored_ids, format_func=labels.get, key=prefix+"rooms")
    rooms = [r for r in all_rooms if r["id"] in ids]
    settings["room_ids"] = ids
    col1,col2 = st.columns([2,1])
    settings["project_name"] = col1.text_input("Prosjektnavn", value=settings.get("project_name", "Prosjekt " + current["input"].get("pnr", "")), max_chars=200, key=prefix+"project")
    try:
        saved_date = date.fromisoformat(settings.get("date", ""))
    except ValueError:
        saved_date = date.today()
    settings["date"] = col2.date_input("Dato",value=saved_date,format="DD.MM.YYYY",key=prefix+"date").isoformat()
    if mode == "Tilbud":
        left,right = st.columns(2)
        settings["customer"] = left.text_input("Kunde", value=settings.get("customer", ""), max_chars=200, key=prefix+"customer")
        settings["contact"] = right.text_input("Kontaktperson", value=settings.get("contact", ""), max_chars=200, key=prefix+"contact")
        settings["reference"] = left.text_input("Tilbudsreferanse", value=settings.get("reference", ""), max_chars=200, key=prefix+"reference")
        settings["valid_until"] = right.text_input("Gyldig til", value=settings.get("valid_until", ""), placeholder="Dato eller antall dager", max_chars=100, key=prefix+"valid")
        saved_amount = settings.get("amount")
        settings["amount"] = st.number_input("Tilbudssum eks. mva (kr)", value=float(saved_amount) if saved_amount is not None else None, min_value=0.0, max_value=1e9, step=1000.0, format="%.2f", key=prefix+"amount", help="Kundens avtalte tilbudspris. Kalkulasjonen brukes som underlag, ikke som automatisk tilbudssum.")
    settings["description"] = st.text_area("Leveransebeskrivelse" if mode == "Tilbud" else "Arbeidsbeskrivelse", value=settings.get("description", ""), max_chars=8000, key=prefix+"description")
    if mode == "Tilbud":
        settings["terms"] = st.text_area("Levering, forbehold og vilkår", value=settings.get("terms", ""), max_chars=8000, key=prefix+"terms")
    st.markdown("**Vedlegg i PDF-en**")
    choices = available_documents(mode,rooms)
    prior = settings.get("parts",list(DEFAULTS[mode]))
    parts = []
    columns = st.columns(2)
    for index, key in enumerate(choices):
        label, hint = DOCUMENTS[key]
        if columns[index%2].checkbox(label, value=key in prior, key=prefix+key, help=hint):
            parts.append(key)
    settings["parts"] = parts
    settings_store[mode] = settings
    if mode == "Produksjon" and rooms:
        with st.expander("Se elementer og bestillingsmengder"):
            from purchase_summary import element_cutlist
            from cutlist_pdf import project_materials, material_tables
            preview = st.selectbox("Vis liste", ["Elementkappliste", "Bestillingslister"], key=prefix+"preview")
            if preview == "Elementkappliste":
                st.dataframe(element_cutlist(rooms).drop(columns="Vekt (kg)"), hide_index=True, width="stretch")
            else:
                for title, frame in material_tables(project_materials(rooms)):
                    st.markdown(f"**{title}**")
                    st.dataframe(frame.rename(columns={"Stk":"Antall (stk)","Høyde_mm":"Høyde / lengde (mm)",
                        "Bredde_mm":"Bredde (mm)","Tykkelse_mm":"Tykkelse (mm)","Areal_m2":"Areal (m²)"}),hide_index=True, width="stretch")
    stamp = package_fingerprint(mode,rooms,settings)
    cache_key = prefix+"generated"
    cached = st.session_state.get(cache_key)
    if cached and cached[0] != stamp:
        del st.session_state[cache_key]
        cached = None
        st.info("Innholdet er endret. Lag PDF-en på nytt for å få med de siste endringene.")
    ready = bool(rooms and parts and settings["project_name"].strip())
    if mode == "Tilbud":
        ready = ready and bool(settings["customer"].strip()) and settings["amount"] is not None
    if not rooms:
        st.info("Velg minst ett rom.")
    elif not parts:
        st.info("Velg minst ett vedlegg.")
    elif not ready:
        st.caption("Fyll inn prosjektnavn, kunde og tilbudssum før du lager tilbudet." if mode == "Tilbud" else "Fyll inn prosjektnavn før du lager PDF-en.")
    if st.button("Lag tilbuds-PDF" if mode == "Tilbud" else "Lag produksjons-PDF", type="primary", disabled=not ready, key=prefix+"build", icon=":material/picture_as_pdf:"):
        # Remove the old file first: a failed build must not offer a previous PDF.
        st.session_state.pop(cache_key,None)
        cached = None
        try:
            with st.spinner("Samler valgte dokumenter …"):
                data = build_package(mode,rooms,settings)
            cached = (stamp,data)
            st.session_state[cache_key] = cached
        except Exception as exc:
            st.error(f"PDF-en ble ikke laget: {exc}")
    if cached:
        from pypdf import PdfReader
        count = len(PdfReader(io.BytesIO(cached[1])).pages)
        st.success(f"Én samlet PDF er klar – {count} sider, {len(rooms)} rom.")
        name = "".join(c if c.isalnum() or c in " -_" else "-" for c in settings["project_name"]).strip()
        st.download_button("Last ned tilbud PDF" if mode == "Tilbud" else "Last ned produksjon PDF", cached[1], f"{name}-{mode.lower()}.pdf", "application/pdf", key=prefix+"download", on_click="ignore")
