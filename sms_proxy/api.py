import simplejson as json

from flask import Flask, request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from FlowrouteMessagingLib.Controllers.APIController import APIController
from FlowrouteMessagingLib.Models.Message import Message

from settings import (FLOWROUTE_SECRET_KEY, FLOWROUTE_ACCESS_KEY,
                      ORG_NAME, SESSION_START_MSG, SESSION_END_MSG,
                      NO_SESSION_MSG, DEBUG_MODE, TEST_DB, DB)
from database import db_session, init_db
from log import log
from models import VirtualTN, ProxySession

app = Flask(__name__)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

init_db()

sms_controller = APIController(username=FLOWROUTE_ACCESS_KEY,
                               password=FLOWROUTE_SECRET_KEY)

# Attach the Flowroute messaging controller to the app
app.sms_controller = sms_controller


@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


# Use prod, or dev database depending on debug mode
if DEBUG_MODE:
    app.debug = DEBUG_MODE
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + TEST_DB
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB


def send_message(recipients, virtual_tn, msg, session_id, is_system_msg=False):
    if is_system_msg:
        msg = "[{}]: {}".format(ORG_NAME.upper(), msg)
    for recipient in recipients:
        message = Message(
            to=recipient,
            from_=virtual_tn,
            content=msg)
        try:
            app.sms_controller.create_message(message)
        except Exception as e:
            try:
                log.critical({"message": "raised an exception sending SMS",
                              "status": "failed",
                              "exc": e,
                              "strerr": e.response_body})
            except:
                pass
            raise
        else:
            log.info(
                {"message": "Message sent to {} for session {}".format(
                 recipient, session_id),
                 "status": "succeeded"})


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
def virtual_tn():
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
            db_session.add(virtual_tn)
            db_session.commit()
        except IntegrityError:
            db_session.rollback()
            msg = ("did not add virtual TN {} to the pool "
                   "-- already exists").format(value)
            log.info({"message": msg})
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
            log.info({"message": msg,
                      "status": "failed"})
            raise InvalidAPIUsage(
                "Virtual TN could not be deleted because it does not exist",
                status_code=404,
                payload={'reason':
                         'virtual TN not found'})
        else:
            # Release any VirtualTNs from expired ProxySessions
            ProxySession.clean_expired()
            try:
                active_session = ProxySession.query.filter_by(
                    virtual_TN=virtual_tn).one()
            except NoResultFound:
                db_session.delete(virtual_tn)
                db_session.commit()
            else:
                msg = ("Cannot delete the number. There is an active "
                       "ProxySession {} using that VirtualTN.".format(
                           active_session.id))
                return Response(
                    json.dumps(
                        {"message": msg,
                         "status": "failed",
                         }),
                    content_type="application/json",
                    status=400)
        return Response(
            json.dumps({"message": "successfully removed TN from pool",
                        "value": value,
                        "status": "succeeded"}),
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
        # Release any VirtualTNs from expired ProxySessions back to the pool
        ProxySession.clean_expired()

        # TODO This can become a model method (creating a session with a free virtual tn, and raising custom errors)
        virtual_tn = VirtualTN.get_next_available()
        if virtual_tn is None:
            msg = "Could not create a new session -- No virtual TNs available."
            log.critical({"message": msg,
                          "status": "failed"})
            return Response(
                json.dumps(
                    {"message": msg,
                     "status": "failed",
                     }),
                content_type="application/json",
                status=400)
        else:
            session = ProxySession(
                virtual_tn.value,
                participant_a,
                participant_b,
                expiry_window
            )
            try:
                virtual_tn.session_id = session.id
                db_session.add(virtual_tn)
                db_session.add(session)
                db_session.commit()
            except IntegrityError:
                db_session.rollback()
                msg = "There were two sessions attempting to reserve the same virtual tn. Please retry."
                log.error({"message": msg,
                           "status": "failed"})
                return Response(
                    json.dumps({"message": msg, "status": "failed"}),
                    content_type="application/json",
                    status=500)
            # TODO ends here
            expiry_date = session.expiry_date.strftime('%Y-%m-%d %H:%M:%S') if session.expiry_date else None
            recipients = [participant_a, participant_b]
            send_message(
                recipients,
                virtual_tn.value,
                SESSION_START_MSG,
                session.id,
                is_system_msg=True)
            msg = "ProxySession {} started with participants {} and {}".format(
                session.id,
                participant_a,
                participant_b)
            log.info({"message": msg,
                      "status": "succeeded"})
            return Response(
                json.dumps(
                    {"message": "created session",
                     "status": "succeeded",
                     "session_id": session.id,
                     "expiry_date": expiry_date,
                     "virtual_tn": virtual_tn.value,
                     "participant_a": participant_a,
                     "participant_b": participant_b}),
                content_type="application/json")
    if request.method == 'GET':
        sessions = ProxySession.query.all()
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
            session = ProxySession.query.filter_by(id=session_id).one()
        except NoResultFound:
            msg = ("could not delete session '{}' "
                   "because it does not exist").format(
                session_id)
            log.info({"message": msg,
                      "status": "failed"})
            raise InvalidAPIUsage(
                "ProxySession could not be deleted because it does not exist",
                status_code=404,
                payload={'reason':
                         'ProxySession not found'})
        participant_a, participant_b, virtual_tn = ProxySession.terminate(
            session_id)
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
        log.info({"message": msg,
                  "status": "succeeded"})

        return Response(
            json.dumps({"message": "successfully ended session",
                        "status": "succeeded",
                        "session_id": session_id}),
            content_type="application/json")


@app.route("/", methods=['POST'])
def inbound_handler():
    # We'll take this time to clear out any expired sessions and release
    # TNs back to the pool if possible
    # TODO we could fire off a thread here.
    ProxySession.clean_expired()
    body = request.json
    try:
        virtual_tn = body['to']
        int(body['to'])
        tx_participant = body['from']
        int(body['from'])
        message = body['body']
    except (KeyError, ValueError) as e:
        msg = ("Malformed inbound message: {}".format(body))
        log.error({"message": msg,
                   "status": "failed",
                   "exc": str(e)})
        return
    rcv_participant, session_id = ProxySession.get_other_participant(
        virtual_tn,
        tx_participant)
    if rcv_participant is not None:
        recipients = [rcv_participant]
        send_message(
            recipients,
            virtual_tn,
            message,
            session_id
        )
    else:
        recipients = [tx_participant]
        message = NO_SESSION_MSG
        send_message(
            recipients,
            virtual_tn,
            message,
            None,
            is_system_msg=True,
        )
        msg = ("ProxySession not found, or {} is not authorized to participate".format(
            tx_participant))
        log.info({"message": msg,
                  "status": "failed"})
        # TODO given for internal use, we can indicate whether the
        # session isn't found or participants are unauthorized.
    return Response(status=200)

if __name__ == "__main__":
    app.run('0.0.0.0', 8000)
