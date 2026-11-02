import pytest

from pages.registration_page import RegistrationPage
from reporting import report, tc
from utils.data_factory import (
    unique_email, valid_mobile, valid_password, valid_person,
    INVALID_EMAILS, INVALID_MOBILES, INVALID_PASSWORDS,
)

pytestmark = [pytest.mark.registration]

SIGNUP_OPEN = "Signup page is open"
UAT_OTP = "UAT OTP is fixed to SNXT_OTP (default 123456)"
NEG_WAIT_MS = 4000  # negative tests: how long to make sure the success page does NOT appear


@pytest.fixture
def reg(page, config):
    return RegistrationPage(page, config).open()


# ---------------------------- POSITIVE ----------------------------

@pytest.mark.positive
@pytest.mark.smoke
@tc("REG-001", "Register a new merchant with valid details", feature="Merchant signup",
    types=["Functional", "Smoke"], preconditions=[SIGNUP_OPEN, UAT_OTP],
    expected="Email and mobile verify via OTP and the 'Registration Successful' page is shown")
def test_register_happy_path(reg):
    p = valid_person()
    report.data("person", p)
    reg.register(p["first_name"], p["last_name"], p["business_name"],
                 unique_email(), valid_mobile(), valid_password())
    assert reg.is_registration_success(), "Expected the 'Registration Successful' page"


# ---------------------------- NEGATIVE ----------------------------

@pytest.mark.negative
@tc("REG-002", "Empty form cannot be submitted", feature="Form validation",
    types=["Negative", "Validation"], preconditions=[SIGNUP_OPEN],
    expected="Sign Up is disabled (or required-field errors are shown) and nothing is submitted")
def test_required_fields_block_submit(reg):
    reg.submit()
    assert not reg.is_registration_success(timeout=NEG_WAIT_MS)
    assert not reg.signup_enabled() or reg.has_validation_error(), \
        "Empty form: Sign Up is enabled and no validation error is shown"


@pytest.mark.negative
@pytest.mark.parametrize("email,reason", INVALID_EMAILS, ids=[r for _, r in INVALID_EMAILS])
@tc("REG-003", "Invalid email format is rejected", feature="Email validation",
    types=["Negative", "Validation", "Boundary"], preconditions=[SIGNUP_OPEN],
    expected="Email is not verified and registration does not complete")
def test_invalid_email_rejected(reg, email, reason):
    p = valid_person()
    reg.fill_basic(p["first_name"], p["last_name"], p["business_name"])
    reg.fill_email(email)
    reg.submit()
    assert not reg.email_verified_safe(), f"Invalid email treated as verified: {reason}"
    assert not reg.is_registration_success(timeout=NEG_WAIT_MS)


@pytest.mark.negative
@pytest.mark.parametrize("mobile,reason", INVALID_MOBILES, ids=[r for _, r in INVALID_MOBILES])
@tc("REG-004", "Invalid mobile number is rejected", feature="Mobile validation",
    types=["Negative", "Validation", "Boundary"], preconditions=[SIGNUP_OPEN],
    expected="Registration does not complete")
def test_invalid_mobile_rejected(reg, mobile, reason):
    p = valid_person()
    reg.fill_basic(p["first_name"], p["last_name"], p["business_name"])
    reg.fill_mobile(mobile)
    reg.submit()
    assert not reg.is_registration_success(timeout=NEG_WAIT_MS), f"Invalid mobile accepted: {reason}"


@pytest.mark.negative
@pytest.mark.parametrize("pw,reason", INVALID_PASSWORDS, ids=[r for _, r in INVALID_PASSWORDS])
@tc("REG-005", "Password violating the policy is rejected", feature="Password policy",
    types=["Negative", "Validation", "Boundary"], preconditions=[SIGNUP_OPEN],
    expected="Registration does not complete (policy: 12-15 chars, upper, lower, digit, special)")
def test_invalid_password_rejected(reg, pw, reason):
    p = valid_person()
    reg.fill_basic(p["first_name"], p["last_name"], p["business_name"])
    reg.fill_passwords(pw, pw)
    reg.submit()
    assert not reg.is_registration_success(timeout=NEG_WAIT_MS), f"Weak password accepted: {reason}"


@pytest.mark.negative
@tc("REG-006", "Password and confirm password must match", feature="Password policy",
    types=["Negative", "Validation"], preconditions=[SIGNUP_OPEN],
    expected="A mismatch error is shown and registration does not complete")
def test_password_mismatch(reg):
    p = valid_person()
    reg.fill_basic(p["first_name"], p["last_name"], p["business_name"])
    reg.fill_passwords(valid_password(), valid_password() + "X")
    reg.submit()
    assert not reg.is_registration_success(timeout=NEG_WAIT_MS)
    assert reg.has_validation_error()


@pytest.mark.negative
@tc("REG-007", "Wrong email OTP does not verify the email", feature="Email OTP",
    types=["Negative", "Security"], preconditions=[SIGNUP_OPEN, UAT_OTP],
    expected="Email stays unverified after entering 000000")
def test_wrong_email_otp_does_not_verify(reg):
    reg.require_otp_available()
    p = valid_person()
    reg.fill_basic(p["first_name"], p["last_name"], p["business_name"])
    reg.fill_email(unique_email())
    reg.verify_email_otp(code="000000")  # valid UAT OTP is 123456
    assert not reg.email_verified_safe(), "A wrong OTP must not verify the email"


@pytest.mark.negative
@tc("REG-008", "Already-registered email cannot register again", feature="Duplicate detection",
    types=["Negative", "Functional"], preconditions=[SIGNUP_OPEN, UAT_OTP],
    expected="Second registration with the same email is blocked")
def test_duplicate_email(reg, page, config):
    p = valid_person()
    email = unique_email()
    report.data("email", email)
    reg.register(p["first_name"], p["last_name"], p["business_name"],
                 email, valid_mobile(), valid_password())
    assert reg.is_registration_success()

    reg2 = RegistrationPage(page, config).open()
    reg2.fill_basic(p["first_name"], p["last_name"], p["business_name"])
    reg2.fill_email(email)
    reg2.submit()
    body = reg2.page_text()
    assert ("already" in body or "exist" in body or not reg2.is_registration_success()), \
        "Re-using an existing email should be blocked"
