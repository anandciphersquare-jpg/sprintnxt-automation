import pytest

from pages.registration_page import RegistrationPage
from utils.data_factory import valid_password
from utils.payloads import SQLI_PAYLOADS, XSS_PAYLOADS, SQL_ERROR_SIGNS

pytestmark = [pytest.mark.registration, pytest.mark.security]

# Email and mobile are deliberately left empty: the portal sends an OTP as soon as a valid
# email/mobile is typed, and these 14 tests would otherwise trip the UAT send-otp rate limit.


@pytest.fixture
def reg(page, config):
    return RegistrationPage(page, config).open()


@pytest.mark.parametrize("payload", SQLI_PAYLOADS)
def test_sqli_in_name_fields(reg, payload):
    reg.fill_basic(payload, payload, payload)
    reg.fill_passwords(valid_password())
    reg.submit()
    body = reg.page_text()
    assert not any(sign in body for sign in SQL_ERROR_SIGNS), \
        f"Possible SQL error surfaced for payload: {payload!r}"


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_in_name_fields(reg, page, payload):
    fired = {"alert": False}
    page.on("dialog", lambda d: (fired.__setitem__("alert", True), d.dismiss()))
    reg.fill_basic(payload, "QA", "QA Corp")
    reg.fill_passwords(valid_password())
    reg.submit()
    page.wait_for_timeout(1000)
    assert not fired["alert"], f"XSS executed (alert fired) for payload: {payload!r}"
