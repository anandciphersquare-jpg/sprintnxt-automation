"""Remembers the merchant that E2E-001 registered and activated, so later modules log in with it
(no new registration, no OTPs, no admin step). Stored locally in .merchant.json - never commit it."""
import json
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent / ".merchant.json"


def save_merchant(email, password, **extra):
    STORE.write_text(json.dumps({"email": email, "password": password, **extra}, indent=2), encoding="utf-8")


def load_merchant():
    """{'email', 'password', ...} of the last activated merchant, or None."""
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def update_password(new_password):
    data = load_merchant()
    if data:
        data["password"] = new_password
        STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")
