"""Add Bank test data in one place: banks/services that work on UAT, the form fields and their rules,
and the invalid inputs with the exact messages the portal shows (captured from UAT on 2026-10-16)."""
import random
import string
import time

# Banks that work on UAT right now. IDFC: all three services. HDFC: only Payout works,
# although the UI also offers UPI / VID / All Services cards for it.
BANKS = {
    "IDFC": {"name": "IDFC First Bank", "short": "IDFC", "ifsc": "IDFB0040101",
             "services": ["All Services"], "expect_services": ["Payout", "UPI Collection", "VID Collection"]},
    "HDFC": {"name": "HDFC Bank", "short": "HDFC", "ifsc": "HDFC0000001",
             "services": ["Payout"], "expect_services": ["Payout"]},
}

SERVICE_CARDS = ["Payout", "UPI Collection", "VID Collection", "All Services"]

# Step 3 "Fill Details": label -> placeholder, mandatory, maxlength (from the DOM)
FIELDS = {
    "Organisation Name":        {"placeholder": "Enter organisation name",        "mandatory": True,  "max": 255},
    "Bank Account Number":      {"placeholder": "Enter bank account number",      "mandatory": True,  "max": 18},
    "Confirm Account No":       {"placeholder": "Re-enter account number",        "mandatory": True,  "max": 18},
    "IFSC Code":                {"placeholder": "Enter IFSC code",                "mandatory": True,  "max": 11},
    "Registered Mobile Number": {"placeholder": "Enter registered mobile number", "mandatory": True,  "max": 10},
    "Registered Email ID":      {"placeholder": "Enter registered email ID",      "mandatory": True,  "max": 225},
    "PAN Number":               {"placeholder": "Enter PAN number",               "mandatory": True,  "max": 10},
    "GST Number":               {"placeholder": "Enter GST number",               "mandatory": False, "max": 15},
}
MANDATORY_FIELDS = [label for label, f in FIELDS.items() if f["mandatory"]]
# Clearing Registered Mobile Number puts the profile mobile back, so it never shows "Field is required"
SELF_RESTORING_FIELDS = ["Registered Mobile Number"]
# Organisation name, mobile and email come prefilled from the merchant profile
PREFILLED_FIELDS = ["Organisation Name", "Registered Mobile Number", "Registered Email ID"]

MSG_REQUIRED = "Field is required"

# (field, value, expected message, id). Values for the field under test only; others stay as they are.
INVALID_INPUTS = [
    ("Organisation Name", " ", "Min 3 characters is required", "org-blank-space"),
    ("Bank Account Number", "123", "Min 9 characters is required", "acc-too-short"),
    ("Confirm Account No", "999999999", "Confirm Account No does not match.", "confirm-acc-mismatch"),
    ("IFSC Code", "IDFB1234", "Min 11 characters is required", "ifsc-too-short"),
    ("IFSC Code", "IDFB1X40101", "Invalid IFSC Code", "ifsc-5th-char-not-0"),
    ("Registered Mobile Number", "12345", "Min 10 characters is required", "mobile-too-short"),
    ("Registered Mobile Number", "1234567890", "Invalid Registered Mobile Number", "mobile-bad-start-digit"),
    ("Registered Mobile Number", "abcdefghij", "Invalid Registered Mobile Number", "mobile-letters"),
    ("Registered Email ID", "bad.email", "Invalid Registered Email ID", "email-no-at"),
    ("PAN Number", "ABCDE1234", "Min 10 characters is required", "pan-too-short"),
    ("PAN Number", "12345ABCDE", "Invalid PAN Number", "pan-wrong-pattern"),
    ("PAN Number", "ABCDE1234F", "Invalid PAN Number", "pan-4th-char-not-holder-type"),
    ("GST Number", "22AAAAA0000", "Min 15 characters is required", "gst-too-short"),
    ("GST Number", "ZZZZZZZZZZZZZZZ", "Invalid GST Number", "gst-wrong-pattern"),
]

# (field, typed value, value kept by the field, id): maxlength truncation and auto-uppercase
INPUT_TRANSFORMS = [
    ("Bank Account Number", "1234567890123456789012", "123456789012345678", "acc-max-18"),
    ("IFSC Code", "idfb0040101", "IDFB0040101", "ifsc-uppercased"),
    ("PAN Number", "abcpe1234f", "ABCPE1234F", "pan-uppercased"),
    ("Registered Mobile Number", "98765432109", "9876543210", "mobile-max-10"),
]

GST_PAN_MISMATCH = "Correct PAN number should exist in your GST number."


def account_number():
    """12-digit account number, unique per run."""
    return "5" + str(int(time.time() * 1000))[-11:]


def valid_pan():
    """Valid PAN pattern: 3 letters + holder type (C = company) + letter + 4 digits + letter."""
    letters = string.ascii_uppercase
    return ("".join(random.choices(letters, k=3)) + "C" + random.choice(letters)
            + "".join(random.choices(string.digits, k=4)) + random.choice(letters))


def gst_for(pan, state_code="27"):
    """A GST number that contains the given PAN (the portal requires it)."""
    return f"{state_code}{pan}1Z5"


def bank_details(bank_key, with_gst=False):
    """Valid Step 3 values for BANKS[bank_key]. Organisation, mobile and email are left to the prefill."""
    acc, pan = account_number(), valid_pan()
    data = {"Bank Account Number": acc, "Confirm Account No": acc,
            "IFSC Code": BANKS[bank_key]["ifsc"], "PAN Number": pan}
    if with_gst:
        data["GST Number"] = gst_for(pan)
    return data
