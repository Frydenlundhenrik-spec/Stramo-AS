from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

import pyotp
from streamlit.testing.v1 import AppTest

from auth_core import (Account, AuthStore, SESSION_SECONDS, authenticate,
                       password_hash, read_accounts, session_account)
import login
from setup_login import config_text, gated_app, private_write


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "A long isolated test password"
        encoded = password_hash(cls.password)
        cls.one = Account("one@example.invalid", "Test One", encoded, pyotp.random_base32())
        cls.two = Account("two@example.invalid", "Test Two", encoded, pyotp.random_base32())

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.store = AuthStore(self.root / "auth.sqlite3")
        self.accounts = {a.email: a for a in (self.one, self.two)}
        self.now = 1_800_000_010

    def tearDown(self):
        self.directory.cleanup()

    def sign_in(self, account=None, **overrides):
        account = account or self.one
        values = dict(email=account.email, password=self.password,
                      code=pyotp.TOTP(account.totp_secret).at(self.now), now=self.now)
        values.update(overrides)
        return authenticate(self.accounts, self.store, **values)

    def test_both_factors_and_known_account_required(self):
        self.assertEqual(self.sign_in(password="incorrect")[0], "invalid")
        self.assertEqual(self.sign_in(code="wrong")[0], "invalid")
        self.assertEqual(self.sign_in(email="unknown@example.invalid")[0], "invalid")
        self.assertEqual(self.sign_in(email=" ONE@EXAMPLE.INVALID ")[0], "ok")

    def test_accounts_have_separate_phone_keys(self):
        self.assertEqual(self.sign_in(code=pyotp.TOTP(self.two.totp_secret).at(self.now))[0], "invalid")
        self.assertEqual(self.sign_in()[0], "ok")
        self.assertEqual(self.sign_in(self.two)[0], "ok")

    def test_used_and_expired_codes_rejected_after_reopening_database(self):
        self.assertEqual(self.sign_in()[0], "ok")
        self.store = AuthStore(self.root / "auth.sqlite3")
        self.assertEqual(self.sign_in()[0], "invalid")
        self.assertEqual(self.sign_in(now=self.now + 120)[0], "invalid")
        self.assertEqual(self.sign_in(now=self.now + 120, code=pyotp.TOTP(self.one.totp_secret).at(self.now + 120))[0], "ok")

    def test_concurrent_code_is_accepted_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: self.sign_in()[0], range(2)))
        self.assertCountEqual(outcomes, ["ok", "invalid"])

    def test_attempt_limit_shared_between_sessions_but_not_accounts(self):
        for _ in range(5):
            self.assertEqual(self.sign_in(password="incorrect")[0], "invalid")
        self.store = AuthStore(self.root / "auth.sqlite3")
        self.assertEqual(self.sign_in()[0], "limited")
        self.assertEqual(self.sign_in(self.two)[0], "ok")
        later = self.now + 901
        self.assertEqual(self.sign_in(now=later, code=pyotp.TOTP(self.one.totp_secret).at(later))[0], "ok")

    def test_session_expires_and_credential_change_revokes(self):
        session = {"email": self.one.email, "fingerprint": self.one.fingerprint, "issued_at": self.now}
        self.assertEqual(session_account(session, self.accounts, self.now), self.one)
        self.assertIsNone(session_account(session, self.accounts, self.now + SESSION_SECONDS))
        self.assertIsNone(session_account(session, self.accounts, self.now - 1))
        self.assertIsNone(session_account(session, {}, self.now))
        changed = replace(self.one, totp_secret=pyotp.random_base32())
        self.assertIsNone(session_account(session, {changed.email: changed}, self.now))

    def test_config_and_installation_preserve_other_content(self):
        import tomllib
        rows = [vars(self.one), vars(self.two)]
        text = config_text(rows)
        self.assertEqual(read_accounts(tomllib.loads(text)["stramo_login"]), self.accounts)
        target = self.root / "private.toml"
        private_write(target, text)
        self.assertEqual(target.read_text(encoding="utf-8"), text)
        private_write(target, text)
        source = "# existing custom design\nprepare_project()\n# existing calculations\n"
        updated = gated_app(source)
        self.assertEqual(gated_app(updated), updated)
        self.assertIn("# existing custom design", updated)
        self.assertIn("# existing calculations", updated)
        with self.assertRaises(ValueError):
            read_accounts({"users": []})

    def test_streamlit_gate_login_logout_and_expiry(self):
        script = "from login import require_login\nimport streamlit as st\nrequire_login()\nst.write('PROTECTED PROJECT')\n"
        with patch.object(login, "ROOT", self.root), patch.object(login, "load_accounts", return_value=self.accounts):
            app = AppTest.from_string(script, default_timeout=15).run()
            self.assertFalse(app.exception)
            self.assertNotIn("PROTECTED PROJECT", [x.value for x in app.markdown])
            app.text_input(key="stramo_login_email").set_value(self.one.email)
            app.text_input(key="stramo_login_password").set_value(self.password)
            app.text_input(key="stramo_login_code").set_value(pyotp.TOTP(self.one.totp_secret).now())
            app.button[0].click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertIn("PROTECTED PROJECT", [x.value for x in app.markdown])
            app.session_state["private_project"] = "must disappear"
            app.button(key="stramo_logout").click().run()
            self.assertNotIn("PROTECTED PROJECT", [x.value for x in app.markdown])
            self.assertNotIn("private_project", app.session_state)
            app.session_state["stramo_login_session"] = {
                "email": self.one.email, "fingerprint": self.one.fingerprint,
                "issued_at": time.time() - SESSION_SECONDS - 1,
            }
            app.session_state["private_project"] = "must also disappear"
            app.run()
            self.assertNotIn("PROTECTED PROJECT", [x.value for x in app.markdown])
            self.assertNotIn("private_project", app.session_state)

    def test_missing_configuration_fails_closed(self):
        with patch.object(login, "load_accounts", side_effect=KeyError("unconfigured")):
            app = AppTest.from_string("from login import require_login\nimport streamlit as st\nrequire_login()\nst.write('PROTECTED PROJECT')").run()
            self.assertFalse(app.exception)
            self.assertNotIn("PROTECTED PROJECT", [x.value for x in app.markdown])
            self.assertEqual(len(app.info), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
