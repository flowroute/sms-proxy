from flask.ext.testing import LiveServerTestCase
import requests


# Testing with LiveServer
class MyTest(LiveServerTestCase):
    # if the create_app is not implemented NotImplementedError will be raised
    def create_app(self):
        from sms_proxy.api import app
        app.debug = True
        return app

    def test_flask_application_is_up_and_running(self):
        response = requests.get(self.get_server_url() + '/tn')
        self.assertEqual(response.status_code, 200)
        response = requests.get(self.get_server_url() + '/session')
        self.assertEqual(response.status_code, 200)
