"""Public Stramo homepage, personal activation and authenticated app chooser."""
import base64
import io
import time

import pyotp
import qrcode
import streamlit as st

import portal_client
from branding import LOGO_PATH, logo_finnes


def _logo():
    if logo_finnes():
        from pathlib import Path
        data = base64.b64encode(Path(LOGO_PATH).read_bytes()).decode('ascii')
        st.markdown(f'<img class="stramo-logo" src="data:image/png;base64,{data}" width="220" alt="Stramo AS" style="display:block;margin:0 auto;max-width:100%">', unsafe_allow_html=True)


def _remember(response):
    st.session_state.clear()
    st.session_state['portal_token'] = response['token']
    st.session_state['portal_expires'] = response['expires_at']
    st.rerun()


def _logout():
    try:
        portal_client.request('logout', {}, st.session_state.get('portal_token'))
    except portal_client.LoginError:
        st.error('Kunne ikke logge ut av begge appene. Prøv igjen når forbindelsen er tilbake.')
        st.stop()
    st.session_state.clear()
    st.rerun()


def _public():
    st.markdown('''<style>
      .block-container{max-width:600px;padding:2rem 1.4rem 1.2rem;}
      [data-testid="stSidebar"]{display:none;} h1,h2,h3{color:#0d3b54;}
      [data-testid="stHeader"]{display:none;}
      h3{text-align:center;}
      .stApp{background:linear-gradient(135deg,#f8fbfd,#fff 60%,#fcfce9);}
      .stramo-contact{border:1px solid #e2e8ed;border-radius:14px;padding:20px 24px;background:white;color:#0d3b54;margin:18px 0;}
      .stramo-contact p{margin:8px 0;} .stramo-contact a{color:#0d3b54;}
      @media(max-height:620px){.block-container{padding-top:1rem;padding-bottom:.5rem;}.stramo-logo{width:170px;}h3{font-size:1.2rem;}.stramo-contact{padding:12px 18px;margin:10px 0;}}
      </style>''', unsafe_allow_html=True)
    _logo()
    st.subheader('Leverandør av kjøl og fryserom')
    mode = st.session_state.get('portal_mode', 'home')
    if mode == 'home':
        st.markdown('''<div class="stramo-contact"><p><strong>Besøksadresse</strong><br>Kampenveien 4, 1618 Fredrikstad</p>
          <p><strong>Telefon</strong><br><a href="tel:+4769878777">69 87 87 77</a></p>
          <p><strong>Åpningstider</strong><br>Mandag–fredag · 10:00–14:00</p>
          <p><a href="mailto:post@stramo.no">Send oss e-post</a></p></div>''', unsafe_allow_html=True)
        if st.button('Logg inn', type='primary', use_container_width=True):
            st.session_state['portal_mode'] = 'login'
            st.rerun()
        st.caption('© 2026 Stramo AS · Kampenveien 4, 1618 Fredrikstad')
        st.stop()
    if st.button('← Til forsiden', key='public_back'):
        st.session_state.pop('portal_enrollment', None)
        st.session_state['portal_mode'] = 'home'
        st.rerun()
    if mode == 'activate':
        _activation()
    else:
        st.header('Logg inn')
        with st.form('portal_login', clear_on_submit=True):
            email = st.text_input('E-post', key='login_email', max_chars=254)
            password = st.text_input('Passord', type='password', key='login_password', max_chars=256)
            code = st.text_input('Kode fra Authenticator', key='login_code', max_chars=7)
            submit = st.form_submit_button('Logg inn', type='primary', use_container_width=True)
        if submit:
            try:
                _remember(portal_client.request('login', {'email': email, 'password': password, 'code': code}))
            except portal_client.LoginError as exc:
                st.error(str(exc))
        st.caption('Bruk koden fra Google eller Microsoft Authenticator på telefonen.')
        if st.button('Første gang? Aktiver kontoen din', key='activate_account'):
            st.session_state['portal_mode'] = 'activate'
            st.rerun()
    st.stop()


def _activation():
    st.header('Aktiver kontoen din')
    pending = st.session_state.get('portal_enrollment')
    if pending and pending['expires_at'] <= time.time() * 1000:
        st.session_state.pop('portal_enrollment', None)
        st.warning('Oppsettet utløp. Start på nytt med aktiveringskoden din.')
        pending = None
    if not pending:
        st.write('Bruk e-postadressen og den private aktiveringskoden du har fått fra Stramo.')
        with st.form('portal_activation', clear_on_submit=True):
            email = st.text_input('E-post', key='activation_email', max_chars=254)
            invite = st.text_input('Aktiveringskode', type='password', key='activation_invite', max_chars=80)
            password = st.text_input('Velg passord', type='password', key='activation_password', max_chars=256, help='Minst 12 tegn.')
            repeat = st.text_input('Gjenta passordet', type='password', key='activation_repeat', max_chars=256)
            submit = st.form_submit_button('Fortsett til telefonen', type='primary', use_container_width=True)
        if submit:
            if password != repeat:
                st.error('Passordene må være like.')
            elif len(password) < 12:
                st.error('Velg et passord på minst 12 tegn.')
            else:
                try:
                    st.session_state['portal_enrollment'] = portal_client.request('begin', {'email': email, 'invite': invite, 'password': password})
                    st.rerun()
                except portal_client.LoginError as exc:
                    st.error(str(exc))
        return
    st.write('Åpne Google Authenticator eller Microsoft Authenticator. Trykk + og velg å skanne en QR-kode.')
    uri = pyotp.TOTP(pending['secret']).provisioning_uri(name=pending['email'], issuer_name='Stramo')
    qr = io.BytesIO()
    qrcode.make(uri).save(qr, format='PNG')
    # Inline the image: Streamlit's shared media URLs must not carry enrollment secrets.
    image_data = base64.b64encode(qr.getvalue()).decode('ascii')
    st.markdown(f'<img src="data:image/png;base64,{image_data}" width="260" alt="Privat QR-kode for Authenticator">', unsafe_allow_html=True)
    st.caption('QR-koden er personlig. Skriv deretter de seks sifrene fra telefonen nedenfor.')
    with st.form('portal_confirm_phone', clear_on_submit=True):
        code = st.text_input('Sekssifret kode', key='activation_code', max_chars=7)
        submit = st.form_submit_button('Bekreft og logg inn', type='primary', use_container_width=True)
    if submit:
        try:
            _remember(portal_client.request('activate', {'enrollment_token': pending['enrollment_token'], 'code': code}))
        except portal_client.LoginError as exc:
            st.error(str(exc))
    if st.button('Avbryt oppsett', key='cancel_activation'):
        st.session_state.pop('portal_enrollment', None)
        st.session_state['portal_mode'] = 'login'
        st.rerun()


def require_login():
    token = st.session_state.get('portal_token')
    if not token:
        _public()
    try:
        user = portal_client.request('session', token=token)
    except portal_client.LoginError as exc:
        if exc.status == 401:
            st.session_state.clear()
            st.session_state['portal_mode'] = 'login'
            st.rerun()
        st.error(str(exc))
        st.stop()
    if st.session_state.get('portal_destination') == 'cold':
        with st.sidebar.container(key='portal_account'):
            st.caption('Innlogget som ' + user['name'])
            if st.button('← Mine apper', key='portal_home', use_container_width=True):
                st.session_state.pop('portal_destination', None)
                st.rerun()
            if st.button('Logg ut', key='portal_logout', use_container_width=True):
                _logout()
            st.caption('Last ned prosjektfilen før utlogging.')
        return user
    st.markdown('''<style>
      .block-container{max-width:500px;padding:2rem 1.25rem;}
      [data-testid="stSidebar"],[data-testid="stHeader"]{display:none;}
      .st-key-portal_chooser [data-testid="stMarkdownContainer"],
      .st-key-portal_chooser [data-testid="stCaptionContainer"]{text-align:center;}
      .st-key-portal_chooser h1,.st-key-portal_chooser h3{color:#0d3b54;}
      .st-key-portal_chooser h1{font-size:2rem;line-height:1.25;padding-bottom:.5rem;}
      .st-key-portal_chooser h3{font-size:1.4rem;padding-top:0;}
      .st-key-portal_cold_card,.st-key-portal_time_card{padding:1.25rem;border-radius:14px;}
      .st-key-portal_logout{margin-inline:auto;}
      @media(max-width:480px){
        .block-container{padding:1.25rem 1rem;}
        .st-key-portal_chooser h1{font-size:1.65rem;}
      }
      </style>''', unsafe_allow_html=True)
    with st.container(key='portal_chooser'):
        _logo()
        st.title('Velkommen, ' + user['name'].split()[0], anchor=False)
        with st.container(border=True, key='portal_cold_card'):
            st.subheader('Kalkulasjon', anchor=False)
            if st.button('Åpne kalkulasjon', key='open_cold', use_container_width=True, type='primary'):
                st.session_state['portal_destination'] = 'cold'
                st.rerun()
        with st.container(border=True, key='portal_time_card'):
            st.subheader('Timeregistrering', anchor=False)
            try:
                link = portal_client.request('launch', {}, token)
                st.link_button('Åpne timeregistrering', link['url'], use_container_width=True, type='primary')
                st.caption('Lenken er gyldig i to minutter. Oppdater siden hvis du venter lenger.')
            except portal_client.LoginError as exc:
                st.error(str(exc))
        st.caption('Begge kontoene har tilgang til samme Stramo-arbeidsområde. Bruk testdata under utprøvingen.')
        if st.button('Logg ut', key='portal_logout'):
            _logout()
    st.stop()
