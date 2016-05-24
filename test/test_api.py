import pytest
import json
import urllib
import uuid

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


def setup_function(function):
    if TEST_DB in app.config['SQLALCHEMY_DATABASE_URI']:
        VirtualTN.query.delete()
        ProxySession.query.delete()
    else:
        raise AttributeError(("The production database is turned on. "
                              "Flip settings.DEBUG to True"))
class MockController():
        def __init__(self):
            self.request = None

        def create_message(self, msg):
            self.request = msg

mock_controller = MockController()


def test_post_new_tn():
    client = app.test_client()
    test_num = '12223334444'
    resp = client.post('/tn', data=json.dumps({'value': test_num}),
                       content_type='application/json')
    assert resp.status_code == 200
    resp = client.post('/tn', data=json.dumps({'value': test_num}),
                       content_type='application/json')
    assert resp.status_code == 400


def test_get_tns():
    client = app.test_client()
    num_1 = '12347779999'
    num_2 = '12347778888'
    vnum1 = VirtualTN(num_1)
    vnum2 = VirtualTN(num_2)
    vnum2.session_id = 'aaaaa'
    db_session.add(vnum1)
    db_session.add(vnum2)
    db_session.commit()
    resp = client.get('/tn')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data['virtual_tns']) == 2
    assert data['available'] == 1
    assert data['in_use'] == 1
    assert data['pool_size'] == 2


def test_delete_tn():
    client = app.test_client()
    test_num = '12223334444'
    session = ProxySession(test_num, '12223334444', '12223335555',
                           expiry_window=None)
    vnum = VirtualTN(test_num)
    vnum.session_id = 'fake_session_id'
    db_session.add(session)
    db_session.add(vnum)
    db_session.commit()
    resp = client.delete('/tn',
                         data=json.dumps({'value': test_num}),
                         content_type='application/json')
    data = json.loads(resp.data)
    assert data['status'] == 'failed'
    assert "Cannot delete the number." in data['message']
    assert session.id in data['message']
    assert resp.status_code == 400
    db_session.delete(session)
    vnum.session_id = None
    db_session.add(vnum)
    db_session.commit()
    resp = client.delete('/tn',
                         data=json.dumps({'value': test_num}),
                         content_type='application/json')
    data = json.loads(resp.data)
    assert 'successfully removed TN from pool' in data['message']
    assert resp.status_code == 200
