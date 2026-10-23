# Stramo kjøleromssystem

Versjon **2026.10.23-r07**. App for kjøle- og fryserom, med flere rom i samme prosjekt.

## Kjør lokalt

Bruk Python 3.12 og installer avhengighetene:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

På Linux/macOS brukes `.venv/bin/python` i stedet for `.venv\Scripts\python.exe`.
Appen trenger ingen API-nøkler. AI-assistenten er fjernet.

## Innhold

- Kalkulasjon med vegg- og takareal, fryseromsgulv, gulvfiberplater og beslag.
- FDV med logo, PE25 25 µm og inkluderte leverandørdokumenter.
- Montasjetegninger: plan, vegger, prinsippsnitt, paneler, tak/gulv, 3D og IFC.
- Kapplister og materiallister for ett rom eller hele prosjektet.
- Rom og sammenstilling med delte vegger, dører og gjennomsiktige tak.
- Transportforslag med status for alle kolli, også de som ikke er plassert.
- U-verdi og varmetap under kalkulasjon.

Målene er innvendige rommål. Veggpanelene legges på utsiden av romkonturen.
90-graders hjørner har rette støtskjøter. Tegninger, IFC og mengder bruker samme panelinndeling.
Siste smale panel bestilles som ett helt element. Bare beslag får 10 % kapp og rundes opp til hele lengder på 2500 mm.
Gulvfiberplatenes standard er 1500 × 3000 × 12 mm.

## Prosjektfiler og Tasty-eksempel

Last opp `Tasty-Rom4-og-fryserom-med-dorer.json` i appen for å åpne det kontrollerte eksemplet med kjølerom og fryserom.
Bruk **Last ned prosjektfil** for å ta vare på endringer. Prosjekter lagres i nettleserøkten til du laster dem ned;
en serveromstart kan avslutte økten. Lokale databaser og hemmeligheter er utelatt fra kildepakken.

For å generere Tasty-tegningspakken fra kommandolinjen:

```powershell
.\.venv\Scripts\python.exe deliver_tasty_drawings.py output/Tasty
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe run_checks.py
```

Testene kjøres i en midlertidig kopi og endrer ikke prosjektfilene dine.
Kontroll av en generert tegningspakke: `python check_delivery.py output/Tasty`.
Revisjon 07 er lokalt kontrollert med 41 regresjonsskript og 22 kontroller av den installerte appen.

## Publisering

Eksisterende Streamlit Community Cloud-app bruker dette repositoriet, `main`, `app.py` og Python 3.12.
Avhengighetene er låst til versjonene som ble testet. Logo og standard-FDV ligger i `assets/`.

Transport er et lasteforslag og kontrollerer ikke lastsikring eller aksellast.
Ukjente vekter og mengder vises som manglende. FDV for skruer, fugemasse og fiberplater ettersendes.
Varmeberegninger med manglende U-verdier eller forutsetninger er foreløpige.
