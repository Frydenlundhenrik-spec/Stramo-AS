"""Run interactively on a trusted computer; never expose enrollment on the public app."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import getpass
import html
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import tomllib
import webbrowser

import pyotp
import qrcode
import qrcode.image.svg

from auth_core import password_hash, read_accounts


def private_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".stramo-enrollment-", dir=path.parent)
    temporary = Path(name)
    try:
        if os.name == "nt":
            identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
            sid = next(csv.reader([identity.strip()]))[1]
            subprocess.run(["icacls", str(temporary), "/inheritance:r", "/grant:r",
                            f"*{sid}:F", "*S-1-5-18:F"], check=True, capture_output=True)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = None
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if fd is not None:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def config_text(users):
    lines = ["# Privat innloggingsoppsett. Skal aldri legges på GitHub.", "[stramo_login]", ""]
    for user in users:
        lines.append("[[stramo_login.users]]")
        for key in ("email", "name", "password_hash", "totp_secret"):
            lines.append(f"{key} = {json.dumps(user[key], ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines)


def gated_app(source: str) -> str:
    if "from login import require_login\nrequire_login()" in source:
        return source
    anchor = "\nprepare_project()\n"
    if source.count(anchor) != 1:
        raise ValueError("Fant ikke forventet startpunkt i app.py. Ingen appfiler ble endret.")
    return source.replace(anchor, "\nfrom login import require_login\nrequire_login()\n" + anchor, 1)


def setup(target: Path, email: str, name: str, install: bool):
    target = target.resolve()
    app_path = target / "app.py"
    initial = app_path.read_bytes()
    prepared = gated_app(initial.decode("utf-8-sig").replace("\r\n", "\n"))
    config_path = target / ".streamlit" / "stramo_login.toml"
    existing = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {"stramo_login": {"users": []}}
    users = list(existing["stramo_login"].get("users", []))
    email = email.strip().lower()
    print(f"\nPersonlig innlogging for {name} ({email})")
    print("Den som eier kontoen velger selv passordet og skanner med sin egen telefon.")
    print("Passordet vises ikke mens du skriver. Ingen SMS eller nettjeneste benyttes.")
    if any(u["email"].lower() == email for u in users):
        if input("Kontoen finnes. Skriv BYTT for å bytte begge innloggingsfaktorene: ").strip() != "BYTT":
            return
    while True:
        password = getpass.getpass("Velg passord (minst 12 tegn): ")
        try:
            encoded = password_hash(password)
        except ValueError as exc:
            print(str(exc))
            continue
        if password == getpass.getpass("Gjenta passordet: "):
            break
        print("Passordene var forskjellige. Prøv igjen.")
    del password
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name="Stramo kjøl og frys")
    qr = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    svg = io.BytesIO()
    qr.save(svg)
    enrollment = target / f".stramo-enrollment-{secrets.token_hex(8)}.html"
    page = ("<!doctype html><meta charset='utf-8'><title>Koble telefon til Stramo</title>"
            "<meta name='referrer' content='no-referrer'><style>body{font:18px system-ui;max-width:650px;margin:40px auto;color:#0d3b54}"
            "svg{width:330px;height:330px}code{word-break:break-all}</style>"
            f"<h1>Koble telefonen til Stramo</h1><p>{html.escape(name)} · {html.escape(email)}</p>"
            "<p>Åpne Microsoft Authenticator → + → Annen konto, eller Google Authenticator → + → Skann QR-kode.</p>"
            + svg.getvalue().decode().split("?>", 1)[-1] +
            "<p>Skriv deretter de seks sifrene fra telefonen i oppsettvinduet på PC-en.</p>"
            "<p>QR-koden er privat. Lukk denne siden etterpå.</p>")
    try:
        private_write(enrollment, page)
        webbrowser.open(enrollment.as_uri())
        print(f"QR-koden åpnes i nettleseren. Hvis ikke, åpne: {enrollment}")
        for _ in range(5):
            code = getpass.getpass("Sekssifret kode fra telefonen: ").strip().replace(" ", "")
            if totp.verify(code, valid_window=1):
                break
            print("Koden ble ikke godkjent. Kontroller at klokken på telefonen er automatisk.")
        else:
            raise ValueError("Telefonen ble ikke bekreftet. Kontoen ble ikke lagret.")
        row = {"email": email, "name": name, "password_hash": encoded, "totp_secret": secret}
        updated = [u for u in users if u["email"].lower() != email] + [row]
        read_accounts({"users": updated})
        if app_path.read_bytes() != initial:
            raise ValueError("Appen ble endret under oppsettet. Kjør oppsettet på nytt.")
        if install:
            backup = target / "backups" / ("innlogging-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            backup.mkdir(parents=True)
            source = Path(__file__).resolve().parent
            for filename in ("app.py", "requirements.txt", "auth_core.py", "login.py"):
                current = target / filename
                if current.exists():
                    shutil.copy2(current, backup / filename)
            for filename in ("auth_core.py", "login.py"):
                if source != target:
                    shutil.copy2(source / filename, target / filename)
            requirements = target / "requirements.txt"
            text = requirements.read_text(encoding="utf-8")
            if "pyotp==" not in text:
                requirements.write_text(text.rstrip() + "\npyotp==2.10.0\n", encoding="utf-8")
        private_write(config_path, config_text(updated))
        if install:
            app_path.write_text(prepared, encoding="utf-8")
        print(f"\nKontoen er klar lokalt. {len(updated)} konto(er) er konfigurert.")
        print("Lukk QR-siden. Start appen på nytt for å bruke innloggingen.")
        print(f"Privat serveroppsett: {config_path}")
        print("For nettappen legges dette i Streamlit Settings → Secrets før innloggingsversjonen publiseres.")
        print("Ikke send denne filen i chat, e-post eller til GitHub.")
    finally:
        enrollment.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sett opp personlig passord og Authenticator for Stramo")
    parser.add_argument("--target", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--install", action="store_true", help="Installer innlogging i denne appkopien etter bekreftet telefon")
    args = parser.parse_args()
    try:
        setup(args.target, args.email, args.name, args.install)
    except (ValueError, OSError, KeyboardInterrupt, EOFError) as exc:
        print("\nOppsettet ble ikke fullført." if isinstance(exc, (KeyboardInterrupt, EOFError)) else str(exc))
        raise SystemExit(1)
