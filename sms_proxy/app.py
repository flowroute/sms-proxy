from flask import Flask
from FlowrouteMessagingLib.Controllers.APIController import APIController

from sms_proxy.database import init_db
from sms_proxy.settings import (FLOWROUTE_ACCESS_KEY, FLOWROUTE_SECRET_KEY,
                                DEBUG_MODE, DB, TEST_DB)


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Use prod, or dev database depending on debug mode
    if DEBUG_MODE:
        app.debug = DEBUG_MODE
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + TEST_DB
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB
    init_db()
    sms_controller = APIController(username=FLOWROUTE_ACCESS_KEY,
                                   password=FLOWROUTE_SECRET_KEY)

    # Attach the Flowroute messaging controller to the app
    app.sms_controller = sms_controller
    return app
