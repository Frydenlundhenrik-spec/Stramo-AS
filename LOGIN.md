# Personlig innlogging via Stramo-hjemmesiden

Hjemmeside: https://stramo-as-n7zzenre2auarxeuzha8pk.streamlit.app/

Forsiden viser bare logo og kontaktinformasjon. Appvalgene Timeregistrering og
Kjøl og frys vises først etter godkjent innlogging. Prosjektkoden kjører først
etter at serveren har kontrollert økten. Direkteadresser gir ikke tilgang uten innlogging.

## Første gang

1. Åpne hjemmesiden og trykk **Logg inn → Første gang? Aktiver kontoen din**.
2. Bruk e-postadressen og den private aktiveringskoden i din egen invitasjon.
3. Velg et passord på minst 12 tegn.
4. Åpne Google Authenticator eller Microsoft Authenticator, trykk + og skann QR-koden på nettsiden.
5. Skriv den sekssifrede koden fra telefonen på nettsiden og bekreft.

Hver person har eget passord og egen telefonkobling. Ingen SMS sendes. Kontoen
blir aktiv først etter at telefonkoden er godkjent. En invitasjon kan ikke brukes
for å erstatte en aktivert konto. Passord og Authenticator-koder skal ikke sendes
på e-post eller legges i Git. Ved mistet telefon må administrator verifisere
personen og hjelpe med gjenoppretting; selvbetjent nullstilling er ikke implementert.

## Vanlig bruk

Logg inn med e-post, passord og kode fra Authenticator. Velg deretter app.
Timeregistrering åpnes i en ny fane med en engangslenke. Kjøl og frys åpnes i samme
Streamlit-side. Logg ut avslutter alle økter for denne personen i begge nettappene.
Den andre brukerens økter påvirkes ikke. En ny nettleserøkt kan kreve ny innlogging.

Begge brukere har tilgang til samme Stramo-testområde i timeappen. Personlig
innlogging oppretter ikke private arbeidsområder. Kjøleromsprosjekter ligger i
Streamlit-økten: **last ned prosjektfilen før utlogging eller omstart**.

## Drift

Kontotjenesten kjører i Stramo Flyts eksisterende Sites Worker. Kontoer, økter,
forsøksbegrensning og brukte TOTP-tidssteg lagres varig i D1. Passord er scrypt-hashet,
telefonhemmeligheter kryptert med AES-256-GCM, og sesjonstokens lagres som hash.
Runtime-hemmelighetene STRAMO_AUTH_KEY og STRAMO_INVITATIONS_JSON finnes bare i Sites.
Invitasjonslisten inneholder engangskodenes hasher, aldri selve kodene. Eksisterende
kontoers e-postadresser beholdes i listen også etter invitasjonens utløpsdato.

Streamlit trenger ingen egne Secrets. portal_client.py bruker HTTPS og lagrer
sesjonstoken kun i brukerens serverøkt. Hver kjøring kontrollerer den mot kontotjenesten.
Manglende forbindelse eller ugyldig innlogging stopper før appen åpnes. Økten varer
høyst åtte timer. Den gamle lokale setup_login.py/TOML-metoden brukes ikke av nettappen.
Skrivebordsoriginalen er beholdt separat og har ikke blitt endret av denne publiseringen.

## Kontroll

python -m unittest test_portal.py kontrollerer offentlig visning, invitasjonsflyt,
TOTP-bekreftelse, appvalg, utlogging og at utløpt økt fjerner prosjektstatus. Konto-APIet
har egne integrasjonstester i timeappens tests/portal-api.mjs. Testene bruker syntetiske
kontoer. Reell førstegangsaktivering gjøres av hver bruker med egen telefon.
