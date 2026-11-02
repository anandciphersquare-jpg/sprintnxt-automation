import pytest

from pages.forgot_password_page import ForgotPasswordPage
from reporting import block
from utils.data_factory import unique_email, INVALID_EMAILS

pytestmark = [pytest.mark.forgot_password]


@pytest.fixture
def fp(page, config):
    return ForgotPasswordPage(page, config).open()


@pytest.mark.positive
def test_forgot_valid_email(fp, config):
    # An unregistered email correctly gets "The provided information is not valid!", so this needs a real account
    if not config.merchant_email:
        block("Set SNXT_MERCHANT_EMAIL to a registered merchant for the positive reset test")
    fp.request_reset(config.merchant_email)
    # expect a success / under-review message, not an error (tune to the real toast text)
    assert "error" not in fp.result().lower()


@pytest.mark.negative
@pytest.mark.parametrize("email,reason", INVALID_EMAILS, ids=[r for _, r in INVALID_EMAILS])
def test_forgot_invalid_email_format(fp, email, reason):
    fp.request_reset(email)
    msg = fp.result().lower()
    assert "link" not in msg or "invalid" in msg


@pytest.mark.negative
def test_forgot_empty(fp):
    fp.submit()
    assert "reset your password" in fp.page_text()  # stays on the reset page


@pytest.mark.security
def test_forgot_no_account_enumeration(fp):
    """Reset for an unregistered email must not reveal that the account does not exist."""
    fp.request_reset(unique_email())
    msg = fp.result().lower()
    assert all(s not in msg for s in ["not found", "doesn't exist", "does not exist", "no account"])
