import re

import pytest

from pages.login_page import LoginPage
from reporting import block, tc
from utils.data_factory import unique_email, INVALID_EMAILS

pytestmark = [pytest.mark.login]

LOGIN_OPEN = "Login page is open"


@pytest.fixture
def login(page, config):
    return LoginPage(page, config).open()


@pytest.mark.positive
@pytest.mark.smoke
@tc("LOGIN-001", "Activated merchant logs in with valid credentials", feature="Merchant login",
    types=["Functional", "Smoke"], preconditions=[LOGIN_OPEN, "Seeded merchant is activated"],
    expected="Merchant lands on the dashboard")
def test_login_valid(login, config):
    if not (config.merchant_email and config.merchant_pass):
        block("Set SNXT_MERCHANT_EMAIL and SNXT_MERCHANT_PASS for the positive login test")
    login.login(config.merchant_email, config.merchant_pass)
    login.page.wait_for_load_state("networkidle")
    assert re.search(r"dashboard", login.page.url, re.I) or "dashboard" in login.page_text()


@pytest.mark.negative
@tc("LOGIN-002", "Wrong password is rejected", feature="Merchant login",
    types=["Negative", "Security"], preconditions=[LOGIN_OPEN], expected="User stays off the dashboard")
def test_login_wrong_password(login, config):
    email = config.merchant_email or unique_email()
    login.login(email, "WrongPass@123")
    assert not re.search(r"dashboard", login.page.url, re.I)


@pytest.mark.negative
@tc("LOGIN-003", "Unregistered email is rejected", feature="Merchant login",
    types=["Negative", "Security"], preconditions=[LOGIN_OPEN], expected="User stays off the dashboard")
def test_login_unregistered_email(login):
    login.login(unique_email(), "Whatever@123")
    assert not re.search(r"dashboard", login.page.url, re.I)


@pytest.mark.negative
@pytest.mark.parametrize("email,reason", INVALID_EMAILS, ids=[r for _, r in INVALID_EMAILS])
@tc("LOGIN-004", "Malformed email cannot log in", feature="Input validation",
    types=["Negative", "Validation"], preconditions=[LOGIN_OPEN], expected="User stays off the dashboard")
def test_login_invalid_email_format(login, email, reason):
    login.login(email, "Whatever@123")
    assert not re.search(r"dashboard", login.page.url, re.I)


@pytest.mark.negative
@tc("LOGIN-005", "Empty login form cannot be submitted", feature="Input validation",
    types=["Negative", "Validation"], preconditions=[LOGIN_OPEN], expected="User stays off the dashboard")
def test_login_empty(login):
    login.submit()
    assert not re.search(r"dashboard", login.page.url, re.I)
