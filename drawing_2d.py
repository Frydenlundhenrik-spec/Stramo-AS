from __future__ import annotations
from construction import roof_outline, wall_polygon, wall_panel_polygon, wall_panel_layout, wall_span
from construction import CHANNEL_HEIGHT, CHANNEL_FLANGE, FLOOR_PIR, FLOOR_BOARD, BATTEN_HEIGHT, wall_base, floor_outline, floor_depth, finished_floor
import io
import math
from typing import Sequence
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MplPolygon, Arc, FancyArrowPatch
from matplotlib.path import Path
import matplotlib.patheffects as pe
from database import PANEL_DB, DOR_DB
from geometry import wall_lengths, ensure_ccw, Point, door_dimensions, polygon_winding
from dimensions import exterior_door, exterior_wall
from panel_engine import generate_roof_floor_panels, main_axis_from_longest_wall
from branding import logo_bilde, logo_sideforhold

# ── Farger og konstanter ──────────────────────────────────────────────────────
DIM_COL   = "#5c6670"
TOTAL_DIM_COL = "#07384c"
DIM_FS    = 8.0
BLUE      = "#000000"
WALL_FILL = "#e8e8e8"
WALL_EDGE = "#000000"
HATCH_COL = "#555"
RED       = "#000000"
GREEN     = "#000000"
ORANGE    = "#555555"
# Figures fit their available canvas and may be resized in the app/PDF export.
# A user-entered ratio cannot describe their physical print scale reliably.
DRAWING_SCALE = "Ikke målfast"


# ── Hjelpefunksjoner ──────────────────────────────────────────────────────────

def _door_entry(d):
    """Normaliserer dør-oppføring til (dk, ant, wall_idx, offset_m, hengsel)."""
    if len(d) == 2:
        return (d[0], d[1], 0, 0.35, "Venstre")
    if len(d) == 4:
        return (d[0], d[1], int(d[2]), float(d[3]), "Venstre")
    return (d[0], d[1], int(d[2]), float(d[3]), str(d[4]))


def _dh(ax, x1, x2, y, lbl, ey=None, fs=DIM_FS, col=None, total=False):
    """Horisontal målpil med stiplede forlengelseslinjer."""
    col = col or (TOTAL_DIM_COL if total else DIM_COL)
    ey  = y if ey is None else ey
    ax.plot([x1, x1], [y, ey], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.plot([x2, x2], [y, ey], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.annotate("", xy=(x2, ey), xytext=(x1, ey),
                arrowprops=dict(arrowstyle="<->", shrinkA=0, shrinkB=0, color=col, lw=1.6 if total else 0.8, mutation_scale=8), zorder=9)
    ax.text((x1+x2)/2, ey + 0.03, lbl, ha="center", va="bottom",
            fontsize=fs, color=col, fontweight="bold" if total else "normal", zorder=10)


def _dv(ax, y1, y2, x, lbl, ex=None, fs=DIM_FS, col=None, total=False):
    """Vertikal målpil med stiplede forlengelseslinjer."""
    col = col or (TOTAL_DIM_COL if total else DIM_COL)
    ex  = x if ex is None else ex
    ax.plot([x, ex], [y1, y1], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.plot([x, ex], [y2, y2], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.annotate("", xy=(ex, y2), xytext=(ex, y1),
                arrowprops=dict(arrowstyle="<->", shrinkA=0, shrinkB=0, color=col, lw=1.6 if total else 0.8, mutation_scale=8), zorder=9)
    ax.text(ex + 0.03, (y1+y2)/2, lbl, ha="left", va="center",
            fontsize=fs, color=col, fontweight="bold" if total else "normal", rotation=90, zorder=10)


def _dim_along_wall(ax, p1, p2, lbl, offset=0.30, fs=DIM_FS, col=None, winding=1, total=False):
    """Målpil langs en skrå vegg, offset perpendikulært utover."""
    col = col or (TOTAL_DIM_COL if total else DIM_COL)
    p1, p2 = np.array(p1), np.array(p2)
    L = np.linalg.norm(p2 - p1)
    if L < 1e-6:
        return
    dx = (p2 - p1) / L
    perp = winding * np.array([-dx[1], dx[0]])
    s = p1 + perp * (-offset)
    e = p2 + perp * (-offset)
    ax.plot([p1[0], s[0]], [p1[1], s[1]], color=col, lw=0.4, zorder=8)
    ax.plot([p2[0], e[0]], [p2[1], e[1]], color=col, lw=0.4, zorder=8)
    ax.annotate("", xy=(e[0], e[1]), xytext=(s[0], s[1]),
                arrowprops=dict(arrowstyle="<->", shrinkA=0, shrinkB=0, color=col, lw=1.6 if total else 0.65, mutation_scale=7), zorder=9)
    mid   = (s + e) / 2
    angle = math.degrees(math.atan2(dx[1], dx[0]))
    # Normaliser slik at teksten alltid er lesbar (aldri opp-ned)
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    ax.text(mid[0] - perp[0]*0.14, mid[1] - perp[1]*0.14, lbl,
            ha="center", va="center", fontsize=fs, rotation=angle,
            color=col, fontweight="bold" if total else "normal", zorder=10,
            bbox=dict(fc="white", ec="none", pad=0.5))


def _polygon_ccw(pts_a) -> bool:
    """Sant dersom polygonet går mot klokka (positivt fortegnsareal)."""
    x = np.asarray(pts_a)[:, 0]; y = np.asarray(pts_a)[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) > 0


def _side_label(ax, pts_a, i, nn, fs=9, avstand=0.55):
    """
    Veggetikett («Vegg 1», «Vegg 2», ...) plassert midt på veggsiden – ikke i
    hjørnet, som ellers blir overfylt av vinkelbue og hjørneelement-skille.
    Trukket lenger inn enn V-nummerne slik at den ikke kolliderer med dem.
    """
    p1 = pts_a[i]; p2 = pts_a[(i+1) % nn]
    d  = p2 - p1; L = np.linalg.norm(d)
    if L < 1e-6:
        return
    d /= L
    perp = polygon_winding(pts_a) * np.array([-d[1], d[0]])
    mid  = (p1 + p2) / 2 + perp * avstand
    # Samme utforming som de fete totalmålene, rotert langs veggen og aldri opp-ned.
    angle = math.degrees(math.atan2(d[1], d[0]))
    if angle > 90.5:
        angle -= 180
    elif angle <= -89.5:
        angle += 180
    ax.text(mid[0], mid[1], f"Vegg {i+1}", ha="center", va="center", rotation=angle,
            fontsize=fs, color=TOTAL_DIM_COL, fontweight="bold", zorder=14,
            bbox=dict(fc="white", ec="none", pad=0.2))


def _corner_angle(ax, pts_a, i, radius=0.16, fs=8, vis_utvendig=True):
    """An unlabelled square only at a convex right angle."""
    pc = np.asarray(pts_a[i], float)
    prev = np.asarray(pts_a[i-1], float)-pc
    nxt = np.asarray(pts_a[(i+1)%len(pts_a)], float)-pc
    if min(np.linalg.norm(prev), np.linalg.norm(nxt)) < 1e-8:
        return
    u, v = prev/np.linalg.norm(prev), nxt/np.linalg.norm(nxt)
    turn = -u[0]*v[1]+u[1]*v[0]
    if abs(float(u@v)) > 1e-6 or polygon_winding(pts_a)*turn <= 0:
        return
    r = min(radius, np.linalg.norm(prev)*.2, np.linalg.norm(nxt)*.2)
    square = np.array([pc+u*r, pc+(u+v)*r, pc+v*r])
    ax.plot(square[:,0], square[:,1], color=TOTAL_DIM_COL, lw=.8, zorder=12)


def _door_dim(ax, p1d, dx_n, offset_m, dw, wall_perp, wall_length, lane=0, height_mm=None):
    """Chain dimensions from both wall corners, retaining the opening width."""
    start, _, end, _ = door_dimensions(wall_length, offset_m, dw)
    angle = math.degrees(math.atan2(dx_n[1], dx_n[0]))
    if angle > 90: angle -= 180
    if angle < -90: angle += 180
    def dimension(a, b, distance, label, color):
        pa = p1d + dx_n*a; pb = p1d + dx_n*b
        qa = pa + wall_perp*distance; qb = pb + wall_perp*distance
        for point, q in ((pa,qa),(pb,qb)):
            ax.plot([point[0],q[0]], [point[1],q[1]], color=color, lw=.4, zorder=11)
        ax.annotate("", xy=qb, xytext=qa,
                    arrowprops=dict(arrowstyle="<->", shrinkA=0, shrinkB=0, color=color, lw=.6), zorder=11)
        mid = (qa+qb)/2 + wall_perp*.07
        ax.text(*mid, label, rotation=angle, ha="center", va="center", fontsize=6,
                color=color, zorder=12, bbox=dict(fc="white",ec="none",pad=.4))
    offset = .60 + lane*.60
    dimension(0,start,offset,f"{start*1000:.0f} mm", "#555")
    dimension(start,start+dw,offset,f"{dw*1000:.0f} × {height_mm} mm" if height_mm else f"Dør {dw*1000:.0f} mm", TOTAL_DIM_COL)
    dimension(start+dw,wall_length,offset,f"{end*1000:.0f} mm", "#555")


def _tegn_logo(ax, cx, cy, maks_bredde, maks_hoyde, fallback_fs=14):
    """
    Tegner Stramo-logoen sentrert i (cx, cy), skalert til å passe innenfor
    maks_bredde × maks_hoyde med bevart sideforhold. Faller tilbake på
    tekst dersom logofilen mangler.
    """
    bilde = logo_bilde()
    if bilde is None:
        ax.text(cx, cy, "STRAMO", ha="center", va="center", fontsize=fallback_fs,
                fontweight="bold", color=BLUE, zorder=21)
        return
    ar = logo_sideforhold()
    w  = min(maks_bredde, maks_hoyde * ar)
    hh = w / ar
    # imshow setter aksens aspekt – legg det tilbake slik det var
    aspekt = ax.get_aspect()
    ax.imshow(bilde, extent=(cx - w/2, cx + w/2, cy - hh/2, cy + hh/2),
              zorder=21, interpolation="antialiased")
    ax.set_aspect(aspekt)


def _tegn_fig_logo(fig, x=0.012, y_topp=0.995, bredde=0.075) -> bool:
    """
    Plasserer logoen i figurens øvre venstre hjørne (figurkoordinater).
    Returnerer False hvis logofilen mangler, slik at kalleren kan bruke tekst.
    """
    bilde = logo_bilde()
    if bilde is None:
        return False
    fw, fh = fig.get_size_inches()
    hoyde  = bredde * (fw / fh) / logo_sideforhold()
    lax = fig.add_axes([x, y_topp - hoyde, bredde, hoyde], zorder=30)
    lax.imshow(bilde, interpolation="antialiased")
    lax.axis("off")
    return True


def _tegn_fig_title_block(fig, info, x: float = 0.815, y_topp: float = 0.96, width: float = 0.17,
                          y_bunn: float | None = None):
    """
    Samme tittelblokk som _title_block, men som en egen fastplassert boks i
    figurkoordinater – for sider uten én enkelt data-akse å feste boksen
    til (f.eks. produksjonstegninger med flere paneler per side).

    Med y_bunn strekkes boksen fra y_topp ned til y_bunn (f.eks. like høy som
    rommet), men aldri lavere enn at feltene får plass.
    """
    bw, bh = 3.2, 5.0
    fw, fh = fig.get_size_inches()
    height = (fw * width) * (bh / bw) / fh
    if y_bunn is not None:
        height = max(y_topp - y_bunn, 3.6 / fh)
    bax = fig.add_axes([x, y_topp - height, width, height], zorder=30)
    bax.set_xlim(0, bw); bax.set_ylim(0, bh)
    bax.axis("off")
    _title_block(bax, 0, 0, 0, bh, info, mg=0)


def _title_block(ax, xmn, xmx, ymn, ymx, info, mg: float = 0.85):
    # Marginen må være stor nok til at utvendige vinkeletiketter (og ev.
    # målsettinger som stikker ut til høyre) får plass før boksen begynner.
    bw = 3.2; tx = xmx + mg; h = ymx - ymn
    ax.add_patch(mpatches.FancyBboxPatch(
        (tx, ymn), bw, h, boxstyle="square,pad=0",
        facecolor="white", edgecolor="black", linewidth=1.0, zorder=20))
    # Every label and value stays inside its own field, including units.
    _tegn_logo(ax, tx + bw/2, ymn + h * 0.91, bw - 0.40, h * 0.12)

    rows = [
        ("Prosjekt",   info["navn"],         0.82, True,   9),
        ("Tegning",    info["ttype"],        0.72, False,  8),
        ("Prosjektnr", info["pnr"],          0.62, False,  8),
        ("Tegningsnr", info["tnr"],          0.52, False,  8),
        ("Dato",       info["dato"],         0.42, False,  8),
        ("Målestokk",  DRAWING_SCALE,       0.32, False,  8),
        ("Areal",      f"{info['A']:.2f} m²",0.22, False,  8),
        ("Omkrets",    f"{info['P']:.2f} m", 0.12, False,  8),
    ]
    for lbl, val, frac, bold, fs in rows:
        yp = ymn + h * frac
        ax.text(tx+0.14, yp-h*0.014, lbl, fontsize=6.5, color="#5c6670", va="top", zorder=21)
        value_text = ax.text(tx+0.14, yp-h*0.047, str(val) or "–", fontsize=fs+0.5,
                fontweight="bold" if bold else "normal",
                color=BLUE if bold else "black", va="top", zorder=21)
        renderer = ax.figure.canvas.get_renderer()
        text_width = value_text.get_window_extent(renderer).width
        field_width = (bw-0.28) * ax.bbox.width / bw
        if text_width > field_width:
            value_text.set_fontsize((fs+0.5)*field_width/text_width)
        ax.plot([tx, tx+bw], [yp, yp], color="#aaa", lw=0.4, zorder=21)
    return tx + bw


# ══ PLANTEGNING ══════════════════════════════════════════════════════════════

def stramo_plan(pts, H, pw_m, dorer, info, bakgrunn=None, apninger=None, wall_thickness=0.09, excluded_walls=(), ax=None, dimension_obstacles=()):
    """
    Detaljert plantegning:
    • Vegger med element-oppdeling og nummerering
    • Innvendige vinkler ved alle hjørner
    • Dørmarkering med nøyaktige mål: avstand fra hjørne + bredde
    • Ytre totalsmål + individuelle vegg-mål
    • Hjørnepunktmerking
    """
    pts_a = np.array(pts); nn = len(pts_a)
    xs, ys = pts_a[:, 0], pts_a[:, 1]
    wls    = wall_lengths(pts)

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(18, 11))
    else:
        fig = ax.figure
    fig.patch.set_facecolor("white"); ax.set_facecolor("white")

    # Bakgrunnsbilde
    if bakgrunn is not None:
        try:
            from PIL import Image
            img = Image.open(bakgrunn).convert("RGBA")
            ax.imshow(np.array(img),
                      extent=[xs.min(), xs.max(), ys.min(), ys.max()],
                      alpha=0.22, aspect="auto", origin="upper", zorder=0)
        except Exception:
            pass

    WT = wall_thickness

    # All views use the same physical panel spans and corner joints.
    for panel in wall_panel_layout(pts,round(pw_m*1000),WT,excluded_walls):
        i=panel['wall']
        outline=wall_panel_polygon(pts,i,panel['start_mm']/1000,
            (panel['start_mm']+panel['width_mm'])/1000,WT,excluded_walls)
        ax.add_patch(MplPolygon(outline,closed=True,facecolor=WALL_FILL,
                                edgecolor='black',hatch='////',linewidth=1.1,zorder=4))
        direction=(pts_a[(i+1)%nn]-pts_a[i])/wls[i]
        inward=polygon_winding(pts_a)*np.array([-direction[1],direction[0]])
        mid=pts_a[i]+direction*(panel['start_mm']+panel['width_mm']/2)/1000+inward*.08
        ax.text(*mid,panel['name'],ha='center',va='center',fontsize=5.8,
                color='black',fontweight='bold',zorder=5)

    # ── Dørmarkering med mål ──────────────────────────────────────────────────
    door_cursors = {}
    for entry in dorer:
        dk, ant, wall_idx, offset_m, hengsel = _door_entry(entry)
        if wall_idx in excluded_walls or ant <= 0 or wall_idx >= nn or wls[wall_idx] < 1e-6:
            continue
        p1d   = pts_a[wall_idx]; p2d = pts_a[(wall_idx+1) % nn]
        vL    = wls[wall_idx]
        dx_n  = (p2d - p1d) / vL
        perp  = polygon_winding(pts_a) * np.array([-dx_n[1], dx_n[0]])   # innadrettet (CCW polygon)
        outw  = -perp                              # utoverretning
        cursor = offset_m
        dw     = DOR_DB[dk]["bw"] / 1000
        door_angle = math.degrees(math.atan2(dx_n[1], dx_n[0]))

        for idx_d in range(ant):
            if cursor + dw > vL + 1e-6:
                break
            s = p1d + dx_n * cursor
            e = p1d + dx_n * (cursor + dw)
            # Åpning i veggen
            ax.add_patch(MplPolygon([s,e,e-perp*WT,s-perp*WT],closed=True,
                                    facecolor='white',edgecolor='none',zorder=6))
            ax.plot([s[0], e[0]], [s[1], e[1]],
                    color="white", lw=4.5, solid_capstyle="butt", zorder=6)
            ax.plot([s[0], e[0]], [s[1], e[1]],
                    color=WALL_EDGE, lw=1.1, solid_capstyle="butt", zorder=7)

            # Svingebue utover – hengsel velger side
            if hengsel == "Høyre":
                # Hengsel i e, referanseretning -dx_n (mot s = lukket posisjon)
                # theta: 0 = mot s (lukket), 90 = utover (CCW-sveip)
                hinge    = e
                arc_ang  = door_angle + 180
                t1, t2   = 0, 90
            else:
                # Hengsel i s, referanseretning dx_n (mot e = lukket posisjon)
                # theta: 0 = mot e (lukket), -90 = utover (CW-sveip)
                hinge    = s
                arc_ang  = door_angle
                t1, t2   = -90, 0

            if polygon_winding(pts_a) < 0:
                t1, t2 = -t2, -t1
            leaf_end = hinge + outw * dw

            ax.add_patch(Arc(tuple(hinge), dw*2, dw*2,
                             angle=arc_ang, theta1=t1, theta2=t2,
                             color=WALL_EDGE, lw=0.8, zorder=7))
            # Dørblad i åpen posisjon (stiplet linje utover)
            ax.plot([hinge[0], leaf_end[0]], [hinge[1], leaf_end[1]],
                    color=WALL_EDGE, lw=0.6, linestyle="--", zorder=7)

            # Dørhåndtak nær den frie kanten (motsatt hengselet) – flytter
            # seg automatisk med hengselsiden siden den følger dørbladet.
            handle_pt = hinge + (leaf_end - hinge) * 0.85
            ax.plot([handle_pt[0]], [handle_pt[1]], marker="o",
                    markersize=3.0, color=WALL_EDGE, zorder=8)

            # Mål-piler: hjørne→dør og dørbredde
            from dimensions import exterior_door
            outer_start, outer_length, outer_offset = exterior_door(pts, WT, wall_idx, cursor, excluded_walls)
            # Door dimensions stay outside their room, also beside a shared wall.
            _door_dim(ax, outer_start, dx_n, outer_offset, dw, -perp, outer_length, idx_d,
                      height_mm=DOR_DB[dk]["bh"])

            cursor += dw + 0.20
        door_cursors[wall_idx] = cursor

    # ── Åpninger / klassfronter i plan ───────────────────────────────────────
    if apninger:
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, ap_lbl = ap
            if ap_wall >= nn or wls[ap_wall] < 1e-6:
                continue
            p1a = pts_a[ap_wall]; p2a = pts_a[(ap_wall+1) % nn]
            vL  = wls[ap_wall]
            da  = (p2a - p1a) / vL
            perp_a = polygon_winding(pts_a) * np.array([-da[1], da[0]])
            s_a = p1a + da * ap_off
            e_a = p1a + da * (ap_off + ap_w)
            # Hvit gap i veggen (åpning)
            ax.plot([s_a[0], e_a[0]], [s_a[1], e_a[1]],
                    color="white", lw=5.0, solid_capstyle="butt", zorder=6)
            # Tre linjer = vindu-symbol i plan
            for frac in (0.25, 0.5, 0.75):
                m = s_a + da * ap_w * frac
                ax.plot([m[0] - perp_a[0]*0.05, m[0] + perp_a[0]*0.05],
                        [m[1] - perp_a[1]*0.05, m[1] + perp_a[1]*0.05],
                        color="#000", lw=1.2, zorder=8)
            ax.plot([s_a[0], e_a[0]], [s_a[1], e_a[1]],
                    color="#000", lw=1.5, solid_capstyle="butt", zorder=7,
                    linestyle="--")
            # Etikett
            mid_a = (s_a + e_a) / 2
            sill_txt = f" {round(ap_sill*1000)} mm" if ap_sill > 0 else ""
            ax.text(mid_a[0] + perp_a[0]*0.35,
                    mid_a[1] + perp_a[1]*0.35,
                    f"{ap_lbl}\n{round(ap_w*1000)}×{round(ap_h*1000)} mm{sill_txt}",
                    ha="center", va="center", fontsize=6.5, color="#000",
                    fontweight="bold", zorder=9)

    # ── Vinkler ved hjørner ───────────────────────────────────────────────────
    for i in range(nn):
        _corner_angle(ax, pts_a, i, radius=0.20)
        _side_label(ax, pts_a, i, nn)
        ax.annotate(f"H{i+1}", pts_a[i], xytext=(5,5), textcoords="offset points",
                    fontsize=6, color="#1a3a5c", zorder=15)

    # All plan dimensions and extension lines originate at OUTSIDE corners.
    outer = np.asarray(floor_outline(pts, WT))
    xmn, ymn = outer.min(axis=0); xmx, ymx = outer.max(axis=0)
    if standalone:
        _dh(ax, xmn, xmx, ymn, f"{(xmx-xmn)*1000:.0f} mm", ey=ymn-1.65, fs=10, total=True)
        _dv(ax, ymn, ymx, xmx, f"{(ymx-ymn)*1000:.0f} mm", ex=xmx+1.65, fs=10, total=True)
    for i in range(nn):
        p1, p2 = exterior_wall(pts, WT, i, excluded_walls) if i not in excluded_walls else (outer[i], outer[(i+1)%nn])
        length = np.linalg.norm(p2-p1)
        full_width = np.isclose(abs(p2[0]-p1[0]), xmx-xmn) and np.isclose(p1[1],p2[1])
        full_height = np.isclose(abs(p2[1]-p1[1]), ymx-ymn) and np.isclose(p1[0],p2[0])
        if standalone and (full_width or full_height):
            continue
        if not standalone and i in excluded_walls:
            continue
        has_door = any(_door_entry(d)[2] == i and _door_entry(d)[1] > 0 for d in dorer)
        lane = 1.65 if has_door else .45
        outward = polygon_winding(pts_a)*np.array([(p2-p1)[1],-(p2-p1)[0]])/length
        if not standalone and any(path.contains_point((p1+p2)/2+outward*lane) for path in dimension_obstacles):
            continue
        _dim_along_wall(ax, p1, p2, f"{length*1000:.0f} mm", offset=1.65 if has_door else .45,
                        fs=10, winding=polygon_winding(pts_a), total=True)

    if not standalone:
        return fig
    ax.text((xmn+xmx)/2, ymn - 2.05,
            f"PLANTEGNING  –  {DRAWING_SCALE}  ·  Utvendige mål",
            ha="center", va="top", fontsize=9, fontweight="bold", color=BLUE)

    ax.set_xlim(xmn - 2.0, xmx + 2.1)
    ax.set_ylim(ymn - 2.55, ymx + 2.1)
    ax.set_aspect("equal"); ax.axis("off")
    fig.subplots_adjust(left=0.02, right=0.79, top=0.97, bottom=0.03)
    # Tittelblokken skal være like høy som rommet: les rommets topp og bunn
    # i figurkoordinater etter at aksen har fått sitt endelige sideforhold.
    ax.apply_aspect()
    til_figur = ax.transData + fig.transFigure.inverted()
    rom_bunn = til_figur.transform((xmx, ymn))[1]
    rom_topp = til_figur.transform((xmx, ymx))[1]
    _tegn_fig_title_block(fig, info, y_topp=rom_topp, y_bunn=rom_bunn)
    return fig


# ══ TAKTEGNING ═══════════════════════════════════════════════════════════════

def stramo_tak(pts, H, pw_m, dorer, info, rom_type="Kjølerom", panel_key="PIR 80 mm"):
    """
    Detaljert taktegning (sett ovenfra):
    • Alle takelementer (T1, T2 …) med riktig polygon klippet mot rommets form
    • Hel/kapp markert med farger
    • Alle vegg-mål rundt rommet med vinkler
    • Elementbredde-mål langs spans-retning
    • Titleblokk
    """
    pts_a  = np.array(roof_outline(pts,PANEL_DB[panel_key]["t"]/1000,rom_type), dtype=float)
    nn     = len(pts_a)
    xs, ys = pts_a[:, 0], pts_a[:, 1]
    wls    = wall_lengths(pts_a)
    pw_mm  = round(pw_m * 1000)
    WT     = PANEL_DB[panel_key]["t"] / 1000

    panels = generate_roof_floor_panels(roof_outline(pts,PANEL_DB[panel_key]["t"]/1000,rom_type), pw_mm, prefix="T", label="Tak")
    is_frys = "Fryserom" in rom_type
    if is_frys:
        gulv_panels = generate_roof_floor_panels(floor_outline(pts, PANEL_DB[panel_key]["t"]/1000), pw_mm, prefix="G", label="Gulv")
    else:
        gulv_panels = []

    fig, axes = plt.subplots(
        1, 2 if is_frys else 1,
        figsize=(18 if is_frys else 14, 10),
        squeeze=False,
    )
    fig.patch.set_facecolor("white")

    def _draw_panel_plan(ax, panel_list, tittel, show_gulv=False):
        ax.set_facecolor("white")

        # ── Romkontour med vegg-tykkelse ──────────────────────────────────────
        ax.add_patch(MplPolygon(pts_a, closed=True, facecolor="#e0e0e0",
                                 edgecolor=WALL_EDGE, linewidth=1.8, zorder=1))
        ax.add_patch(MplPolygon(pts_a, closed=True, facecolor="none",
                                 edgecolor="#aaa", linewidth=0,
                                 hatch="xxxx", zorder=1.5, alpha=0.4))

        # Indre åpning
        inn = []
        for i in range(nn):
            p1 = pts_a[i]; p2 = pts_a[(i+1)%nn]; pm = pts_a[(i-1)%nn]
            d1 = p2-p1; d1 /= np.linalg.norm(d1)+1e-9
            d0 = p1-pm; d0 /= np.linalg.norm(d0)+1e-9
            n1 = polygon_winding(pts_a) * np.array([-d1[1], d1[0]]); n0 = polygon_winding(pts_a) * np.array([-d0[1], d0[0]])
            na = (n1+n0)/2; na /= np.linalg.norm(na)+1e-9
            inn.append(p1 + na*WT)
        ax.add_patch(MplPolygon(np.array(inn), closed=True, facecolor="white",
                                 edgecolor=WALL_EDGE, linewidth=0.9, zorder=2))

        # ── Takpaneler ────────────────────────────────────────────────────────
        FILL_HEL  = "#e8e8e8"
        FILL_KAPP = "#cccccc"
        FILL_REST = "#e8e8e8"

        for p in panel_list:
            if not p.polygon or len(p.polygon) < 3:
                continue
            poly_w = np.array(p.polygon)
            is_kapp = "kapp" in p.kind.lower() or "start" in p.kind.lower()
            fc = FILL_KAPP if is_kapp else FILL_HEL
            ec = "#000"

            ax.add_patch(MplPolygon(poly_w, closed=True, facecolor=fc,
                                     edgecolor=ec, linewidth=1.0, zorder=3, alpha=0.85))
            ax.add_patch(MplPolygon(poly_w, closed=True, facecolor="none",
                                     edgecolor="#555", linewidth=0,
                                     hatch="////" if not is_kapp else ".....",
                                     zorder=3.5, alpha=0.3))

            # Etikett
            from shapely.geometry import Polygon
            point = Polygon(poly_w).representative_point()
            cx,cy=point.x,point.y
            narrow=p.width_mm<350
            direction,_=main_axis_from_longest_wall(p.polygon)
            angle=math.degrees(math.atan2(direction[1],direction[0])) if narrow else 0
            if angle>90:angle-=180
            if angle<-90:angle+=180
            label=f"{p.name} · {p.width_mm} mm" if narrow else f"{p.name}\n{p.width_mm} mm"
            ax.text(cx, cy, label, rotation=angle,
                    ha="center", va="center", fontsize=8,
                    color=TOTAL_DIM_COL,
                    fontweight="bold", zorder=5,
                    bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.85))

        # ── Mål: alle vegg-sider ──────────────────────────────────────────────
        xmn, xmx = xs.min(), xs.max(); ymn, ymx = ys.min(), ys.max()
        DIM_OFF = 0.65

        # Totalmål. Høyde-målet må stanse klart før tittelblokken (0.85 til
        # høyre for xmx), ellers stipler linjen inn i boksen.
        _dh(ax, xmn, xmx, ymn, f"{(xmx-xmn)*1000:.0f} mm", ey=ymn - DIM_OFF - 0.55, fs=10, total=True)
        _dv(ax, ymn, ymx, xmx, f"{(ymx-ymn)*1000:.0f} mm", ex=xmx + DIM_OFF - 0.10, fs=10, total=True)

        # Per-vegg mål
        for i in range(nn):
            p1,p2=pts_a[i],pts_a[(i+1)%nn]
            full_width=np.isclose(abs(p2[0]-p1[0]),xmx-xmn) and np.isclose(p1[1],p2[1])
            full_height=np.isclose(abs(p2[1]-p1[1]),ymx-ymn) and np.isclose(p1[0],p2[0])
            if full_width or full_height:
                continue  # already shown by the overall exterior dimension
            _dim_along_wall(ax, pts_a[i], pts_a[(i+1)%nn],
                            f"{wls[i]*1000:.0f} mm", offset=0.35, fs=10, total=True)

        # ── Vinkler ───────────────────────────────────────────────────────────
        # Sideetiketter er droppet her: takflaten er allerede full av
        # panel-etiketter, og de trengs uansett kun for referanse i
        # plantegningen.
        for i in range(nn):
            _corner_angle(ax, pts_a, i, radius=0.22, fs=8)

        # ── Element-bredde kjede langs hoved-aksen ────────────────────────────
        x_axis, _ = main_axis_from_longest_wall(pts)
        _draw_panel_width_chain(ax, panels, x_axis, pts_a, ymn, DIM_OFF)

        # ── Legende ───────────────────────────────────────────────────────────
        leg = [
            mpatches.Patch(facecolor=FILL_HEL,  edgecolor="#2980b9", label="Hel panel"),
            mpatches.Patch(facecolor=FILL_KAPP, edgecolor=ORANGE,    label="Kapp/start"),
        ]
        ax.legend(handles=leg, loc="upper left", fontsize=8, framealpha=0.9)

        ax.text((xmn+xmx)/2, ymn - DIM_OFF - 1.0, tittel,
                ha="center", va="top", fontsize=9, fontweight="bold", color=BLUE)

        ax.set_xlim(xmn - DIM_OFF - 1.6, xmx + DIM_OFF + 0.8)
        ax.set_ylim(ymn - DIM_OFF - 2.0, ymx + DIM_OFF + 1.2)
        ax.set_aspect("equal"); ax.axis("off")

        # ── Statistikk-boks ───────────────────────────────────────────────────
        n_hel  = sum(1 for p in panel_list if "hel" in p.kind.lower())
        n_kapp = len(panel_list) - n_hel
        ax.text(xmn - DIM_OFF - 1.4, ymx + 0.1,
                f"Totalt {len(panel_list)} elementer\n{n_hel} hele · {n_kapp} kapp",
                fontsize=8, color=BLUE, va="top", zorder=14,
                bbox=dict(fc="white", ec=BLUE, pad=5, linewidth=0.8))

    _draw_panel_plan(axes[0][0], panels, f"TAKTEGNING – {DRAWING_SCALE}")
    if is_frys:
        _draw_panel_plan(axes[0][1], gulv_panels, f"GULV PIR – {DRAWING_SCALE}", show_gulv=True)

    fig.tight_layout(rect=[0, 0, 0.79, 0.97], pad=0.5)
    _tegn_fig_title_block(fig, info)
    return fig


def _draw_panel_width_chain(ax, panels, x_axis, pts_a, ymn, dim_off):
    """Mål-kjede som viser bredden på hvert panel langs hoved-aksen."""
    if not panels:
        return
    # Beregn kursorposisjoner langs x_axis
    origin   = pts_a[0]
    perp     = np.array([-x_axis[1], x_axis[0]])
    y_chain  = ymn - dim_off - 0.90

    # Finn y-posisjonen til mål-kjeden i verdenskoordinater
    # Projiser ymn-punktet til lokal Y og bruk et globalt offset
    base_pt  = np.array([xs_min := float(pts_a[:, 0].min()),
                          float(pts_a[:, 1].min())])

    # Vi tegner mål-kjeden rett under rommet
    prev_world = None
    cursor_m   = 0.0
    for p in panels:
        w_m = p.width_mm / 1000.0
        # Startpunkt av panel i verden langs hoved-aksen
        poly_w = np.array(p.polygon)
        if len(poly_w) < 3:
            cursor_m += w_m; continue
        # Bruk midten av panelet
        cx = float(np.mean(poly_w[:, 0])); cy = float(np.mean(poly_w[:, 1]))
        cursor_m += w_m


# ══ VEGGOPPSTALT ═════════════════════════════════════════════════════════════

def _global_start_el_nr(wls, pw_m, vegg_idx, excluded_walls=()):
    """Beregn første globale V-nummer for gitt vegg (samme logikk som kappliste)."""
    pw_mm = round(pw_m * 1000)
    el_nr = 1; rest_mm = 0
    for vi, wl in enumerate(wls):
        if vi in excluded_walls:
            continue
        L_mm = round(wl * 1000); brukt = 0
        if vi == vegg_idx:
            return el_nr, rest_mm
        if rest_mm > 0:
            bredde = min(rest_mm, L_mm)
            brukt += bredde; el_nr += 1; rest_mm = max(rest_mm - L_mm, 0)
        while brukt + pw_mm <= L_mm:
            brukt += pw_mm; el_nr += 1
        remaining = L_mm - brukt
        if remaining > 0:
            el_nr += 1; rest_mm = pw_mm - remaining
    return el_nr, rest_mm


def tegn_veggoppstalt(pts, H, pw_m, dorer, info, vegg_idx: int = 0, apninger=None, rom_type="Kjølerom", excluded_walls=(), wall_thickness=.08):
    """Veggoppstalt per vegg med elementoppdeling, dørmål og høyde-mål."""
    floor_offset = floor_depth(rom_type)
    wls   = wall_lengths(pts)
    nn    = len(pts)
    L     = wls[vegg_idx]
    pw_mm = round(pw_m * 1000)
    L_mm  = round(L * 1000)
    H_mm  = round(H * 1000)

    fig, ax = plt.subplots(figsize=(max(10, L*2.8), 7))
    fig.patch.set_facecolor("white"); ax.set_facecolor("white")

    lo,hi=wall_span(pts,vegg_idx,wall_thickness,excluded_walls)
    el_positions=[(p['start_mm']/1000,p['width_mm']/1000,p['name'],
                   'hel' if p['kind']=='Hel' else 'kapp')
                  for p in wall_panel_layout(pts,pw_mm,wall_thickness,excluded_walls)
                  if p['wall']==vegg_idx]
    ax.add_patch(mpatches.Rectangle((lo,0),hi-lo,H,facecolor=WALL_FILL,
                                    edgecolor=WALL_EDGE,linewidth=1.5,zorder=1))

    for x, w, lbl, typ in el_positions:
        col_fill = "#e8e8e8" if typ == "hel" else "#cccccc"
        ax.add_patch(mpatches.Rectangle((x, 0), w, H, facecolor=col_fill,
                                         edgecolor="#000", linewidth=0.9, zorder=2, alpha=0.7))
        ax.text(x + w/2, H/2, f"{lbl}\n{round(w*1000)} mm",
                ha="center", va="center", fontsize=8,
                color="#000",
                fontweight="bold", zorder=4)
        if x > 0:
            ax.plot([x, x], [0, H], color=WALL_EDGE, lw=0.8, zorder=3)

    # ── Dørmarkering med mål ──────────────────────────────────────────────────
    door_cursor = 0.35
    for entry in dorer:
        dk, ant, wall_idx_d, offset_m, hengsel_v = _door_entry(entry)
        if int(wall_idx_d) != vegg_idx or ant <= 0:
            continue
        d  = DOR_DB[dk]
        dw = d["bw"] / 1000; dh = d["bh"] / 1000
        cursor = offset_m
        for _ in range(min(ant, 4)):
            ax.add_patch(mpatches.Rectangle(
                (cursor, floor_offset), dw, dh, facecolor="white",
                edgecolor=RED, linewidth=1.8, zorder=5))
            ax.text(cursor + dw/2, floor_offset + dh/2, f"D\n{d['label']}",
                    ha="center", va="center", fontsize=5.5,
                    color=RED, fontweight="bold", zorder=6)
            # Dørhåndtak motsatt hengselet, i vanlig håndtakshøyde
            handle_x = cursor + dw * (0.10 if hengsel_v == "Høyre" else 0.90)
            handle_y = floor_offset + min(1.0, dh * 0.5)
            ax.plot([handle_x], [handle_y], marker="o", markersize=4,
                    color=RED, zorder=7)
            # Dørmål fra begge utvendige hjørner.
            _, outside_length, outside_offset = exterior_door(pts, wall_thickness, vegg_idx, cursor, excluded_walls)
            outside_start = cursor-outside_offset
            outside_end = outside_start+outside_length
            _dh(ax, outside_start, cursor, -.25, f"{round(outside_offset*1000)} mm", ey=-.25, col="#555", fs=5.5)
            _dh(ax, cursor+dw, outside_end, -.25, f"{round((outside_length-outside_offset-dw)*1000)} mm", ey=-.25, col="#555", fs=5.5)
            # Dørbredde
            _dh(ax, cursor, cursor+dw, -0.45, f"{d['bw']} mm", ey=-0.45, col=RED, fs=5.5)
            # Dørhøyde
            _dv(ax, floor_offset, floor_offset + dh, cursor+dw+0.05, f"{d['bh']} mm", ex=cursor+dw+0.05, col=RED, fs=5.5)
            cursor += dw + 0.20
        door_cursor = cursor

    # ── Åpninger / klassfronter på denne veggen ───────────────────────────────
    AP_COL = "#000000"   # sort for åpning, linjer og mål
    dim_bot = -0.70   # tracker for mål-linjer nedover
    if apninger:
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, ap_lbl = ap
            ap_sill += floor_offset
            if int(ap_wall) != vegg_idx:
                continue
            # Tegn åpning som hvit rektangel
            ax.add_patch(mpatches.Rectangle(
                (ap_off, ap_sill), ap_w, ap_h,
                facecolor="white", edgecolor=AP_COL,
                linewidth=2.0, zorder=5))
            # Tre horisontale linjer = klassfront-symbol
            for frac in (0.25, 0.5, 0.75):
                yy = ap_sill + ap_h * frac
                ax.plot([ap_off + ap_w*0.15, ap_off + ap_w*0.85],
                        [yy, yy], color=AP_COL, lw=0.8, linestyle="-", zorder=6)
            # Etikett inne i åpningen
            ax.text(ap_off + ap_w/2, ap_sill + ap_h/2,
                    f"{ap_lbl}\n{round(ap_w*1000)}×{round(ap_h*1000)} mm",
                    ha="center", va="center", fontsize=8,
                    color=AP_COL, fontweight="bold", zorder=7)
            # Horisontale mål under veggen
            _dh(ax, 0, ap_off, dim_bot,
                f"{round(ap_off*1000)} mm", ey=dim_bot, col=AP_COL, fs=5.5)
            _dh(ax, ap_off, ap_off+ap_w, dim_bot - 0.25,
                f"{round(ap_w*1000)} mm", ey=dim_bot - 0.25, col=AP_COL, fs=5.5)
            dim_bot -= 0.55

            # Vertikale mål: forlengelseslinjer fra høyre kant av utsparringen
            ap_right = ap_off + ap_w   # høyre kant av åpningen
            arr_x    = L + 0.55        # x for selve pil-linjen
            # Fra gulv til underkant åpning
            if ap_sill > 0.001:
                _dv(ax, 0, ap_sill, ap_right,
                    f"{round(ap_sill*1000)} mm", ex=arr_x, col=AP_COL, fs=5.5)
            # Åpningshøyde
            _dv(ax, ap_sill, ap_sill + ap_h, ap_right,
                f"{round(ap_h*1000)} mm", ex=arr_x, col=AP_COL, fs=5.5)
            # Fra topp åpning til topp element
            top_gap = H - (ap_sill + ap_h)
            if top_gap > 0.001:
                _dv(ax, ap_sill + ap_h, H, ap_right,
                    f"{round(top_gap*1000)} mm", ex=arr_x, col=AP_COL, fs=5.5)

    # ── Mål ───────────────────────────────────────────────────────────────────
    _dh(ax, lo, hi, 0, f"{round((hi-lo)*1000)} mm panelrekke", ey=dim_bot-.20,total=True,fs=10)
    _dv(ax, 0, H, L, f"{H_mm} mm", ex=L + 0.90, total=True, fs=10)

    # Element-mål kjede (toppen)
    for x, w, lbl, _ in el_positions:
        _dh(ax, x, x+w, H, f"{round(w*1000)}", ey=H + 0.20, fs=5.5)

    ax.text(L/2, H + 0.55,
            f"VEGG {vegg_idx+1}  –  {DRAWING_SCALE}",
            ha="center", va="bottom", fontsize=9, fontweight="bold", color=BLUE)

    # Tittelblokken må stå klar av høyde-målet til høyre (ex=L+0.90 + tekst).
    # Bruker samme høyde som aksens fulle utstrekning (ikke bare veggen H) –
    # ellers blir boksen for kort i fysiske tommer og radene klemmes sammen.
    _tegn_fig_title_block(fig, info)

    ax.set_xlim(-0.9, L + 1.4); ax.set_ylim(dim_bot - 0.8, H + 0.9)
    ax.set_aspect("equal"); ax.axis("off")
    fig.subplots_adjust(left=0.02, right=0.79, top=0.97, bottom=0.03)
    return fig


# ══ SNITT ═════════════════════════════════════════════════════════════════════

def _snitt_konstruksjon(ax, L, H, WT, rom_type, pw_m, dorer,
                         show_labels=True,
                         vegg_label_left="V", vegg_label_right="V",
                         vegg_idx=0):
    UC = BATTEN_HEIGHT + WT if "Fryserom" in rom_type else 0.0; TAK = WT
    IS_FRYS = "Fryserom" in rom_type
    GFL = WT if IS_FRYS else 0.0
    SPL = FLOOR_BOARD if IS_FRYS else 0.0

    CPANEL = "#c8c8c8"; CSPON = "#d4a96a"
    CPIR_G  = "#b8d4b8"; CUKAN  = "#5a7a9a"; CWHITE = "white"

    def rect(x, y, w, h, fc, ec="black", lw=0.8, hatch=None, zo=2, alpha=1.0):
        ax.add_patch(mpatches.Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec,
                                         linewidth=lw, zorder=zo, alpha=alpha))
        if hatch:
            ax.add_patch(mpatches.Rectangle((x, y), w, h, facecolor="none",
                                             edgecolor="#888", linewidth=0,
                                             hatch=hatch, zorder=zo+0.5, alpha=0.4))

    # Betong ikke kalkulert – ikke vist i snitt
    UW = WT + 2*CHANNEL_FLANGE; FLG = CHANNEL_FLANGE
    if not IS_FRYS:
        for x in (-WT-FLG, L-FLG):
            rect(x, 0, UW, FLG, CUKAN, lw=0.6, zo=4)
            rect(x, FLG, FLG, CHANNEL_HEIGHT-FLG, CUKAN, lw=0.6, zo=4)
            rect(x+UW-FLG, FLG, FLG, CHANNEL_HEIGHT-FLG, CUKAN, lw=0.6, zo=4)

    if IS_FRYS:
        for x in (-WT, L/2, L):
            rect(x, 0, min(.05,WT), BATTEN_HEIGHT, CSPON, zo=3)
        rect(-WT, BATTEN_HEIGHT, L+2*WT, GFL, CPIR_G, hatch="....", zo=2)
        rect(0, UC, L, SPL, CSPON, zo=3)

    rect(-WT, UC, WT, H, CPANEL, hatch="////", zo=3)
    rect(L, UC, WT, H, CPANEL, hatch="////", zo=3)
    inn_y0 = UC + (SPL if IS_FRYS else 0)
    rect(0, inn_y0, L, H-(inn_y0-UC), CWHITE, ec="#aaa", lw=0.4, zo=2)
    rect(-WT, UC+H, L+2*WT, TAK, CPANEL, hatch="////", zo=3)

    n_vegg_el = math.ceil(H / pw_m)
    for pi in range(1, n_vegg_el):
        hz = UC + pi*pw_m
        if hz >= UC+H: break
        ax.plot([-WT, 0], [hz, hz], color="black", lw=0.6, zorder=5)
        ax.plot([L, L+WT], [hz, hz], color="black", lw=0.6, zorder=5)

    n_tak_el = math.ceil(L / pw_m)
    for ti in range(1, n_tak_el):
        tx = ti*pw_m
        if tx >= L: break
        ax.plot([tx, tx], [UC+H, UC+H+TAK], color="black", lw=0.6, zorder=5)

    # Dør på denne veggen
    for entry in dorer:
        dk, ant, wall_idx_d, offset_m, _hengsel_s = _door_entry(entry)
        if int(wall_idx_d) != vegg_idx or ant <= 0:
            continue
        d  = DOR_DB[dk]; dh = d["bh"] / 1000
        rect(-WT, UC+SPL, WT, dh, CWHITE, ec=RED, lw=1.5, zo=7)
        ax.text(-WT/2, UC+SPL+dh/2, "D", ha="center", va="center",
                fontsize=6, color=RED, fontweight="bold", zorder=8)
        break

    if not show_labels:
        return

    def lbl(x, y, txt, col="#222", fs=6, ha="center", va="center", rot=0):
        ax.text(x, y, txt, ha=ha, va=va, fontsize=fs, color=col,
                rotation=rot, zorder=10,
                bbox=dict(fc="white", ec="none", pad=0.5, alpha=0.85))

    lbl(-WT/2, UC/2,        ("Vinkelbeslag" if IS_FRYS else f"U-kanal\n{round(WT*1000)} mm"),  fs=5.5, col="#1a3a5c")
    lbl(L+WT/2, UC/2,      ("Vinkelbeslag" if IS_FRYS else f"U-kanal\n{round(WT*1000)} mm"),  fs=5.5, col="#1a3a5c")
    lbl(-WT/2, UC+H/2,      vegg_label_left if vegg_label_left.startswith("Vegg ") else f"Vegg\n{vegg_label_left}", fs=6, col="#1a3a5c")
    lbl(L+WT/2, UC+H/2,    f"Vegg\n{vegg_label_right}", fs=6, col="#1a3a5c")
    lbl(L/2, UC+H+TAK/2,   "Tak", fs=6)
    if IS_FRYS:
        lbl(L/2, BATTEN_HEIGHT+GFL/2,  f"Gulvpanel {round(WT*1000)} mm",             fs=5.5, col="#2d6e2d")
        lbl(L/2, UC+SPL/2,     "Gulvplate 12 mm", fs=5.5, col="#7a5c20")


def stramo_snitt(pts, H, pw_m, dorer, info, rom_type, panel_key,
                 vegg_idx=0, seksjon="A-A", apninger=None):
    WT     = PANEL_DB[panel_key]["t"] / 1000
    pts_a  = np.array(pts); nn = len(pts_a)
    outside = np.asarray(floor_outline(pts, WT))
    direction = outside[(vegg_idx+1)%nn] - outside[vegg_idx]
    L = float(np.linalg.norm(direction))-2*WT
    vl_left  = f"Vegg {vegg_idx+1}"
    vl_right = "prinsipp"

    UC = wall_base(rom_type, panel_key); TAK = WT
    IS_FRYS = "Fryserom" in rom_type
    GFL = WT if IS_FRYS else 0.0
    SPL = FLOOR_BOARD if IS_FRYS else 0.0
    DIM_OFF = 0.35

    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor("white"); ax.set_facecolor("white")

    _snitt_konstruksjon(ax, L, H, WT, rom_type, pw_m, dorer,
                        vegg_label_left=vl_left, vegg_label_right=vl_right,
                        vegg_idx=vegg_idx)

    # ── Åpninger i snitt (vises som hvite rektangler i venstre vegg) ──────────
    CYAN = "#00aacc"
    if apninger:
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, ap_lbl = ap
            if int(ap_wall) != vegg_idx:
                continue
            # Vis åpning som hvit rektangel i veggen (venstre side = vegg i snitt)
            ax.add_patch(mpatches.Rectangle(
                (-WT, UC+SPL + ap_sill), WT, ap_h,
                facecolor="white", edgecolor=CYAN,
                linewidth=1.8, zorder=6))
            ax.text(-WT/2, UC+SPL + ap_sill + ap_h/2,
                    f"{ap_lbl}\n{round(ap_h*1000)} mm",
                    ha="center", va="center", fontsize=5, color=CYAN,
                    fontweight="bold", zorder=7,
                    bbox=dict(fc="white", ec="none", pad=0.2, alpha=0.9))
            _dv(ax, UC+SPL + ap_sill, UC+SPL + ap_sill + ap_h, -DIM_OFF - 0.40,
                f"{round(ap_h*1000)} mm", ex=-DIM_OFF - 0.40, col=CYAN, fs=5.5)
            if ap_sill > 0:
                _dv(ax, UC+SPL, UC+SPL + ap_sill, -DIM_OFF - 0.65,
                    f"{round(ap_sill*1000)} mm", ex=-DIM_OFF - 0.65, col="#555", fs=5.5)

    H_mm  = round(H*1000); WT_mm = round(WT*1000)

    # ── Horizontal mål ────────────────────────────────────────────────────────
    _dh(ax, -WT, L+WT, 0, f"{(L+2*WT)*1000:.0f} mm", ey=-DIM_OFF, total=True, fs=10)
    _dh(ax, -WT, 0, 0, f"{WT_mm} mm",                 ey=-DIM_OFF-0.55)
    _dh(ax, L, L+WT, 0, f"{WT_mm} mm",                 ey=-DIM_OFF-0.55)

    # ── Vertikal mål ──────────────────────────────────────────────────────────
    _dv(ax, 0, UC+H+TAK, L+WT,
        f"{round((UC+H+TAK)*1000)} mm utvendig", ex=L+DIM_OFF+0.35, total=True, fs=10)
    _dv(ax, UC+SPL, UC+H, 0, f"{round((H-SPL)*1000)} mm innvendig", ex=-DIM_OFF-0.38)
    if IS_FRYS:
        _dv(ax, 0, UC, L, f"{round(UC*1000)} mm gulvoppbygging", ex=L+DIM_OFF)
    else:
        _dv(ax, 0, CHANNEL_HEIGHT, L, f"{round(CHANNEL_HEIGHT*1000)} mm U-kanal", ex=L+DIM_OFF)
    _dv(ax, UC+H, UC+H+TAK,        L, f"{WT_mm} mm tak",ex=L+DIM_OFF)

    if IS_FRYS:
        ax.text(L/2, -1.05, f"Gulv: 22 mm lekter + {round(WT*1000)} mm panel; vegger på panel, 12 mm gulvplate innenfor",
                ha="center", fontsize=8, color="#365c37")

    # ── Skrå hjørner ──────────────────────────────────────────────────────────
    pts_ccw = ensure_ccw(pts); a_ccw = np.array(pts_ccw)
    for i in range(len(a_ccw)):
        pm = a_ccw[(i-1)%len(a_ccw)]; pc = a_ccw[i]; pn = a_ccw[(i+1)%len(a_ccw)]
        v1 = pc-pm; v2 = pn-pc
        ang = math.degrees(math.acos(max(-1, min(1,
            np.dot(v1, v2)/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-9)))))
        if abs(ang-90) > 5:
            ax.text(0.12, UC+H*0.88, f"Hjørnevinkel ≈ {180-ang:.1f}°",
                    fontsize=6, color=RED, zorder=10,
                    bbox=dict(fc="#fff3cd", ec=RED, pad=1.5))

    ax.text(L/2, -DIM_OFF-1.0,
            f"Prinsippsnitt langs {vl_left}  –  {seksjon}  –  {DRAWING_SCALE}",
            ha="center", va="top", fontsize=9, fontweight="bold", color=BLUE)
    # Tittelblokken må stå klar av det ytterste høyde-målet ("... mm tot.",
    # ex=L+DIM_OFF+0.35) – ellers stipler målsettingen inn i boksen.
    _tegn_fig_title_block(fig, {**info, "ttype": f"Prinsippsnitt langs {vl_left}"})

    ax.set_xlim(-DIM_OFF-0.9, L+DIM_OFF+1.0)
    ax.set_ylim(-DIM_OFF-1.3, UC+H+TAK+DIM_OFF+0.5)
    ax.set_aspect("equal"); ax.axis("off")
    fig.subplots_adjust(left=0.02, right=0.79, top=0.97, bottom=0.03)
    return fig


# ══ PRODUKSJONSTEGNINGER ═════════════════════════════════════════════════════

def _panel_to_local(polygon_world: list) -> np.ndarray:
    """
    Transformerer et panel-polygon til lokale koordinater med
    den lengste kanten langs positiv X-akse og massesenter i første kvadrant.
    """
    pts = np.array(polygon_world, dtype=float)
    n   = len(pts)
    # Finn lengste kant → bruk som X-akse
    best_len = -1.0; best_i = 0
    for i in range(n):
        L = float(np.linalg.norm(pts[(i+1) % n] - pts[i]))
        if L > best_len:
            best_len = L; best_i = i
    p0   = pts[best_i]
    x_ax = (pts[(best_i+1) % n] - p0) / (best_len + 1e-9)
    y_ax = np.array([-x_ax[1], x_ax[0]])
    local = np.column_stack([(pts - p0) @ x_ax, (pts - p0) @ y_ax])
    # Sørg for positiv Y (panel opp)
    if np.mean(local[:, 1]) < 0:
        local[:, 1] = -local[:, 1]
    return local


def _edge_kind(local_pts: np.ndarray, panel_width_mm: int, idx: int) -> str:
    """
    Klassifiserer en kant: 'fabrikk' (rett kant), 'rett kapp', 'vinklet kapp'.
    Fabrikk-kanter er de to lange sidene (spenn-retning).
    """
    n  = len(local_pts)
    p1 = local_pts[idx]; p2 = local_pts[(idx+1) % n]
    L_mm = np.linalg.norm(p2 - p1) * 1000
    dx   = p2 - p1
    angle_deg = abs(math.degrees(math.atan2(dx[1], dx[0])))
    # Rett horisontale/vertikale kanter med riktig lengde = fabrikkant
    is_horiz = angle_deg < 2 or angle_deg > 178
    is_vert  = 88 < angle_deg < 92
    if is_vert and abs(L_mm - panel_width_mm) < 5:
        return "fabrikk"
    if is_horiz or is_vert:
        return "rett kapp"
    return "vinklet kapp"


def _draw_one_panel(ax, local_pts: np.ndarray, panel, panel_key: str,
                    panel_number: int, category: str = "Tak", cutouts: list | None = None):
    """Tegner én panel-detalj med alle mål, vinkler og produksjonsnotes."""
    n = len(local_pts)
    WT_mm = PANEL_DB[panel_key]["t"]

    # ── Panelform ─────────────────────────────────────────────────────────────
    is_kapp = "kapp" in panel.kind.lower() or "start" in panel.kind.lower()
    fc = "#edf3f5"
    ec = TOTAL_DIM_COL

    ax.add_patch(MplPolygon(local_pts, closed=True, facecolor=fc,
                             edgecolor=ec, linewidth=1.8, zorder=2))
    ax.add_patch(MplPolygon(local_pts, closed=True, facecolor="none",
                             edgecolor="#777", linewidth=0,
                             hatch="////" if not is_kapp else ".....",
                             zorder=2.5, alpha=0.35))

    center = local_pts.mean(axis=0)
    xmn, ymn = local_pts.min(axis=0)
    xmx, ymx = local_pts.max(axis=0)

    # ── Utsparinger (dører og åpninger) ───────────────────────────────────────
    for lane, (lx, ly, lw, lh, cut_lbl) in enumerate(cutouts or []):
        ax.add_patch(mpatches.Rectangle(
            (lx, ly), lw, lh,
            facecolor="white", edgecolor="#000", linewidth=1.4,
            linestyle="--", zorder=5))
        ax.text((xmn+xmx)/2, ymx + .65 + lane*.20, cut_lbl,
                ha="center", va="center", fontsize=9,
                color="#000", fontweight="bold", zorder=6)
        # Målpiler for utsparing
        _dv(ax, ly, ly + lh, lx + lw, f"{round(lh*1000)} mm",
            ex=xmx + .65 + lane*.35, col=DIM_COL, fs=9)
        _dh(ax, lx, lx + lw, ly, f"{round(lw*1000)} mm",
            ey=ymn - .55 - lane*.32, col=DIM_COL, fs=9)
        if ly > 0.001:
            _dv(ax, 0, ly, lx, f"{round(ly*1000)} mm",
                ex=xmn - .65 - lane*.35, col=DIM_COL, fs=9)

    # ── Kantmål og klassifisering ──────────────────────────────────────────────
    for i in range(n):
        p1  = local_pts[i]; p2 = local_pts[(i+1) % n]
        L_m = float(np.linalg.norm(p2 - p1))
        if L_m < 0.001:
            continue
        L_mm = L_m * 1000
        dx   = (p2 - p1) / L_m
        perp = np.array([-dx[1], dx[0]])

        # Utoverretning (vekk fra massesenter)
        mid          = (p1 + p2) / 2
        to_center    = center - mid
        if np.dot(perp, to_center) > 0:
            perp = -perp

        kind = _edge_kind(local_pts, panel.width_mm, i)
        dim_col = TOTAL_DIM_COL
        dim_off = 0.50 if L_m < 0.40 else 0.23

        # Forlengelseslinjer
        ax.plot([p1[0], p1[0]+perp[0]*dim_off],
                [p1[1], p1[1]+perp[1]*dim_off], color=dim_col, lw=0.5, zorder=6)
        ax.plot([p2[0], p2[0]+perp[0]*dim_off],
                [p2[1], p2[1]+perp[1]*dim_off], color=dim_col, lw=0.5, zorder=6)
        # Målpil
        s_dim = p1 + perp * dim_off; e_dim = p2 + perp * dim_off
        ax.annotate("", xy=(e_dim[0], e_dim[1]), xytext=(s_dim[0], s_dim[1]),
                    arrowprops=dict(arrowstyle="<->", shrinkA=0, shrinkB=0, color=dim_col,
                                   lw=1.6, mutation_scale=8), zorder=7)
        angle = math.degrees(math.atan2(dx[1], dx[0]))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        ax.text(mid[0]+perp[0]*(dim_off+0.10),
                mid[1]+perp[1]*(dim_off+0.10),
                f"{L_mm:.0f} mm",
                ha="center", va="center", fontsize=10, rotation=angle,
                color=dim_col, fontweight="bold", zorder=8,
                bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.9))

    for i in range(n):
        _corner_angle(ax, local_pts, i, radius=.12)

    # ── Panel-ID i midten ─────────────────────────────────────────────────────
    ax.text(center[0], center[1], panel.name,
            ha="center", va="center", fontsize=20, color=BLUE,
            alpha=0.18, fontweight="bold", zorder=3)

    # ── Inforamme (nedre del av subplot) ──────────────────────────────────────
    xmn = local_pts[:,0].min(); xmx = local_pts[:,0].max()
    ymn = local_pts[:,1].min(); ymx = local_pts[:,1].max()
    pad_x = (xmx-xmn)*0.12 + 0.25
    pad_y = (ymx-ymn)*0.12 + 0.25

    # Produksjonstabell under panel
    tbl_y  = ymn - pad_y - 0.20
    if cutouts:
        tbl_y = min(tbl_y, ymn - .75 - (len(cutouts)-1)*.32)
    tbl_w  = max(5.0, xmx - xmn)
    tbl_x  = (xmn+xmx-tbl_w)/2
    col1_w = tbl_w * 0.38

    rows = [
        ("Elementnavn",      panel.name),
        ("Type",             panel.kind),
        ("Kategori",         category),
        ("Standardbredde",   f"{panel.width_mm} mm"),
        ("Spenn (lengde)",   f"{panel.span_mm} mm"),
        ("Areal",            f"{panel.area_m2:.3f} m²"),
        ("Paneltype",        PANEL_DB[panel_key]["label"]),
        ("Tykkelse",         f"{WT_mm} mm"),
        ("Antall hjørner",   str(n)),
        ("Produksjon nr.",   str(panel_number)),
    ]

    row_h = max(0.20, tbl_w * 0.028)
    for ri, (lbl, val) in enumerate(rows):
        y0 = tbl_y - ri * row_h
        bg = "#f0f4f8" if ri % 2 == 0 else "white"
        ax.add_patch(mpatches.Rectangle(
            (tbl_x, y0 - row_h), tbl_w, row_h,
            facecolor=bg, edgecolor="#c8d8e8", lw=0.4, zorder=15))
        ax.text(tbl_x + 0.04, y0 - row_h/2, lbl,
                ha="left", va="center", fontsize=9, color=BLUE,
                fontweight="bold", zorder=16)
        ax.text(tbl_x + col1_w + 0.04, y0 - row_h/2, val,
                ha="left", va="center", fontsize=9, color="#111", zorder=16)

    tbl_bot = tbl_y - len(rows) * row_h

    leg_y = tbl_bot - 0.15

    extra = len(cutouts or [])*.35
    ax.set_xlim(min(xmn-pad_x-extra,tbl_x-0.15), max(xmx+pad_x+0.35+extra,tbl_x+tbl_w+0.15))
    ax.set_ylim(leg_y - 0.18, ymx + max(pad_y + .20, .65 + len(cutouts)*.20 if cutouts else 0))
    ax.set_aspect("equal"); ax.axis("off")


def stramo_produksjonstegninger(
    pts,
    H: float,
    pw_m: float,
    panel_key: str,
    rom_type: str,
    info: dict,
    bare_tilpassede: bool = False,
    dorer: list | None = None,
    apninger: list | None = None,
    excluded_walls=(),
) -> list[plt.Figure]:
    """
    Genererer ett figur-objekt per side med produksjonstegninger.
    Hvert element vises med:
      • Nøyaktig polygon i lokal flat-layout
      • Alle kantlengder i mm
      • Alle hjørnevinkler i grader
      • Kanttype: F (fabrikk), RK (rett kapp), VK (vinklet kapp)
      • Produksjonstabell med snittvinkel for skrå kanter
    Returnerer liste med plt.Figure (én per side, 2 panel/side).
    """
    pw_mm   = round(pw_m * 1000)
    is_frys = "Fryserom" in rom_type
    dorer   = dorer   or []
    apninger = apninger or []

    # Hent alle paneler
    tak_p  = generate_roof_floor_panels(roof_outline(pts,PANEL_DB[panel_key]["t"]/1000,rom_type), pw_mm, prefix="T",  label="Tak")
    gulv_p = generate_roof_floor_panels(floor_outline(pts, PANEL_DB[panel_key]["t"]/1000), pw_mm, prefix="G",  label="Gulv") if is_frys else []

    vegg_p=[]
    for panel in wall_panel_layout(pts,pw_mm,PANEL_DB[panel_key]['t']/1000,excluded_walls):
        _make_vegg(vegg_p,int(panel['name'][1:]),panel['wall'],panel['width_mm'],
                   round(H*1000),pw_mm,x_start_mm=panel['start_mm'],
                   rest=panel['kind']=='Rest fra forrige')

    # Samle alt – vegg-tupler er (panel, wall_idx, x_start_mm), tak/gulv er bare panel
    alle = (
        [("Tak",  p, None, 0) for p in tak_p] +
        [("Gulv", p, None, 0) for p in gulv_p] +
        [("Vegg", p, wi, xs) for p, wi, xs in vegg_p]
    )

    if bare_tilpassede:
        alle = [(cat, p, wi, xs) for cat, p, wi, xs in alle
                if "kapp" in p.kind.lower()
                or "start" in p.kind.lower()
                or len(p.polygon) > 4]

    if not alle:
        return []

    def _cutouts_for_panel(cat, wall_idx, x_start_mm, width_mm, height_mm):
        """Returnerer liste med (lx, ly, lw, lh, lbl) i meter relativt til panelet."""
        if cat != "Vegg" or wall_idx is None:
            return []
        cuts = []
        x_end_mm = x_start_mm + width_mm
        # Dører
        for entry in dorer:
            de = _door_entry(entry)
            dk, ant, w_idx, off_m, _hng = de
            if int(w_idx) != wall_idx or ant <= 0:
                continue
            from database import DOR_DB
            d = DOR_DB[dk]
            d_off_mm = off_m * 1000
            d_w_mm   = d["bw"]
            d_h_mm   = d["bh"]
            for _ in range(min(int(ant), 6)):
                lo = max(d_off_mm, x_start_mm) - x_start_mm
                hi = min(d_off_mm + d_w_mm, x_end_mm) - x_start_mm
                if hi > lo + 1:
                    cuts.append((lo/1000, floor_depth(rom_type), (hi-lo)/1000, d_h_mm/1000,
                                 f"Dør {d_w_mm}×{d_h_mm}"))
                d_off_mm += d_w_mm + 200
        # Åpninger / utsparinger
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, ap_lbl = ap
            if int(ap_wall) != wall_idx:
                continue
            d_off_mm = ap_off * 1000
            d_w_mm   = ap_w  * 1000
            lo = max(d_off_mm, x_start_mm) - x_start_mm
            hi = min(d_off_mm + d_w_mm, x_end_mm) - x_start_mm
            if hi > lo + 1:
                cuts.append((lo/1000, floor_depth(rom_type) + ap_sill, (hi-lo)/1000, ap_h,
                             f"{ap_lbl} {round(d_w_mm)}×{round(ap_h*1000)}"))
        return cuts

    # One production drawing for identical whole elements, retaining openings separately.
    from dataclasses import replace
    grouped = {}; standard_counts = {}; compact = []
    for cat,p,wi,xs in alle:
        local = _panel_to_local(p.polygon)
        cuts = _cutouts_for_panel(cat,wi,xs,p.width_mm,p.span_mm)
        standard = len(local)==4 and p.width_mm==pw_mm and "hel" in p.kind.lower() and not cuts
        if standard:
            key = (cat,tuple(map(tuple,np.round(local,6))))
            if key in grouped:
                standard_counts[grouped[key]] += 1
                continue
            label = "Std " + {"Vegg":"vegg","Tak":"tak","Gulv":"gulv"}[cat]
            label += f" {p.span_mm}×{p.width_mm}"
            grouped[key] = label; standard_counts[label] = 1
            p = replace(p,name=label)
        compact.append((cat,p,wi,xs))
    alle = compact

    PANELS_PER_PAGE = 2
    total_sider = math.ceil(len(alle) / PANELS_PER_PAGE)
    figures = []
    num = 0

    for page_start in range(0, len(alle), PANELS_PER_PAGE):
        page = alle[page_start: page_start + PANELS_PER_PAGE]
        ncols = 1; nrows = 2
        fig, axes = plt.subplots(nrows, ncols,
                                  figsize=(18, 14))
        fig.patch.set_facecolor("white")

        # Sidetittel – samme tittelblokk (logo + prosjektinfo) som de andre
        # tegningene, plassert øverst til høyre. Grid med paneler reserverer
        # derfor plass i høyre marg (se tight_layout-rect nedenfor).
        side_nr = len(figures) + 1
        fig.text(0.40, 0.975, "PRODUKSJONSTEGNINGER",
                 ha="center", va="top", fontsize=15, fontweight="bold", color=BLUE)
        fig.text(0.40, 0.950,
                 f"Panel: {PANEL_DB[panel_key]['label']}  ·  Side {side_nr} av {total_sider}",
                 ha="center", va="top", fontsize=10, color="#444")

        axes_flat = np.array(axes).flatten()
        for cell, (cat, p, wi, xs) in enumerate(page):
            num += 1
            ax = axes_flat[cell]
            # Wall cut-outs use X across the panel and Y up from its base.
            # Keep that coordinate frame rather than rotating only the outline.
            local = np.asarray(p.polygon) if cat == "Vegg" else _panel_to_local(p.polygon)
            cuts = _cutouts_for_panel(cat, wi, xs, p.width_mm, p.span_mm)
            _draw_one_panel(ax, local, p, panel_key, num, category=cat, cutouts=cuts)
            ax.set_title(f"  {cat}: {p.name}  –  {standard_counts.get(p.name,1)} stk  [nr. {num}]",
                         fontsize=12, color=BLUE, fontweight="bold", pad=8, loc="left")

        # Skjul tomme celler
        for cell in range(len(page), len(axes_flat)):
            axes_flat[cell].axis("off")

        # Høyre marg (rect-bredde 0.80) er reservert til tittelblokken.
        fig.tight_layout(rect=[0.01, 0.02, 0.79, 0.90], pad=1.2, h_pad=2.5)
        _tegn_fig_title_block(fig, {**info, "ttype": "Produksjonstegning"})
        figures.append(fig)

    return figures


def _make_vegg(out_list, el_nr, wall_idx, width_mm, height_mm, std_width_mm,
               x_start_mm=0, rest=False):
    """Lag et syntetisk vegg-panel for produksjonstegning."""
    from panel_engine import RoofFloorPanel
    w = width_mm / 1000.0; h = height_mm / 1000.0
    polygon = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    kind    = ("Vegg – rest fra forrige" if rest
               else ("Vegg – hel" if width_mm == std_width_mm else "Vegg – kapp"))
    note    = (f"Kapp {width_mm} mm – rett snitt" if "kapp" in kind.lower()
               else "Standard element")
    out_list.append((RoofFloorPanel(
        name=f"V{el_nr}", kind=kind,
        width_mm=width_mm, span_mm=height_mm,
        area_m2=round(w * h, 3),
        polygon=polygon, note=note,
    ), wall_idx, x_start_mm))


def fig2png(fig, dpi: int = 200) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    return buf
