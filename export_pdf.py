from __future__ import annotations
import io
from typing import Iterable
import pandas as pd


def lag_enkel_pdf(tittel: str, linjer: Iterable[str]) -> bytes:
    """Enkel tekstbasert PDF – beholdes for FDV-bruk."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError("Installer reportlab: pip install reportlab") from exc
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, tittel)
    y -= 30
    c.setFont("Helvetica", 9)
    for line in linjer:
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 9)
        c.drawString(40, y, str(line)[:110])
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

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18,
                         textColor=BLUE, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12,
                         textColor=BLUE, spaceAfter=4, spaceBefore=8)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontSize=8,
                            textColor=colors.grey)
    story = []

    # ── Header ─────────────────────────────────────────────────────────────────
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
    info_tbl = Table(info_data, colWidths=[3.5*cm, 6*cm, 3*cm, 4*cm])
    info_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
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

    def fmt_kr(v):
        return f"{v:,.0f} kr".replace(",", " ")

    m_data = [
        ["Gulvareal", "Volum", "Omkrets", "Totalpris", "CO₂", "Kr/m²"],
        [f"{ov.get('A',0):.2f} m²",
         f"{ov.get('V',0):.2f} m³",
         f"{ov.get('P',0):.2f} m",
         fmt_kr(tot_pris), f"{tot_co2:,.0f} kg", fmt_kr(kr_m2)],
    ]
    m_tbl = Table(m_data, colWidths=[2.7*cm]*6)
    m_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BLUE),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND", (0,1), (-1,1), LIGHT),
        ("FONTNAME",   (0,1), (-1,1), "Helvetica-Bold"),
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

        base_w = [3.5*cm, 3.2*cm, 1.1*cm, 1.4*cm, 2.3*cm, 2.3*cm, 1.8*cm]
        if "NS3420" in cols:
            base_w.append(2*cm)
        col_w = base_w[:len(cols)]

        mat_data = [cols] + df_s.values.tolist()
        mat_tbl = Table(mat_data, colWidths=col_w, repeatRows=1)
        mat_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  BLUE),
            ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
            ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 7.5),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, LIGHT]),
            ("GRID",          (0,0), (-1,-1), 0.3, GRID),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("ALIGN",         (3,0), (-1,-1), "RIGHT"),
        ]))
        story.append(mat_tbl)

        # Totalsum-rad
        story.append(Spacer(1, 0.2*cm))
        ts_data = [[""] * (len(cols)-2) + ["TOTALSUM:", fmt_kr(tot_pris)]]
        ts_tbl = Table(ts_data, colWidths=col_w)
        ts_tbl.setStyle(TableStyle([
            ("FONTNAME",  (0,0), (-1,-1), "Helvetica-Bold"),
            ("FONTSIZE",  (0,0), (-1,-1), 9),
            ("TEXTCOLOR", (0,0), (-1,-1), BLUE),
            ("ALIGN",     (0,0), (-1,-1), "RIGHT"),
            ("LINEABOVE", (0,0), (-1,0),  1, BLUE),
        ]))
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
