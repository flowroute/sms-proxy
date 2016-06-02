import simplejson as json

from flask import request, Response, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from FlowrouteMessagingLib.Models.Message import Message

from sms_proxy.settings import (ORG_NAME, SESSION_START_MSG, SESSION_END_MSG,
                                NO_SESSION_MSG)
from sms_proxy.database import db_session
from sms_proxy.log import log
from sms_proxy.models import VirtualTN, ProxySession
from sms_proxy.app import create_app

app = create_app()


@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


class InternalSMSDispatcherError(Exception):
    def __init__(self, message, status_code=500, payload=None):
        Exception.__init__(self)
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or())
        rv['message'] = self.message
        return rv


def send_message(recipients, virtual_tn, msg, session_id, is_system_msg=False):
    """
    For each recipient, passes a Message to Flowroute's messaging controller.
    The message will be sent from the 'virtual_tn' number. If this is a system
    message, the message body will be prefixed with the org name for context.
    If an exception is raised by the controller, an error is logged, and an
    internal error is raised with the exception content.
    """
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
            strerr = vars(e).get('response_body', None)
            log.critical({"message": "Raised an exception sending SMS",
                          "status": "failed",
                          "exc": e,
                          "strerr": vars(e).get('response_body', None)})
            raise InternalSMSDispatcherError(
                "An error occured when requesting against Flowroute's API.",
                payload={"strerr": strerr,
                         "reason": "InternalSMSDispatcherError"})
        else:
            log.info(
                {"message": "Message sent to {} for session {}".format(
                 recipient, session_id),
                 "status": "succeeded"})


class InvalidAPIUsage(Exception):
    """
    A generic exception for invalid API interactions.
    """
    def __init__(self, message, status_code=400, payload=None):
        Exception.__init__(self)
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or())
        rv['message'] = self.message
        return rv


@app.route("/tn", methods=['POST'])
def add_virtual_tn():
    """
    The VirtualTN resource endpoint for adding VirtualTN's from the pool.
    """
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
        msg = ("Did not add virtual TN {} to the pool "
               "-- already exists").format(value)
        log.info({"message": msg})
        raise InvalidAPIUsage(
            "Virtual TN already exists",
            payload={'reason':
                     'duplicate virtual TN'})
    return Response(
        json.dumps(
            {"message": "Successfully added TN to pool",
             "value": value}),
        content_type="application/json")


@app.route("/tn", methods=['GET'])
def list_virtual_tns():
    """
    The VirtualTN resource endpoint for listing VirtualTN's from the pool.
    """
    virtual_tns = VirtualTN.query.all()
    res = [{'value': tn.value, 'session_id': tn.session_id} for tn in virtual_tns]
    available = len([tn.value for tn in virtual_tns if tn.session_id is None])
    return Response(
        json.dumps({"virtual_tns": res,
                    "pool_size": len(res),
                    "available": available,
                    "in_use": len(res) - available}),
        content_type="application/json")


@app.route("/tn", methods=['DELETE'])
def remove_virtual_tn():
    """
    The VirtualTN resource endpoint for removing VirtualTN's from the pool.
    """
    body = request.json
    try:
        value = str(body['value'])
    except (AssertionError, KeyError):
        raise InvalidAPIUsage(
            "Required argument: 'value' (str, length <= 18)",
            payload={'reason':
                     'invalidAPIUsage'})
    try:
        virtualTN = VirtualTN.query.filter_by(value=value).one()
    except NoResultFound:
        msg = ("Could not delete virtual TN ({})"
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
                virtual_TN=virtualTN.value).one()
        except NoResultFound:
            db_session.delete(virtualTN)
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
        json.dumps({"message": "Successfully removed TN from pool",
                    "value": value,
                    "status": "succeeded"}),
        content_type="application/json")


@app.route("/session", methods=['POST'])
def add_proxy_session():
    """
    The ProxySession resource endpoint for adding a new ProxySession
    to the pool.
    """
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
            payload={'reason': 'invalidAPIUsage'})
    if 'expiry_window' in body:
        expiry_window = body['expiry_window']
    else:
        expiry_window = None
    # Release any VirtualTNs from expired ProxySessions back to the pool
    ProxySession.clean_expired()
    virtual_tn = VirtualTN.get_next_available()
    if virtual_tn is None:
        msg = "Could not create a new session -- No virtual TNs available."
        log.critical({"message": msg, "status": "failed"})
        return Response(
            json.dumps({"message": msg, "status": "failed"}),
            content_type="application/json", status=400)
    else:
        session = ProxySession(virtual_tn.value, participant_a,
                               participant_b, expiry_window)
        try:
            virtual_tn.session_id = session.id
            db_session.add(session)
            db_session.add(virtual_tn)
            db_session.commit()
        except IntegrityError:
            db_session.rollback()
            msg = "There were two sessions attempting to reserve the same virtual tn. Please retry."
            log.error({"message": msg, "status": "failed"})
            return Response(
                json.dumps({"message": msg, "status": "failed"}),
                content_type="application/json", status=500)
        expiry_date = session.expiry_date.strftime('%Y-%m-%d %H:%M:%S') if session.expiry_date else None
        recipients = [participant_a, participant_b]
        try:
            send_message(
                recipients,
                virtual_tn.value,
                SESSION_START_MSG,
                session.id,
                is_system_msg=True)
        except InternalSMSDispatcherError as e:
            db_session.delete(session)
            virtual_tn.session_id = None
            db_session.add(virtual_tn)
            db_session.commit()
            raise e
        msg = "ProxySession {} started with participants {} and {}".format(
            session.id,
            participant_a,
            participant_b)
        log.info({"message": msg, "status": "succeeded"})
        return Response(
            json.dumps(
                {"message": "Created new session",
                 "status": "succeeded",
                 "session_id": session.id,
                 "expiry_date": expiry_date,
                 "virtual_tn": virtual_tn.value,
                 "participant_a": participant_a,
                 "participant_b": participant_b}),
            content_type="application/json")


@app.route("/session", methods=["GET"])
def list_proxy_sessions():
    """
    The ProxySession resource endpoint for listing ProxySessions
    from the pool.
    """
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
        json.dumps({"total_sessions": len(res), "sessions": res}),
        content_type="application/json")


@app.route("/session", methods=["DELETE"])
def delete_session():
    """
    The ProxySession resource endpoint for removing a ProxySession
    to the pool.
    """
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
        msg = ("ProxySession {} could not be deleted because"
               " it does not exist".format(session_id))
        log.info({"message": msg,
                  "status": "failed"})
        raise InvalidAPIUsage(
            msg, status_code=404,
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
        session_id, virtual_tn.value)
    log.info({"message": msg, "status": "succeeded"})
    return Response(
        json.dumps({"message": "Successfully ended the session.",
                    "status": "succeeded",
                    "session_id": session_id}),
        content_type="application/json")


@app.route("/", methods=['POST'])
def inbound_handler():
    """
    The inbound request handler for consuming HTTP wrapped SMS content from
    Flowroute's messaging service.
    """
    # We'll take this time to clear out any expired sessions and release
    # TNs back to the pool if possible
    ProxySession.clean_expired()
    body = request.json
    try:
        virtual_tn = body['to']
        assert len(virtual_tn) <= 18
        tx_participant = body['from']
        assert len(tx_participant) <= 18
        message = body['body']
    except (TypeError, KeyError, AssertionError) as e:
        msg = ("Malformed inbound message: {}".format(body))
        log.error({"message": msg, "status": "failed", "exc": str(e)})
        return Response('There was an issue parsing your request.', status=400)
    rcv_participant, session_id = ProxySession.get_other_participant(
        virtual_tn, tx_participant)
    if rcv_participant is not None:
        recipients = [rcv_participant]
        send_message(
            recipients,
            virtual_tn,
            message,
            session_id)
    else:
        recipients = [tx_participant]
        send_message(
            recipients,
            virtual_tn,
            NO_SESSION_MSG,
            None,
            is_system_msg=True)
        msg = ("ProxySession not found, or {} is not authorized "
               "to participate".format(tx_participant))
        log.info({"message": msg, "status": "succeeded"})
    return Response(status=200)


@app.errorhandler((InvalidAPIUsage, InternalSMSDispatcherError))
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    response.content_type = 'application/json'
    return response

if __name__ == "__main__":
    app.run('0.0.0.0', 8000)
