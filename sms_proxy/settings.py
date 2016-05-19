import os

DEBUG_MODE = True
SQLALCHEMY_TRACK_MODIFICATIONS = False
LOG_LEVEL = int(os.environ.get('LOG_LEVEL', 20))

FLOWROUTE_SECRET_KEY = os.environ.get('FLOWROUTE_SECRET_KEY', None)
FLOWROUTE_ACCESS_KEY = os.environ.get('FLOWROUTE_ACCESS_KEY', None)

COMPANY_NAME = os.environ.get('COMPANY_NAME', 'Flowroute')
SESSION_START_MSG = "Your new session has started, send a message!"
SESSION_END_MSG = "This session has ended, talk to you again soon!"
NO_SESSION_MSG = "An active session was not found. Please contact support@flowroute.com"
SEND_START_MSG = True
SEND_END_MSG = True
SESSION_END_TRIGGER = "*END*"

TEST_DB = "test_sms_proxy.db"
DB = "sms_proxy.db"
