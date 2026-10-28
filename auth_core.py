"""Server-side password and TOTP verification for a small Stramo team."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from pathlib import Path

import pyotp

ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60
ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Passordet må ha minst 12 og høyst 1024 tegn.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def check_password(password: str, encoded: str) -> bool:
    if len(password) > 1024:
        return False
    try:
        kind, count, salt, expected = encoded.split("$")
        if kind != "pbkdf2_sha256" or not ITERATIONS <= int(count) <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(count))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True, repr=False)
class Account:
    email: str
    name: str
    password_hash: str
    totp_secret: str

    @property
    def fingerprint(self) -> str:
        # Changing either factor immediately invalidates existing server sessions.
        return hashlib.sha256((self.email + "\0" + self.password_hash + "\0" + self.totp_secret).encode()).hexdigest()


def read_accounts(section) -> dict[str, Account]:
    accounts = {}
    for row in section.get("users", []):
        email = str(row["email"]).strip().lower()
        name = str(row["name"]).strip()
        encoded = str(row["password_hash"])
        secret = str(row["totp_secret"])
        if not re.fullmatch(r"[^\s@]{1,128}@[^\s@]{1,128}\.[^\s@]{1,64}", email) or not name:
            raise ValueError("Ugyldig konto")
        if not re.fullmatch(r"pbkdf2_sha256\$(600000|[7-9][0-9]{5}|1[0-9]{6}|2000000)\$[0-9a-f]{32}\$[0-9a-f]{64}", encoded):
            raise ValueError("Ugyldig passordhash")
        if not re.fullmatch(r"[A-Z2-7]{32}", secret) or email in accounts:
            raise ValueError("Ugyldig Authenticator-oppsett")
        accounts[email] = Account(email, name, encoded, secret)
    if not accounts:
        raise ValueError("Ingen kontoer er satt opp")
    return accounts


class AuthStore:
    """Shared across browser sessions; SQLite transactions prevent OTP replay races."""

    def __init__(self, path: Path):
        self.path = path
        with self.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS attempts (bucket TEXT, at REAL)")
            con.execute("CREATE INDEX IF NOT EXISTS attempts_bucket ON attempts(bucket, at)")
            con.execute("CREATE TABLE IF NOT EXISTS used_codes (account TEXT PRIMARY KEY, counter INTEGER)")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        try:
            with con:
                yield con
        finally:
            con.close()

    def reserve_attempt(self, bucket: str, now: float) -> bool:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM attempts WHERE at <= ?", (now - WINDOW_SECONDS,))
            count = con.execute("SELECT COUNT(*) FROM attempts WHERE bucket=?", (bucket,)).fetchone()[0]
            if count >= ATTEMPTS:
                return False
            con.execute("INSERT INTO attempts VALUES (?, ?)", (bucket, now))
            return True

    def consume_code(self, account: Account, counter: int, bucket: str) -> bool:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute("SELECT counter FROM used_codes WHERE account=?", (account.fingerprint,)).fetchone()
            if previous and counter <= previous[0]:
                return False
            con.execute("INSERT OR REPLACE INTO used_codes VALUES (?, ?)", (account.fingerprint, counter))
            con.execute("DELETE FROM attempts WHERE bucket=?", (bucket,))
            return True


# Equal work for an unknown email, without keeping a real password in the code.
_DUMMY_HASH = f"pbkdf2_sha256${ITERATIONS}$" + "00" * 16 + "$" + "00" * 32


def authenticate(accounts: dict[str, Account], store: AuthStore, email: str,
                 password: str, code: str, now: float | None = None) -> tuple[str, Account | None]:
    now = time.time() if now is None else now
    account = accounts.get(email.strip().lower())
    bucket = hashlib.sha256((account.email if account else "unknown").encode()).hexdigest()
    if not store.reserve_attempt(bucket, now):
        return "limited", None
    password_ok = check_password(password, account.password_hash if account else _DUMMY_HASH)
    code = code.strip().replace(" ", "")
    if account is None or not password_ok or not re.fullmatch(r"[0-9]{6}", code):
        return "invalid", None
    totp = pyotp.TOTP(account.totp_secret)
    counter = int(now // 30)
    # A small clock tolerance; each accepted time step can be used only once.
    for step in (counter, counter - 1, counter + 1):
        if hmac.compare_digest(totp.at(step * 30), code) and store.consume_code(account, step, bucket):
            return "ok", account
    return "invalid", None


def session_account(session, accounts: dict[str, Account], now: float | None = None) -> Account | None:
    now = time.time() if now is None else now
    if not isinstance(session, dict):
        return None
    account = accounts.get(session.get("email"))
    issued = session.get("issued_at")
    if (account and isinstance(issued, (int, float)) and 0 <= now - issued < SESSION_SECONDS
            and hmac.compare_digest(str(session.get("fingerprint", "")), account.fingerprint)):
        return account
    return None
