"""One credential-format policy for the existing API and administrator CLI."""

import re

PHONE_PATTERN = re.compile(r'^1\d{10}$')


def valid_passcode(passcode):
    try:
        return isinstance(passcode, str) and len(passcode) >= 4 and len(passcode.encode('utf-8')) <= 72
    except UnicodeEncodeError:
        return False
