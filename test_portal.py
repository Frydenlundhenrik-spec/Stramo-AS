import time
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import portal_client

SCRIPT="from login import require_login\nimport streamlit as st\nrequire_login()\nst.write('PROTECTED ROOM APP')"


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.fail_login=False
        self.fail_session=False
        self.calls=[]

    def api(self, action, payload=None, token=None):
        self.calls.append(action)
        if action=='session':
            if self.fail_session:raise portal_client.LoginError('Expired',401)
            return {'email':'test@example.invalid','name':'Test Person','expires_at':(time.time()+3600)*1000}
        if action=='login':
            if self.fail_login:raise portal_client.LoginError('Invalid',401)
            return {'token':'a'*64,'expires_at':(time.time()+3600)*1000}
        if action=='begin':return {'enrollment_token':'b'*64,'secret':'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ','email':'test@example.invalid','expires_at':(time.time()+900)*1000}
        if action=='activate':
            if payload['code']!='123456':raise portal_client.LoginError('Invalid code',401)
            return {'token':'a'*64,'expires_at':(time.time()+3600)*1000}
        if action=='launch':return {'url':'https://example.invalid/private-entry'}
        if action=='logout':return {'ok':True}
        raise AssertionError(action)

    def text(self, app):return ' '.join(str(x.value) for x in list(app.title)+list(app.subheader)+list(app.markdown))

    def test_public_page_and_direct_destination_do_not_expose_apps(self):
        with patch.object(portal_client,'request',side_effect=self.api):
            app=AppTest.from_string(SCRIPT).run()
            app.session_state['portal_destination']='cold'
            app.run()
            self.assertNotIn('PROTECTED ROOM APP',self.text(app))
            self.assertNotIn('Timeregistrering',self.text(app))
            self.assertEqual(self.calls,[])
            app.button[0].click().run()
            self.fail_login=True
            app.text_input(key='login_email').set_value('test@example.invalid')
            app.text_input(key='login_password').set_value('Wrong test password')
            app.text_input(key='login_code').set_value('123456')
            app.button[-2].click().run()
            self.assertNotIn('PROTECTED ROOM APP',self.text(app))

    def test_enrollment_requires_phone_then_shows_both_apps(self):
        with patch.object(portal_client,'request',side_effect=self.api):
            app=AppTest.from_string(SCRIPT).run()
            app.button[0].click().run()
            app.button(key='activate_account').click().run()
            app.text_input(key='activation_email').set_value('test@example.invalid')
            app.text_input(key='activation_invite').set_value('private-test-invite')
            app.text_input(key='activation_password').set_value('Long test password')
            app.text_input(key='activation_repeat').set_value('Long test password')
            app.button[-1].click().run()
            self.assertNotIn('Timeregistrering',self.text(app))
            self.assertIn('portal_enrollment',app.session_state)
            app.text_input(key='activation_code').set_value('000000')
            app.button[1].click().run()
            self.assertNotIn('Timeregistrering',self.text(app))
            app.text_input(key='activation_code').set_value('123456')
            app.button[1].click().run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertIn('Timeregistrering',self.text(app))
            self.assertIn('Kalkulasjon',self.text(app))
            self.assertNotIn('portal_enrollment',app.session_state)
            app.button(key='open_cold').click().run()
            self.assertIn('PROTECTED ROOM APP',self.text(app))
            app.session_state['private_project']='must disappear'
            app.button(key='portal_logout').click().run()
            self.assertNotIn('PROTECTED ROOM APP',self.text(app))
            self.assertNotIn('private_project',app.session_state)

    def test_revoked_session_removes_project_state(self):
        with patch.object(portal_client,'request',side_effect=self.api):
            app=AppTest.from_string(SCRIPT).run()
            app.session_state['portal_token']='c'*64
            app.session_state['portal_destination']='cold'
            app.session_state['project_rooms']=['private']
            self.fail_session=True
            app.run()
            self.assertNotIn('PROTECTED ROOM APP',self.text(app))
            self.assertNotIn('project_rooms',app.session_state)


if __name__=='__main__':unittest.main()
