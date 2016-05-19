import uuid
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm.exc import NoResultFound

from database import Base, db_session
from log import log


class VirtualTN(Base):
    """
    id (int):
        The identifier of the virtual TN, also it's primary key
    value (str):
        The value of the virtual TN, (1NPANXXXXXX format)
    session_id (str):
        The session_id, if any, for which this virtual TN is assigned to.
    """

    def get_available_tns(cls):
        """
        Returns a virtual TN that does not already have a session attached
        to it, otherwise returns None
        """
        try:
            return cls.query.filter_by(session_id=None).first()
        except NoResultFound:
            return None

    __tablename__ = 'virtual_tn'
    id = Column(Integer)
    value = Column(String(18), primary_key=True)
    session_id = Column(String(40))

    def __init__(self, value):
        self.value = value
        self.session_id = None


class Session(Base):
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
    def clean_expired_sessions(cls):
        """
        Removes sessions that have an expiry date in the past and releases
        the corresponding virtual TN back to the pool
        """
        current_timestamp = datetime.utcnow()
        try:
            expired_sessions = db_session.query(Session).filter(
                Session.expiry_date <= current_timestamp)
        except NoResultFound:
            return
        for session in expired_sessions:
            cls.end_session(session.id)

    def end_session(cls, session_id):
        """
        Ends a given session, and releases the virtual TN back into the pool
        """
        session = Session.query.filter_by(id=session_id).one()
        participant_a = session.participant_a
        participant_b = session.participant_b
        virtual_tn = VirtualTN.query.filter_by(session_id=session_id).one()
        virtual_tn.session_id = None
        db_session.commit()
        db_session.delete(session)
        db_session.commit()
        return participant_a, participant_b

    def get_other_participant(cls, virtual_tn, sender):
        """
        Returns the 2nd particpant and session when given the virtual TN
        and the first participant
        """
        session = None
        try:
            session = Session.query.filter_by(virtual_TN=virtual_tn).one()
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
                msg = ("{} is not a participant of session {}").format(
                    sender,
                    session.id)
                log.info({"message": msg})
                return None, None


    __tablename__ = 'session'
    id = Column(String(40), primary_key=True)
    date_created = Column(DateTime)
    virtual_TN = Column(String(18))
    participant_a = Column(String(18))
    participant_b = Column(String(18))
    expiry_date = Column(DateTime, nullable=True)

    def __init__(self, virtual_TN, participant_A,
                 participant_B, expiry_window=None):
        self.id = uuid.uuid4().hex
        self.date_created = datetime.utcnow()
        self.virtual_TN = virtual_TN
        self.participant_a = participant_A
        self.participant_b = participant_B
        self.expiry_date = self.date_created + timedelta(
            minutes=expiry_window) if expiry_window else None
