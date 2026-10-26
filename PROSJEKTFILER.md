# Flere rom og prosjektfiler

1. Tegn et komplett rom med mål, paneler og dører. Trykk **Legg til ferdig rom**.
2. Trykk **Tegn nytt rom**, tegn neste kjøle- eller fryserom, og legg det til.
3. Velg **Rom og sammenstilling**. Plasser rommene med X/Y eller **Plasser inntil valgt vegg**. Koblingen tar hensyn til tykkelsen på veggen som beholdes.
4. Velg hele vegger som skal utelates. Dette er et avsluttende valg; grunntegningen beholdes. Fjern valget for å få veggen tilbake. Dører og åpninger på den utelatte veggen utelates også.
5. Når en kjøleromsvegg dekkes helt av en fryseromsvegg med tilstrekkelig høyde, kan **Bruk fryseromsvegger som fellesvegger** brukes. Fryseromsveggen beholdes. Delvis overlapp krever annen rominndeling; funksjonen deler ikke vegger.
6. Trykk **Last ned prosjektfil** for å lagre JSON-filen på maskinen. Senere: **Åpne prosjektfil**, velg filen og trykk **Åpne prosjekt**. Rediger og last ned en ny fil.

Prosjektfilen inneholder rommenes mål, L-rotasjon/speiling, materialvalg, dører, åpninger, prisoverstyringer, bakgrunnsbilder, plassering og utelatte vegger. Rommet som redigeres lagres også. Endringer i et allerede tillagt rom oppdaterer prosjektet automatisk i den åpne økten; last ned filen for å beholde endringene etter at økten avsluttes.

Sammenstillingen gir plan/PDF, 3D, materialliste og kappliste. IFC lastes ned som ZIP med én fil per rom i samme koordinatsystem. Utelatte vegger og tilhørende U-kanaler inngår ikke i uttakene. Rommenes mål beholdes slik at veggene kan slås på igjen. Skjemaer og plantegninger bruker utvendige mål. Internt lagres fri romkontur med eksplisitt målbasis i skjemaet. Eldre prosjektfiler konverteres ved åpning uten å endre den fysiske romstørrelsen. Snitt viser både innvendig og utvendig høyde. Rette hjørner utføres som støtskjøter uten skråkapp.

Formatet er versjonert (`stramo-project`, versjon 1). Import valideres før det åpne prosjektet erstattes. Maksimalt 30 rom, 25 MB prosjektfil og 10 MB per bakgrunnsbilde.

## Fryseromsgulv og beslag

Fryserom: 22 mm lekter under gulvpanel av samme type/tykkelse som vegg og tak. Veggene står på gulvpanelet. Gulvplater 12 mm ligger innenfor veggene og monteres etter veggene. Lektenes bredde, avstand og mengde er ikke prosjektert; snittet viser prinsippet.

Knappen **Beregn beslag og gulvplate-kappliste** viser beslag på både inn- og utside av vegghjørner og takkant. Innvendig 50×50 og utvendig 50×150 leveres i 2500 mm lengder. Bare beslag får 10 % svinn/kapp, avrundet opp til hele lengder. Fryserommet bruker gulvbeslag i stedet for U-kanaler. Hvite 22 mm skruer beregnes i to rekker med maks. 400 mm avstand på hjørne- og fryseromsgulvbeslag. Mengdene inngår allerede i materiallisten og skal ikke legges til på nytt.

Gulvplateformatet kan endres i sidepanelet for fryserommet og lagres i prosjektfilen. Standardformatet er 1500×3000×12 mm. Kapplisten vurderer gjenbruk av avkapp med begge restmål over 200 mm og 3 mm sagspor. Råplatenummer viser deler fra samme plate. Ingen prosentvis kapp legges til. Uregelmessige deler beregnes konservativt med omsluttende rektangel. Paneler bestilles i hele bredder også når siste element bare er en smal rest. Kontroller kantavstand, skjøter og leverandørens monteringskrav. Manglende priser og tilbehørsmengder må oppgis før komplett bestilling.
