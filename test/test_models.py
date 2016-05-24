import pytest
import json
import urllib
import uuid
from datetime import datetime

from sms_proxy.api import app, VirtualTN, ProxySession
from sms_proxy.database import db_session, init_db, destroy_db, engine
from sms_proxy.settings import TEST_DB


def teardown_module(module):
    if TEST_DB in app.config['SQLALCHEMY_DATABASE_URI']:
        VirtualTN.query.delete()
        ProxySession.query.delete()
    else:
        raise AttributeError(("The production database is turned on. "
                              "Flip settings.DEBUG to True"))


def setup_module(module):
    if TEST_DB in app.config['SQLALCHEMY_DATABASE_URI']:
        VirtualTN.query.delete()
        ProxySession.query.delete()
    else:
        raise AttributeError(("The production database is turned on. "
                              "Flip settings.DEBUG to True"))


@pytest.fixture
def fresh_session():
    VirtualTN.query.delete()
    ProxySession.query.delete()
    new_tn = VirtualTN('1234567897')
    db_session.add(new_tn)
    db_session.commit()
    new_session = ProxySession(
        new_tn.value, '12223334444', '12223335555', expiry_window=1)
    new_tn.session_id = new_session.id
    db_session.add(new_tn)
    db_session.add(new_session)
    db_session.commit()
    return new_tn, new_session


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


def test_clean_expired_sessions(fresh_session):
    new_tn, new_session = fresh_session
    new_session.expiry_date = datetime.utcnow()
    db_session.add(new_session)
    db_session.commit()
    sessions = ProxySession.query.all()
    assert len(sessions) == 1
    ProxySession.clean_expired()
    sessions = ProxySession.query.all()
    assert len(sessions) == 0


def test_terminate_session(fresh_session):
    new_tn, new_session = fresh_session
    sessions = ProxySession.query.all()
    assert new_session.virtual_TN == new_tn.value
    assert len(sessions) == 1
    ProxySession.terminate(new_session.id)
    released_tn = VirtualTN.query.filter_by(value=new_tn.value).one()
    assert released_tn.session_id is None
    sessions = ProxySession.query.all()
    assert len(sessions) == 0


def test_get_other_participant(fresh_session):
    new_tn, new_session = fresh_session
    other_participant, session_id = ProxySession.get_other_participant(
        new_tn.value, new_session.participant_a)
    assert other_participant == new_session.participant_b
    assert session_id == new_session.id
    other_participant, session_id = ProxySession.get_other_participant(
        new_tn.value, new_session.participant_b)
    assert other_participant == new_session.participant_a
    assert session_id == new_session.id
