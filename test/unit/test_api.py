import pytest
import json
import urllib
import uuid
from datetime import datetime

from sms_proxy.api import app, VirtualTN, ProxySession, InternalSMSDispatcherError
from sms_proxy.database import db_session, init_db, destroy_db, engine
from sms_proxy.settings import (TEST_DB, NO_SESSION_MSG, ORG_NAME,
                                SESSION_END_MSG, SESSION_START_MSG)


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
            self.resp = []

        def create_message(self, msg):
            self.requests.append(msg)
            try:
                err = self.resp.pop(0)
            except:
                pass
            else:
                if err is False:
                    raise Exception("Unkown exception from FlowrouteSDK.")


mock_controller = MockController()


def test_post_new_tn():
    """
    Posts an number to the '/tn' route, checks for 200 then attempts again to
    ensure virtual numbers are idempotent.
    """
    client = app.test_client()
    test_num = '12223334444'
    resp = client.post('/tn', data=json.dumps({'value': test_num}),
                       content_type='application/json')
    assert resp.status_code == 200
    resp = client.post('/tn', data=json.dumps({'value': test_num}),
                       content_type='application/json')
    assert resp.status_code == 400


def test_get_tns():
    """
    Adds two virtual numbers to the database, one reserved in a session
    and one free. The '/tn' GET route is requested to and assertions
    are made that the data returned reflects the state of the virtual tn's.
    """
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
    """
    Creates a new virtual tn attached to a session, and requests to
    delete that number which is an illegal operation. The VirtualTN is then
    released, and the request is made again - this time succeeding.
    """
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
    """
    Initially attempts to create a session when there are no VirtualTN's
    available. The service responds with a 400, and an appropriate message.
    Attempts again, when there is a VirtualTN in the pool, but reserved,
    the service will respond again with a 400. After releasing the 
    VirtualTN, the request succesfully posts, and the response is checked
    for appropriate values. Ensures both session initialization SMS messages
    have been fired off.
    """
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
    msg = "[{}]: {}".format(ORG_NAME.upper(), SESSION_START_MSG)
    sms = mock_controller.requests[0]
    assert sms.content == msg
    assert data['session_id'] is not None


def test_get_session():
    """
    Ensures the '/session' GET method returns json reflecting the state of the
    database.
    """
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
    """
    Initially tries to delete a session from an id that is unknown. The service
    responds with a 404, and helpful message. A session is created an persisted
    to the database. A delete request for that session is executed, and SMS's
    are dispatched to the participants.
    """
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
    sms = mock_controller.requests[0]
    msg = "[{}]: {}".format(ORG_NAME.upper(), SESSION_END_MSG)
    assert sms.content == msg
    assert len(mock_controller.requests) == 2


@pytest.fixture
def virtual_tn():
    virtual_tn = VirtualTN('12069992222')
    db_session.add(virtual_tn)
    db_session.commit()
    return virtual_tn


@pytest.fixture
def valid_session(virtual_tn):
    first_num = '12223334444'
    sec_num = '12223335555'
    proxy_sess = ProxySession(virtual_tn.value, first_num, sec_num)
    virtual_tn.session_id = proxy_sess.id
    db_session.add(virtual_tn)
    db_session.add(proxy_sess)
    db_session.commit()
    return proxy_sess


@pytest.fixture
def fake_app(app=app):
    mock_controller = MockController()
    app.sms_controller = mock_controller
    return app


def test_inbound_handler_success_a_traverse(valid_session, fake_app):
    """
    Tests that incoming messages bound for a VirtualTN are succesfully
    sent back out to the participant in an active session with that sender.
    The proxy capability is bi-directional.
    """
    client = fake_app.test_client()
    req = {'to': valid_session.virtual_TN,
           'from': valid_session.participant_b,
           'body': 'hello from participant b'}
    resp = client.post('/', data=json.dumps(req),
                       content_type='application/json')
    assert resp.status_code == 200
    sms = fake_app.sms_controller.requests[0]
    sms.content == 'hello from participant b'
    sms.to = valid_session.participant_a
    sms.mfrom = valid_session.virtual_TN
    assert len(fake_app.sms_controller.requests) == 1


def test_inbound_handler_success_b_traverse(valid_session, fake_app):
    """
    Tests that incoming messages bound for a VirtualTN are succesfully
    sent back out to the participant in an active session with that sender.
    The proxy capability is bi-directional.
    """
    client = fake_app.test_client()
    req = {'to': valid_session.virtual_TN,
           'from': valid_session.participant_a,
           'body': 'hello from participant a'}
    resp = client.post('/', data=json.dumps(req),
                       content_type='application/json')
    assert resp.status_code == 200
    sms = fake_app.sms_controller.requests[0]
    sms.content == 'hello from participant a'
    sms.to = valid_session.participant_b
    sms.mfrom = valid_session.virtual_TN
    assert len(fake_app.sms_controller.requests) == 1


def test_inbound_handler_expired_session(fake_app, valid_session):
    """
    An inbound message intended for a VirtualTN that is no longer
    in a session with the sender will no proxy to the other 
    participant. Asserts a system message is fired back to the 
    sender.
    """
    valid_session.expiry_date = datetime.utcnow()
    db_session.add(valid_session)
    db_session.commit()
    expired_session = valid_session
    client = fake_app.test_client()
    req = {'to': expired_session.virtual_TN,
           'from': expired_session.participant_a,
           'body': 'hello from participant a'}
    resp = client.post('/', data=json.dumps(req),
                       content_type='application/json')
    # Indicating that we received the message from Flowroute
    assert resp.status_code == 200
    sms = fake_app.sms_controller.requests[0]
    msg = "[{}]: {}".format(ORG_NAME.upper(), NO_SESSION_MSG)
    assert sms.content == msg
    assert sms.to == expired_session.participant_a
    assert sms.mfrom == expired_session.virtual_TN


def test_inbound_handler_unknown_number(fake_app):
    """
    An inbound message to a VirtualTN that is unkown will
    receive a system SMS response indicating that it is 
    not a valid session.
    """
    client = fake_app.test_client()
    to = '12223334444'
    mfrom = '12223335555'
    req = {'to': to,
           'from': mfrom,
           'body': "hello from participant a"}
    resp = client.post('/', data=json.dumps(req),
                       content_type='application/json')
    # Indicating that we received the message from Flowroute
    assert resp.status_code == 200
    sms = fake_app.sms_controller.requests[0]
    assert sms.to == mfrom


@pytest.mark.parametrize("recipients, sys_msg, resp, err", [
    (['12223334444', '12223335555'], False, True, None),
    (['12223334444', '12223335555'], True, True, None),
    (['12223334444'], False, True, None),
    (['13334445555'], False, False, InternalSMSDispatcherError),
])
def test_send_message(fake_app, recipients, sys_msg, resp, err):
    """
    The send message function is able to generate system messages
    by prepending the message with the organization name. It can
    broadcast the message to multiple recipients. If an error 
    occurs when using the SMS controller client, an internal 
    exception is raised, bubbles up and is tranformed to a 
    response for the client side. Database state is not rolled back
    in the event of a message send failure.
    """
    session_id = 'session_id'
    msg = 'hello'
    virtual_tn = '13334445555'
    from sms_proxy.api import send_message
    if resp is False:
        fake_app.sms_controller.resp.append(resp)
        with pytest.raises(err):
            send_message(recipients, virtual_tn, msg, session_id,
                         is_system_msg=sys_msg)
    else:
        send_message(recipients, virtual_tn, msg, session_id,
                     is_system_msg=sys_msg)
        assert len(fake_app.sms_controller.requests) == len(recipients)
        if sys_msg:
            msg = "[{}]: {}".format(ORG_NAME.upper(), msg)
        for sms in fake_app.sms_controller.requests:
            assert sms.to in recipients
            assert sms.mfrom == virtual_tn
            assert sms.content == msg
