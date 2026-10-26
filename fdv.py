from __future__ import annotations

import pandas as pd

from database import PANEL_DB, DOR_DB, BESLAG_DB, GULV_DB_KJOL, GULV_DB_FRYS


def lag_fdv_oversikt(panel_key: str, rom_type: str, dorer: list[tuple[str, int]], beslag_valg: list[str]) -> pd.DataFrame:
    """Prosjektoversikt; originalvedlegg følger den samlede standardpakken."""
    panel = PANEL_DB[panel_key]
    rows = [
        {
            "Bygningsdel": "Vegger og tak",
            "Produkt": panel["label"] + " – PE25 polyesterlakk, 25 µm, RAL 9010",
            "Vedlikehold": "Visuell kontroll av skjøter, overflater og tettinger.",
            "Intervall": "Årlig",
            "Dokumentasjon": "Produktdatablad, ytelseserklæring, hygienesertifikat, EPD, teknisk katalog og monteringsanvisning i standardpakken. Kontroller valgt panel mot vedleggene.",
        }
    ]

    if "Fryserom" in rom_type:
        rows.append({
            "Bygningsdel": "Gulv",
            "Produkt": GULV_DB_FRYS["label"],
            "Vedlikehold": "Kontroller gulvplaten, skjøter og gjennomføringer for skade og fukt. Produktspesifikke anvisninger ettersendes.",
            "Intervall": "Halvårlig",
            "Dokumentasjon": "Paneldokumentasjon vedlagt. Dokumentasjon for 12 mm gulvplate ettersendes. Gulvets understøttelse og tillatte belastning dokumenteres særskilt.",
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
            "Produkt": f"{'Fryseromsdør' if rom_type == 'Fryserom' else 'Kjøleromsdør'} {d['bw']} × {d['bh']} mm ({ant} stk)",
            "Vedlikehold": "Kontroller pakning, hengsler, nødåpner og lukkefunksjon etter dørleverandørens anvisning.",
            "Intervall": "Kvartalsvis",
            "Dokumentasjon": "Dørleverandørens produktspesifikke FDV vedlegges separat.",
        })

    for beslag_key in beslag_valg:
        if rom_type != "Fryserom" and beslag_key in ("Trykkventil / trykkutligningsplugg", "Terskel / rampe rustfritt stål"):
            continue
        b = BESLAG_DB[beslag_key]
        rows.append({
            "Bygningsdel": "Dørbeslag",
            "Produkt": b["label"],
            "Vedlikehold": "Funksjonstest, stramming av skruer og renhold.",
            "Intervall": "Halvårlig",
            "Dokumentasjon": "Produktdatablad / leverandørdokumentasjon.",
        })

    rows.extend([{
        "Bygningsdel": "Platebeslag",
        "Produkt": "0,6 mm stål – PE25 polyesterlakk, 25 µm, RAL 9010",
        "Vedlikehold": "Kontroller lakk, skjøter, festemidler og tetninger. Utbedre skader etter leverandørens anvisning.",
        "Intervall": "Årlig",
        "Dokumentasjon": "Beslagskatalog i standardpakken. Prosjektets måltegninger vedlegges aktuell leveranse.",
    }, {
        "Bygningsdel": "Skruer og fugemasse",
        "Produkt": "22 mm hvite skruer; fugemasse bekreftes for leveransen",
        "Vedlikehold": "Kontroller innfesting og tettinger. Produktspesifikke anvisninger ettersendes.",
        "Intervall": "Årlig kontroll; produktanvisning ettersendes",
        "Dokumentasjon": "Reserverte seksjoner i standardpakken. Produsent og produktdokumentasjon ettersendes.",
    }])
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
Overflate på paneler og platebeslag: PE25 polyesterlakk, 25 µm, RAL 9010  
U-verdi: {panel['u']} W/m²K

## Drift
Rommet skal driftes i henhold til prosjektert temperatur og leverandørens krav til renhold, lufting og service.

## Vedlikehold
Kontroller jevnlig dørfunksjon, pakninger, overganger, skjøter, terskler, beslag og gulvoverflate. Skader i paneloverflate eller tettinger bør utbedres raskt for å hindre fuktinntrenging og hygieniske avvik.

## Standardpakken
Den samlede PDF-en inneholder paneldatablad, ytelseserklæring, hygienesertifikat, EPD, teknisk panelkatalog, monteringsanvisning og beslagskatalog. Leverandørvedleggene er uendret og gjelder BALEX PIR STANDARD.

## Dokumentasjon som ettersendes
Egne seksjoner er reservert for 22 mm hvite skruer, fugemasse og 12 mm gulvplater. Gulvplaten beskytter fryseromsgulvet innenfor veggene; gulvpanelene ligger på 22 mm lekter.

## Prosjektvedlegg
Legg ved aktuelle tegninger, IFC, kapplister og materialliste. Dører, trykkventiler, kjølemaskineri og elektro dokumenteres separat der de inngår. Kontroller produktvalget mot faktisk leveranse; standardpakken er en del av samlet FDV.
"""
