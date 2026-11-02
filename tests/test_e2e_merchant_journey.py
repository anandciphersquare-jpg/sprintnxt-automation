import re

import pytest

from pages.admin_page import ACTIVATION_REMARKS, AdminPage, open_admin_window
from pages.change_password_page import ChangePasswordPage
from pages.login_page import LoginPage
from pages.registration_page import RegistrationPage
from reporting import report, tc
from utils.data_factory import unique_email, valid_mobile, valid_password, valid_person
from utils.merchant_store import save_merchant, update_password

pytestmark = [pytest.mark.e2e]


@pytest.mark.positive
@tc("E2E-001", "Register -> admin activates -> merchant logs in", feature="Merchant onboarding",
    types=["End-to-End", "Functional"],
    preconditions=["Signup and admin portals reachable", "UAT OTP is 123456", "Admin credentials in .env"],
    expected="Merchant registers, admin activates it from Register Partner with remarks, "
             "and the merchant then logs in to the dashboard")
def test_full_merchant_journey(page, browser, browser_context_args, config):
    person = valid_person()
    email, mobile, password = unique_email(), valid_mobile(), valid_password()
    report.data("merchant email", email)
    report.data("merchant mobile", mobile)
    report.data("activation remarks", ACTIVATION_REMARKS)

    # 1) Merchant registers (merchant window)
    reg = RegistrationPage(page, config).open()
    reg.register(person["first_name"], person["last_name"], person["business_name"],
                 email, mobile, password)
    assert reg.is_registration_success(), "Registration did not reach the success page"
    report.screenshot("Merchant: registration successful", page)

    # 2) Admin activates the new partner in a second window; it closes once activation is done
    with open_admin_window(browser, browser_context_args, config) as admin_page:
        admin = AdminPage(admin_page, config).open_login().login()
        admin.open_register_partner().search_partner(email)
        assert admin.partner_status(email).lower() == "inactive", "New partner should start Inactive"
        admin.activate_partner(email, ACTIVATION_REMARKS)
        assert admin.wait_until_active(email).lower() == "active", "Partner did not become Active"
        report.screenshot("Admin: partner activated", admin_page)
    # Later modules reuse this merchant: no new registration, OTPs or admin step
    save_merchant(email, password, mobile=mobile, business_name=person["business_name"])

    # 3) Merchant logs in (merchant window only from here on)
    page.bring_to_front()
    login = LoginPage(page, config).open()
    login.login(email, password)
    landed = login.complete_login()

    # 4) First login forces "Create New Password"; set it, then log in again with it
    if landed == "change-password":
        report.screenshot("Merchant: Create New Password (first login)", page)
        new_password = valid_password()
        ChangePasswordPage(page, config).create_new_password(new_password)
        update_password(new_password)
        if not re.search(r"dashboard", page.url, re.I):
            login = LoginPage(page, config).open()
            login.login(email, new_password)
            landed = login.complete_login()
    assert landed is True, f"Merchant did not reach the dashboard (url: {page.url})"
    report.screenshot("Merchant: dashboard after login", page)
