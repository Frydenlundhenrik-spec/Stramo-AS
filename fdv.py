from __future__ import annotations

import pandas as pd

from database import PANEL_DB, DOR_DB, BESLAG_DB, GULV_DB_KJOL, GULV_DB_FRYS


def lag_fdv_oversikt(panel_key: str, rom_type: str, dorer: list[tuple[str, int]], beslag_valg: list[str]) -> pd.DataFrame:
    """Lager enkel FDV-oversikt som kan eksporteres videre."""
    panel = PANEL_DB[panel_key]
    rows = [
        {
            "Bygningsdel": "Vegger og tak",
            "Produkt": panel["label"],
            "Vedlikehold": "Visuell kontroll av skjøter, overflater og tettinger.",
            "Intervall": "Årlig",
            "Dokumentasjon": "Produktdatablad, monteringsanvisning, eventuell ytelseserklæring.",
        }
    ]

    if "Fryserom" in rom_type:
        rows.append({
            "Bygningsdel": "Gulv",
            "Produkt": GULV_DB_FRYS["label"],
            "Vedlikehold": "Kontroller plastbelegg, skjøter og gjennomføringer. Utbedre skader raskt.",
            "Intervall": "Halvårlig",
            "Dokumentasjon": "Produktdatablad for PIR-gulvpanel og sponplate/plastbelegg.",
        })
    else:
        rows.append({
            "Bygningsdel": "Gulv",
            "Produkt": GULV_DB_KJOL["label"],
            "Vedlikehold": "Kontroller fall, renhold, overflate og overgang mot veggpanel.",
            "Intervall": "Årlig",
            "Dokumentasjon": "Betong-/gulvbeskrivelse og rengjøringsrutine.",
        })

    for door_key, ant in dorer:
        if ant <= 0:
            continue
        d = DOR_DB[door_key]
        rows.append({
            "Bygningsdel": "Dør",
            "Produkt": f"{d['label']} ({ant} stk)",
            "Vedlikehold": "Kontroller pakning, hengsler, låsekasse, terskel, nødåpner og selvlukker.",
            "Intervall": "Kvartalsvis",
            "Dokumentasjon": "FDV for dør, beslag og eventuelt varmekabel.",
        })

    for beslag_key in beslag_valg:
        b = BESLAG_DB[beslag_key]
        rows.append({
            "Bygningsdel": "Dørbeslag",
            "Produkt": b["label"],
            "Vedlikehold": "Funksjonstest, stramming av skruer og renhold.",
            "Intervall": "Halvårlig",
            "Dokumentasjon": "Produktdatablad / leverandørdokumentasjon.",
        })

    rows.append({
        "Bygningsdel": "Renhold",
        "Produkt": "Kjøle-/fryserom generelt",
        "Vedlikehold": "Bruk egnet rengjøringsmiddel. Unngå mekanisk skade på paneloverflater.",
        "Intervall": "Etter brukerens renholdsplan",
        "Dokumentasjon": "Renholdsplan og avvikslogg.",
    })
    return pd.DataFrame(rows)


def lag_fdv_tekst(prosjektnavn: str, panel_key: str, rom_type: str) -> str:
    panel = PANEL_DB[panel_key]
    return f"""# FDV-dokumentasjon – {prosjektnavn or 'Kjølerom'}

## Anlegg
Romtype: {rom_type}  
Panel: {panel['label']}  
U-verdi: {panel['u']} W/m²K

## Drift
Rommet skal driftes i henhold til prosjektert temperatur og leverandørens krav til renhold, lufting og service.

## Vedlikehold
Kontroller jevnlig dørfunksjon, pakninger, overganger, skjøter, terskler, beslag og gulvoverflate. Skader i paneloverflate eller tettinger bør utbedres raskt for å hindre fuktinntrenging og hygieniske avvik.

## Dokumentasjon som bør legges ved
- Produktdatablad for paneler
- Monteringsanvisning
- FDV for dør og beslag
- Eventuell dokumentasjon på gulv, varmekabel og tettemasser
- IFC-fil og montasjetegninger
- Kappliste og materialliste
"""
