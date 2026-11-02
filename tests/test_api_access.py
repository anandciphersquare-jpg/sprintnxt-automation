import pytest

from pages.api_access_page import ApiAccessPage
from reporting import report, tc

pytestmark = [pytest.mark.api_access]

MODULE = "API Access"


@tc("API-001", "API Access Control opens from Profile & Settings", module=MODULE, feature="API keys",
    types=["Functional"], preconditions=["Activated merchant is logged in"],
    expected="API Credentials, Authorized IPs and the webhook / 2FA tabs are shown")
def test_api_access_tabs(logged_in_page, config):
    tabs = ApiAccessPage(logged_in_page, config).open().tabs()
    assert tabs == ["API Credentials", "Authorized IPs", "PayIn Webhook Endpoint",
                    "PayOut Webhook Endpoint", "Payout 2FA Endpoint"], tabs


@pytest.mark.smoke
@tc("API-002", "Merchant has an active API key", module=MODULE, feature="API keys",
    types=["Functional", "Smoke"], preconditions=["Activated merchant is logged in", "API key OTP is 1234 on UAT"],
    expected="An Active key is listed (generated with the OTP if there was none)")
def test_api_key_active(logged_in_page, config):
    api = ApiAccessPage(logged_in_page, config).open().ensure_key()
    report.data("active keys", api.active_keys().count())
    assert api.has_active_key()
