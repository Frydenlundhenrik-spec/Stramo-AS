# Personlig innlogging

Appen krever e-post, passord og en sekssifret kode fra Microsoft Authenticator eller Google Authenticator.
Hver person har eget passord og egen telefonkobling. Det brukes ingen SMS, og telefonnummer er ikke nødvendig.
Kontoene gir tilgang til samme Stramo-app; dette oppsettet oppretter ikke private prosjektområder per person.

## Koble til en konto

Kjør på en betrodd PC med appens Python-miljø og installerte `requirements.txt`:

```powershell
python setup_login.py --email "din-epost@firma.no" --name "Ditt navn"
```

Velg et passord på minst 12 tegn. Skann den lokale QR-koden med din egen telefon, og bekreft en kode i oppsettvinduet.
Ingen konto lagres før telefonen er bekreftet. Gjenta for neste bruker. Et nytt oppsett for en eksisterende konto
krever at du skriver BYTT; det bytter begge faktorene og avslutter gyldigheten til tidligere innloggede økter.
Ved mistet telefon kjører administrator dette oppsettet igjen etter å ha bekreftet hvem brukeren er.

For en annen lokal appkopi brukes `--target "full sti til appmappen" --install`.
Det legger bare til innlogging før prosjektdata åpnes. Eksisterende appfiler sikkerhetskopieres først;
prosjekter og databaser endres ikke. Kjør alltid med et Python-miljø som har `pyotp==2.10.0` installert.

## Streamlit Cloud

Oppsettet lagres privat i `.streamlit/stramo_login.toml`, med saltede PBKDF2-passordhasher og TOTP-hemmeligheter.
Filen er ignorert av Git. Legg hele innholdet i appens **Settings → Secrets**, og behold andre eksisterende
innstillinger. Gjør dette før grenen med innlogging tas i bruk på `main`. Du kan bruke den samme kontoen på PC
og i nettappen ved å bruke samme private konfigurasjon. Selve oppsettfilen må ikke deles via GitHub eller chat.

Uten gyldig konfigurasjon stopper appen på en beskjed om manglende oppsett. Den åpner aldri prosjektvisningen
som reservevei. Det finnes ingen standardkonto, offentlig registrering eller testkode som omgår innloggingen.

## Økter og kontroller

- Appen kontrollerer begge faktorene på serveren før prosjektfunksjonene kjører.
- Økter varer høyst åtte timer og kontrolleres på hver kjøring/handling. En ny nettleserøkt krever ny innlogging.
- Logg ut tømmer prosjekt- og innloggingsstatus for nettleserøkten. Last ned prosjektfilen først.
- Fem innloggingsforsøk per konto på 15 minutter. Ukjente e-postadresser deler en separat begrensning.
- Brukte TOTP-tidssteg avvises med en atomisk databasekontroll, også ved samtidige innloggingsforsøk.
- `.stramo_auth.sqlite3` inneholder forsøksbegrensning og brukte tidssteg, ikke passord eller telefonhemmeligheter.
  Dette er for én Streamlit-instans. Databasen må ligge på varig lagring hvis beskyttelsen skal beholdes ved
  full utskifting av serverdisken. Community Cloud kan miste lokale filer; en slik utskifting nullstiller tellere.
- Bruk HTTPS for nettappen. Lokal kjøring bør bindes til `127.0.0.1`.

## Kontroll

`python -m unittest test_login.py` kontrollerer feil passord/kode, separate kontoer, gjenbruk, samtidighet,
forsøksbegrensning, sesjonsutløp og at Streamlit stopper før prosjektinnhold ved manglende innlogging.
Testene bruker isolerte testkontoer og midlertidige databaser. De sender ingen SMS og berører ingen prosjektfiler.

Dokumentasjon: [PyOTP](https://pyauth.github.io/pyotp/),
[Streamlit Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
