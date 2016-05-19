import pytest
import json
import urllib
import uuid

from sms_proxy.api import app, VirtualTN, Session
from sms_proxy.database import db_session, init_db, destroy_db, engine
from sms_proxy.settings import TEST_DB


def teardown_module(module):
    if TEST_DB in app.config['SQLALCHEMY_DATABASE_URI']:
        destroy_db()
    else:
        raise AttributeError(("The production database is turned on. "
                              "Flip settings.DEBUG to True"))


def setup_module(module):
    if TEST_DB in app.config['SQLALCHEMY_DATABASE_URI']:
        destroy_db()
    else:
        raise AttributeError(("The production database is turned on. "
                              "Flip settings.DEBUG to True"))
    init_db()


class MockController():
        def __init__(self):
            self.request = None

        def create_message(self, msg):
            self.request = msg

mock_controller = MockController()


@pytest.mark.parametrize("session_id,value,expected_value", [
    (str(uuid.uuid4()), '12065551212', None),
    (None, '12065551313', '12065551313'),
])
def test_get_available_virtual_tn(session_id, value, expected_value):
    virtual_tn = VirtualTN(value)
    if session_id:
        virtual_tn.session_id = session_id
    db_session.add(virtual_tn)
    db_session.commit()
    available_tn = VirtualTN.get_available()
    available_value = available_tn.value if available_tn else None
    assert available_value == expected_value
