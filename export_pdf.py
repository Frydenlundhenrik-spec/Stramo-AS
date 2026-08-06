from __future__ import annotations
import io
from typing import Iterable
import pandas as pd

_FONT: dict[str, str] = {}


def _registrer_font() -> tuple[str, str]:
    """
    Registrerer DejaVu Sans hos reportlab og returnerer (vanlig, fet).

    Helvetica bruker WinAnsi-koding og mangler blant annet ₂, → og tynt
    mellomrom – de ble tegnet som firkanter. DejaVu Sans følger med
    matplotlib, så det kreves ingen ny avhengighet. Faller tilbake på
    Helvetica dersom fonten ikke lar seg registrere.
    """
    if _FONT:
        return _FONT["vanlig"], _FONT["fet"]
    vanlig, fet = "Helvetica", "Helvetica-Bold"
    try:
        from pathlib import Path
        import matplotlib
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.fonts import addMapping
        ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        pdfmetrics.registerFont(TTFont("DejaVuSans", str(ttf / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(ttf / "DejaVuSans-Bold.ttf")))
        addMapping("DejaVuSans", 0, 0, "DejaVuSans")
        addMapping("DejaVuSans", 1, 0, "DejaVuSans-Bold")
        vanlig, fet = "DejaVuSans", "DejaVuSans-Bold"
    except Exception:
        pass
    _FONT.update(vanlig=vanlig, fet=fet)
    return vanlig, fet


def lag_enkel_pdf(tittel: str, linjer: Iterable[str]) -> bytes:
    """Enkel tekstbasert PDF – beholdes for FDV-bruk."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception as exc:
        raise RuntimeError("Installer reportlab: pip install reportlab") from exc
    from branding import LOGO_PATH, logo_finnes, logo_sideforhold
    f_vanlig, f_fet = _registrer_font()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    MARG = 40
    maks_bredde = width - 2*MARG

    def _bryt(tekst: str) -> list[str]:
        """Deler linjen slik at hver del får plass innenfor margene."""
        ut, gjeldende = [], ""
        for ord_ in str(tekst).split(" "):
            kandidat = f"{gjeldende} {ord_}".strip()
            if gjeldende and stringWidth(kandidat, f_vanlig, 9) > maks_bredde:
                ut.append(gjeldende)
                gjeldende = ord_
            else:
                gjeldende = kandidat
        ut.append(gjeldende)
        return ut

    y = height - 50
    if logo_finnes():
        logo_h = 34
        c.drawImage(str(LOGO_PATH), MARG, y - logo_h + 8,
                    width=logo_h * logo_sideforhold(), height=logo_h,
                    preserveAspectRatio=True, mask="auto")
        y -= logo_h + 14
    c.setFont(f_fet, 14)
    c.drawString(MARG, y, tittel)
    y -= 30
    c.setFont(f_vanlig, 9)
    for line in linjer:
        for del_ in _bryt(line):
            if y < 50:
                c.showPage()
                y = height - 50
                c.setFont(f_vanlig, 9)
            c.drawString(MARG, y, del_)
            y -= 14
    c.save()
    return buffer.getvalue()


def lag_tilbuds_pdf(
    prosjekt_info: dict,
    result: dict,
    df_mat: pd.DataFrame,
    plan_png: bytes | None = None,
    snitt_png: bytes | None = None,
) -> bytes:
    """Full tilbuds-PDF: prosjektinfo, nøkkeltall, materialliste og tegninger."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            Image, PageBreak, HRFlowable,
        )
        from reportlab.lib.units import cm
    except Exception as exc:
        raise RuntimeError("Installer reportlab: pip install reportlab") from exc

    BLUE = colors.HexColor("#1a3a5c")
    LIGHT = colors.HexColor("#f0f4f8")
    GRID = colors.HexColor("#c8d8e8")

    F, FB = _registrer_font()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    tabell_bredde = doc.width          # tilgjengelig bredde mellom margene
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18,
                         fontName=FB, textColor=BLUE, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12,
                         fontName=FB, textColor=BLUE, spaceAfter=4, spaceBefore=8)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontSize=8,
                            fontName=F, textColor=colors.grey)
    # Cellestiler som brytes over flere linjer i stedet for å flyte over kanten
    celle = ParagraphStyle("celle", parent=styles["Normal"], fontName=F,
                            fontSize=7, leading=8.4)
    celle_h = ParagraphStyle("celle_h", parent=celle, fontName=FB, fontSize=6.5,
                              leading=7.8, textColor=colors.white, alignment=1)
    story = []

    # ── Header ─────────────────────────────────────────────────────────────────
    from branding import LOGO_PATH, logo_finnes, logo_sideforhold
    if logo_finnes():
        logo_b = 4.2*cm
        story.append(Image(str(LOGO_PATH), width=logo_b,
                           height=logo_b / logo_sideforhold(), hAlign="LEFT"))
        story.append(Spacer(1, 0.25*cm))
    else:
        story.append(Paragraph("STRAMO Kjøleromssystem", h1))
    story.append(Paragraph("TILBUD / MENGDEOVERSIKT", h2))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE))
    story.append(Spacer(1, 0.4*cm))

    # ── Prosjektinfo ───────────────────────────────────────────────────────────
    pi = prosjekt_info
    info_data = [
        ["Prosjektnavn:", pi.get("navn", "–"),  "Dato:",       pi.get("dato", "–")],
        ["Prosjektnr:",  pi.get("pnr", "–"),   "Tegningsnr:", pi.get("tnr", "–")],
        ["Romtype:",     pi.get("rom_type", "–"), "Panel:",    pi.get("panel_label", "–")],
    ]
    info_tbl = Table(info_data, colWidths=[3.3*cm, 5.5*cm, 3.0*cm, 5.2*cm])
    info_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("FONTNAME", (0,0), (-1,-1), F),
        ("FONTNAME", (0,0), (0,-1), FB),
        ("FONTNAME", (2,0), (2,-1), FB),
        ("TEXTCOLOR", (0,0), (0,-1), BLUE),
        ("TEXTCOLOR", (2,0), (2,-1), BLUE),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── Nøkkeltall ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Nøkkeltall", h2))
    ov = result.get("ov", {})
    tot_pris = result.get("tot_pris", 0)
    tot_co2  = result.get("tot_co2", 0)
    A = ov.get("A", 1) or 1
    kr_m2 = tot_pris / A

    def fmt_tall(v):
        """Tusenskille med tynt mellomrom, likt i hele dokumentet."""
        return f"{v:,.0f}".replace(",", " ")

    def fmt_kr(v):
        return f"{fmt_tall(v)} kr"

    m_data = [
        ["Gulvareal", "Volum", "Omkrets", "Totalpris", "CO₂", "Kr/m²"],
        [f"{ov.get('A',0):.2f} m²",
         f"{ov.get('V',0):.2f} m³",
         f"{ov.get('P',0):.2f} m",
         fmt_kr(tot_pris), f"{fmt_tall(tot_co2)} kg", fmt_kr(kr_m2)],
    ]
    m_tbl = Table(m_data, colWidths=[tabell_bredde/6]*6)
    m_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BLUE),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), FB),
        ("BACKGROUND", (0,1), (-1,1), LIGHT),
        ("FONTNAME",   (0,1), (-1,1), FB),
        ("TEXTCOLOR",  (0,1), (-1,1), BLUE),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("GRID",       (0,0), (-1,-1), 0.5, GRID),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
    ]))
    story.append(m_tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── Materialliste ──────────────────────────────────────────────────────────
    story.append(Paragraph("Materialliste", h2))
    if not df_mat.empty:
        want = ["Post", "Type", "Enhet", "Mengde",
                "Enhetspris (kr)", "Totalpris (kr)", "CO₂ (kg)", "NS3420"]
        cols = [c for c in want if c in df_mat.columns]
        df_s = df_mat[cols].copy()
        for col in ["Enhetspris (kr)", "Totalpris (kr)"]:
            if col in df_s.columns:
                df_s[col] = df_s[col].apply(
                    lambda x: f"{float(x):,.0f}".replace(",", " ")
                    if pd.notna(x) else ""
                )

        # Kolonnebreddene angis som vekter og skaleres til sidebredden, slik at
        # tabellen aldri blir bredere enn tekstfeltet uansett antall kolonner.
        # Vektene er målt mot bredeste ord i hver kolonne, så overskrifter og
        # ord som «Hjørnebeslag» ikke brytes midt inni.
        vekt = {"Post": 4.00, "Type": 4.10, "Enhet": 1.00, "Mengde": 1.30,
                "Enhetspris (kr)": 1.65, "Totalpris (kr)": 1.65,
                "CO₂ (kg)": 1.35, "NS3420": 1.95}
        v_sum = sum(vekt[c] for c in cols)
        col_w = [tabell_bredde * vekt[c] / v_sum for c in cols]

        # Tekstkolonner brytes over flere linjer; tallkolonner står som de er
        tekst_kol = {"Post", "Type", "NS3420"}
        mat_data = [[Paragraph(c, celle_h) for c in cols]]
        for rad in df_s.values.tolist():
            mat_data.append([
                Paragraph(str(v), celle) if c in tekst_kol else str(v)
                for c, v in zip(cols, rad)
            ])

        mat_tbl = Table(mat_data, colWidths=col_w, repeatRows=1)
        mat_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  BLUE),
            ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
            ("FONTNAME",      (0,0), (-1,-1), F),
            ("FONTNAME",      (0,0), (-1,0),  FB),
            ("FONTSIZE",      (0,0), (-1,-1), 7),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, LIGHT]),
            ("GRID",          (0,0), (-1,-1), 0.3, GRID),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("LEFTPADDING",   (0,0), (-1,-1), 3),
            ("RIGHTPADDING",  (0,0), (-1,-1), 3),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN",         (2,1), (-1,-1), "RIGHT"),
        ]))
        story.append(mat_tbl)

        # Totalsum-rad. Beløpet er bredere enn Totalpris-kolonnen selv med liten
        # skrift, så ledetekst og sum spenner over hver sin halvdel av tabellen
        # og høyrejusteres – summen havner ved tabellens høyre kant.
        story.append(Spacer(1, 0.2*cm))
        ti = cols.index("Totalpris (kr)") if "Totalpris (kr)" in cols else len(cols) - 1
        ts_row = [""] * len(cols)
        ts_row[0]  = "TOTALSUM:"
        ts_row[ti] = fmt_kr(tot_pris)
        ts_stil = [
            ("SPAN", (ti,0), (-1,0)),
            ("FONTNAME",  (0,0), (-1,-1), FB),
            ("FONTSIZE",  (0,0), (-1,-1), 9),
            ("TEXTCOLOR", (0,0), (-1,-1), BLUE),
            ("ALIGN",     (0,0), (-1,-1), "RIGHT"),
            ("LEFTPADDING",  (0,0), (-1,-1), 3),
            ("RIGHTPADDING", (0,0), (-1,-1), 3),
            ("LINEABOVE", (0,0), (-1,0),  1, BLUE),
        ]
        if ti > 0:
            ts_stil.append(("SPAN", (0,0), (ti-1,0)))
        ts_tbl = Table([ts_row], colWidths=col_w)
        ts_tbl.setStyle(TableStyle(ts_stil))
        story.append(ts_tbl)

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"Alle priser ekskl. mva. · Stramo prisgrunnlag · {pi.get('dato','')}", small
    ))

    # ── Plantegning ────────────────────────────────────────────────────────────
    if plan_png:
        story.append(PageBreak())
        story.append(Paragraph("Plantegning", h2))
        story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE))
        story.append(Spacer(1, 0.3*cm))
        buf = io.BytesIO(plan_png if isinstance(plan_png, bytes) else plan_png.read())
        buf.seek(0)
        story.append(Image(buf, width=16.5*cm, height=10.5*cm, hAlign="CENTER"))

    # ── Snitt ──────────────────────────────────────────────────────────────────
    if snitt_png:
        story.append(PageBreak())
        story.append(Paragraph("Snitt A-A", h2))
        story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE))
        story.append(Spacer(1, 0.3*cm))
        buf2 = io.BytesIO(snitt_png if isinstance(snitt_png, bytes) else snitt_png.read())
        buf2.seek(0)
        story.append(Image(buf2, width=16.5*cm, height=10.5*cm, hAlign="CENTER"))

    doc.build(story)
    return buffer.getvalue()
