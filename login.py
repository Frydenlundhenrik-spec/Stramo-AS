"""Gate the whole Streamlit app before loading projects or rendering downloads."""
from pathlib import Path
import sqlite3
import time
import tomllib

import streamlit as st

from auth_core import AuthStore, authenticate, read_accounts, session_account

ROOT = Path(__file__).resolve().parent


def load_accounts():
    local = ROOT / ".streamlit" / "stramo_login.toml"
    if local.exists():
        section = tomllib.loads(local.read_text(encoding="utf-8"))["stramo_login"]
    else:
        section = st.secrets["stramo_login"]
    return read_accounts(section)


def clear_session():
    # Projects and download state must not leak to the next person on this browser.
    st.session_state.clear()


def require_login():
    try:
        accounts = load_accounts()
    except (KeyError, ValueError, TypeError, OSError, st.errors.StreamlitSecretNotFoundError):
        st.title("Stramo · Kjøl og frys")
        st.info("Innlogging er ikke aktivert ennå. Administrator må fullføre oppsettet av brukerkontoene.")
        st.stop()

    account = session_account(st.session_state.get("stramo_login_session"), accounts)
    if account:
        with st.sidebar:
            st.caption(f"Innlogget som {account.name}")
            if st.button("Logg ut", key="stramo_logout", use_container_width=True):
                clear_session()
                st.rerun()
            st.caption("Last ned prosjektfilen før du logger ut for å ta vare på arbeid i denne økten.")
        return account

    if "stramo_login_session" in st.session_state:
        clear_session()
    st.markdown("""<style>
        .block-container {max-width:520px;padding-top:3rem;}
        h1 {color:#0d3b54;} section[data-testid="stSidebar"] {display:none;}
        .stFormSubmitButton button {background:#0d3b54;color:white;}
        </style>""", unsafe_allow_html=True)
    from branding import LOGO_PATH, logo_finnes
    if logo_finnes():
        st.image(str(LOGO_PATH), width=210)
    st.title("Velkommen til Stramo")
    st.write("Logg inn for å åpne kjøl- og frysappen.")
    with st.form("stramo_login_form", clear_on_submit=True):
        email = st.text_input("E-post", key="stramo_login_email", max_chars=254)
        password = st.text_input("Passord", type="password", key="stramo_login_password", max_chars=1024)
        code = st.text_input("Kode fra Authenticator", key="stramo_login_code", max_chars=7,
                             help="Skriv de seks sifrene fra Microsoft eller Google Authenticator.")
        submitted = st.form_submit_button("Logg inn", use_container_width=True)
    st.caption("Bruk din personlige konto og koden på telefonen. Ingen SMS er nødvendig.")
    if submitted:
        try:
            status, account = authenticate(accounts, AuthStore(ROOT / ".stramo_auth.sqlite3"), email, password, code)
        except (sqlite3.Error, OSError):
            st.error("Innlogging er midlertidig utilgjengelig. Prøv igjen senere.")
            st.stop()
        if account:
            clear_session()
            st.session_state["stramo_login_session"] = {
                "email": account.email, "fingerprint": account.fingerprint, "issued_at": time.time(),
            }
            st.rerun()
        elif status == "limited":
            st.error("For mange innloggingsforsøk. Vent 15 minutter før du prøver igjen.")
        else:
            st.error("Innloggingen lyktes ikke. Kontroller e-post, passord og en ny kode fra telefonen.")
    st.stop()
