from __future__ import annotations

import math
import numpy as np
import plotly.graph_objects as go

from database import PANEL_DB, DOR_DB
from geometry import ensure_ccw
from panel_engine import generate_roof_floor_panels


def _poly_centroid(pts: np.ndarray) -> np.ndarray:
    return np.array([float(np.mean(pts[:, 0])), float(np.mean(pts[:, 1]))])


def _add_polygon_mesh(fig: go.Figure, pts: np.ndarray, z: float, *, name: str, color: str, opacity: float = 1.0, showlegend: bool = False) -> None:
    if len(pts) < 3:
        return
    c = _poly_centroid(pts)
    x = [float(c[0])] + [float(p[0]) for p in pts]
    y = [float(c[1])] + [float(p[1]) for p in pts]
    zz = [float(z)] * (len(pts) + 1)
    i, j, k = [], [], []
    for n in range(1, len(pts) + 1):
        i.append(0); j.append(n); k.append(1 if n == len(pts) else n + 1)
    fig.add_trace(go.Mesh3d(x=x, y=y, z=zz, i=i, j=j, k=k, color=color, opacity=opacity, name=name,
                             flatshading=True, hoverinfo="name", showlegend=showlegend))


def _add_vertical_faces(fig: go.Figure, pts: np.ndarray, z0: float, z1: float, *, name: str, color: str, opacity: float = 1.0) -> None:
    for i in range(len(pts)):
        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
        x = [p1[0], p2[0], p2[0], p1[0]]
        y = [p1[1], p2[1], p2[1], p1[1]]
        z = [z0, z0, z1, z1]
        fig.add_trace(go.Mesh3d(x=x, y=y, z=z, i=[0,0], j=[1,2], k=[2,3], color=color, opacity=opacity, name=name if i == 0 else name, flatshading=True, hoverinfo="name", showlegend=False))


def _add_quad(fig: go.Figure, p1, p2, z0: float, z1: float, *, name: str, color: str, opacity: float = 1.0, showlegend: bool = False) -> None:
    x = [p1[0], p2[0], p2[0], p1[0]]
    y = [p1[1], p2[1], p2[1], p1[1]]
    z = [z0, z0, z1, z1]
    fig.add_trace(go.Mesh3d(x=x, y=y, z=z, i=[0,0], j=[1,2], k=[2,3], color=color, opacity=opacity, name=name, flatshading=True, hoverinfo="name", showlegend=showlegend))


def _add_line(fig: go.Figure, xs, ys, zs, *, name: str, color: str = "#222", width: int = 3, dash: str | None = None, showlegend: bool = False) -> None:
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", name=name, line=dict(color=color, width=width, dash=dash or "solid"), showlegend=showlegend, hoverinfo="name"))


class _QuadBatch:
    """
    Samler mange firkanter i én Mesh3d-trace i stedet for én trace per
    firkant. Hver ekstra trace har egen oppsett-kostnad i nettleserens
    WebGL-visning, så beslag som består av dusinvis av små flenser blir
    fort tregt å laste hvis hver av dem er sin egen trace. Bygg opp med
    quad()/quad_horisontal(), og kall flush() én gang til slutt.
    """
    def __init__(self, name: str, color: str, opacity: float = 1.0, showlegend: bool = False):
        self.name, self.color, self.opacity, self.showlegend = name, color, opacity, showlegend
        self.x: list[float] = []; self.y: list[float] = []; self.z: list[float] = []
        self.i: list[int] = []; self.j: list[int] = []; self.k: list[int] = []

    def _tri(self, xs, ys, zs) -> None:
        n = len(self.x)
        self.x += xs; self.y += ys; self.z += zs
        self.i += [n, n]; self.j += [n + 1, n + 2]; self.k += [n + 2, n + 3]

    def quad(self, p1, p2, z0: float, z1: float) -> None:
        self._tri([p1[0], p2[0], p2[0], p1[0]], [p1[1], p2[1], p2[1], p1[1]], [z0, z0, z1, z1])

    def quad_horisontal(self, p1, p2, perp, depth0: float, depth1: float, z: float) -> None:
        a0, a1 = p1 + perp * depth0, p2 + perp * depth0
        b0, b1 = p1 + perp * depth1, p2 + perp * depth1
        self._tri([a0[0], a1[0], b1[0], b0[0]], [a0[1], a1[1], b1[1], b0[1]], [z, z, z, z])

    def flush(self, fig: go.Figure) -> None:
        if not self.x:
            return
        fig.add_trace(go.Mesh3d(x=self.x, y=self.y, z=self.z, i=self.i, j=self.j, k=self.k,
                                 color=self.color, opacity=self.opacity, name=self.name,
                                 flatshading=True, hoverinfo="name", showlegend=self.showlegend))


def _add_u_kanal(batch: _QuadBatch, p1, p2, perp, width: float, height: float) -> None:
    """U-profil (gulv→vegg-kanal): to oppbrettede sider forbundet med en flat bunn, langs p1-p2."""
    batch.quad(p1, p2, 0, height)
    batch.quad(p1 + perp * width, p2 + perp * width, 0, height)
    batch.quad_horisontal(p1, p2, perp, 0, width, 0)


def _add_l_flange_run(batch: _QuadBatch, p1, p2, perp, *, z_knekk: float, leg_v: float, leg_h: float,
                       vert_up: bool, horiz_inn: bool) -> None:
    """
    Vinkeljern (L-profil) langs en rett strekning p1-p2: én vertikal flens og
    én horisontal flens som møtes i et knekk ved z_knekk. `vert_up` styrer om
    den vertikale flensen går opp eller ned fra knekken, `horiz_inn` om den
    horisontale flensen går innover (positiv perp) eller utover.
    """
    gap = 0.005  # liten avstand fra vegglinja, kun for å unngå z-fighting
    side = 1 if horiz_inn else -1
    p1o, p2o = p1 + perp * gap * side, p2 + perp * gap * side
    z_top = z_knekk + leg_v if vert_up else z_knekk
    z_bot = z_knekk if vert_up else z_knekk - leg_v
    batch.quad(p1o, p2o, z_bot, z_top)
    d0, d1 = gap * side, (gap + leg_h) * side
    batch.quad_horisontal(p1, p2, perp, d0, d1, z_knekk)


def _add_l_post(batch: _QuadBatch, corner, dir_a, dir_b, perp_a, perp_b, leg: float,
                 z0: float, z1: float, *, offset: float) -> None:
    """Vertikal hjørnestolpe (L-profil) i et bygningshjørne, med én flens langs hver tilstøtende vegg."""
    a0 = corner + perp_a * offset
    batch.quad(a0, a0 + dir_a * leg, z0, z1)
    b0 = corner + perp_b * offset
    batch.quad(b0, b0 + dir_b * leg, z0, z1)


def _wall_color(i: int) -> str:
    return ["#d7dde6", "#c7d0dc", "#e4e8ef", "#bcc8d6"][i % 4]


def tegn_3d(pts, H, dorer, panel_key, rom_type, azimuth=-55, elevation=28):
    return tegn_3d_med_panelbredde(pts, H, dorer, panel_key, rom_type, 1.10, azimuth, elevation)


def tegn_3d_med_panelbredde(pts, H, dorer, panel_key, rom_type, panelbredde_m, azimuth=-55, elevation=28,
                             apninger=None):
    """
    Interaktiv 3D-modell med samme panelmotor som kapplisten.
    Tak-/gulvpanelene klippes mot polygonet, slik at avskåret hjørne vises riktig.
    """
    pts_a = np.array(ensure_ccw(pts), dtype=float)
    nn = len(pts_a)
    if nn < 3:
        return go.Figure()

    WT = PANEL_DB[panel_key]["t"] / 1000.0
    UC = 0.080
    TAK = WT
    BET = 0.080
    z0 = UC
    z1 = UC + H
    z_roof_top = z1 + TAK
    IS_FRYS = "Fryserom" in rom_type

    UKAN_W, UKAN_H = 0.090, UC          # U-kanal: bredde/høyde
    INNV_LEG = 0.050                    # Innv. hjørnebeslag 50×50
    UTV_LEG_UT, UTV_LEG_H = 0.050, 0.125  # Utv. hjørnebeslag 50×125

    fig = go.Figure()

    # Sokkel/gulv
    _add_polygon_mesh(fig, pts_a, 0, name="Gulvflate", color="#9aa8b6", opacity=0.45)

    if IS_FRYS:
        gulvpaneler = generate_roof_floor_panels(pts, int(round(panelbredde_m * 1000)), prefix="G", label="Gulv PIR", cut_position="end")
        for idx, p in enumerate(gulvpaneler):
            pa = np.array(p.polygon, dtype=float)
            _add_polygon_mesh(fig, pa, 0.10, name=f"{p.name} {p.width_mm}×{p.span_mm} mm", color="#88b886", opacity=0.65)
            _add_vertical_faces(fig, pa, 0, 0.10, name=f"{p.name} gulvtykkelse", color="#6a9f6a", opacity=0.35)

    # Vegger
    for i in range(nn):
        p1, p2 = pts_a[i], pts_a[(i + 1) % nn]
        _add_quad(fig, p1, p2, z0, z1, name=f"Vegg {i+1} – panel", color=_wall_color(i), opacity=0.96)

        # Elementskjøter på vegger
        L = float(np.linalg.norm(p2 - p1))
        if L > 1e-6 and panelbredde_m > 0:
            direction = (p2 - p1) / L
            for k in range(1, int(math.floor(L / panelbredde_m)) + 1):
                dist = k * panelbredde_m
                if dist >= L:
                    continue
                q = p1 + direction * dist
                _add_line(fig, [q[0], q[0]], [q[1], q[1]], [z0, z1], name="Vegg-elementskjøt", color="#566573", width=3)

    # Takpaneler – faktiske polygoner, ikke bare én hel takplate
    takpaneler = generate_roof_floor_panels(pts, int(round(panelbredde_m * 1000)), prefix="T", label="Tak", cut_position="end")
    for idx, p in enumerate(takpaneler):
        pa = np.array(p.polygon, dtype=float)
        color = "#6f8fa5" if idx % 2 == 0 else "#7f9db2"
        _add_polygon_mesh(fig, pa, z_roof_top, name=f"{p.name} {p.width_mm}×{p.span_mm} mm", color=color, opacity=0.92)
        _add_vertical_faces(fig, pa, z1, z_roof_top, name=f"{p.name} taktykkelse", color=color, opacity=0.45)
        # Omriss/skjøter
        closed = list(pa) + [pa[0]]
        _add_line(fig, [q[0] for q in closed], [q[1] for q in closed], [z_roof_top + 0.006] * len(closed), name=f"Omriss {p.name}", color="#138a36", width=4)

    # ── Beslag – tegnes alltid, som faktiske bøyde profiler ────────────────────
    # Samlet i tre batcher (én trace hver) i stedet for én trace per liten
    # flens – ellers blir det fort 40+ ekstra traces å laste i nettleseren.
    ukanal_b = _QuadBatch("U-kanal 80 mm", "#315b7d", showlegend=True)
    innv_b   = _QuadBatch("Innv. hjørnebeslag 50×50", "#1f77b4", showlegend=True)
    utv_b    = _QuadBatch("Utv. hjørnebeslag 50×125", "#e67e22", showlegend=True)

    for i in range(nn):
        p1, p2 = pts_a[i], pts_a[(i + 1) % nn]
        dx_n = (p2 - p1) / (float(np.linalg.norm(p2 - p1)) + 1e-9)
        perp = np.array([-dx_n[1], dx_n[0]])   # innadrettet (CCW polygon)

        # U-kanal (gulv→vegg): U-profil med to oppbrettede sider
        _add_u_kanal(ukanal_b, p1, p2, perp, UKAN_W, UKAN_H)

        # Innv. hjørnebeslag – vinkeljern i innvendig vegg/tak-hjørne
        _add_l_flange_run(innv_b, p1, p2, perp, z_knekk=z1, leg_v=INNV_LEG, leg_h=INNV_LEG,
                          vert_up=False, horiz_inn=True)

        # Utv. hjørnebeslag – fasadeblikk utenpå vegg/tak-hjørne
        _add_l_flange_run(utv_b, p1, p2, perp, z_knekk=z1, leg_v=UTV_LEG_H, leg_h=UTV_LEG_UT,
                          vert_up=True, horiz_inn=False)

    # Vertikale hjørnestolper – innv. i vanlige (konvekse) hjørner,
    # utv. i eventuelle re-entrante (konkave) hjørner, som i materiallisten.
    for i in range(nn):
        pm, pc, pn = pts_a[(i - 1) % nn], pts_a[i], pts_a[(i + 1) % nn]
        v1, v2 = pc - pm, pn - pc
        L1, L2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
        if L1 < 1e-9 or L2 < 1e-9:
            continue
        dir_prev, dir_next = -v1 / L1, v2 / L2
        perp_prev = np.array([-v1[1], v1[0]]) / L1
        perp_next = np.array([-v2[1], v2[0]]) / L2
        konveks = (v1[0] * v2[1] - v1[1] * v2[0]) >= 0
        if konveks:
            _add_l_post(innv_b, pc, dir_prev, dir_next, perp_prev, perp_next, INNV_LEG, z0, z1, offset=0.005)
        else:
            _add_l_post(utv_b, pc, dir_prev, dir_next, -perp_prev, -perp_next, UTV_LEG_UT, z0, z1, offset=0.005)

    ukanal_b.flush(fig)
    innv_b.flush(fig)
    utv_b.flush(fig)

    # Dører – plassert på riktig vegg med offset
    if dorer:
        for entry in dorer:
            dk  = entry[0]; ant = int(entry[1])
            wi  = int(entry[2]) if len(entry) > 2 else 0
            off = float(entry[3]) if len(entry) > 3 else 0.35
            if wi >= len(pts_a):
                continue
            p1d = pts_a[wi]; p2d = pts_a[(wi+1) % len(pts_a)]
            Ld  = float(np.linalg.norm(p2d - p1d))
            if Ld < 1e-6:
                continue
            direction = (p2d - p1d) / Ld
            dw = DOR_DB[dk]["bw"] / 1000.0
            dh = DOR_DB[dk]["bh"] / 1000.0
            cursor = off
            for _ in range(min(int(ant), 3)):
                if cursor + dw > Ld:
                    break
                s = p1d + direction * cursor
                e = p1d + direction * (cursor + dw)
                _add_quad(fig, s, e, z0, z0 + dh,
                          name=f"Dør – {DOR_DB[dk]['label']}", color="#ffffff", opacity=1.0)
                _add_line(fig,
                          [s[0], e[0], e[0], s[0], s[0]],
                          [s[1], e[1], e[1], s[1], s[1]],
                          [z0, z0, z0+dh, z0+dh, z0],
                          name="Dørkarm", color="#b00020", width=5)
                cursor += dw + 0.20

    # Åpninger / klassfronter – hvit fyll + cyan ramme
    if apninger:
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, ap_lbl = ap
            if ap_wall >= len(pts_a):
                continue
            p1a = pts_a[ap_wall]; p2a = pts_a[(ap_wall+1) % len(pts_a)]
            La  = float(np.linalg.norm(p2a - p1a))
            if La < 1e-6 or ap_off + ap_w > La:
                continue
            da = (p2a - p1a) / La
            s_a = p1a + da * ap_off
            e_a = p1a + da * (ap_off + ap_w)
            z_bot = z0 + ap_sill
            z_top = z_bot + ap_h
            _add_quad(fig, s_a, e_a, z_bot, z_top,
                      name=ap_lbl, color="#aaddff", opacity=0.55)
            _add_line(fig,
                      [s_a[0], e_a[0], e_a[0], s_a[0], s_a[0]],
                      [s_a[1], e_a[1], e_a[1], s_a[1], s_a[1]],
                      [z_bot, z_bot, z_top, z_top, z_bot],
                      name=f"{ap_lbl} – ramme", color="#00aacc", width=4)

    xs, ys = pts_a[:, 0], pts_a[:, 1]
    xmn, xmx, ymn, ymx = xs.min(), xs.max(), ys.min(), ys.max()
    dx, dy = xmx - xmn, ymx - ymn
    off = max(dx, dy) * 0.12 or 0.3
    _add_line(fig, [xmn, xmx], [ymn - off, ymn - off], [0, 0], name=f"Lengde {dx*1000:.0f} mm", color="#111", width=4, dash="dash")
    _add_line(fig, [xmx + off, xmx + off], [ymn, ymx], [0, 0], name=f"Bredde {dy*1000:.0f} mm", color="#111", width=4, dash="dash")
    _add_line(fig, [xmx + off*0.6, xmx + off*0.6], [ymn, ymn], [0, z1], name=f"Høyde {H*1000:.0f} mm", color="#111", width=4, dash="dash")

    fig.update_layout(
        title="3D-simulering – panelbasert kjøle-/fryserom",
        height=760,
        margin=dict(l=0, r=0, t=42, b=0),
        scene=dict(
            xaxis_title="X [m]", yaxis_title="Y [m]", zaxis_title="Z [m]",
            aspectmode="data",
            camera=dict(eye=dict(x=1.6, y=-1.7, z=1.15)),
            bgcolor="#f7f9fc",
        ),
        # Under plottet, ikke over – der kolliderte den med tittelen.
        legend=dict(orientation="h", yanchor="top", y=-0.03, xanchor="left", x=0),
    )
    return fig
