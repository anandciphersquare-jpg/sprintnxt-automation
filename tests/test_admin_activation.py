import pytest

from pages.admin_page import AdminPage, open_admin_window
from reporting import block, tc

pytestmark = [pytest.mark.admin]


@pytest.fixture
def admin(browser, browser_context_args, config):
    with open_admin_window(browser, browser_context_args, config) as admin_page:
        yield AdminPage(admin_page, config).open_login().login()


@pytest.mark.smoke
@tc("ADM-001", "Super admin logs in to the admin portal", feature="Admin login",
    types=["Functional", "Smoke"], preconditions=["Admin credentials in .env"],
    expected="Admin lands on the dashboard")
def test_admin_login(admin):
    assert admin.is_logged_in(), f"Still on the auth pages: {admin.page.url}"


@tc("ADM-002", "Register Partner list opens and searches", feature="Partner activation",
    types=["Functional"], preconditions=["Admin logged in"],
    expected="Register Partner grid opens with a search box")
def test_register_partner_list(admin):
    admin.open_register_partner()
    assert admin.page.get_by_placeholder("Search by user details").first.is_visible()


@tc("ADM-003", "Activate a configured merchant", feature="Partner activation",
    types=["Functional"], preconditions=["SNXT_MERCHANT_EMAIL is an Inactive partner"],
    expected="Partner status becomes Active")
def test_activate_merchant(admin, config):
    if not config.merchant_email:
        block("Set SNXT_MERCHANT_EMAIL to the merchant you want to activate (E2E-001 covers a fresh one)")
    admin.open_register_partner().search_partner(config.merchant_email)
    if admin.partner_status(config.merchant_email).lower() != "active":
        admin.activate_partner(config.merchant_email)
    assert admin.wait_until_active(config.merchant_email).lower() == "active"
