import os
import uuid
import simplejson as json
from datetime import datetime, timedelta

from flask import Flask, request, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from FlowrouteMessagingLib.Controllers.APIController import APIController
from FlowrouteMessagingLib.Models.Message import Message

from settings import (COMPANY_NAME, SESSION_START_MSG, SESSION_END_MSG,
                      SEND_START_MSG, SEND_END_MSG, NO_SESSION_MSG,
                      SESSION_END_TRIGGER, DEBUG_MODE, TEST_DB, DB)

from log import log

FLOWROUTE_SECRET_KEY = os.environ['FLOWROUTE_SECRET_KEY']
FLOWROUTE_ACCESS_KEY = os.environ['FLOWROUTE_ACCESS_KEY']

app = Flask(__name__)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

sms_controller = APIController(username=FLOWROUTE_ACCESS_KEY,
                               password=FLOWROUTE_SECRET_KEY)

# Attach the Flowroute messaging controller to the app
app.sms_controller = sms_controller


class VirtualTN(db.Model):
    """
    id (int):
        The identifier of the virtual TN, also it's primary key
    value (str):
        The value of the virtual TN, (1NPANXXXXXX format)
    session_id (str):
        The session_id, if any, for which this virtual TN is assigned to.
    """
    id = db.Column(db.Integer)
    value = db.Column(db.String(18), primary_key=True)
    session_id = db.Column(db.String(40))

    def __init__(self, value):
        self.value = value
        self.session_id = None


class Sessions(db.Model):
    """
    id (str):
        The unique session identifier
    date_created (timestamp):
        The timestamp, in UTC of when the session was created
    virtual_TN (str):
        The virtual TN assigned to this session
    participant_a (str):
        The phone number of the first participant of the session
    participant_b (str):
        The phone number of the second participant of the session
    expiry_date (timestamp):
        The timestamp of when this session should expire.  If a time, in
        minutes, is not provided when creating the session, the
        DEFAULT_EXPIRATION in settings is used
    """
    id = db.Column(db.String(40), primary_key=True)
    date_created = db.Column(db.DateTime)
    virtual_TN = db.Column(db.String(18))
    participant_a = db.Column(db.String(18))
    participant_b = db.Column(db.String(18))
    expiry_date = db.Column(db.DateTime, nullable=True)

    def __init__(self, virtual_TN, participant_A, participant_B, expiry_window=None):
        self.id = uuid.uuid4().hex
        self.date_created = datetime.utcnow()
        self.virtual_TN = virtual_TN
        self.participant_a = participant_A
        self.participant_b = participant_B
        self.expiry_date = self.date_created + timedelta(
            minutes=expiry_window) if expiry_window else None

# Use prod, or dev database depending on debug mode
if DEBUG_MODE:
    app.debug = DEBUG_MODE
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + TEST_DB
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB
db.create_all()
db.session.commit()


class InvalidAPIUsage(Exception):
    def __init__(self, message, status_code=400, payload=None):
        Exception.__init__(self)
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or())
        rv['message'] = self.message
        return rv


def get_available_virtual_tn():
    """
    Returns a virtual TN that does not already have a session attached to it,
    otherwise returns None
    """
    try:
        return VirtualTN.query.filter_by(session_id=None).first()
    except NoResultFound:
        return None


def clean_expired_sessions():
    """
    Removes sessions that have an expiry date in the past and releases
    the corresponding virtual TN back to the pool
    """
    current_timestamp = datetime.utcnow()
    try:
        expired_sessions = db.session.query(Sessions).filter(
            Sessions.expiry_date <= current_timestamp)
    except NoResultFound:
        return
    for session in expired_sessions:
        end_session(session.id)


def end_session(session_id):
    """
    Ends a given session, and releases the virtual TN back into the pool
    """
    session = Sessions.query.filter_by(id=session_id).one()
    participant_a = session.participant_a
    participant_b = session.participant_b
    virtual_tn = VirtualTN.query.filter_by(session_id=session_id).one()
    virtual_tn.session_id = None
    db.session.commit()
    db.session.delete(session)
    db.session.commit()
    if SEND_END_MSG:
        recipients = [participant_a, participant_b]
        send_message(
            recipients,
            virtual_tn.value,
            SESSION_END_MSG,
            session_id,
            is_system_msg=True)
    msg = "Ended session {} and released {} back to pool".format(
        session_id,
        virtual_tn.value)
    log.info({"message": msg})


def send_message(recipients, virtual_tn, msg, session_id, is_system_msg=False):
    if is_system_msg:
        msg = "[{}]: {}".format(COMPANY_NAME.upper(), msg)
    for recipient in recipients:
        message = Message(
            to=recipient,
            from_=virtual_tn,
            content=msg)
        try:
            app.sms_controller.create_message(message)
        except Exception as e:
            try:
                log.info("got exception e {}, code: {}, response {}".format(
                    e, e.response_code, e.response_body))
            except:
                pass
            raise
        else:
            log.info(
                {"message": "Message sent to {} for session {}".format(recipient, session_id)})


def get_other_participant(virtual_tn, sender):
    """
    Returns the 2nd particpant and session when given the virtual TN
    and the first participant
    """
    session = None
    try:
        session = Sessions.query.filter_by(virtual_TN=virtual_tn).one()
    except NoResultFound:
            msg = ("A session with virtual TN '{}'"
                   " could not be found").format(virtual_tn)
            log.info({"message": msg})
            return None, None
    if session:
        participant_a = session.participant_a
        participant_b = session.participant_b
        if participant_a == sender:
            return participant_b, session.id
        elif participant_b == sender:
            return participant_a, session.id
        else:
            msg = ("{} is not a participant of session {}").format(sender, session.id)
            log.info({"message": msg})
            return None, None


@app.route("/tn", methods=['POST', 'GET', 'DELETE'])
def viritual_tn():
    # Add a TN to the virtual TN pool
    if request.method == 'POST':
        body = request.json
        try:
            value = str(body['value'])
            assert len(value) <= 18
        except (AssertionError, KeyError):
            raise InvalidAPIUsage(
                "Required argument: 'value' (str, length <= 18)",
                payload={'reason':
                         'invalidAPIUsage'})
        virtual_tn = VirtualTN(value)
        try:
            db.session.add(virtual_tn)
            db.session.commit()
        except IntegrityError:
            # TODO: WHY DONT WE EVER GET HERE??
            db.session.rollback()
            msg = ("did not add virtual TN {} to the pool "
                   "-- already exists").format(value)
            log.debug({"message": msg})
            raise InvalidAPIUsage(
                "Virtual TN already exists",
                payload={'reason':
                         'duplicate virtual TN'})
        return Response(
            json.dumps(
                {"message": "successfully added TN to pool",
                 "value": value}),
            content_type="application/json")
    # Retrieve all virtual TNs from pool
    if request.method == 'GET':
        virtual_tns = VirtualTN.query.all()
        res = [{'value': tn.value, 'session_id': tn.session_id} for tn in virtual_tns]
        available = len([tn.value for tn in virtual_tns if tn.session_id is None])
        return Response(
            json.dumps({"virtual_tns": res,
                        "pool_size": len(res),
                        "available": available,
                        "in_use": len(res) - available}),
            content_type="application/json")
    # Delete a virtual TN from pool
    if request.method == "DELETE":
        body = request.json
        try:
            value = str(body['value'])
        except (AssertionError, KeyError):
            raise InvalidAPIUsage(
                "Required argument: 'value' (str, length <= 18)",
                payload={'reason':
                         'invalidAPIUsage'})
        try:
            virtual_tn = VirtualTN.query.filter_by(value=value).one()
        except NoResultFound:
            msg = ("could not delete virtual TN ({})"
                   " because it does not exist").format(value)
            log.info({"message": msg})
            raise InvalidAPIUsage(
                "Virtual TN could not be deleted because it does not exist",
                status_code=404,
                payload={'reason':
                         'virtual TN not found'})
        db.session.delete(virtual_tn)
        db.session.commit()
        return Response(
            json.dumps({"message": "successfully removed TN from pool",
                        "value": value}),
            content_type="application/json")


@app.route("/session", methods=['POST', 'GET', 'DELETE'])
def proxy_session():
    # Create a new session
    if request.method == "POST":
        body = request.json
        try:
            participant_a = body['participant_a']
            participant_b = body['participant_b']
            assert len(participant_a) <= 18
            assert len(participant_b) <= 18
        except (AssertionError, KeyError):
            raise InvalidAPIUsage(
                ("Required argument: 'participant_a' (str, length <= 18)"
                 ", 'participant_b' (str, length <= 18)"),
                payload={'reason':
                         'invalidAPIUsage'})
        if 'expiry_window' in body:
            expiry_window = body['expiry_window']
        else:
            expiry_window = None
        # We'll take this time to clear out any expired sessions and release
        # TNs back to the pool if possible
        clean_expired_sessions()
        virtual_tn = get_available_virtual_tn()
        if virtual_tn is None:
            msg = "Could not create session -- No virtual TNs available"
            log.info({"message": msg})
            return Response(
                json.dumps(
                    {"message": msg}),
                content_type="application/json",
                status=400)
        else:
            session = Sessions(
                virtual_tn.value,
                participant_a,
                participant_b,
                expiry_window
            )
            virtual_tn.session_id = session.id
            db.session.add(session)
            db.session.commit()
            expiry_date = session.expiry_date.strftime('%Y-%m-%d %H:%M:%S') if session.expiry_date else None
            if SEND_START_MSG:
                recipients = [participant_a, participant_b]
                msg = SESSION_START_MSG
                if SESSION_END_TRIGGER:
                    msg += " Send '{}' to end this session.".format(SESSION_END_TRIGGER)
                send_message(
                    recipients,
                    virtual_tn.value,
                    msg,
                    session.id,
                    is_system_msg=True)
            msg = "Session {} started with participants {} and {}".format(
                session.id,
                participant_a,
                participant_b)
            log.info({"message": msg})
            return Response(
                json.dumps(
                    {"message": "created session",
                     "session_id": session.id,
                     "expiry_date": expiry_date,
                     "virtual_tn": virtual_tn.value,
                     "participant_a": participant_a,
                     "participant_b": participant_b}),
                content_type="application/json")
    if request.method == 'GET':
        sessions = Sessions.query.all()
        res = [{
            'id': s.id,
            'date_created': s.date_created.strftime('%Y-%m-%d %H:%M:%S'),
            'virtual_tn': s.virtual_TN,
            'participant_a': s.participant_a,
            'participant_b': s.participant_b,
            'expiry_date': s.expiry_date.strftime('%Y-%m-%d %H:%M:%S')
            if s.expiry_date else None}
            for s in sessions]
        return Response(
            json.dumps({"total_sessions": len(res),
                        "sessions": res}),
            content_type="application/json")
    # Delete an existing session
    if request.method == "DELETE":
        body = request.json
        try:
            session_id = str(body['session_id'])
        except (KeyError):
            raise InvalidAPIUsage(
                "Required argument: 'session_id' (str)",
                payload={'reason':
                         'invalidAPIUsage'})
        try:
            session = Sessions.query.filter_by(id=session_id).one()
        except NoResultFound:
            msg = ("could not delete session '{}' "
                   "because it does not exist").format(
                session_id)
            log.info({"message": msg})
            raise InvalidAPIUsage(
                "Session could not be deleted because it does not exist",
                status_code=404,
                payload={'reason':
                         'Session not found'})
        end_session(session_id)
        return Response(
            json.dumps({"message": "successfully ended session",
                        "session_id": session_id}),
            content_type="application/json")


@app.route("/", methods=['POST'])
def inbound_handler():
    # We'll take this time to clear out any expired sessions and release
    # TNs back to the pool if possible
    clean_expired_sessions()
    body = request.json
    try:
        virtual_tn = body['to']
        tx_participant = body['from']
        message = body['body']
    except (KeyError):
        msg = ("Malformed inbound message: {}".format(body))
        log.info({"message": msg})
    rcv_participant, session_id = get_other_participant(virtual_tn, tx_participant)
    if rcv_participant is not None:
        # See if the participant sent to trigger to end the session
        if SESSION_END_TRIGGER and message == SESSION_END_TRIGGER:
            end_session(session_id)
            return Response(
                json.dumps({"message": "successfully ended session",
                            "session_id": session_id}),
                content_type="application/json")
        recipients = [rcv_participant]
        send_message(
            recipients,
            virtual_tn,
            message,
            session_id
        )
        return Response(
            json.dumps({"message": "successfully proxied message",
                        "session_id": session_id,
                        "from": tx_participant,
                        "to": rcv_participant}),
            content_type="application/json")
    recipients = [tx_participant]
    message = NO_SESSION_MSG
    send_message(
        recipients,
        virtual_tn,
        message,
        None,
        is_system_msg=True,
    )
    msg = ("Session not found, or {} is not authorized to participate".format(tx_participant))
    log.info({"message": msg})
    return Response(
        json.dumps({"message": "Session not found, or {} is not authorized to participate".format(tx_participant)}),
        content_type="application/json",
        status=404)


if __name__ == "__main__":
    db.create_all()
    app.run('0.0.0.0', 8000)