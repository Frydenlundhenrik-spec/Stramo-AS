from __future__ import annotations
from construction import roof_outline
import math
import pandas as pd
from database import PANEL_DB, GULV_DB_KJOL, GULV_DB_FRYS, BESLAG_DB, DOR_DB
from geometry import beslag_beregning, poly_perim, poly_area
from construction import floor_outline, floor_depth, fixing_screw_count
from kappliste import lag_kappliste, panel_order_rows

# ── NS 3420 / kode-mapping ────────────────────────────────────────────────────
_NS: dict[str, str] = {
    "vegg":    "NS3420-H / Panel vegg",
    "tak":     "NS3420-H / Panel tak",
    "gulv_pir":"NS3420-H / PIR gulv",
    "gulv_bet":"NS3420-54 / Gulv avrettet",
    "gulv_spon":"NS3420-54 / Gulvplate",
    "dor":     "NS3420-H40 / Dør kjøl",
    "beslag":  "NS3420-H / Dørbeslag",
    "ukan":    "NS3420-H / U-kanal",
    "beslag_h":"NS3420-H / Hjørnebeslag",
}


def materialliste(
    ov: dict,
    panel_key: str,
    rom_type: str,
    dorer: list[tuple[str, int]],
    beslag_valg: list[str],
    pw_m: float,
    wls: list[float],
    pts_polygon: list[tuple[float, float]],
    pris_override: dict | None = None,
    breeam_multiplier: float = 1.0,
    excluded_walls=(),
    cut_list: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Bygger fullstendig materialliste.
    pris_override: dict med {post_key: ny_enhetspris} – for prisjustering i UI.
    breeam_multiplier: prisjustering for miljøkrav (1.0 = ingen).
    """
    pan = PANEL_DB[panel_key]
    H   = ov["H"]
    override = pris_override or {}
    rows = []

    if cut_list is None:
        cut_list = lag_kappliste(pts_polygon, round(H*1000), round(pw_m*1000), rom_type,
                                excluded_walls=tuple(excluded_walls), floor_panel_mm=pan["t"])
    ordered = panel_order_rows(cut_list, round(H*1000), round(pw_m*1000))

    def ep(key: str, default: float) -> float:
        return override.get(key, default) * breeam_multiplier

    # ── Vegger ──────────────────────────────────────────────────────────────
    for i, wl in enumerate(wls):
        if i in excluded_walls:
            continue
        np_ = len(ordered[ordered.Vegg == f"Vegg {i+1}"])
        area = float(ordered.loc[ordered.Vegg == f"Vegg {i+1}", "Bestill_m2"].sum())
        unit_p = ep(f"vegg_{i}", pan["pris"])
        rows.append(dict(
            Post=f"Vegg {i+1}", Type=pan["label"], Enhet="m²",
            Mengde=area, **_kr(unit_p, area), NS3420=_NS["vegg"],
            CO2_k=pan["co2"],
        ))

    # ── Tak ─────────────────────────────────────────────────────────────────
    unit_tak = ep("tak", pan["pris"])
    roof_area = float(ordered.loc[ordered.Vegg == "Tak", "Bestill_m2"].sum())
    rows.append(dict(
        Post="Tak (panel)", Type=pan["label"], Enhet="m²",
        Mengde=roof_area, **_kr(unit_tak, roof_area), NS3420=_NS["tak"],
        CO2_k=pan["co2"],
    ))

    # ── Gulv ─────────────────────────────────────────────────────────────────
    if rom_type.startswith("Kjølerom"):
        pass  # Kjølerom: gulvet er eksisterende betong, ikke kalkulert
    else:
        unit_pir = ep("gulv_pir", pan["pris"])
        floor_area = float(ordered.loc[ordered.Vegg == "Gulv", "Bestill_m2"].sum())
        rows.append(dict(
            Post=f"Gulv – {pan['label']}", Type=pan["label"],
            Enhet="m²", Mengde=floor_area, **_kr(unit_pir, floor_area),
            NS3420=_NS["gulv_pir"], CO2_k=pan["co2"],
        ))
        unit_spon = ep("gulv_finer", 0)
        rows.append(dict(
            Post="Gulv – gulvplate 12 mm", Type="Gulvplate 12 mm" + (" – PRIS MANGLER" if unit_spon == 0 else ""),
            Enhet="m²", Mengde=ov["A"], **_kr(unit_spon, ov["A"]),
            NS3420=_NS["gulv_spon"], CO2_k=8.5,
        ))

    # ── Dører ─────────────────────────────────────────────────────────────────
    nd = 0
    for dk, ant in dorer:
        if ant > 0:
            d = DOR_DB[dk]
            door_label = ("Fryseromsdør" if rom_type == "Fryserom" else "Kjøleromsdør") + f" {d['bw']}×{d['bh']} mm"
            unit_dor = ep(f"dor_{dk}", d["pris"])
            rows.append(dict(
                Post="Dør", Type=door_label + (" – PRIS MANGLER" if unit_dor == 0 else ""), Enhet="stk",
                Mengde=ant, **_kr(unit_dor, ant),
                NS3420="NS3420-H40 / Dør frys" if rom_type == "Fryserom" else _NS["dor"], CO2_k=0.0,
            ))
            nd += ant

    # ── Dørbeslag ─────────────────────────────────────────────────────────────
    valve_key = "Trykkventil / trykkutligningsplugg"
    selected = list(dict.fromkeys(beslag_valg))
    if rom_type == "Fryserom" and valve_key not in selected:
        selected.append(valve_key)
    for bk in selected:
        b = BESLAG_DB[bk]
        if b["label"] in ("Varmekabel pr. m","Låsekasse kjøl","Hengsel rustfritt"):
            continue
        if bk == valve_key and rom_type != "Fryserom":
            continue
        if b["label"] == "Terskel rustfritt" and rom_type != "Fryserom":
            continue
        ant = 1 if bk == valve_key else b["ape"] * nd
        unit_b = ep(f"beslag_{bk}", b["pris"])
        rows.append(dict(
            Post="Tilbehør", Type=b["label"], Enhet="stk",
            Mengde=ant, **_kr(unit_b, ant),
            NS3420=_NS["beslag"], CO2_k=0.0,
        ))

    # ── U-kanal ───────────────────────────────────────────────────────────────
    if rom_type != "Fryserom":
        UKAN_M  = 2.5
        unit_uk = ep("ukan", 220)
        from finishing import trim_order
        from construction import wall_span
        spans = [wall_span(pts_polygon,i,pan['t']/1000,excluded_walls)
                 for i in range(len(wls)) if i not in excluded_walls]
        stk_uk = trim_order(sum(hi-lo for lo,hi in spans))
        rows.append(dict(
            Post=f"U-kanal {pan['t']} mm (gulv→vegg)",
            Type=f"U-kanal {pan['t']} mm · 0,6 mm stål · RAL 9010 · lengde 2500 mm",
            Enhet="stk", Mengde=stk_uk, **_kr(unit_uk, stk_uk),
            NS3420=_NS["ukan"], CO2_k=UKAN_M * 0.6,
        ))

    # ── Hjørnebeslag ──────────────────────────────────────────────────────────
    bb = beslag_beregning(pts_polygon, H, excluded_walls, pan["t"]/1000, H-floor_depth(rom_type), floor_angles=rom_type=="Fryserom")
    unit_inn = ep("beslag_inn", 185)
    unit_ut  = ep("beslag_ut",  265)
    rows.append(dict(
        Post="Innv. hjørnebeslag 50×50 mm",
        Type="Innvendig 50×50 mm · 0,6 mm stål · RAL 9010 · lengde 2500 mm",
        Enhet="stk", Mengde=bb["stk_inn"], **_kr(unit_inn, bb["stk_inn"]),
        NS3420=_NS["beslag_h"], CO2_k=2.5 * 0.8,
    ))
    rows.append(dict(
        Post="Utv. hjørnebeslag 50×150 mm",
        Type="Utvendig 50×150 mm · 0,6 mm stål · RAL 9010 · lengde 2500 mm",
        Enhet="stk", Mengde=bb["stk_ut"], **_kr(unit_ut, bb["stk_ut"]),
        NS3420=_NS["beslag_h"], CO2_k=2.5 * 0.8,
    ))

    screw_count = fixing_screw_count(pts_polygon, H, rom_type, pan["t"]/1000, excluded_walls)
    screw_price = ep("skruer", 0)
    rows.append(dict(Post="Skruer", Type="22 mm hvite skruer", Enhet="stk",
                     Mengde=screw_count, **_kr(screw_price, screw_count),
                     NS3420="Festemidler", CO2_k=0.0))
    for row in rows:
        if row["Mengde"] > 0 and row["EP"] <= 0 and "PRIS MANGLER" not in row["Type"]:
            row["Type"] += " – PRIS MANGLER"
    df = pd.DataFrame(rows)
    df["CO₂ (kg)"] = (df["Mengde"] * df["CO2_k"]).round(1)
    df = df.drop(columns=["CO2_k"])
    df = df.rename(columns={"EP": "Enhetspris (kr)", "TP": "Totalpris (kr)"})
    df["Mengde"] = df["Mengde"].round(6)
    return df


def _kr(ep: float, mengde: float) -> dict:
    return {"EP": round(ep, 2), "TP": round(ep * mengde, 2)}
