"""Stramo transmission report, using the same thermal model as the app."""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, LongTable, TableStyle,
    PageBreak, KeepTogether,
)

from branding import LOGO_PATH, logo_finnes, logo_sideforhold
from export_pdf import _registrer_font, draw_pdf_footer
from thermal import calculate_project, thermal_settings, panel_u, SOURCE, LIMIT_SOURCE


SOURCE_URL = "https://balex.eu/en/products/sandwich-panels/pu-w-st-wall-sandwich-panel-polyurethane-core"
INK = colors.HexColor("#07384c")
MUTED = colors.HexColor("#526b78")
PALE = colors.HexColor("#f3f7f9")
RULE = colors.HexColor("#d6e0e5")
LIME = colors.HexColor("#d5e600")


def _number(value, decimals=2):
    if value is None:
        return "–"
    if abs(value) < .5 * 10**(-decimals):
        value = 0
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def thermal_pdf(rooms, selected_ids=None):
    """Return PDF bytes; calculate all rooms before selecting the report scope.

    Neighbour temperatures and shared walls therefore remain available when
    exporting one room. This function does not modify rooms or write files.
    """
    rooms = list(rooms)
    if not rooms:
        raise ValueError("Velg minst ett rom for varmeberegningen.")
    project = calculate_project(rooms)
    by_id = {room["id"]: room for room in rooms}
    ids = set(by_id) if selected_ids is None else ({selected_ids} if isinstance(selected_ids, str) else set(selected_ids))
    if not ids or ids - set(by_id):
        raise ValueError("Rapportvalget må inneholde rom som finnes i prosjektet.")
    results = [result for result in project["rooms"] if result["id"] in ids]
    selected = [by_id[result["id"]] for result in results]
    totals = {key: sum(result[key] for result in results) for key in (
        "known_positive_w", "known_negative_w", "known_net_w", "unknown_area_m2", "unknown_surface_count")}
    complete = all(result["complete"] for result in results)
    project_numbers = ", ".join(dict.fromkeys(room["input"].get("pnr", "") or "Ikke angitt" for room in selected))
    font, bold = _registrer_font()
    styles = {
        "title": ParagraphStyle("thermal-title", fontName=bold, fontSize=23, leading=28, textColor=INK, spaceAfter=10),
        "heading": ParagraphStyle("thermal-heading", fontName=bold, fontSize=12, leading=16, textColor=INK,
                                  spaceBefore=12, spaceAfter=6, keepWithNext=True),
        "body": ParagraphStyle("thermal-body", fontName=font, fontSize=9, leading=13, textColor=INK, spaceAfter=7),
        "note": ParagraphStyle("thermal-note", fontName=font, fontSize=8, leading=11, textColor=MUTED, spaceAfter=6),
        "cell": ParagraphStyle("thermal-cell", fontName=font, fontSize=8, leading=11, textColor=INK),
        "headcell": ParagraphStyle("thermal-headcell", fontName=bold, fontSize=8, leading=11, textColor=colors.white),
    }
    width = A4[0] - 88

    def p(value, style="body"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def table(rows, widths, numeric=(), long=False):
        cells = []
        for row_index, row in enumerate(rows):
            line = []
            for col_index, value in enumerate(row):
                style = styles["headcell" if row_index == 0 else "cell"]
                if col_index in numeric:
                    style = ParagraphStyle("thermal-numeric", parent=style, alignment=2)
                line.append(Paragraph(escape(str(value)).replace("\n", "<br/>"), style))
            cells.append(line)
        cls = LongTable if long else Table
        item = cls(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        item.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), INK),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, PALE]),
            ("LINEBELOW", (0,0), (-1,0), 2, LIME),
            ("LINEBELOW", (0,1), (-1,-1), .35, RULE),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        item.spaceAfter = 8
        return item

    def summary(result, full):
        heading = ("Beregnet transmisjon" if full else
                   "Delsum – kun flater med kjent grunnlag" if result["unknown_surface_count"] else
                   "Foreløpig transmisjon – ubekreftet grunnlag")
        return KeepTogether([
            p(heading, "heading"),
            table([
                ["Inn i rommet / rommene", "Ut av rommet / rommene", "Netto inn"],
                [_number(result["known_positive_w"]) + " W", _number(result["known_negative_w"]) + " W",
                 _number(result["known_net_w"]) + " W"],
            ], [width/3]*3, numeric=(0,1,2)),
        ])

    def status(result, full):
        if full:
            return "Alle oppførte flater har tallgrunnlag for den forenklede transmisjonsmodellen."
        if not result["unknown_surface_count"]:
            return "Alle oppførte flater har tallverdier, men temperaturer og randbetingelser er ikke bekreftet. Resultatet er foreløpig."
        return (f"Ufullstendig beregning: {int(result['unknown_surface_count'])} flateposter / "
                f"{_number(result['unknown_area_m2'])} m² mangler U-verdi eller avklart randbetingelse. "
                "Disse er vist med tankestrek og er ikke regnet som null. Oppgitt wattverdi er en delsum.")

    story = [p("Varmetransmisjon", "title"), p(f"PROSJEKT {project_numbers}", "note"),
             p(" / ".join(result["name"] for result in results)),
             p("Foreløpig beregningsgrunnlag for kjøle- og fryserom. Rapporten bruker rommenes faktiske "
               "mål, åpninger og valgte fellesvegger."),
             p(status(totals, complete)), summary(totals, complete),
             p("Omfang og fortegn", "heading"),
             p("Q = U × A × ΔT. U oppgis i W/(m²K), A i m² og ΔT som temperatur på andre siden minus "
               "romtemperatur. Positiv Q betyr varme inn i rommet; negativ Q betyr varme ut. "
               "Resultatet er stasjonær varmeeffekt i watt, ikke energiforbruk."),
             p("Fellesvegger inngår med motsatt fortegn i de to rommene. Overføringen kansellerer i netto "
               "prosjektsum når begge rom er valgt. Summene inn og ut viser også intern overføring. "
               "Et enkeltrom beholder naborommenes temperaturer fra hele prosjektet."),
             p("Forutsetninger", "heading"),
             p("Standardverdiene er +5 °C i kjølerom, −18 °C i fryserom, +18 °C ved vegger og over tak, "
               "+15 °C under gulv og 60 % relativ fuktighet på varm side. Disse er eksempelverdier inntil "
               "de bekreftes. Tabellen for hvert rom viser verdiene som faktisk er brukt."),
             p("Arealene følger innvendige referanseflater. Tilslutninger og høydeforskjeller ved fellesvegger "
               "kontrolleres mot faktisk geometrisk overlapp; udekkede partier får ukjent grunnlag. "
               "Frysergulvets panelverdi er et forenklet anslag, ikke en lagberegning av gulv og grunn."),
             p("Dokumentgrunnlag", "heading"), p(SOURCE + ". Dokumenterte panelverdier benyttes når de finnes; "
               "manuelle U-verdier fremgår av rommets forutsetninger. Dørdata og eksisterende gulv må dokumenteres separat."),
             Paragraph(f'<link href="{escape(SOURCE_URL)}" color="#07384c"><u>BALEX – PIR STANDARD produkt og dokumentasjon</u></link>', styles["note"]),
             p("Avgrensning", "heading"),
             p("Rapporten omfatter ikke luftutskifting, døråpning, varekjøling, personer, belysning, avriming "
               "eller annet internt varmebidrag. Den fastsetter ikke kjølemaskinstørrelse eller elektrisk "
               "energiforbruk. Kuldebroer, lufttetthet og lokale overflatetemperaturer er ikke detaljberegnet; "
               "rapporten dokumenterer derfor ikke endelig kondenssikkerhet. Ingen samlet U-verdi oppgis.", "note")]

    for result in results:
        room = by_id[result["id"]]
        data = room["input"]
        cfg = thermal_settings(room)
        source = "Manuelt angitt – dokumenteres for leveransen" if cfg["panel_u"] is not None else SOURCE
        source_u = panel_u(room)
        story.extend([PageBreak(), p(result["name"], "title"),
                      p(f"PROSJEKT {data.get('pnr', '')}  |  {data['rom_type']}  |  {data['panel_key']}", "note"),
                      p("Temperaturgrunnlag bekreftet i prosjektet." if cfg["conditions_confirmed"] else
                        "FORUTSETNINGER MÅ BEKREFTES – temperaturer, grunnforhold og relativ fuktighet er foreløpige."),
                      table([
                          ["Forutsetning", "Verdi", "Forutsetning", "Verdi"],
                          ["Inne i rommet", _number(cfg["inside_c"], 1)+" °C", "Omgivelser ved vegg", _number(cfg["ambient_c"], 1)+" °C"],
                          ["Over tak", _number(cfg["ceiling_c"], 1)+" °C", "Under gulv", _number(cfg["ground_c"], 1)+" °C"],
                          ["RF på varm side", _number(cfg["rh_pct"], 1)+" %", "Panel U", _number(source_u, 3)+" W/(m²K)"],
                          ["Dør U", _number(cfg["door_u"], 3)+" W/(m²K)", "Eksisterende gulv U",
                           "Panelanslag" if data["rom_type"] == "Fryserom" else _number(cfg["floor_u"], 3)+" W/(m²K)"],
                      ], [137, 116, 137, width-390]),
                      p("Panelgrunnlag: " + source, "note"),
                      p("Transmisjon per flate", "heading")])
        rows = [["Flate", "Areal\nm²", "U\nW/(m²K)", "Andre siden\n°C", "ΔT\nK", "Q inn\nW"]]
        for surface in result["surfaces"]:
            label = surface["surface"] + ("\nFellesvegg" if surface["shared"] else "")
            rows.append([label, _number(surface["area_m2"]), _number(surface["u"], 3),
                         _number(surface["neighbor_c"], 1), _number(surface["delta_t"], 1), _number(surface["watts"])])
        story.append(table(rows, [159, 58, 67, 74, 52, width-410], numeric=(1,2,3,4,5), long=True))
        story.extend([summary(result, result["complete"]), p(status(result, result["complete"]), "note")])
        notes = list(dict.fromkeys(surface["note"] for surface in result["surfaces"]
                                  if surface["note"] and surface["note"] != SOURCE))
        if notes or result["warnings"]:
            story.append(p("Flategrunnlag og avklaringer", "heading"))
            story.extend(p("• " + note, "note") for note in dict.fromkeys(notes + result["warnings"]))

        comparison = result.get("panel_comparison", [])
        if comparison:
            rows = [["PIR STANDARD", "U\nW/(m²K)", "Største |U × ΔT|\nW/m²", "Paneler netto inn\nW", "Innen grense"]]
            for alternative in comparison:
                meets = alternative["meets_flux_limit"]
                rows.append([f"{alternative['thickness_mm']} mm", _number(alternative["u"], 3),
                             _number(alternative["max_abs_heat_flux_w_m2"]), _number(alternative["known_panel_net_w"]),
                             "–" if meets is None else ("Ja" if meets else "Nei")])
            story.extend([p("Sammenligning av paneltykkelser", "heading"),
                          p("Alternativene gjelder paneler som tilhører dette rommet. Dører, ukjente flater og "
                            "fellesvegger som tilhører naborommet endres ikke. Dette endrer ikke prosjektets bestillingsliste.", "note"),
                          table(rows, [110, 76, 118, 113, width-417], numeric=(1,2,3))])
            limit = cfg["heat_flux_limit"]
            story.append(p(("Ingen prosjektgrense for varmefluks er angitt." if limit is None else
                            f"Valgt prosjektgrense: {_number(limit)} W/m². ") + " " + LIMIT_SOURCE, "note"))

    def chrome(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(44, A4[1]-39, "STRAMO / VARMETRANSMISJON")
        if logo_finnes():
            canvas.drawImage(str(LOGO_PATH), A4[0]-123, A4[1]-52, width=79,
                             height=79/logo_sideforhold(), mask="auto")
        canvas.setFillColor(INK)
        canvas.rect(44, A4[1]-64, width, 3, fill=1, stroke=0)
        canvas.setFillColor(LIME)
        canvas.rect(44, A4[1]-64, 52, 3, fill=1, stroke=0)
        canvas.setFillColor(INK)
        canvas.rect(44, 18, width, 24, fill=1, stroke=0)
        canvas.setFillColor(LIME)
        canvas.rect(44, 18, 3, 24, fill=1, stroke=0)
        draw_pdf_footer(canvas, doc.page, A4[0], left=54, right=54, y=27,
                        text_color=colors.white)
        canvas.restoreState()

    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=44, rightMargin=44,
                                 topMargin=78, bottomMargin=55,
                                 title=f"Stramo varmetransmisjon – prosjekt {project_numbers}", author="Stramo")
    document.build(story, onFirstPage=chrome, onLaterPages=chrome)
    return output.getvalue()
