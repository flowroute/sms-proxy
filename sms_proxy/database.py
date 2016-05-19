from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from settings import DB, TEST_DB, DEBUG_MODE

if DEBUG_MODE:
    engine = create_engine('sqlite:////tmp/{}'.format(TEST_DB),
                           convert_unicode=True)
else:
    engine = create_engine('sqlite:///{}'.format(DB), convert_unicode=True)

db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    import models
    Base.metadata.create_all(bind=engine)
