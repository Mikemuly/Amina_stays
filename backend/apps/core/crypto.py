"""Field-level encryption for sensitive guest data (ID / passport numbers).

Kenya's Data Protection Act 2019 expects appropriate safeguards for personal data:
ID numbers are encrypted at rest (Fernet = AES-128-CBC + HMAC-SHA256) and only the
last 4 characters are ever shown in the console.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = settings.ID_ENCRYPTION_KEY
    if not key:
        # derive a stable key from SECRET_KEY so development works out of the box
        key = base64.urlsafe_b64encode(hashlib.sha256(("id-key:" + settings.SECRET_KEY).encode()).digest())
    return Fernet(key)


def encrypt(value):
    if not value:
        return ""
    return _fernet().encrypt(str(value).encode()).decode()


def decrypt(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def last4(value):
    value = (value or "").strip()
    return ("•" * max(0, len(value) - 4) + value[-4:]) if value else ""
