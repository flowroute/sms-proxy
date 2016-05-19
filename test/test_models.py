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


@pytest.mark.parametrize("tns, available", [
    ({1234567891: False}, False),
    ({1234567892: False, 1234567893: True}, False),
    ({1234567894: True}, True),
    ({1234567895: True, 1234567896: True}, True),
     ])
def test_virtual_tn_available(tns, available):
    VirtualTN.query.delete()
    for num, available in tns.iteritems():
        new_tn = VirtualTN(num)
        if not available:
            new_tn.session_id = 'active_session_id'
        db_session.add(new_tn)
    db_session.commit()
    available_tn = VirtualTN.get_next_available()
    if not available:
        assert available_tn is None
    else:
        for num, available in tns.iteritems():
            if available:
                assert available_tn.value == str(num)
                return


def test_clean_expired_sessions():
    pass


def test_terminate_session():
    pass


def test_get_other_participant():
    pass
