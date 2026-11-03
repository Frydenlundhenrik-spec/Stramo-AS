"""Dimensioned profile sketches shared by the screen and PDF order list."""
import io
import math
import re
from functools import lru_cache
from finishing import GLASS_FRONT_TRIM, format_trim_angle


def profile_rows(materials):
    rows = []
    for r in materials.itertuples():
        if r.Gruppe != "Beslag" or r.Stk <= 0:
            continue
        details = {}
        side = getattr(r, "Profil_side", None)
        if side in ("inner", "outer"):
            angle = float(r.Profilvinkel_grad)
            concave_finish = (side == "inner") != bool(r.Profil_inntrukket)
            kind = "skew_inner" if concave_finish else "skew_outer"
            width = 100
            name = ("Innvendig" if side == "inner" else "Utvendig") + " skråbeslag 100 × 100 mm"
            if r.Profil_inntrukket:
                name += " – inntrukket hjørne"
            details = dict(angle=angle, angles=f"Ferdig vinkel {format_trim_angle(angle)} · "
                           f"Knekk fra flat plate {format_trim_angle(180 - angle)}",
                           corners=r.Profil_hjorner)
            if angle == 0:
                details["angles"] += " · Profil må avklares med verkstedet"
        elif r.Produkt.startswith("Innvendig 50×50"):
            kind, width, name = "inner", 50, "Innvendig vinkel 50 × 50 mm"
        elif r.Produkt.startswith("Utvendig 50×150"):
            kind, width, name = "outer", 150, "Utvendig vinkel 50 × 150 mm"
        elif r.Produkt.startswith("Gulvvinkel fryserom 30×50"):
            kind, width, name = "floor", 30, "Gulvvinkel fryserom 30 × 50 mm"
        elif r.Produkt.startswith(GLASS_FRONT_TRIM):
            kind, width, name = "opening", 80, GLASS_FRONT_TRIM.replace("×", " × ")
        elif r.Produkt.startswith("U-kanal"):
            kind, width = "channel", int(re.search(r"U-kanal (\d+)", r.Produkt)[1])
            name = f"U-kanal {width} mm"
        else:
            continue
        rows.append(dict(kind=kind, width=width, name=name, qty=int(r.Stk), lm=float(r.Løpemeter), **details))
    return rows


def _skew_profile(ax, kind, width, angle, ink):
    """Section through a vertical corner; arms are symmetric about the angle bisector."""
    from matplotlib.patches import Arc
    if angle == 0:
        # Two coincident wings would be misleading as a production drawing.
        for y, label, size in ((.76, "Ferdig vinkel 0°", 14), (.58, "Knekk fra flat plate 180°", 12),
                               (.39, f"{width} × {width} mm · 10 mm omknekk", 11),
                               (.22, "Profil må avklares med verkstedet", 10)):
            ax.text(.5, y, label, transform=ax.transAxes, ha="center", va="center",
                    fontsize=size, color=ink)
        return
    half = math.radians(angle / 2)
    sine, cosine = math.sin(half), math.cos(half)
    concave_finish = kind == "skew_inner"
    for side in (-1, 1):
        # Direction of the flange and its normal towards the convex face.
        ux, uy = side * sine, cosine
        nx, ny = side * cosine, -sine
        tip = (width * ux, width * uy)
        back = 1.2 if concave_finish else -1.2
        fold = (tip[0] + back * nx, tip[1] + back * ny)
        end = (fold[0] - 10 * ux, fold[1] - 10 * uy)
        ax.plot([0, tip[0], fold[0], end[0]], [0, tip[1], fold[1], end[1]],
                color=ink, lw=2)
        # Dimension both flanges from their joint to their outer ends.
        start = (23 * nx, 23 * ny)
        stop = (tip[0] + start[0], tip[1] + start[1])
        for x, y in ((0, 0), tip):
            ax.plot([x, x + 27 * nx], [y, y + 27 * ny], color=ink, lw=.5)
        ax.annotate("", stop, start, arrowprops=dict(arrowstyle="<->", color=ink, lw=1.2,
                                                     shrinkA=0, shrinkB=0))
        ax.text((start[0]+stop[0])/2, (start[1]+stop[1])/2, f"{width} mm",
                rotation=side * (90 - angle / 2), rotation_mode="anchor",
                fontsize=10, fontweight="bold", ha="center", va="center",
                bbox=dict(facecolor="white", edgecolor="none", pad=1))
        ax.text(tip[0] + side * 5, tip[1] + 10, "10 mm", fontsize=9, color=ink,
                ha="right" if side < 0 else "left", va="bottom")
    ax.add_patch(Arc((0, 0), 34, 34, theta1=90-angle/2, theta2=90+angle/2,
                     color=ink, lw=1))
    if angle >= 65:
        ax.text(0, 28, format_trim_angle(angle), ha="center", va="center",
                fontsize=10, fontweight="bold", color=ink)
    else:
        # A narrow wedge cannot contain a legible angle label.
        ax.text(.02, .94, format_trim_angle(angle), transform=ax.transAxes,
                ha="left", va="top", fontsize=10, fontweight="bold", color=ink)
    # Call out the coated face from the gap between the arms or from below the joint.
    if concave_finish:
        target = (.60 * width * sine, .60 * width * cosine)
        label = (.55 * width * sine, max(width * cosine + 30, 49))
    else:
        target = (0, 0)
        label = (0, -44)
    ax.annotate("RAL 9010 · lakkert side", target, label, fontsize=9,
                ha="center", va="center",
                arrowprops=dict(arrowstyle="->", color=ink, shrinkB=1))
    ax.set_xlim(-148, 148)
    ax.set_ylim(-57, max(width * cosine + 48, 67))


@lru_cache(maxsize=24)
def profile_png(kind, width, angle=None):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(4.8, 2.5))
    ink = "#18374c"
    def line(xs, ys):
        ax.plot(xs, ys, color=ink, linewidth=2)
    def dimension(a, b, label, label_offset=(0, 0)):
        ax.annotate("", b, a, arrowprops=dict(arrowstyle="<->", color=ink, lw=1.2, shrinkA=0, shrinkB=0))
        x, y = (a[0]+b[0])/2, (a[1]+b[1])/2
        ax.text(x+label_offset[0], y+label_offset[1], f"{label} mm", ha="center", va="center", fontsize=12, fontweight="bold",
                bbox=dict(facecolor="white", edgecolor="none", pad=1))
    def hem(x, y):
        ax.text(x, y, "10 mm", fontsize=10, ha="center", va="center", color=ink,
                bbox=dict(facecolor="white", edgecolor="none", pad=1))
    if kind in ("skew_inner", "skew_outer"):
        _skew_profile(ax, kind, width, angle, ink)
    elif kind == "floor":
        # 30 mm flange points left, with a straight free edge.
        # Only the 50 mm wall flange retains its 10 mm return.
        line([-1.2, -1.2, 0, 0, -30], [40, 50, 50, 0, 0])
        dimension((-52, 0), (-52, 50), 50)
        dimension((-30, -16), (0, -16), 30, (0, -13))
        ax.plot([-55, -30], [0, 0], color=ink, lw=.5)
        ax.plot([-55, 0], [50, 50], color=ink, lw=.5)
        ax.plot([0, 0], [0, -27], color=ink, lw=.5)
        ax.plot([-30, -30], [0, -27], color=ink, lw=.5)
        hem(0, 63)
        ax.annotate("RAL 9010\nlakkert side", (0, 25), (63, 47), fontsize=10,
                    ha="center", va="center", arrowprops=dict(arrowstyle="->", color=ink))
        ax.set_xlim(-85, 115)
    elif kind == "opening":
        # Asymmetric U: 50 mm outside, 80 mm reveal, 15 mm inside.
        line([1.2, 1.2, 0, 0, 80, 80], [40, 50, 50, 0, 0, 15])
        dimension((-22, 0), (-22, 50), 50)
        dimension((0, -15), (80, -15), 80)
        dimension((103, 0), (103, 15), 15, (28, 0))
        for y in (0, 50):
            ax.plot([-27, 0], [y, y], color=ink, lw=.5)
        for y in (0, 15):
            ax.plot([80, 115], [y, y], color=ink, lw=.5)
        for x in (0, 80):
            ax.plot([x, x], [0, -20], color=ink, lw=.5)
        hem(2, 63)
        ax.annotate("RAL 9010 · lakkert side", (52, 0), (70, -36), fontsize=10,
                    ha="center", va="center", arrowprops=dict(arrowstyle="->", color=ink))
        ax.set_xlim(-55, 165)
    elif kind == "inner":
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
        side_gap = 34 if kind == "channel" else 22
        if kind == "channel":
            line([2, 2, 0, 0, width, width, width-2, width-2],
                 [40, 50, 50, 0, 0, 50, 50, 40])
            dimension((-side_gap, 0), (-side_gap, 50), 50)
            for y in (0, 50):
                ax.plot([-side_gap-4, 0], [y, y], color=ink, lw=.5)
            line([0, 8, 8], [8, 8, 0])
            ax.text(11, 12, "90°", fontsize=9)
        else:
            line([10, 0, 0, width, width, width-2, width-2],
                 [2, 2, 0, 0, 50, 50, 40])
        dimension((0, -14), (width, -14), width)
        dimension((width+side_gap, 0), (width+side_gap, 50), 50)
        line([width-8, width-8, width], [0, 8, 8])
        ax.text(width-27, 14, "90°", fontsize=9)
        hem(width-10, 61)
        hem(10, 61 if kind == "channel" else 17)
        ax.plot([0,0],[0,-19],color=ink,lw=.5)
        ax.plot([width,width],[0,-19],color=ink,lw=.5)
        for y in (0, 50):
            ax.plot([width, width+side_gap+4], [y, y], color=ink, lw=.5)
        if kind == "channel":
            ax.annotate("RAL 9010\nlakkert side", (width, 42), (width+21, 78),
                        fontsize=10, ha="left", va="center",
                        arrowprops=dict(arrowstyle="->", color=ink))
            ax.set_xlim(-62, width+88)
        else:
            ax.text(width+52, 76, "RAL 9010\nlakkert side", fontsize=10,
                    ha="center", va="center")
            ax.annotate("", (width, 32), (width+52, 65),
                        arrowprops=dict(arrowstyle="->", color=ink,
                                        connectionstyle="angle,angleA=-90,angleB=0,rad=3"))
            ax.set_xlim(-36, width+88)
    if angle is None:
        ax.set_ylim(-48 if kind == "opening" else -35, 94)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=.01, right=.99, top=.98, bottom=.02)
    out = io.BytesIO()
    fig.savefig(out, format="png", dpi=200, facecolor="white")
    plt.close(fig)
    return out.getvalue()


def profile_cards(rows, normal, heading, available_width):
    from xml.sax.saxutils import escape
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
        if r.get("angles"):
            text.insert(1, Paragraph(r["angles"], heading))
            if r["corners"]:
                text.append(Paragraph(escape("Hjørner: " + r["corners"]), detail))
        if r["kind"] == "floor":
            text.append(Paragraph('50 mm mot vegg · 30 mm mot gulv', detail))
        card = Table([[Image(io.BytesIO(profile_png(r["kind"], r["width"], r.get("angle"))), width=252, height=252*2.5/4.8), text]],
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
