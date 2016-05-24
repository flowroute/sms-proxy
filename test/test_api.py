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
        db_session.commit()
    else:
        raise AttributeError(("The production database is turned on. "
                              "Flip settings.DEBUG to True"))


def setup_function(function):
    if TEST_DB in app.config['SQLALCHEMY_DATABASE_URI']:
        VirtualTN.query.delete()
        ProxySession.query.delete()
        db_session.commit()
    else:
        raise AttributeError(("The production database is turned on. "
                              "Flip settings.DEBUG to True"))


class MockController():
        def __init__(self):
            self.requests = []

        def create_message(self, msg):
            self.requests.append(msg)

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
    assert 'Successfully removed TN from pool' in data['message']
    assert resp.status_code == 200


def test_post_session():
    mock_controller = MockController()
    app.sms_controller = mock_controller
    client = app.test_client()
    test_num = '12223334444'
    resp = client.post('/session', data=json.dumps({'participant_a': '13334445555',
                                                    'participant_b': '14445556666'}),
                       content_type='application/json')
    data = json.loads(resp.data)
    assert resp.status_code == 400
    assert 'Could not create a new session -- No virtual TNs available.' in data['message']
    vnum = VirtualTN(test_num)
    vnum.session_id = 'fake_session_id'
    db_session.add(vnum)
    db_session.commit()
    resp = client.post('/session', data=json.dumps({'participant_a': '13334445555',
                                                    'participant_b': '14445556666'}),
                       content_type='application/json')
    data = json.loads(resp.data)
    assert resp.status_code == 400
    vnum.session_id = None
    db_session.add(vnum)
    db_session.commit()
    resp = client.post('/session', data=json.dumps({'participant_a': '13334445555',
                                                    'participant_b': '14445556666'}),
                       content_type='application/json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'Created new session' in data['message']
    assert data['virtual_tn'] == vnum.value
    assert len(mock_controller.requests) == 2
    assert data['session_id'] is not None


def test_get_session():
    client = app.test_client()
    test_num_1 = '12223334444'
    test_num_2 = '12223335555'
    resp = client.get('/session')
    data = json.loads(resp.data)
    assert data['total_sessions'] == 0
    assert data['sessions'] == []
    sess_1 = ProxySession(test_num_1, 'cust_1_num', 'cust_2_num')
    sess_2 = ProxySession(test_num_2, 'cust_1_num', 'cust_2_num')
    db_session.add(sess_1)
    db_session.add(sess_2)
    db_session.commit()
    resp = client.get('/session')
    data = json.loads(resp.data)
    assert data['total_sessions'] == 2


def test_delete_session():
    mock_controller = MockController()
    app.sms_controller = mock_controller
    client = app.test_client()
    resp = client.delete('/session',
                         data=json.dumps({'session_id': 'fake_id'}),
                         content_type='application/json')
    data = json.loads(resp.data)
    assert resp.status_code == 404
    msg = ("ProxySession {} could not be deleted because"
           " it does not exist".format('fake_id'))
    assert data['message'] == msg
    test_num_1 = '12223334444'
    vnum_1 = VirtualTN(test_num_1)
    sess_1 = ProxySession(test_num_1, 'cust_1_num', 'cust_2_num')
    vnum_1.session_id = sess_1.id
    db_session.add(sess_1)
    db_session.add(vnum_1)
    db_session.commit()
    resp = client.delete('/session',
                         data=json.dumps({'session_id': sess_1.id}),
                         content_type='application/json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['message'] == 'Successfully ended the session.'
    assert data['session_id'] == sess_1.id
    assert len(mock_controller.requests) == 2
