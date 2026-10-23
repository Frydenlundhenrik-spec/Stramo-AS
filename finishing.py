"""Conservative cutting proposals: 2500 mm trims and one plywood blank per tile."""
import math
import re
import numpy as np
from panel_engine import clip_polygon_between_x, polygon_area


def trim_order(net_m):
    """Beslag only: add 10 percent once, then round up to whole 2500 mm bars."""
    return math.ceil(net_m * 1.10 / 2.5 - 1e-10)


def trim_cuts(lengths, stock_mm=2500):
    pieces = []
    for label, length in lengths:
        remaining = round(length*1000)
        while remaining > 0:
            cut = min(stock_mm, remaining)
            pieces.append((label,cut))
            remaining -= cut
    bars = []
    for label,cut in sorted(pieces,key=lambda p:-p[1]):
        bar = next((b for b in bars if sum(p[1] for p in b)+cut<=stock_mm),None)
        if bar is None:
            bar = []; bars.append(bar)
        bar.append((label,cut))
    return [dict(Stang=i+1,Kapp=" + ".join(f"{n} mm ({s})" for s,n in bar),
                 Rest_mm=stock_mm-sum(n for _,n in bar)) for i,bar in enumerate(bars)]


def grouped_trim_bars(rows):
    """Combine identical cutting patterns per profile, including across rooms."""
    groups = {}
    for row in rows:
        lengths = tuple(sorted((int(n) for n in re.findall(r"(\d+) mm \(", row["Kapp"])), reverse=True))
        if not lengths or sum(lengths)+row["Rest_mm"] != 2500:
            raise ValueError("Ugyldig kappforslag for 2500 mm beslag.")
        key = row["Profil"], lengths, row["Rest_mm"]
        if key not in groups:
            groups[key] = dict(Profil=row["Profil"],Antall_stenger=0,
                Kapp_pr_stang=" + ".join(f"{n} mm" for n in lengths),Rest_pr_stang_mm=row["Rest_mm"],
                Løpemeter=0.0)
        groups[key]["Antall_stenger"] += 1
        groups[key]["Løpemeter"] += 2.5
    return list(groups.values())


def plywood_cuts(pts, width_mm=1500, length_mm=3000):
    if min(width_mm,length_mm)<100 or max(width_mm,length_mm)>10000:
        raise ValueError("Plateformat må være mellom 100 og 10000 mm.")
    poly = np.asarray(pts,float)
    def layout(w,h):
        rows = []
        x0,y0 = poly.min(axis=0); x1,y1 = poly.max(axis=0)
        for i in range(math.ceil((x1-x0)*1000/w)):
            strip = clip_polygon_between_x(poly,x0+i*w/1000,x0+(i+1)*w/1000)
            if len(strip)<3: continue
            for j in range(math.ceil((y1-y0)*1000/h)):
                tile = clip_polygon_between_x(strip[:,::-1],y0+j*h/1000,y0+(j+1)*h/1000)[:,::-1]
                if len(tile)<3 or polygon_area(tile)<1e-8: continue
                span = np.ptp(tile,axis=0)*1000
                rows.append(dict(Plate=f"F{len(rows)+1}",Bredde_mm=round(span[0]),Lengde_mm=round(span[1]),
                    Tykkelse_mm=12,Areal_m2=round(polygon_area(tile),6),
                    X_mm=round(tile[:,0].min()*1000),Y_mm=round(tile[:,1].min()*1000),
                    Merknad="Tilpasses polygon" if len(tile)!=4 else "Rektangulært kapp",
                    polygon=tile.tolist()))
        return rows
    return min((layout(width_mm,length_mm),layout(length_mm,width_mm)),key=len)


def plywood_plan(pts, width_mm=1500, length_mm=3000):
    """Use the same numbered plate layout in the app and the drawing delivery."""
    import matplotlib.pyplot as plt
    cuts = plywood_cuts(pts, width_mm, length_mm)
    fig, ax = plt.subplots(figsize=(8, 9))
    for cut in cuts:
        polygon = np.asarray(cut['polygon']) * 1000
        ax.fill(polygon[:, 0], polygon[:, 1], facecolor='#dfd2e9', edgecolor='#526b78')
        center = polygon.mean(axis=0)
        ax.text(*center, f"{cut['Plate']}\n{cut['Bredde_mm']} ×\n{cut['Lengde_mm']} mm",
                ha='center', va='center', fontsize=10, color='#07384c')
    ax.set_aspect('equal')
    ax.set_xlabel('mm'); ax.set_ylabel('mm')
    ax.set_title(f'Gulvplateplan – 12 mm\nPlateformat {width_mm} × {length_mm} mm', fontsize=14)
    fig.tight_layout()
    return fig
