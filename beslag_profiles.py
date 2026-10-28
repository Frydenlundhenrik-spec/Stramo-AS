"""Dimensioned profile sketches shared by the screen and PDF order list."""
import io
import re
from functools import lru_cache


def profile_rows(materials):
    rows = []
    for r in materials.itertuples():
        if r.Gruppe != "Beslag" or r.Stk <= 0:
            continue
        if r.Produkt.startswith("Innvendig 50×50"):
            kind, width, name = "inner", 50, "Innvendig vinkel 50 × 50 mm"
        elif r.Produkt.startswith("Utvendig 50×150"):
            kind, width, name = "outer", 150, "Utvendig vinkel 50 × 150 mm"
        elif r.Produkt.startswith("U-kanal"):
            kind, width = "channel", int(re.search(r"U-kanal (\d+)", r.Produkt)[1])
            name = f"U-kanal {width} mm"
        else:
            continue
        rows.append(dict(kind=kind, width=width, name=name, qty=int(r.Stk), lm=float(r.Løpemeter)))
    return rows


@lru_cache(maxsize=24)
def profile_png(kind, width):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(4.8, 2.5))
    ink = "#18374c"
    def line(xs, ys):
        ax.plot(xs, ys, color=ink, linewidth=2)
    def dimension(a, b, label):
        ax.annotate("", b, a, arrowprops=dict(arrowstyle="<->", color=ink, lw=1.2, shrinkA=0, shrinkB=0))
        x, y = (a[0]+b[0])/2, (a[1]+b[1])/2
        ax.text(x, y, f"{label} mm", ha="center", va="center", fontsize=12, fontweight="bold",
                bbox=dict(facecolor="white", edgecolor="none", pad=1))
    def hem(x, y):
        ax.text(x, y, "10 mm", fontsize=10, ha="center", va="center", color=ink,
                bbox=dict(facecolor="white", edgecolor="none", pad=1))
    if kind == "inner":
        # Inside angle: finish on the concave face; returns fold to the back.
        line([10, 0, 0, 50, 50, 51.2, 51.2], [51.2, 51.2, 50, 50, 0, 0, 10])
        dimension((0, 78), (50, 78), 50)
        dimension((82, 0), (82, 50), 50)
        line([42, 42, 50], [50, 42, 42])
        ax.text(34, 34, "90°", fontsize=9)
        hem(5, 61)
        hem(61, -10)
        ax.plot([0,0],[50,81],color=ink,lw=.5)
        ax.plot([50,50],[50,81],color=ink,lw=.5)
        ax.plot([50,85],[0,0],color=ink,lw=.5)
        ax.plot([50,85],[50,50],color=ink,lw=.5)
        ax.annotate("RAL 9010\nlakkert side", (31, 50), (-33, 18), fontsize=10,
                    ha="center", va="center",
                    arrowprops=dict(arrowstyle="->", color=ink, connectionstyle="angle,angleA=0,angleB=90,rad=3"))
        ax.set_xlim(-65, 110)
    else:
        if kind == "channel":
            line([2, 2, 0, 0, width, width, width-2, width-2],
                 [40, 50, 50, 0, 0, 50, 50, 40])
            dimension((-14, 0), (-14, 50), 50)
            line([0, 8, 8], [8, 8, 0])
            ax.text(11, 12, "90°", fontsize=9)
        else:
            line([10, 0, 0, width, width, width-2, width-2],
                 [2, 2, 0, 0, 50, 50, 40])
        dimension((0, -14), (width, -14), width)
        dimension((width+22, 0), (width+22, 50), 50)
        line([width-8, width-8, width], [0, 8, 8])
        ax.text(width-27, 14, "90°", fontsize=9)
        hem(width-10, 61)
        hem(10, 61 if kind == "channel" else 17)
        ax.plot([0,0],[0,-19],color=ink,lw=.5)
        ax.plot([width,width],[0,-19],color=ink,lw=.5)
        ax.plot([width,width+26],[0,0],color=ink,lw=.5)
        ax.plot([width,width+26],[50,50],color=ink,lw=.5)
        ax.text(width+52, 76, "RAL 9010\nlakkert side", fontsize=10,
                ha="center", va="center")
        ax.annotate("", (width, 32), (width+52, 65),
                    arrowprops=dict(arrowstyle="->", color=ink,
                                    connectionstyle="angle,angleA=-90,angleB=0,rad=3"))
        ax.set_xlim(-36, width+88)
    ax.set_ylim(-35, 94)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=.01, right=.99, top=.98, bottom=.02)
    out = io.BytesIO()
    fig.savefig(out, format="png", dpi=200, facecolor="white")
    plt.close(fig)
    return out.getvalue()


def profile_cards(rows, normal, heading, available_width):
    from reportlab.platypus import Table, TableStyle, Image, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    ink = colors.HexColor("#07384c")
    muted = colors.HexColor("#526b78")
    title = ParagraphStyle("profile_title", parent=heading, textColor=ink, fontSize=12, leading=16, spaceAfter=9)
    metric = ParagraphStyle("profile_metric", parent=heading, textColor=ink, fontSize=17, leading=20, spaceAfter=0)
    label = ParagraphStyle("profile_label", parent=normal, textColor=muted, fontSize=7, leading=10, spaceAfter=0)
    detail = ParagraphStyle("profile_detail", parent=normal, textColor=muted, fontSize=8, leading=12, spaceAfter=0)
    cards = []
    for r in rows:
        quantities = Table([
            [Paragraph(v, label) for v in ("ANTALL", "LENGDE PER STK", "SAMLET LENGDE")],
            [Paragraph(v, metric) for v in (f'{r["qty"]} stk', '2500 mm', f'{r["lm"]:g} LM'.replace('.', ','))],
        ], colWidths=[145, 160, available_width-599])
        quantities.setStyle(TableStyle([
            ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
            ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),2),
        ]))
        text = [Paragraph(r["name"], title), quantities, Spacer(1,7),
                Paragraph('0,6 mm stål · RAL 9010', detail)]
        card = Table([[Image(io.BytesIO(profile_png(r["kind"], r["width"])), width=252, height=252*2.5/4.8), text]],
                     colWidths=[270, available_width-270])
        card.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("BOX", (0,0), (-1,-1), .8, colors.HexColor("#526b78")),
            ("BACKGROUND", (1,0), (1,0), colors.HexColor("#f3f7f9")),
            ("LINEBEFORE", (1,0), (1,0), .8, colors.HexColor("#526b78")),
            ("ALIGN", (0,0), (0,0), "CENTER"),
            ("LEFTPADDING",(1,0),(1,0),16),("RIGHTPADDING",(1,0),(1,0),8),
            ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3)]))
        cards.extend([card, Spacer(1,8)])
    return cards
