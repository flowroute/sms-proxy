import sys
import os
import logging
from pythonjsonlogger import jsonlogger


log = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
log.addHandler(handler)
log.setLevel(int(os.environ.get('LOG_LEVEL', 20)))  # Default to INFO log level
