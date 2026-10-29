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
    dorer: list[tuple],
    beslag_valg: list[str],
    pw_m: float,
    wls: list[float],
    pts_polygon: list[tuple[float, float]],
    pris_override: dict | None = None,
    breeam_multiplier: float = 1.0,
    excluded_walls=(),
    cut_list: pd.DataFrame | None = None,
    plywood_width_mm: int = 1500,
    plywood_length_mm: int = 3000,
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

    # Hele råelementer grupperes på leveringsmål, som i bestillingslisten.
    for (length, width), blanks in ordered.groupby(
            ["Leveringslengde_mm", "Bredde_mm"], sort=False):
        area = float(blanks.Bestill_m2.sum())
        cost = 0.0
        missing_price = False
        for allocation in blanks.Fordeling_m2:
            for zone, allocated_area in allocation.items():
                key = f"vegg_{int(zone.split()[1])-1}" if zone.startswith("Vegg ") else {
                    "Tak": "tak", "Gulv": "gulv_pir"}[zone]
                unit_price = ep(key, pan["pris"])
                missing_price |= not math.isfinite(unit_price) or unit_price <= 0
                cost += allocated_area * unit_price
        rows.append(dict(
            Post="Panel", Type=pan["label"] + (" – PRIS MANGLER" if missing_price else ""), Enhet="m²",
            Leveringslengde_mm=int(length), Bredde_mm=int(width), Tykkelse_mm=pan["t"],
            Bestill_hele_elementer=len(blanks), Mengde=area,
            **_kr(cost / area, area), NS3420=_NS["vegg"], CO2_k=pan["co2"],
        ))

    # ── Gulv ─────────────────────────────────────────────────────────────────
    if rom_type.startswith("Kjølerom"):
        pass  # Kjølerom: gulvet er eksisterende betong, ikke kalkulert
    else:
        from finishing import plywood_cuts, board_count
        board_area = board_count(plywood_cuts(pts_polygon, plywood_width_mm, plywood_length_mm)) * plywood_width_mm * plywood_length_mm / 1e6
        unit_spon = ep("gulv_finer", 1000)
        rows.append(dict(
            Post="Gulv – gulvplate 12 mm", Type="Gulvplate 12 mm" + (" – PRIS MANGLER" if unit_spon == 0 else ""),
            Enhet="m²", Mengde=board_area, **_kr(unit_spon, board_area),
            NS3420=_NS["gulv_spon"], CO2_k=8.5,
        ))

    # ── Dører ─────────────────────────────────────────────────────────────────
    nd = 0
    for door in dorer:
        dk, ant = door[:2]
        if ant > 0:
            d = DOR_DB[dk]
            door_label = ("Fryseromsdør" if rom_type == "Fryserom" else "Kjøleromsdør") + f" {d['bw']}×{d['bh']} mm"
            hinge = door[4] if len(door) > 4 else "Ikke angitt"
            door_label += f" · Slagretning: {hinge} (sett innenfra)"
            if len(door) > 2:
                door_label += f" · Vegg {int(door[2]) + 1}"
            unit_dor = ep(f"dor_{dk}", d["pris"])
            for _ in range(int(ant)):
                rows.append(dict(
                    Post="Dør", Type=door_label + (" – PRIS MANGLER" if unit_dor == 0 else ""), Enhet="stk",
                    Mengde=1, **_kr(unit_dor, 1),
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
        if b["label"] in ("Varmekabel pr. m","Låsekasse kjøl","Hengsel rustfritt","Magnetpakning"):
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
        from finishing import trim_order
        from construction import wall_span
        spans = [wall_span(pts_polygon,i,pan['t']/1000,excluded_walls)
                 for i in range(len(wls)) if i not in excluded_walls]
        stk_uk = trim_order(sum(hi-lo for lo,hi in spans))
        rows.append(dict(
            Post=f"U-kanal {pan['t']} mm (gulv→vegg)",
            Type=f"U-kanal {pan['t']} mm · 0,6 mm stål · RAL 9010 · lengde 2500 mm",
            Enhet="stk", Mengde=stk_uk, **_kr(math.nan, stk_uk),
            NS3420=_NS["ukan"], CO2_k=UKAN_M * 0.6,
        ))

    # ── Hjørnebeslag ──────────────────────────────────────────────────────────
    bb = beslag_beregning(pts_polygon, H, excluded_walls, pan["t"]/1000, H-floor_depth(rom_type), floor_angles=rom_type=="Fryserom")
    # Beslag føres uten pris, også når eldre prosjektfiler har prisoverstyringer.
    rows.append(dict(
        Post="Innv. hjørnebeslag 50×50 mm",
        Type="Innvendig 50×50 mm · 0,6 mm stål · RAL 9010 · lengde 2500 mm",
        Enhet="stk", Mengde=bb["stk_inn"], **_kr(math.nan, bb["stk_inn"]),
        NS3420=_NS["beslag_h"], CO2_k=2.5 * 0.8,
    ))
    rows.append(dict(
        Post="Utv. hjørnebeslag 50×150 mm",
        Type="Utvendig 50×150 mm · 0,6 mm stål · RAL 9010 · lengde 2500 mm",
        Enhet="stk", Mengde=bb["stk_ut"], **_kr(math.nan, bb["stk_ut"]),
        NS3420=_NS["beslag_h"], CO2_k=2.5 * 0.8,
    ))

    from accessories import CATALOG, accessory_needs, order_quantities
    needs = accessory_needs(pts_polygon, H, rom_type, pan["t"]/1000, dorer, cut_list, excluded_walls)
    for key, count in order_quantities(needs).items():
        label, unit, default, _ = CATALOG[key]
        rows.append(dict(Post="Tilbehør beregnet", Type=label, Enhet=unit,
                         Mengde=count, **_kr(ep(key, default), count),
                         NS3420="Tilbehør", CO2_k=0.0))
    for row in rows:
        if row["Mengde"] > 0 and (not math.isfinite(row["EP"]) or row["EP"] <= 0) and "PRIS MANGLER" not in row["Type"]:
            row["Type"] += " – PRIS MANGLER"
    df = pd.DataFrame(rows)
    df["CO₂ (kg)"] = (df["Mengde"] * df["CO2_k"]).round(1)
    df = df.drop(columns=["CO2_k"])
    df = df.rename(columns={"EP": "Enhetspris (kr)", "TP": "Totalpris (kr)"})
    df["Mengde"] = df["Mengde"].round(6)
    return df


def _kr(ep: float, mengde: float) -> dict:
    return {"EP": round(ep, 2), "TP": round(ep * mengde, 2)}


def materialliste_med_sum(frame: pd.DataFrame) -> pd.DataFrame:
    """Present material rows and the sum of entered prices, without changing calculation data."""
    table = frame.drop(columns=["CO₂ (kg)", "NS3420"], errors="ignore").copy()
    table["Type"] = table["Type"].str.removesuffix(" – PRIS MANGLER")
    dimensions = {"Leveringslengde_mm": "Leveringslengde (mm)", "Bredde_mm": "Bredde (mm)",
                  "Tykkelse_mm": "Tykkelse (mm)", "Bestill_hele_elementer": "Antall (stk)"}
    table = table.rename(columns=dimensions)
    table = table.reindex(columns=["Post", "Type", *dimensions.values(), "Enhet", "Mengde",
                                   "Enhetspris (kr)", "Totalpris (kr)"])
    total = {"Post": "SUM", "Type": "", "Enhet": "",
             "Totalpris (kr)": round(float(table["Totalpris (kr)"].sum()), 2)}
    return pd.concat([table, pd.DataFrame([total])], ignore_index=True)
