from __future__ import annotations
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
from geometry import wall_lengths, ensure_ccw, Point
from panel_engine import generate_roof_floor_panels, main_axis_from_longest_wall

# ── Farger og konstanter ──────────────────────────────────────────────────────
DIM_COL   = "#000000"
DIM_FS    = 8.0
BLUE      = "#000000"
WALL_FILL = "#e8e8e8"
WALL_EDGE = "#000000"
HATCH_COL = "#555"
RED       = "#000000"
GREEN     = "#000000"
ORANGE    = "#555555"


# ── Hjelpefunksjoner ──────────────────────────────────────────────────────────

def _door_entry(d):
    """Normaliserer dør-oppføring til (dk, ant, wall_idx, offset_m, hengsel)."""
    if len(d) == 2:
        return (d[0], d[1], 0, 0.35, "Venstre")
    if len(d) == 4:
        return (d[0], d[1], int(d[2]), float(d[3]), "Venstre")
    return (d[0], d[1], int(d[2]), float(d[3]), str(d[4]))


def _dh(ax, x1, x2, y, lbl, ey=None, fs=DIM_FS, col=None):
    """Horisontal målpil med stiplede forlengelseslinjer."""
    col = col or DIM_COL
    ey  = y if ey is None else ey
    ax.plot([x1, x1], [y, ey], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.plot([x2, x2], [y, ey], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.annotate("", xy=(x2, ey), xytext=(x1, ey),
                arrowprops=dict(arrowstyle="<->", color=col, lw=1.1, mutation_scale=8), zorder=9)
    ax.text((x1+x2)/2, ey + 0.03, lbl, ha="center", va="bottom",
            fontsize=fs, color=col, fontweight="bold", zorder=10)


def _dv(ax, y1, y2, x, lbl, ex=None, fs=DIM_FS, col=None):
    """Vertikal målpil med stiplede forlengelseslinjer."""
    col = col or DIM_COL
    ex  = x if ex is None else ex
    ax.plot([x, ex], [y1, y1], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.plot([x, ex], [y2, y2], color=col, lw=0.5, linestyle="--", dashes=(3,2), zorder=8)
    ax.annotate("", xy=(ex, y2), xytext=(ex, y1),
                arrowprops=dict(arrowstyle="<->", color=col, lw=1.1, mutation_scale=8), zorder=9)
    ax.text(ex + 0.03, (y1+y2)/2, lbl, ha="left", va="center",
            fontsize=fs, color=col, fontweight="bold", rotation=90, zorder=10)


def _dim_along_wall(ax, p1, p2, lbl, offset=0.30, fs=DIM_FS, col=None):
    """Målpil langs en skrå vegg, offset perpendikulært utover."""
    col = col or DIM_COL
    p1, p2 = np.array(p1), np.array(p2)
    L = np.linalg.norm(p2 - p1)
    if L < 1e-6:
        return
    dx = (p2 - p1) / L
    perp = np.array([-dx[1], dx[0]])
    s = p1 + perp * (-offset)
    e = p2 + perp * (-offset)
    ax.plot([p1[0], s[0]], [p1[1], s[1]], color=col, lw=0.4, zorder=8)
    ax.plot([p2[0], e[0]], [p2[1], e[1]], color=col, lw=0.4, zorder=8)
    ax.annotate("", xy=(e[0], e[1]), xytext=(s[0], s[1]),
                arrowprops=dict(arrowstyle="<->", color=col, lw=0.65, mutation_scale=5), zorder=9)
    mid   = (s + e) / 2
    angle = math.degrees(math.atan2(dx[1], dx[0]))
    # Normaliser slik at teksten alltid er lesbar (aldri opp-ned)
    if angle > 90:
        angle -= 180
    elif angle < -90:
        angle += 180
    ax.text(mid[0] - perp[0]*0.14, mid[1] - perp[1]*0.14, lbl,
            ha="center", va="center", fontsize=fs, rotation=angle,
            color=col, zorder=10, bbox=dict(fc="white", ec="none", pad=0.5))


def _corner_angle(ax, pts_a, i, radius=0.22, fs=5.8):
    """Tegner vinkelmerke og grader ved hjørne i."""
    nn  = len(pts_a)
    pc  = pts_a[i]
    pm  = pts_a[(i - 1) % nn]
    pn  = pts_a[(i + 1) % nn]
    v1  = pm - pc
    v2  = pn - pc
    L1  = np.linalg.norm(v1); L2 = np.linalg.norm(v2)
    if L1 < 1e-6 or L2 < 1e-6:
        return
    v1n = v1 / L1; v2n = v2 / L2
    dot = float(np.clip(np.dot(v1n, v2n), -1, 1))
    ang = math.degrees(math.acos(dot))

    a1  = math.degrees(math.atan2(v1n[1], v1n[0]))
    a2  = math.degrees(math.atan2(v2n[1], v2n[0]))
    # Sørg for at vi tegner den innvendige vinkelen
    if (a2 - a1) % 360 > 180:
        a1, a2 = a2, a1
    ax.add_patch(Arc(tuple(pc), radius*2, radius*2,
                     angle=0, theta1=a1, theta2=a2,
                     color="#555", lw=0.7, zorder=12))
    # Etikett midt i vinkelbuen
    a_mid  = math.radians((a1 + a2) / 2)
    lx     = pc[0] + (radius + 0.13) * math.cos(a_mid)
    ly     = pc[1] + (radius + 0.13) * math.sin(a_mid)
    ax.text(lx, ly, f"{ang:.1f}°", ha="center", va="center",
            fontsize=fs, color="#333", zorder=13,
            bbox=dict(fc="white", ec="none", pad=0.2))


def _door_dim(ax, p1d, dx_n, offset_m, dw, wall_perp, dim_side=1.0):
    """
    Tegner mål fra hjørnet til døren og dørens bredde.
    dim_side: +1 = utenfor (nedre) mål, -1 = inne
    """
    off_base = 0.25 * dim_side
    off_door = 0.50 * dim_side

    door_s = p1d + dx_n * offset_m
    door_e = p1d + dx_n * (offset_m + dw)

    # Avstand hjørne → dørstart
    if offset_m > 0.02:
        s_off = np.array(p1d)   + wall_perp * off_base
        e_off = np.array(door_s) + wall_perp * off_base
        ax.plot([p1d[0], s_off[0]], [p1d[1], s_off[1]], color="#555", lw=0.4, zorder=11)
        ax.plot([door_s[0], e_off[0]], [door_s[1], e_off[1]], color="#555", lw=0.4, zorder=11)
        ax.annotate("", xy=(e_off[0], e_off[1]), xytext=(s_off[0], s_off[1]),
                    arrowprops=dict(arrowstyle="<->", color="#555", lw=0.55, mutation_scale=5), zorder=11)
        mid = (s_off + e_off) / 2
        angle = math.degrees(math.atan2(dx_n[1], dx_n[0]))
        ax.text(mid[0] - wall_perp[0]*0.12, mid[1] - wall_perp[1]*0.12,
                f"{round(offset_m*1000)} mm",
                ha="center", va="center", fontsize=5.5, rotation=angle,
                color="#555", zorder=12, bbox=dict(fc="white", ec="none", pad=0.3))

    # Dørbredde
    s_off2 = np.array(door_s) + wall_perp * off_door
    e_off2 = np.array(door_e) + wall_perp * off_door
    ax.plot([door_s[0], s_off2[0]], [door_s[1], s_off2[1]], color=RED, lw=0.4, zorder=11)
    ax.plot([door_e[0], e_off2[0]], [door_e[1], e_off2[1]], color=RED, lw=0.4, zorder=11)
    ax.annotate("", xy=(e_off2[0], e_off2[1]), xytext=(s_off2[0], s_off2[1]),
                arrowprops=dict(arrowstyle="<->", color=RED, lw=0.55, mutation_scale=5), zorder=11)
    mid2  = (s_off2 + e_off2) / 2
    angle = math.degrees(math.atan2(dx_n[1], dx_n[0]))
    ax.text(mid2[0] - wall_perp[0]*0.12, mid2[1] - wall_perp[1]*0.12,
            f"Dør {round(dw*1000)} mm",
            ha="center", va="center", fontsize=5.5, rotation=angle,
            color=RED, zorder=12, bbox=dict(fc="white", ec="none", pad=0.3))


def _title_block(ax, xmn, xmx, ymn, ymx, info):
    bw = 3.2; mg = 0.5; tx = xmx + mg; h = ymx - ymn
    ax.add_patch(mpatches.FancyBboxPatch(
        (tx, ymn), bw, h, boxstyle="square,pad=0",
        facecolor="white", edgecolor="black", linewidth=1.0, zorder=20))
    rows = [
        ("",           "STRAMO",            0.94, True,  14),
        ("Prosjekt",   info["navn"],         0.82, True,   9),
        ("Tegning",    info["ttype"],        0.72, False,  8),
        ("Prosjektnr", info["pnr"],          0.62, False,  8),
        ("Tegningsnr", info["tnr"],          0.52, False,  8),
        ("Dato",       info["dato"],         0.42, False,  8),
        ("Målestokk",  info["maal"],         0.32, False,  8),
        ("Areal",      f"{info['A']:.2f} m²",0.22, False,  8),
        ("Omkrets",    f"{info['P']:.2f} m", 0.12, False,  8),
    ]
    for lbl, val, frac, bold, fs in rows:
        yp = ymn + h * frac
        if lbl:
            ax.text(tx+0.1, yp+0.04, lbl, fontsize=5, color="#666", va="bottom", zorder=21)
        ax.text(tx+0.1, yp-0.02, val, fontsize=fs,
                fontweight="bold" if bold else "normal",
                color=BLUE if bold else "black", va="top", zorder=21)
        ax.plot([tx, tx+bw], [yp, yp], color="#aaa", lw=0.4, zorder=21)
    return tx + bw


# ══ PLANTEGNING ══════════════════════════════════════════════════════════════

def stramo_plan(pts, H, pw_m, dorer, info, bakgrunn=None, apninger=None):
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

    fig, ax = plt.subplots(figsize=(18, 11))
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

    WT = 0.09

    # ── Veggskal ──────────────────────────────────────────────────────────────
    ax.add_patch(MplPolygon(pts_a, closed=True, facecolor=WALL_FILL,
                             edgecolor=WALL_EDGE, linewidth=1.8, zorder=2))
    ax.add_patch(MplPolygon(pts_a, closed=True, facecolor="none",
                             edgecolor=HATCH_COL, linewidth=0,
                             hatch="////", zorder=2.5, alpha=0.55))
    # Innvendig polygon
    inn = []
    for i in range(nn):
        p1 = pts_a[i]; p2 = pts_a[(i+1)%nn]; pm = pts_a[(i-1)%nn]
        d1 = p2-p1; d1 /= np.linalg.norm(d1)+1e-9
        d0 = p1-pm; d0 /= np.linalg.norm(d0)+1e-9
        n1 = np.array([-d1[1], d1[0]]); n0 = np.array([-d0[1], d0[0]])
        na = (n1+n0)/2; na /= np.linalg.norm(na)+1e-9
        inn.append(p1 + na*WT)
    ax.add_patch(MplPolygon(np.array(inn), closed=True, facecolor="white",
                             edgecolor=WALL_EDGE, linewidth=0.9, zorder=3))

    # ── Elementoppdeling på vegger ────────────────────────────────────────────
    el_nr = 1; rest_mm = 0; pw_mm = round(pw_m * 1000)
    for i in range(nn):
        p1 = pts_a[i]; p2 = pts_a[(i+1)%nn]; L = wls[i]
        if L < 1e-6:
            continue
        dx_n = (p2-p1)/L; perp = np.array([-dx_n[1], dx_n[0]])
        inw  = perp * (WT*0.5 + 0.05)
        L_mm = round(L * 1000); brukt_mm = 0; positions = []

        if rest_mm > 0:
            bredde = min(rest_mm, L_mm)
            positions.append((0, bredde/L_mm, f"V{el_nr}", "rest"))
            brukt_mm += bredde; el_nr += 1; rest_mm = max(rest_mm-L_mm, 0)

        while brukt_mm + pw_mm <= L_mm:
            t0 = brukt_mm/L_mm; t1 = (brukt_mm+pw_mm)/L_mm
            positions.append((t0, t1, f"V{el_nr}", "hel"))
            brukt_mm += pw_mm; el_nr += 1

        remaining = L_mm - brukt_mm
        if remaining > 0:
            positions.append((brukt_mm/L_mm, 1.0, f"V{el_nr}", "kapp"))
            el_nr += 1; rest_mm = pw_mm - remaining

        for t0, t1, lbl, typ in positions:
            if t1 < 0.999:
                px = p1[0]+t1*(p2[0]-p1[0]); py = p1[1]+t1*(p2[1]-p1[1])
                tk_v = perp * 0.065
                ax.plot([px-tk_v[0]/2, px+tk_v[0]/2],
                        [py-tk_v[1]/2, py+tk_v[1]/2],
                        color="black", lw=0.9, zorder=4)
            mid_t = (t0+t1)/2
            mx = p1[0]+mid_t*(p2[0]-p1[0]); my = p1[1]+mid_t*(p2[1]-p1[1])
            col = RED if typ == "kapp" else (GREEN if typ == "rest" else BLUE)
            ax.text(mx+inw[0], my+inw[1], lbl, ha="center", va="center",
                    fontsize=5.8, color=col, fontweight="bold", zorder=5)

    # ── Dørmarkering med mål ──────────────────────────────────────────────────
    door_cursors = {}
    for entry in dorer:
        dk, ant, wall_idx, offset_m, hengsel = _door_entry(entry)
        if ant <= 0 or wall_idx >= nn or wls[wall_idx] < 1e-6:
            continue
        p1d   = pts_a[wall_idx]; p2d = pts_a[(wall_idx+1) % nn]
        vL    = wls[wall_idx]
        dx_n  = (p2d - p1d) / vL
        perp  = np.array([-dx_n[1], dx_n[0]])   # innadrettet (CCW polygon)
        outw  = -perp                              # utoverretning
        cursor = door_cursors.get(wall_idx, offset_m)
        dw     = DOR_DB[dk]["bw"] / 1000
        door_angle = math.degrees(math.atan2(dx_n[1], dx_n[0]))

        for idx_d in range(min(ant, 4)):
            s = p1d + dx_n * cursor
            e = p1d + dx_n * (cursor + dw)
            # Åpning i veggen
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

            leaf_end = hinge + outw * dw

            ax.add_patch(Arc(tuple(hinge), dw*2, dw*2,
                             angle=arc_ang, theta1=t1, theta2=t2,
                             color=WALL_EDGE, lw=0.8, zorder=7))
            # Dørblad i åpen posisjon (stiplet linje utover)
            ax.plot([hinge[0], leaf_end[0]], [hinge[1], leaf_end[1]],
                    color=WALL_EDGE, lw=0.6, linestyle="--", zorder=7)

            # Mål-piler: hjørne→dør og dørbredde
            _door_dim(ax, p1d + dx_n * (cursor - offset_m if idx_d > 0 else 0),
                      dx_n, cursor if idx_d == 0 else offset_m,
                      dw, perp * -1)

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
            perp_a = np.array([-da[1], da[0]])
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
        # Hjørnepunkt-label
        ax.text(pts_a[i][0], pts_a[i][1], f" P{i+1}",
                fontsize=5, color="#444", zorder=14,
                bbox=dict(fc="white", ec="none", pad=0.2))

    # ── Målsetting ────────────────────────────────────────────────────────────
    xmn, xmx = xs.min(), xs.max(); ymn, ymx = ys.min(), ys.max()
    DIM_OFF = 0.55

    # Ytre totalmål
    _dh(ax, xmn, xmx, ymn, f"{(xmx-xmn)*1000:.0f} mm", ey=ymn - DIM_OFF - 0.45)
    _dv(ax, ymn, ymx, xmx, f"{(ymx-ymn)*1000:.0f} mm", ex=xmx + DIM_OFF + 0.45)

    # Per-vegg mål (offset 0.30 utover fra veggen)
    for i in range(nn):
        p1 = pts_a[i]; p2 = pts_a[(i+1)%nn]; L = wls[i]
        if L < 0.05:
            continue
        _dim_along_wall(ax, p1, p2, f"{L*1000:.0f} mm", offset=0.30)

    # Koordinatboks for hjørnepunkter (tabell nede til venstre)
    _corner_table(ax, pts_a, xmn, ymn)

    # N-pil
    ax.annotate("", xy=(xmn+0.35, ymx+0.40), xytext=(xmn+0.35, ymx+0.10),
                arrowprops=dict(arrowstyle="-|>", color="black", lw=1.4, mutation_scale=12), zorder=15)
    ax.text(xmn+0.35, ymx+0.52, "N", ha="center", va="bottom",
            fontsize=11, fontweight="bold", zorder=15)

    xright = _title_block(ax, xmn, xmx, ymn, ymx, info)
    ax.text((xmn+xmx)/2, ymn - DIM_OFF - 1.10,
            f"PLANTEGNING  –  {info['maal']}",
            ha="center", va="top", fontsize=9, fontweight="bold", color=BLUE)

    ax.set_xlim(xmn - DIM_OFF - 1.2, xright + 0.25)
    ax.set_ylim(ymn - DIM_OFF - 1.8, ymx + DIM_OFF + 1.0)
    ax.set_aspect("equal"); ax.axis("off")
    return fig


def _corner_table(ax, pts_a, xmn, ymn):
    """Tabell med hjørnekoordinater."""
    rows = [f"P{i+1}: ({p[0]:.3f}, {p[1]:.3f})" for i, p in enumerate(pts_a)]
    tx = xmn; ty = ymn - 1.05
    ax.text(tx, ty, "Hjørnepunkter (m)", fontsize=5.5, color=BLUE,
            fontweight="bold", va="top", zorder=14)
    for j, r in enumerate(rows):
        ax.text(tx, ty - 0.13*(j+1), r, fontsize=5, color="#333",
                va="top", zorder=14,
                bbox=dict(fc="white", ec="none", pad=0.1))


# ══ TAKTEGNING ═══════════════════════════════════════════════════════════════

def stramo_tak(pts, H, pw_m, dorer, info, rom_type="Kjølerom", panel_key="PIR 80 mm"):
    """
    Detaljert taktegning (sett ovenfra):
    • Alle takelementer (T1, T2 …) med riktig polygon klippet mot rommets form
    • Hel/kapp markert med farger
    • Alle vegg-mål rundt rommet med vinkler
    • Elementbredde-mål langs spans-retning
    • Spennpil og retningsindikator
    • Titleblokk
    """
    pts_a  = np.array(pts, dtype=float)
    nn     = len(pts_a)
    xs, ys = pts_a[:, 0], pts_a[:, 1]
    wls    = wall_lengths(pts)
    pw_mm  = round(pw_m * 1000)
    WT     = PANEL_DB[panel_key]["t"] / 1000

    panels = generate_roof_floor_panels(pts, pw_mm, prefix="T", label="Tak")
    is_frys = "Fryserom" in rom_type
    if is_frys:
        gulv_panels = generate_roof_floor_panels(pts, pw_mm, prefix="G", label="Gulv")
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
            n1 = np.array([-d1[1], d1[0]]); n0 = np.array([-d0[1], d0[0]])
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
            cx = float(np.mean(poly_w[:, 0])); cy = float(np.mean(poly_w[:, 1]))
            ax.text(cx, cy, f"{p.name}\n{p.width_mm} mm",
                    ha="center", va="center", fontsize=8,
                    color=BLUE if not is_kapp else "#8b3e00",
                    fontweight="bold", zorder=5,
                    bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.85))

        # ── Mål: alle vegg-sider ──────────────────────────────────────────────
        xmn, xmx = xs.min(), xs.max(); ymn, ymx = ys.min(), ys.max()
        DIM_OFF = 0.65

        # Totalmål
        _dh(ax, xmn, xmx, ymn, f"{(xmx-xmn)*1000:.0f} mm", ey=ymn - DIM_OFF - 0.55, fs=9)
        _dv(ax, ymn, ymx, xmx, f"{(ymx-ymn)*1000:.0f} mm", ex=xmx + DIM_OFF + 0.55, fs=9)

        # Per-vegg mål
        for i in range(nn):
            _dim_along_wall(ax, pts_a[i], pts_a[(i+1)%nn],
                            f"{wls[i]*1000:.0f} mm", offset=0.35, fs=8.5)

        # ── Vinkler ───────────────────────────────────────────────────────────
        for i in range(nn):
            _corner_angle(ax, pts_a, i, radius=0.22, fs=8)
            ax.text(pts_a[i][0], pts_a[i][1], f" P{i+1}",
                    fontsize=6.5, color="#444", zorder=14,
                    bbox=dict(fc="white", ec="none", pad=0.2))

        # ── Element-bredde kjede langs hoved-aksen ────────────────────────────
        x_axis, _ = main_axis_from_longest_wall(pts)
        _draw_panel_width_chain(ax, panels, x_axis, pts_a, ymn, DIM_OFF)

        # ── Spennpil ──────────────────────────────────────────────────────────
        cx_room = float(xs.mean()); cy_room = float(ys.mean())
        half_span = min(float(np.linalg.norm(pts_a.max(0)-pts_a.min(0))) * 0.28, 1.2)
        ax.annotate("",
            xy=(cx_room + x_axis[0]*half_span, cy_room + x_axis[1]*half_span),
            xytext=(cx_room - x_axis[0]*half_span, cy_room - x_axis[1]*half_span),
            arrowprops=dict(arrowstyle="<->", color="#2980b9", lw=1.4, mutation_scale=12),
            zorder=8)
        ax.text(cx_room + x_axis[0]*half_span*1.08,
                cy_room + x_axis[1]*half_span*1.08,
                "Spenn", fontsize=9, color="#2980b9", ha="center", va="center", zorder=9)

        # ── Legende ───────────────────────────────────────────────────────────
        leg = [
            mpatches.Patch(facecolor=FILL_HEL,  edgecolor="#2980b9", label="Hel panel"),
            mpatches.Patch(facecolor=FILL_KAPP, edgecolor=ORANGE,    label="Kapp/start"),
        ]
        ax.legend(handles=leg, loc="upper left", fontsize=8, framealpha=0.9)

        # ── N-pil ─────────────────────────────────────────────────────────────
        ax.annotate("", xy=(xmn+0.30, ymx+0.38), xytext=(xmn+0.30, ymx+0.10),
                    arrowprops=dict(arrowstyle="-|>", color="black", lw=1.3, mutation_scale=11), zorder=15)
        ax.text(xmn+0.30, ymx+0.50, "N", ha="center", va="bottom",
                fontsize=10, fontweight="bold", zorder=15)

        xright = _title_block(ax, xmn, xmx, ymn, ymx, {**info, "ttype": tittel})
        ax.text((xmn+xmx)/2, ymn - DIM_OFF - 1.0, tittel,
                ha="center", va="top", fontsize=9, fontweight="bold", color=BLUE)

        ax.set_xlim(xmn - DIM_OFF - 1.6, xright + 0.25)
        ax.set_ylim(ymn - DIM_OFF - 2.0, ymx + DIM_OFF + 1.2)
        ax.set_aspect("equal"); ax.axis("off")

        # ── Statistikk-boks ───────────────────────────────────────────────────
        n_hel  = sum(1 for p in panel_list if "hel" in p.kind.lower())
        n_kapp = len(panel_list) - n_hel
        ax.text(xmn - DIM_OFF - 1.4, ymx + 0.1,
                f"Totalt {len(panel_list)} elementer\n{n_hel} hele · {n_kapp} kapp",
                fontsize=8, color=BLUE, va="top", zorder=14,
                bbox=dict(fc="white", ec=BLUE, pad=5, linewidth=0.8))

    _draw_panel_plan(axes[0][0], panels, f"TAKTEGNING – {info['maal']}")
    if is_frys:
        _draw_panel_plan(axes[0][1], gulv_panels, f"GULV PIR – {info['maal']}", show_gulv=True)

    fig.tight_layout(pad=0.5)
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

def _global_start_el_nr(wls, pw_m, vegg_idx):
    """Beregn første globale V-nummer for gitt vegg (samme logikk som kappliste)."""
    pw_mm = round(pw_m * 1000)
    el_nr = 1; rest_mm = 0
    for vi, wl in enumerate(wls):
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


def tegn_veggoppstalt(pts, H, pw_m, dorer, info, vegg_idx: int = 0, apninger=None):
    """Veggoppstalt per vegg med elementoppdeling, dørmål og høyde-mål."""
    wls   = wall_lengths(pts)
    nn    = len(pts)
    L     = wls[vegg_idx]
    pw_mm = round(pw_m * 1000)
    L_mm  = round(L * 1000)
    H_mm  = round(H * 1000)

    fig, ax = plt.subplots(figsize=(max(10, L*2.8), 7))
    fig.patch.set_facecolor("white"); ax.set_facecolor("white")

    # ── Veggskal ──────────────────────────────────────────────────────────────
    ax.add_patch(mpatches.Rectangle((0, 0), L, H, facecolor=WALL_FILL,
                                     edgecolor=WALL_EDGE, linewidth=1.5, zorder=1))
    ax.add_patch(mpatches.Rectangle((0, 0), L, H, facecolor="none",
                                     edgecolor="#888", linewidth=0, hatch="////",
                                     zorder=1.5, alpha=0.5))

    # ── Elementoppdeling med global V-nummerering ─────────────────────────────
    el_nr, rest_mm_v = _global_start_el_nr(wls, pw_m, vegg_idx)
    brukt = 0
    el_positions = []
    if rest_mm_v > 0:
        bredde = min(rest_mm_v / 1000, L)
        el_positions.append((brukt, bredde, f"V{el_nr}", "rest"))
        brukt += bredde; el_nr += 1
    while brukt + pw_m <= L + 1e-6:
        w = min(pw_m, L - brukt)
        if w < 0.001: break
        el_positions.append((brukt, w, f"V{el_nr}", "hel"))
        brukt += w; el_nr += 1
    kapp = L - brukt
    if kapp > 0.001:
        el_positions.append((brukt, kapp, f"V{el_nr}", "kapp"))

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
        dk, ant, wall_idx_d, offset_m, _hengsel_s = _door_entry(entry)
        if int(wall_idx_d) != vegg_idx or ant <= 0:
            continue
        d  = DOR_DB[dk]
        dw = d["bw"] / 1000; dh = d["bh"] / 1000
        cursor = offset_m
        for _ in range(min(ant, 4)):
            ax.add_patch(mpatches.Rectangle(
                (cursor, 0), dw, dh, facecolor="white",
                edgecolor=RED, linewidth=1.8, zorder=5))
            ax.text(cursor + dw/2, dh/2, f"D\n{d['label']}",
                    ha="center", va="center", fontsize=5.5,
                    color=RED, fontweight="bold", zorder=6)
            # Mål hjørne→dør
            _dh(ax, 0, cursor, -0.25, f"{round(cursor*1000)} mm", ey=-0.25, col="#555", fs=5.5)
            # Dørbredde
            _dh(ax, cursor, cursor+dw, -0.45, f"{d['bw']} mm", ey=-0.45, col=RED, fs=5.5)
            # Dørhøyde
            _dv(ax, 0, dh, cursor+dw+0.05, f"{d['bh']} mm", ex=cursor+dw+0.05, col=RED, fs=5.5)
            cursor += dw + 0.20
        door_cursor = cursor

    # ── Åpninger / klassfronter på denne veggen ───────────────────────────────
    AP_COL = "#000000"   # sort for åpning, linjer og mål
    dim_bot = -0.70   # tracker for mål-linjer nedover
    if apninger:
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, ap_lbl = ap
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
    _dh(ax, 0, L,  0, f"{L_mm} mm",  ey=dim_bot - 0.20)
    _dv(ax, 0, H, L, f"{H_mm} mm", ex=L + 0.90)

    # Element-mål kjede (toppen)
    for x, w, lbl, _ in el_positions:
        _dh(ax, x, x+w, H, f"{round(w*1000)}", ey=H + 0.20, fs=5.5)

    ax.text(L/2, H + 0.55,
            f"VEGG {vegg_idx+1}  –  {info['maal']}  (total {L_mm} mm)",
            ha="center", va="bottom", fontsize=9, fontweight="bold", color=BLUE)

    ax.set_xlim(-0.9, L + 1.6); ax.set_ylim(dim_bot - 0.8, H + 0.9)
    ax.set_aspect("equal"); ax.axis("off")
    return fig


# ══ SNITT ═════════════════════════════════════════════════════════════════════

def _snitt_konstruksjon(ax, L, H, WT, rom_type, pw_m, dorer,
                         show_labels=True,
                         vegg_label_left="V", vegg_label_right="V",
                         vegg_idx=0):
    UC = 0.080; TAK = WT
    IS_FRYS = "Fryserom" in rom_type
    GFL = 0.100 if IS_FRYS else 0.0
    SPL = 0.022 if IS_FRYS else 0.0

    CPANEL = "#c8c8c8"; CSPON = "#d4a96a"
    CPIR_G  = "#b8d4b8"; CUKAN  = "#5a7a9a"; CBESL_I = "#2980b9"
    CBESL_U = "#e67e22"; CWHITE = "white"

    def rect(x, y, w, h, fc, ec="black", lw=0.8, hatch=None, zo=2, alpha=1.0):
        ax.add_patch(mpatches.Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec,
                                         linewidth=lw, zorder=zo, alpha=alpha))
        if hatch:
            ax.add_patch(mpatches.Rectangle((x, y), w, h, facecolor="none",
                                             edgecolor="#888", linewidth=0,
                                             hatch=hatch, zorder=zo+0.5, alpha=0.4))

    # Betong ikke kalkulert – ikke vist i snitt
    UW = 0.090; FLG = 0.005
    rect(0,     0, UW, UC, CUKAN, lw=1.2, zo=4)
    rect(L-UW,  0, UW, UC, CUKAN, lw=1.2, zo=4)
    rect(FLG,       FLG, UW-2*FLG, UC-FLG, CWHITE, ec="none", zo=5)
    rect(L-UW+FLG,  FLG, UW-2*FLG, UC-FLG, CWHITE, ec="none", zo=5)

    if IS_FRYS:
        rect(WT, 0,   L-2*WT, GFL, CPIR_G, hatch="....", zo=2)
        rect(WT, GFL, L-2*WT, SPL, CSPON, zo=3)

    rect(0,    UC, WT, H, CPANEL, hatch="////", zo=3)
    rect(L-WT, UC, WT, H, CPANEL, hatch="////", zo=3)
    inn_y0 = UC + (GFL+SPL if IS_FRYS else 0)
    rect(WT, inn_y0, L-2*WT, H-(inn_y0-UC), CWHITE, ec="#aaa", lw=0.4, zo=2)
    rect(0, UC+H, L, TAK, CPANEL, hatch="////", zo=3)

    BSZ_I = 0.050
    rect(WT-BSZ_I/2,   UC+H-BSZ_I/2, BSZ_I, BSZ_I, CBESL_I, lw=0.6, zo=6)
    rect(L-WT-BSZ_I/2, UC+H-BSZ_I/2, BSZ_I, BSZ_I, CBESL_I, lw=0.6, zo=6)
    BSZ_UW = 0.050; BSZ_UH = 0.125
    rect(-BSZ_UW, UC+H, BSZ_UW, BSZ_UH, CBESL_U, lw=0.6, zo=6)
    rect(L,       UC+H, BSZ_UW, BSZ_UH, CBESL_U, lw=0.6, zo=6)

    n_vegg_el = math.ceil(H / pw_m)
    for pi in range(1, n_vegg_el):
        hz = UC + pi*pw_m
        if hz >= UC+H: break
        ax.plot([0, WT], [hz, hz], color="black", lw=0.6, zorder=5)
        ax.plot([L-WT, L], [hz, hz], color="black", lw=0.6, zorder=5)

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
        rect(0, UC, WT, dh, CWHITE, ec=RED, lw=1.5, zo=7)
        ax.text(WT/2, UC+dh/2, "D", ha="center", va="center",
                fontsize=6, color=RED, fontweight="bold", zorder=8)
        break

    if not show_labels:
        return

    def lbl(x, y, txt, col="#222", fs=6, ha="center", va="center", rot=0):
        ax.text(x, y, txt, ha=ha, va=va, fontsize=fs, color=col,
                rotation=rot, zorder=10,
                bbox=dict(fc="white", ec="none", pad=0.5, alpha=0.85))

    lbl(UW/2, UC/2,        "U-kanal\n80 mm",  fs=5.5, col="#1a3a5c")
    lbl(L-UW/2, UC/2,      "U-kanal\n80 mm",  fs=5.5, col="#1a3a5c")
    lbl(WT/2, UC+H/2,      f"Vegg\n{vegg_label_left}", fs=6, col="#1a3a5c")
    lbl(L-WT/2, UC+H/2,    f"Vegg\n{vegg_label_right}", fs=6, col="#1a3a5c")
    lbl(L/2, UC+H+TAK/2,   "Tak", fs=6)
    lbl(WT,      UC+H,     "50×50\ninnv.", fs=5, col=CBESL_I)
    lbl(L-WT,    UC+H,     "50×50\ninnv.", fs=5, col=CBESL_I)
    lbl(-BSZ_UW*0.5, UC+H+BSZ_UH*0.6, "50×125\nutv.", fs=5, col=CBESL_U)
    lbl(L+BSZ_UW*0.5, UC+H+BSZ_UH*0.6, "50×125\nutv.", fs=5, col=CBESL_U)
    if IS_FRYS:
        lbl(L/2, GFL/2+UC*0.1,  "PIR gulv 100 mm",             fs=5.5, col="#2d6e2d")
        lbl(L/2, GFL+SPL/2,     "Sponplate 22 mm m/ plastbelegg", fs=5.5, col="#7a5c20")


def stramo_snitt(pts, H, pw_m, dorer, info, rom_type, panel_key,
                 vegg_idx=0, seksjon="A-A", apninger=None):
    WT     = PANEL_DB[panel_key]["t"] / 1000
    pts_a  = np.array(pts); nn = len(pts_a)
    xs, ys = pts_a[:, 0], pts_a[:, 1]
    bx = xs.max()-xs.min(); by = ys.max()-ys.min()
    L  = bx if vegg_idx % 2 == 0 else by
    vl_left  = f"V{vegg_idx+1}"
    vl_right = f"V{(vegg_idx+2)%nn+1}"

    UC = 0.080; TAK = WT
    IS_FRYS = "Fryserom" in rom_type
    GFL = 0.100 if IS_FRYS else 0.0
    SPL = 0.022 if IS_FRYS else 0.0
    BSZ_UH = 0.125
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
                (0, UC + ap_sill), WT, ap_h,
                facecolor="white", edgecolor=CYAN,
                linewidth=1.8, zorder=6))
            ax.text(WT/2, UC + ap_sill + ap_h/2,
                    f"{ap_lbl}\n{round(ap_h*1000)} mm",
                    ha="center", va="center", fontsize=5, color=CYAN,
                    fontweight="bold", zorder=7,
                    bbox=dict(fc="white", ec="none", pad=0.2, alpha=0.9))
            _dv(ax, UC + ap_sill, UC + ap_sill + ap_h, -DIM_OFF - 0.40,
                f"{round(ap_h*1000)} mm", ex=-DIM_OFF - 0.40, col=CYAN, fs=5.5)
            if ap_sill > 0:
                _dv(ax, UC, UC + ap_sill, -DIM_OFF - 0.65,
                    f"{round(ap_sill*1000)} mm", ex=-DIM_OFF - 0.65, col="#555", fs=5.5)

    H_mm  = round(H*1000); WT_mm = round(WT*1000)
    inn_fri = L - 2*WT

    # ── Horizontal mål ────────────────────────────────────────────────────────
    _dh(ax, 0, L,    0, f"{L*1000:.0f} mm",            ey=-DIM_OFF)
    _dh(ax, WT, L-WT, 0, f"{inn_fri*1000:.0f} mm innv.", ey=-DIM_OFF-0.30)
    _dh(ax, 0, WT,   0, f"{WT_mm} mm",                 ey=-DIM_OFF-0.55)
    _dh(ax, L-WT, L, 0, f"{WT_mm} mm",                 ey=-DIM_OFF-0.55)

    # ── Vertikal mål ──────────────────────────────────────────────────────────
    _dv(ax, 0, UC+H+TAK+BSZ_UH, L,
        f"{round((UC+H+TAK+BSZ_UH)*1000)} mm tot.", ex=L+DIM_OFF+1.0)
    _dv(ax, UC,   UC+H,            L, f"{H_mm} mm",     ex=L+DIM_OFF)
    _dv(ax, 0,    UC,              L, "80 mm U-kan.",   ex=L+DIM_OFF)
    _dv(ax, UC+H, UC+H+TAK,        L, f"{WT_mm} mm tak",ex=L+DIM_OFF)
    _dv(ax, UC+H, UC+H+BSZ_UH,     L, "125 mm besl.",  ex=L+DIM_OFF+0.65)

    if IS_FRYS:
        _dv(ax, UC, UC+GFL,         0, "100 mm PIR",   ex=-DIM_OFF)
        _dv(ax, UC+GFL, UC+GFL+SPL, 0, "22 mm spon",  ex=-DIM_OFF)
        inn_brutto = H - GFL - SPL
        _dv(ax, UC+GFL+SPL, UC+H,   0,
            f"{round(inn_brutto*1000)} mm fri h.", ex=-DIM_OFF-0.38)

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
            f"SNITT {seksjon}  –  {info['maal']}  (vegg {vl_left} / {vl_right})",
            ha="center", va="top", fontsize=9, fontweight="bold", color=BLUE)
    _title_block(ax, 0, L, -0.05, UC+H+TAK+BSZ_UH+0.1,
                 {**info, "ttype": f"Snitt {seksjon}"})

    ax.set_xlim(-DIM_OFF-0.9, L+DIM_OFF+4.2)
    ax.set_ylim(-DIM_OFF-1.3, UC+H+TAK+BSZ_UH+DIM_OFF+0.5)
    ax.set_aspect("equal"); ax.axis("off")
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
    if is_horiz:
        return "rett kapp"
    return "vinklet kapp"


def _draw_one_panel(ax, local_pts: np.ndarray, panel, panel_key: str,
                    panel_number: int, category: str = "Tak", cutouts: list | None = None):
    """Tegner én panel-detalj med alle mål, vinkler og produksjonsnotes."""
    n = len(local_pts)
    WT_mm = PANEL_DB[panel_key]["t"]

    # ── Panelform ─────────────────────────────────────────────────────────────
    is_kapp = "kapp" in panel.kind.lower() or "start" in panel.kind.lower()
    fc = "#cce4f7" if not is_kapp else "#fde4c8"
    ec = BLUE     if not is_kapp else ORANGE

    ax.add_patch(MplPolygon(local_pts, closed=True, facecolor=fc,
                             edgecolor=ec, linewidth=1.8, zorder=2))
    ax.add_patch(MplPolygon(local_pts, closed=True, facecolor="none",
                             edgecolor="#777", linewidth=0,
                             hatch="////" if not is_kapp else ".....",
                             zorder=2.5, alpha=0.35))

    center = local_pts.mean(axis=0)

    # ── Utsparinger (dører og åpninger) ───────────────────────────────────────
    for (lx, ly, lw, lh, cut_lbl) in (cutouts or []):
        ax.add_patch(mpatches.Rectangle(
            (lx, ly), lw, lh,
            facecolor="white", edgecolor="#000", linewidth=1.4,
            linestyle="--", zorder=5))
        ax.text(lx + lw/2, ly + lh/2, cut_lbl,
                ha="center", va="center", fontsize=6,
                color="#000", fontweight="bold", zorder=6)
        # Målpiler for utsparing
        _dv(ax, ly, ly + lh, lx + lw, f"{round(lh*1000)} mm",
            ex=lx + lw + 0.08, col="#000", fs=5.5)
        _dh(ax, lx, lx + lw, ly - 0.08, f"{round(lw*1000)} mm",
            ey=ly - 0.08, col="#000", fs=5.5)
        if ly > 0.001:
            _dv(ax, 0, ly, lx - 0.08, f"{round(ly*1000)} mm",
                ex=lx - 0.08, col="#000", fs=5.5)

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
        dim_col = "#c0392b" if "vinklet" in kind else ("#2980b9" if "fabrikk" in kind else "#2d6e2d")
        dim_off = 0.13

        # Forlengelseslinjer
        ax.plot([p1[0], p1[0]+perp[0]*dim_off],
                [p1[1], p1[1]+perp[1]*dim_off], color=dim_col, lw=0.5, zorder=6)
        ax.plot([p2[0], p2[0]+perp[0]*dim_off],
                [p2[1], p2[1]+perp[1]*dim_off], color=dim_col, lw=0.5, zorder=6)
        # Målpil
        s_dim = p1 + perp * dim_off; e_dim = p2 + perp * dim_off
        ax.annotate("", xy=(e_dim[0], e_dim[1]), xytext=(s_dim[0], s_dim[1]),
                    arrowprops=dict(arrowstyle="<->", color=dim_col,
                                   lw=0.7, mutation_scale=6), zorder=7)
        angle = math.degrees(math.atan2(dx[1], dx[0]))
        ax.text(mid[0]+perp[0]*(dim_off+0.10),
                mid[1]+perp[1]*(dim_off+0.10),
                f"{L_mm:.0f} mm",
                ha="center", va="center", fontsize=7, rotation=angle,
                color=dim_col, zorder=8,
                bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.9))

        # Kant-type label (vist langs kanten inne)
        kind_lbl = {"fabrikk": "F", "rett kapp": "RK", "vinklet kapp": "VK"}.get(kind, "?")
        kind_col = {"F": "#2980b9", "RK": "#2d6e2d", "VK": "#c0392b"}.get(kind_lbl, "#555")
        ax.text(mid[0] - perp[0]*0.06, mid[1] - perp[1]*0.06,
                kind_lbl, ha="center", va="center", fontsize=5.5,
                color=kind_col, fontweight="bold", zorder=9,
                bbox=dict(fc="white", ec=kind_col, pad=1.5, linewidth=0.6, alpha=0.85))

    # ── Vinkler ved alle hjørner ───────────────────────────────────────────────
    for i in range(n):
        pc = local_pts[i]; pm = local_pts[(i-1)%n]; pn = local_pts[(i+1)%n]
        v1 = pm - pc; v2 = pn - pc
        L1 = np.linalg.norm(v1); L2 = np.linalg.norm(v2)
        if L1 < 0.001 or L2 < 0.001:
            continue
        v1n = v1/L1; v2n = v2/L2
        dot = float(np.clip(np.dot(v1n, v2n), -1, 1))
        ang = math.degrees(math.acos(dot))
        a1  = math.degrees(math.atan2(v1n[1], v1n[0]))
        a2  = math.degrees(math.atan2(v2n[1], v2n[0]))
        r   = min(0.14, min(L1, L2) * 0.28)

        theta1, theta2 = sorted([a1, a2])
        if theta2 - theta1 > 180:
            theta1, theta2 = theta2, theta1 + 360
        ax.add_patch(Arc(tuple(pc), r*2, r*2, angle=0,
                         theta1=theta1, theta2=theta2,
                         color=RED, lw=0.9, zorder=10))
        a_mid = math.radians((theta1 + theta2) / 2)
        ax.text(pc[0]+(r+0.09)*math.cos(a_mid),
                pc[1]+(r+0.09)*math.sin(a_mid),
                f"{ang:.1f}°",
                ha="center", va="center", fontsize=6.5, color=RED,
                fontweight="bold", zorder=11,
                bbox=dict(fc="white", ec="none", pad=0.3))

        # Hjørnepunkt-label
        dir_out = (pc - center); L_out = np.linalg.norm(dir_out)
        if L_out > 1e-6:
            dir_out /= L_out
        ax.text(pc[0]+dir_out[0]*0.11, pc[1]+dir_out[1]*0.11,
                f"H{i+1}", ha="center", va="center", fontsize=5,
                color="#444", zorder=12,
                bbox=dict(fc="white", ec="none", pad=0.15))

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
    tbl_y  = ymn - pad_y - 0.05
    tbl_x  = xmn
    tbl_w  = xmx - xmn
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

    # Legg til snitt-informasjon for alle vinklede kanter
    vk_edges = [i for i in range(n)
                if "vinklet" in _edge_kind(local_pts, panel.width_mm, i)]
    for vi in vk_edges:
        p1 = local_pts[vi]; p2 = local_pts[(vi+1) % n]
        dx = p2 - p1; L = np.linalg.norm(dx)
        ang_abs = abs(math.degrees(math.atan2(dx[1], dx[0])))
        cut_ang = round(min(ang_abs, 180-ang_abs), 1)
        rows.append((f"Snittvinkel kant {vi+1}→{(vi+1)%n+1}", f"{cut_ang}° fra rett"))

    row_h = 0.10
    for ri, (lbl, val) in enumerate(rows):
        y0 = tbl_y - ri * row_h
        bg = "#f0f4f8" if ri % 2 == 0 else "white"
        ax.add_patch(mpatches.Rectangle(
            (tbl_x, y0 - row_h), tbl_w, row_h,
            facecolor=bg, edgecolor="#c8d8e8", lw=0.4, zorder=15))
        ax.text(tbl_x + 0.04, y0 - row_h/2, lbl,
                ha="left", va="center", fontsize=5.8, color=BLUE,
                fontweight="bold", zorder=16)
        ax.text(tbl_x + col1_w + 0.04, y0 - row_h/2, val,
                ha="left", va="center", fontsize=5.8, color="#111", zorder=16)

    tbl_bot = tbl_y - len(rows) * row_h

    # Fargeforklaring
    leg_y = tbl_bot - 0.12
    for lbl, col in [("F = Fabrikkant", "#2980b9"),
                     ("RK = Rett kapp", "#2d6e2d"),
                     ("VK = Vinklet kapp", "#c0392b")]:
        ax.add_patch(mpatches.Rectangle(
            (tbl_x, leg_y - 0.09), 0.08, 0.08,
            facecolor="white", edgecolor=col, lw=1.5, zorder=16))
        ax.text(tbl_x + 0.12, leg_y - 0.045, lbl,
                ha="left", va="center", fontsize=5.5, color=col, zorder=16)
        tbl_x += col1_w * 0.95

    ax.set_xlim(xmn - pad_x,       xmx + pad_x + 0.35)
    ax.set_ylim(leg_y - 0.18,      ymx + pad_y + 0.20)
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
) -> list[plt.Figure]:
    """
    Genererer ett figur-objekt per side med produksjonstegninger.
    Hvert element vises med:
      • Nøyaktig polygon i lokal flat-layout
      • Alle kantlengder i mm
      • Alle hjørnevinkler i grader
      • Kanttype: F (fabrikk), RK (rett kapp), VK (vinklet kapp)
      • Produksjonstabell med snittvinkel for skrå kanter
    Returnerer liste med plt.Figure (én per side, 4 panel/side).
    """
    pw_mm   = round(pw_m * 1000)
    is_frys = "Fryserom" in rom_type
    dorer   = dorer   or []
    apninger = apninger or []

    # Hent alle paneler
    tak_p  = generate_roof_floor_panels(pts, pw_mm, prefix="T",  label="Tak")
    gulv_p = generate_roof_floor_panels(pts, pw_mm, prefix="G",  label="Gulv") if is_frys else []

    # Vegg-kapp: rektangulære panel men kortere enn standardbredde
    from geometry import wall_lengths as _wl
    wls     = _wl(pts)
    vegg_p  = []   # list of (panel, wall_idx, x_start_mm)
    el_nr   = 1; rest_mm = 0
    for wi, wl in enumerate(wls):
        L_mm = round(wl * 1000); brukt = 0
        if rest_mm > 0:
            bredde = min(rest_mm, L_mm)
            _make_vegg(vegg_p, el_nr, wi, bredde, round(H*1000), pw_mm,
                       x_start_mm=brukt, rest=True)
            brukt += bredde; el_nr += 1; rest_mm = max(rest_mm-L_mm, 0)
        while brukt + pw_mm <= L_mm:
            _make_vegg(vegg_p, el_nr, wi, pw_mm, round(H*1000), pw_mm,
                       x_start_mm=brukt)
            brukt += pw_mm; el_nr += 1
        remaining = L_mm - brukt
        if remaining > 0:
            _make_vegg(vegg_p, el_nr, wi, remaining, round(H*1000), pw_mm,
                       x_start_mm=brukt)
            el_nr += 1; rest_mm = pw_mm - remaining

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
                    cuts.append((lo/1000, 0, (hi-lo)/1000, d_h_mm/1000,
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
                cuts.append((lo/1000, ap_sill, (hi-lo)/1000, ap_h,
                             f"{ap_lbl} {round(d_w_mm)}×{round(ap_h*1000)}"))
        return cuts

    PANELS_PER_PAGE = 4   # 2×2 per side
    figures = []
    num = 0

    for page_start in range(0, len(alle), PANELS_PER_PAGE):
        page = alle[page_start: page_start + PANELS_PER_PAGE]
        ncols = 2; nrows = math.ceil(len(page) / ncols)
        fig, axes = plt.subplots(nrows, ncols,
                                  figsize=(22, nrows * 10))
        fig.patch.set_facecolor("white")

        # Sidetittel
        fig.text(0.5, 0.995, f"STRAMO – PRODUKSJONSTEGNINGER  ·  {info['navn'] or '–'}  ·  {info['dato']}",
                 ha="center", va="top", fontsize=11, fontweight="bold", color=BLUE)
        fig.text(0.5, 0.988,
                 f"Prosjektnr: {info['pnr']}  ·  Tegningsnr: {info['tnr']}  ·  "
                 f"Panel: {PANEL_DB[panel_key]['label']}  ·  "
                 f"Side {len(figures)+1} av {math.ceil(len(alle)/PANELS_PER_PAGE)}",
                 ha="center", va="top", fontsize=8, color="#444")
        fig.text(0.5, 0.983,
                 "F = Fabrikkant (ingen kapping)   RK = Rett kapp (90°)   VK = Vinklet kapp (se snittvinkel i tabell)",
                 ha="center", va="top", fontsize=7.5, color="#666")

        axes_flat = np.array(axes).flatten()
        for cell, (cat, p, wi, xs) in enumerate(page):
            num += 1
            ax = axes_flat[cell]
            local = _panel_to_local(p.polygon)
            cuts = _cutouts_for_panel(cat, wi, xs, p.width_mm, p.span_mm)
            _draw_one_panel(ax, local, p, panel_key, num, category=cat, cutouts=cuts)
            ax.set_title(f"  {cat}: {p.name}  –  {p.kind}  [nr. {num}]",
                         fontsize=9, color=BLUE, fontweight="bold", pad=6, loc="left")

        # Skjul tomme celler
        for cell in range(len(page), len(axes_flat)):
            axes_flat[cell].axis("off")

        fig.tight_layout(rect=[0, 0, 1, 0.982], pad=1.2, h_pad=2.5, w_pad=2.0)
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
