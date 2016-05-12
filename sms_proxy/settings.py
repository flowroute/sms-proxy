import os

DEBUG_MODE = True

LOG_LEVEL = int(os.environ.get('LOG_LEVEL', 20))
SQLALCHEMY_TRACK_MODIFICATIONS = False
COMPANY_NAME = "Flowroute"
SESSION_START_MSG = "This session has begun, send a message!"
SESSION_END_MSG = "This session has ended, see you again soon!"
SEND_START_MSG = True
SEND_END_MSG = True

TEST_DB = "test_sms_proxy.db"
DB = "sms_proxy.db"