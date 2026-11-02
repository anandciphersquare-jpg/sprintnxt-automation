"""Test-data generators and curated invalid-input sets for data-driven tests."""
import random
import re
import string
import time

from faker import Faker

fake = Faker("en_IN")


def unique_email(prefix="qa.auto"):
    """A fresh, valid, unique email on every call (timestamp + random suffix)."""
    ts = int(time.time() * 1000)
    return f"{prefix}+{ts}{random.randint(100, 999)}@gmail.com"


def valid_mobile():
    """Valid Indian mobile: 10 digits, starts 6-9."""
    return random.choice("6789") + "".join(random.choices(string.digits, k=9))


def valid_person():
    return {
        "first_name": fake.first_name(),
        "last_name": fake.last_name(),
        # Portal accepts letters and spaces only; Faker companies contain commas/hyphens
        "business_name": re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", fake.company())).strip(),
    }


def valid_password(length=12):
    """12-15 char password guaranteed to contain upper, lower, digit and special."""
    assert 12 <= length <= 15
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    special = random.choice("!@#$%^&*")
    rest = "".join(random.choices(string.ascii_letters + string.digits, k=length - 4))
    chars = list(upper + lower + digit + special + rest)
    random.shuffle(chars)
    return "".join(chars)


def random_string(length=10):
    return "".join(random.choices(string.ascii_letters, k=length))


# (value, human-readable reason) — reasons double as parametrize ids
INVALID_EMAILS = [
    ("plainaddress", "no-at-or-domain"),
    ("missingatsign.com", "missing-at"),
    ("user@", "missing-domain"),
    ("user@domain", "missing-tld"),
    ("user@@domain.com", "double-at"),
    ("user name@domain.com", "space-in-local"),
    ("user!#@domain.com", "illegal-chars"),
    ("@nouser.com", "missing-local"),
    ("", "empty"),
]

INVALID_MOBILES = [
    ("12345", "too-short"),
    ("12345678901234", "too-long"),
    ("98765abcde", "non-numeric"),
    ("0123456789", "invalid-start-digit"),
    ("98765 43210", "contains-space"),
    ("+91-9876543210", "contains-symbols"),
    ("0000000000", "all-zeros"),
    ("", "empty"),
]

# each fails exactly one rule (except the length/empty ones), so assertions are unambiguous
INVALID_PASSWORDS = [
    ("Ab@1234567", "length-10-below-min"),
    ("Ab@1234567890123", "length-16-above-max"),
    ("ab@123456789", "no-uppercase"),
    ("AB@123456789", "no-lowercase"),
    ("Abcd@efghijk", "no-digit"),
    ("Abcd12345678", "no-special"),
    ("Ab@1", "far-too-short"),
    ("", "empty"),
]
