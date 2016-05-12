import uuid
import simplejson as json
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from FlowrouteMessagingLib.Controllers.APIController import APIController
from FlowrouteMessagingLib.Models.Message import Message

from settings import (DEBUG_MODE, TEST_DB, DB)

from credentials import (FLOWROUTE_ACCESS_KEY, FLOWROUTE_SECRET_KEY)
from log import log


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
    session_id = db.Column(db.String(32))

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
    id = db.Column(db.String(32), primary_key=True)
    date_created = db.Column(db.DateTime)
    virtual_TN = db.Column(db.String(18))
    participant_a = db.Column(db.String(18))
    participant_b = db.Column(db.String(18))
    expiry_date = db.Column(db.DateTime, nullable=True)

    def __init__(self, virtual_TN, participant_A, participant_B, expiry_window=None):
        self.id = uuid.uuid4()
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


@app.route("/tn", methods=['POST', 'GET', 'DELETE'])
def viritual_tn():
    # Add a TN to the virtual TN pool
    if request.method == 'POST':
        body = request.json
        try:
            value = str(body['value'])
            assert len(value) <= 18
        except (AssertionError, ValueError):
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
            msg = "did not add virtual TN {} to the pool -- already exists".format(value)
            log.debug({"message": msg})
            raise InvalidAPIUsage(
                "Virtual TN already exists",
                payload={'reason':
                         'duplicate virtual TN'})
        return Response(
            json.dumps({"message": "successfully added {} to pool".format(value)}),
            content_type="application/json")
    # Retrieve all virtual TNs from pool
    if request.method == 'GET':
        virtual_tns = VirtualTN.query.all()
        res = [{'value': tn.value, 'session_id': tn.session_id} for tn in virtual_tns]
        available = len([tn.value for tn in virtual_tns if tn.session_id != 'null'])
        return Response(
            json.dumps({"virtual_tns": res,
                        "pool_size": len(res),
                        "available": available,
                        "in_use": len(res)-available}),
            content_type="application/json")
    # Delete a virtual TN from pool
    if request.method == "DELETE":
        body = request.json
        try:
            value = str(body['value'])
        except (AssertionError, ValueError):
            raise InvalidAPIUsage(
                "Required argument: 'value' (str, length <= 18)",
                payload={'reason':
                         'invalidAPIUsage'})
        try:
            virtual_tn = VirtualTN.query.filter_by(value=value).one()
        except NoResultFound:
            msg = "could not delete virtual TN ({}) because it does not exist".format(value)
            log.info({"message": msg})
            raise InvalidAPIUsage(
                "Virtual TN could not be deleted because it does not exist",
                status_code=404,
                payload={'reason':
                         'virtual TN not found'})
        db.session.delete(virtual_tn)
        db.session.commit()
        return Response(
            json.dumps({"message": "successfully removed {} from pool".format(value)}),
            content_type="application/json")


@app.route("/session", methods=['POST', 'GET', 'DELETE'])
def proxy_session():
    # Create a new session 



if __name__ == "__main__":
    db.create_all()
    app.run('0.0.0.0', 8000)