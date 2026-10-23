from __future__ import annotations

import io
from typing import Any

import pandas as pd


def lag_excel(result: dict[str, Any], fdv_df: pd.DataFrame | None = None) -> bytes:
    """Eksporterer kalkulasjon, materialliste, kappliste og FDV til én Excel-fil."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result["df_mat"].to_excel(writer, index=False, sheet_name="Materialliste")
        result["df_kapp"].to_excel(writer, index=False, sheet_name="Kappliste")
        pd.DataFrame([
            {"Post": "Gulvareal", "Verdi": result["ov"]["A"], "Enhet": "m²"},
            {"Post": "Volum", "Verdi": result["ov"]["V"], "Enhet": "m³"},
            {"Post": "Omkrets", "Verdi": result["ov"]["P"], "Enhet": "m"},
            {"Post": "Totalpris" if result.get("pricing_complete",True) else "Priset delsum", "Verdi": result["tot_pris"], "Enhet": "kr"},
            {"Post": "Manglende priser", "Verdi": "; ".join(result.get("missing_prices",[])), "Enhet": ""},
            {"Post": "CO₂", "Verdi": result["tot_co2"], "Enhet": "kg"},
        ]).to_excel(writer, index=False, sheet_name="Sammendrag")
        if fdv_df is not None:
            fdv_df.to_excel(writer, index=False, sheet_name="FDV")
    return output.getvalue()
