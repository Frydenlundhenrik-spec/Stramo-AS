from __future__ import annotations
from typing import Any
from database import PANEL_DB

from drawing_2d import stramo_plan, stramo_snitt, stramo_tak, tegn_veggoppstalt, stramo_produksjonstegninger, fig2png
from drawing_3d import tegn_3d_med_panelbredde


def tegn_plantegning(inp: Any, result: dict, bakgrunn=None, apninger=None):
    info = lag_tegningsinfo(inp, result, "Plantegning")
    return stramo_plan(inp.pts, inp.hoyde_m, inp.panelbredde_m,
                       inp.dorer, info, bakgrunn, apninger=apninger,
                       wall_thickness=PANEL_DB[inp.panel_key]["t"] / 1000, excluded_walls=inp.excluded_walls)


def tegn_snitt(inp: Any, result: dict, vegg_idx: int = 0, seksjon: str = "A-A", apninger=None):
    info = lag_tegningsinfo(inp, result, f"Snitt {seksjon}")
    return stramo_snitt(inp.pts, inp.hoyde_m, inp.panelbredde_m,
                        inp.dorer, info, inp.rom_type, inp.panel_key,
                        vegg_idx, seksjon, apninger=apninger)


def tegn_veggoppstaltt(inp: Any, result: dict, vegg_idx: int = 0, apninger=None):
    info = lag_tegningsinfo(inp, result, f"Veggoppstalt V{vegg_idx+1}")
    return tegn_veggoppstalt(inp.pts, inp.hoyde_m, inp.panelbredde_m,
                              inp.dorer, info, vegg_idx, apninger=apninger, rom_type=inp.rom_type, excluded_walls=getattr(inp,"excluded_walls",()), wall_thickness=PANEL_DB[inp.panel_key]["t"]/1000)


def tegn_taktegning(inp: Any, result: dict):
    info = lag_tegningsinfo(inp, result, "Taktegning")
    return stramo_tak(inp.pts, inp.hoyde_m, inp.panelbredde_m,
                      inp.dorer, info, inp.rom_type, inp.panel_key)


def tegn_produksjonsfigurer(inp: Any, result: dict, bare_tilpassede: bool = False):
    info = lag_tegningsinfo(inp, result, "Produksjonstegning")
    return stramo_produksjonstegninger(
        pts=inp.pts,
        H=inp.hoyde_m,
        pw_m=inp.panelbredde_m,
        panel_key=inp.panel_key,
        rom_type=inp.rom_type,
        info=info,
        bare_tilpassede=bare_tilpassede,
        excluded_walls=getattr(inp,"excluded_walls",()),
        dorer=getattr(inp, "dorer", []),
        apninger=getattr(inp, "apninger", []),
    )


def tegn_3d_modell(inp: Any, azimuth: int = -55, elevation: int = 28, apninger=None):
    return tegn_3d_med_panelbredde(inp.pts, inp.hoyde_m, inp.dorer,
                                    inp.panel_key, inp.rom_type,
                                    inp.panelbredde_m, azimuth, elevation,
                                    apninger=apninger, excluded_walls=getattr(inp, "excluded_walls", ()))


def lag_tegningsinfo(inp: Any, result: dict, ttype: str) -> dict:
    ov = result["ov"]
    return {
        "navn": inp.navn.strip() or "–",
        "pnr":  inp.pnr,
        "tnr":  inp.tnr,
        "dato": inp.dato,
        "maal": inp.maalestokk,
        "ttype": ttype,
        "A": ov["A"],
        "P": ov["P"],
    }


def figur_som_png(fig, dpi: int = 180) -> bytes:
    return fig2png(fig, dpi=dpi)


def figur_som_pdf(fig, title="Tegninger") -> bytes:
    import io
    from drawing_pdf import drawing_pdf
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", bbox_inches="tight")
    return drawing_pdf(buf.getvalue(),title)


def figurer_som_samlet_pdf(figs: list) -> bytes:
    """Slår sammen flere matplotlib-figurer til én PDF."""
    import io
    from drawing_pdf import drawing_pdf
    from matplotlib.backends.backend_pdf import PdfPages
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for fig in figs:
            pdf.savefig(fig, bbox_inches="tight")
    return drawing_pdf(buf.getvalue(),"Produksjonstegninger")
