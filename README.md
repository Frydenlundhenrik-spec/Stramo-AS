# Stramo kjøleromssystem

Dette er en modulær Streamlit-app for:

- Kalkulasjon
- FDV
- Montasjetegninger
- Kapplister
- IFC-eksport
- Samlet eksport til Excel/CSV/PDF/IFC

## Kjøring i PowerShell

Stå i prosjektmappen og kjør:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Hvis `py` ikke virker:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Filstruktur

```text
app.py
kalkulasjon.py
fdv.py
montasje.py
kappliste.py
materialer.py
ifc_export.py
drawing_2d.py
drawing_3d.py
database.py
geometry.py
export_excel.py
export_pdf.py
requirements.txt
README.md
```

## Viktig rettelse

Takelementer regnes nå slik:

- samme elementbredde som veggelementer
- takelement går fra vegg til vegg
- taket deles ikke opp som rutenett i begge retninger

## Oppdatering: polygonbasert tak/gulv og bedre IFC

Denne versjonen bruker `panel_engine.py` som felles motor for tak- og gulvpaneler.
Det betyr at kappliste, 3D-visning og IFC-eksport bruker samme geometri:

- Takelementer har samme bredde som veggelementene.
- Takelementer går fra vegg til vegg.
- Avskåret/skrå hjørne klippes riktig mot polygonet.
- Siste element blir sluttkapp som standard.
- IFC-eksporten lager egne IfcSlab-objekter for hvert takelement.
