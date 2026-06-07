import datetime
import bcrypt
import jwt
from flask import current_app

TOKEN_TTL_DAYS = 7


def hash_passcode(passcode: str) -> str:
    return bcrypt.hashpw(passcode.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_passcode(passcode: str, passcode_hash: str) -> bool:
    try:
        return bcrypt.checkpw(passcode.encode('utf-8'), passcode_hash.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def issue_token(clinician_id: int) -> str:
    payload = {
        'clinician_id': clinician_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def decode_token(token: str) -> dict:
    return jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
