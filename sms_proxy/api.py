import uuid
import simplejson as json
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from FlowrouteMessagingLib.Controllers.APIController import APIController
from FlowrouteMessagingLib.Models.Message import Message

from sms_proxy.settings import (
    DEBUG_MODE, CODE_LENGTH, CODE_EXPIRATION,
    TEST_DB, DB, RETRIES_ALLOWED, AUTH_MESSAGE)

from credentials import (FLOWROUTE_ACCESS_KEY, FLOWROUTE_SECRET_KEY,
                         FLOWROUTE_NUMBER)
from sms_proxy.log import log


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
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(18))
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


@app.route("/tn", methods=['POST', 'GET', 'DELETE'])
def viritual_tn():
    pass


@app.route("/session", methods=['POST', 'GET', 'DELETE'])
def proxy_session():
    pass


if __name__ == "__main__":
    db.create_all()
    app.run('0.0.0.0', 8000)