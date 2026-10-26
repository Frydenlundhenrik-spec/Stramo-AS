from __future__ import annotations
from construction import roof_outline, wall_polygon, wall_panel_polygon, wall_panel_layout, floor_depth

import math
import numpy as np
import plotly.graph_objects as go

from construction import CHANNEL_HEIGHT, CHANNEL_FLANGE, FLOOR_PIR, FLOOR_BOARD, BATTEN_HEIGHT, wall_base, floor_outline, finished_floor
from database import PANEL_DB, DOR_DB
from geometry import polygon_winding
from panel_engine import generate_roof_floor_panels


def _polygon_triangles(pts: np.ndarray) -> list[tuple[int, int, int]]:
    """Triangulate a simple polygon without filling concave recesses."""
    def cross(a, b, c):
        u, v = b-a, c-a
        return float(u[0]*v[1]-u[1]*v[0])

    winding = polygon_winding(pts)
    tolerance = max(float(np.ptp(pts, axis=0).max())**2, 1.0)*1e-10
    remaining = list(range(len(pts)))
    # Clipping can leave repeated or collinear vertices along a panel edge.
    while len(remaining) > 3:
        for pos, index in enumerate(remaining):
            previous, following = remaining[pos-1], remaining[(pos+1)%len(remaining)]
            if abs(cross(pts[previous],pts[index],pts[following])) <= tolerance:
                remaining.pop(pos)
                break
        else:
            break
    triangles = []
    while len(remaining) > 3:
        for pos, index in enumerate(remaining):
            previous, following = remaining[pos-1], remaining[(pos+1)%len(remaining)]
            a, b, c = pts[[previous,index,following]]
            if winding*cross(a,b,c) <= tolerance:
                continue
            others = [pts[j] for j in remaining if j not in (previous,index,following)]
            if any(all(winding*cross(u,v,p) >= -tolerance for u,v in ((a,b),(b,c),(c,a))) for p in others):
                continue
            triangles.append((previous,index,following))
            remaining.pop(pos)
            break
        else:
            raise ValueError("Kan ikke triangulere tegningspolygonet uten overlapp.")
    if len(remaining) == 3 and abs(cross(*pts[remaining])) > tolerance:
        triangles.append(tuple(remaining))
    return triangles


def _add_polygon_mesh(fig: go.Figure, pts: np.ndarray, z: float, *, name: str, color: str, opacity: float = 1.0, showlegend: bool = False) -> None:
    if len(pts) < 3:
        return
    triangles = _polygon_triangles(pts)
    if not triangles:
        return
    i, j, k = zip(*triangles)
    fig.add_trace(go.Mesh3d(x=pts[:,0], y=pts[:,1], z=[float(z)]*len(pts), i=i, j=j, k=k, color=color, opacity=opacity, name=name,
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


def _add_u_kanal(batch: _QuadBatch, p1, p2, perp, width: float, height: float, base: float = 0) -> None:
    """U-profil (gulv→vegg-kanal): to oppbrettede sider forbundet med en flat bunn, langs p1-p2."""
    batch.quad(p1, p2, base, base+height)
    batch.quad(p1 + perp * width, p2 + perp * width, base, base+height)
    batch.quad_horisontal(p1, p2, perp, 0, width, base)


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


def _roof_hatching(fig, polygon, z):
    """Clip diagonal hatch lines to the actual (possibly L-shaped) roof outline."""
    points = np.asarray(polygon, dtype=float)
    diagonals = points[:, 0] - points[:, 1]
    xs, ys, zs = [], [], []
    for level in np.arange(math.floor(diagonals.min() / .35) * .35, diagonals.max(), .35):
        intersections = []
        for a, b in zip(points, np.roll(points, -1, axis=0)):
            da, db = a[0] - a[1], b[0] - b[1]
            if min(da, db) <= level < max(da, db):
                intersections.append(a + (b - a) * (level - da) / (db - da))
        intersections.sort(key=lambda p: p[0])
        for a, b in zip(intersections[::2], intersections[1::2]):
            xs.extend([a[0], b[0], None]); ys.extend([a[1], b[1], None]); zs.extend([z, z, None])
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", name="Takskravering",
                             line=dict(color="#7c858b", width=2), opacity=.48,
                             showlegend=False, hoverinfo="skip"))


def tegn_3d(pts, H, dorer, panel_key, rom_type, azimuth=-55, elevation=28):
    return tegn_3d_med_panelbredde(pts, H, dorer, panel_key, rom_type, 1.10, azimuth, elevation)


def tegn_3d_med_panelbredde(pts, H, dorer, panel_key, rom_type, panelbredde_m, azimuth=-55, elevation=28,
                             apninger=None, excluded_walls=()):
    """
    Interaktiv 3D-modell med samme panelmotor som kapplisten.
    Tak-/gulvpanelene klippes mot polygonet, slik at avskåret hjørne vises riktig.
    """
    pts_a = np.array(pts, dtype=float)
    winding = polygon_winding(pts)
    nn = len(pts_a)
    if nn < 3:
        return go.Figure()

    WT = PANEL_DB[panel_key]["t"] / 1000.0
    UC = CHANNEL_HEIGHT
    TAK = WT
    BET = 0.080
    z0 = wall_base(rom_type,panel_key)
    z1 = z0 + H
    z_roof_top = z1 + TAK
    IS_FRYS = "Fryserom" in rom_type

    UKAN_W, UKAN_H = WT + 2*CHANNEL_FLANGE, UC          # U-kanal: bredde/høyde
    INNV_LEG = 0.050                    # Innv. hjørnebeslag 50×50
    UTV_LEG_UT, UTV_LEG_H = 0.050, 0.150  # Utv. hjørnebeslag 50×150

    fig = go.Figure()

    # Sokkel/gulv
    _add_polygon_mesh(fig, pts_a, BATTEN_HEIGHT if IS_FRYS else finished_floor(rom_type,panel_key), name="Gulvflate", color="#9aa8b6", opacity=0.45)

    if IS_FRYS:
        gulvpaneler = generate_roof_floor_panels(floor_outline(pts,WT), int(round(panelbredde_m * 1000)), prefix="G", label="Gulv PIR", cut_position="end")
        for idx, p in enumerate(gulvpaneler):
            pa = np.array(p.polygon, dtype=float)
            _add_polygon_mesh(fig, pa, wall_base(rom_type,panel_key), name=f"{p.name} {p.width_mm}×{p.span_mm} mm", color="#88b886", opacity=0.65)
            _add_vertical_faces(fig, pa, BATTEN_HEIGHT, wall_base(rom_type,panel_key), name=f"{p.name} gulvtykkelse", color="#6a9f6a", opacity=0.35)

        for p in generate_roof_floor_panels(pts, int(round(panelbredde_m*1000)), prefix="F"):
            pa = np.array(p.polygon, dtype=float)
            _add_polygon_mesh(fig, pa, finished_floor(rom_type, panel_key), name="Gulvplate 12 mm", color="#d4a96a", opacity=0.8)
            _add_vertical_faces(fig, pa, wall_base(rom_type,panel_key), finished_floor(rom_type, panel_key), name="Fiberplate tykkelse", color="#d4a96a")

    # Vegger
    layout=wall_panel_layout(pts,round(panelbredde_m*1000),WT,excluded_walls)
    for i in range(nn):
        if i in excluded_walls:
            continue
        p1,p2=pts_a[i],pts_a[(i+1)%nn]
        direction=(p2-p1)/np.linalg.norm(p2-p1)
        inward=winding*np.array([-direction[1],direction[0]])
        footprint=wall_polygon(pts,i,WT,excluded_walls)
        distances=(footprint-p1)@direction
        lo,hi=float(distances.min()),float(distances.max())
        holes=[]
        for entry in dorer or []:
            key,count=entry[:2]
            wi=entry[2] if len(entry)>2 else 0
            off=entry[3] if len(entry)>3 else .35
            if wi==i:
                width=DOR_DB[key]['bw']/1000
                for k in range(count):
                    x=off+k*(width+.2)
                    holes.append((x,x+width,floor_depth(rom_type),floor_depth(rom_type)+DOR_DB[key]['bh']/1000))
        for wi,off,width,height,sill,*_ in apninger or []:
            if wi==i:
                holes.append((off,off+width,floor_depth(rom_type)+sill,floor_depth(rom_type)+sill+height))
        xs=sorted({lo,hi,*[max(lo,min(hi,x)) for hole in holes for x in hole[:2]]})
        zs=sorted({0.,H,*[max(0.,min(H,z)) for hole in holes for z in hole[2:]]})
        batch=_QuadBatch(f"Vegg {i+1} – panel",_wall_color(i),opacity=.96)
        for left,right in zip(xs,xs[1:]):
            poly=wall_panel_polygon(pts,i,left,right,WT,excluded_walls)
            for bottom,top in zip(zs,zs[1:]):
                if any(x0<(left+right)/2<x1 and b<(bottom+top)/2<t for x0,x1,b,t in holes):
                    continue
                for u,v in zip(poly,np.roll(poly,-1,axis=0)):
                    batch.quad(u,v,z0+bottom,z0+top)
                for level in (z0+bottom,z0+top):
                    for indices in _polygon_triangles(poly):
                        triangle=poly[list(indices)]
                        n=len(batch.x)
                        batch.x.extend(triangle[:,0]);batch.y.extend(triangle[:,1]);batch.z.extend([level]*3)
                        batch.i.append(n);batch.j.append(n+1);batch.k.append(n+2)
        batch.flush(fig)
        for panel in (p for p in layout if p['wall']==i):
            distance=panel['start_mm']/1000
            if distance<=lo+1e-6:
                continue
            for depth in (0.,-WT):
                q=p1+direction*distance+inward*depth
                _add_line(fig,[q[0],q[0]],[q[1],q[1]],[z0,z1],name='Vegg-elementskjøt',color='#566573',width=3)

    # Takpaneler – faktiske polygoner, ikke bare én hel takplate
    takpaneler = generate_roof_floor_panels(roof_outline(pts,WT,rom_type), int(round(panelbredde_m * 1000)), prefix="T", label="Tak", cut_position="end")
    for idx, p in enumerate(takpaneler):
        pa = np.array(p.polygon, dtype=float)
        color = "#aab1b7"
        _add_polygon_mesh(fig, pa, z_roof_top, name=f"{p.name} {p.width_mm}×{p.span_mm} mm", color=color, opacity=0.18)
        _add_vertical_faces(fig, pa, z1, z_roof_top, name=f"{p.name} taktykkelse", color=color, opacity=0.12)
        # Omriss/skjøter
        closed = list(pa) + [pa[0]]
        _add_line(fig, [q[0] for q in closed], [q[1] for q in closed], [z_roof_top + 0.006] * len(closed), name=f"Omriss {p.name}", color="#727d85", width=2)
    _roof_hatching(fig, roof_outline(pts, WT, rom_type), z_roof_top + .009)

    # ── Beslag – tegnes alltid, som faktiske bøyde profiler ────────────────────
    # Samlet i tre batcher (én trace hver) i stedet for én trace per liten
    # flens – ellers blir det fort 40+ ekstra traces å laste i nettleseren.
    ukanal_b = _QuadBatch(f"U-kanal {round(WT*1000)} mm", "#315b7d", showlegend=True)
    innv_b   = _QuadBatch("Innv. hjørnebeslag 50×50", "#1f77b4", showlegend=True)
    utv_b    = _QuadBatch("Utv. hjørnebeslag 50×150", "#e67e22", showlegend=True)

    for i in range(nn):
        if i in excluded_walls:
            continue
        p1, p2 = pts_a[i], pts_a[(i + 1) % nn]
        dx_n = (p2 - p1) / (float(np.linalg.norm(p2 - p1)) + 1e-9)
        perp = winding * np.array([-dx_n[1], dx_n[0]])   # innadrettet (CCW polygon)

        # U-kanal (gulv→vegg): U-profil med to oppbrettede sider
        if IS_FRYS:
            _add_l_flange_run(innv_b,p1,p2,perp,z_knekk=z0,leg_v=INNV_LEG,leg_h=INNV_LEG,vert_up=True,horiz_inn=True)
            _add_l_flange_run(utv_b,p1-perp*WT,p2-perp*WT,perp,z_knekk=z0,leg_v=UTV_LEG_H,leg_h=UTV_LEG_UT,vert_up=False,horiz_inn=False)
        else:
            from construction import wall_span
            lo,hi=wall_span(pts,i,WT,excluded_walls)
            _add_u_kanal(ukanal_b,p1+dx_n*lo+perp*CHANNEL_FLANGE,p1+dx_n*hi+perp*CHANNEL_FLANGE,-perp,UKAN_W,UKAN_H,base=0)

        # Innv. hjørnebeslag – vinkeljern i innvendig vegg/tak-hjørne
        _add_l_flange_run(innv_b, p1, p2, perp, z_knekk=z1, leg_v=INNV_LEG, leg_h=INNV_LEG,
                          vert_up=False, horiz_inn=True)

        # Utv. hjørnebeslag – fasadeblikk utenpå vegg/tak-hjørne
        _add_l_flange_run(utv_b, p1, p2, perp, z_knekk=z1, leg_v=UTV_LEG_H, leg_h=UTV_LEG_UT,
                          vert_up=True, horiz_inn=False)

    # Vertikale hjørnestolper – innv. i vanlige (konvekse) hjørner,
    # utv. i eventuelle re-entrante (konkave) hjørner, som i materiallisten.
    for i in range(nn):
        if i in excluded_walls or (i-1)%nn in excluded_walls:
            continue
        pm, pc, pn = pts_a[(i - 1) % nn], pts_a[i], pts_a[(i + 1) % nn]
        v1, v2 = pc - pm, pn - pc
        L1, L2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
        if L1 < 1e-9 or L2 < 1e-9:
            continue
        dir_prev, dir_next = -v1 / L1, v2 / L2
        perp_prev = winding * np.array([-v1[1], v1[0]]) / L1
        perp_next = winding * np.array([-v2[1], v2[0]]) / L2
        konveks = winding * (v1[0] * v2[1] - v1[1] * v2[0]) >= 0
        _add_l_post(innv_b, pc, dir_prev, dir_next, perp_prev, perp_next, INNV_LEG, z0, z1, offset=0.005)
        _add_l_post(utv_b, pc, dir_prev, dir_next, -perp_prev, -perp_next, UTV_LEG_UT, z0, z1, offset=WT)


    ukanal_b.flush(fig)
    innv_b.flush(fig)
    utv_b.flush(fig)

    # Dører – plassert på riktig vegg med offset
    if dorer:
        for entry in dorer:
            dk  = entry[0]; ant = int(entry[1])
            wi  = int(entry[2]) if len(entry) > 2 else 0
            off = float(entry[3]) if len(entry) > 3 else 0.35
            if wi >= len(pts_a) or wi in excluded_walls:
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
                _add_quad(fig, s, e, finished_floor(rom_type, panel_key), finished_floor(rom_type, panel_key) + dh,
                          name=f"Dør – {DOR_DB[dk]['label']}", color="#ffffff", opacity=1.0)
                _add_line(fig,
                          [s[0], e[0], e[0], s[0], s[0]],
                          [s[1], e[1], e[1], s[1], s[1]],
                          [finished_floor(rom_type, panel_key), finished_floor(rom_type, panel_key), finished_floor(rom_type, panel_key)+dh, finished_floor(rom_type, panel_key)+dh, finished_floor(rom_type, panel_key)],
                          name="Dørkarm", color="#b00020", width=5)
                outward=winding*np.array([direction[1],-direction[0]])
                so,eo=s+outward*WT,e+outward*WT
                _add_quad(fig,so,eo,finished_floor(rom_type,panel_key),finished_floor(rom_type,panel_key)+dh,
                          name='Utside dør',color='#ffffff',opacity=1.)
                _add_line(fig,[so[0],eo[0],eo[0],so[0],so[0]],[so[1],eo[1],eo[1],so[1],so[1]],
                          [finished_floor(rom_type,panel_key),finished_floor(rom_type,panel_key),
                           finished_floor(rom_type,panel_key)+dh,finished_floor(rom_type,panel_key)+dh,finished_floor(rom_type,panel_key)],
                          name='Dørkarm utside',color='#b00020',width=5)
                cursor += dw + 0.20

    # Åpninger / klassfronter – hvit fyll + cyan ramme
    if apninger:
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, ap_lbl = ap
            if ap_wall >= len(pts_a) or ap_wall in excluded_walls:
                continue
            p1a = pts_a[ap_wall]; p2a = pts_a[(ap_wall+1) % len(pts_a)]
            La  = float(np.linalg.norm(p2a - p1a))
            if La < 1e-6 or ap_off + ap_w > La:
                continue
            da = (p2a - p1a) / La
            s_a = p1a + da * ap_off
            e_a = p1a + da * (ap_off + ap_w)
            z_bot = finished_floor(rom_type, panel_key) + ap_sill
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
            dragmode="turntable",
            camera=dict(eye=dict(x=1.6, y=-1.7, z=1.15), up=dict(x=0,y=0,z=1), projection=dict(type="orthographic")),
            bgcolor="#f7f9fc",
        ),
        # Under plottet, ikke over – der kolliderte den med tittelen.
        legend=dict(orientation="h", yanchor="top", y=-0.03, xanchor="left", x=0),
    )
    return fig
