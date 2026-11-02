import pytest

from pages.change_password_page import ChangePasswordPage
from utils.data_factory import valid_password, INVALID_PASSWORDS

pytestmark = [pytest.mark.change_password]


@pytest.fixture
def cp(logged_in_page, config):
    return ChangePasswordPage(logged_in_page, config).open()


@pytest.mark.positive
def test_change_password_valid_roundtrip(cp, logged_in_page, config):
    """Change to a new password, then change back so seeded creds stay valid."""
    new_pw = valid_password()
    cp.change(config.merchant_pass, new_pw)
    cp.page.wait_for_timeout(1500)
    # revert
    cp2 = ChangePasswordPage(logged_in_page, config).open()
    cp2.change(new_pw, config.merchant_pass)
    cp2.page.wait_for_timeout(1000)


@pytest.mark.negative
def test_wrong_current_password(cp, config):
    cp.change("WrongCurrent@123", valid_password())
    assert "success" not in cp.result().lower()


@pytest.mark.negative
@pytest.mark.parametrize("pw,reason", INVALID_PASSWORDS, ids=[r for _, r in INVALID_PASSWORDS])
def test_invalid_new_password(cp, config, pw, reason):
    cp.change(config.merchant_pass, pw, pw)
    assert "success" not in cp.result().lower(), f"Weak new password accepted: {reason}"


@pytest.mark.negative
def test_new_confirm_mismatch(cp, config):
    cp.change(config.merchant_pass, valid_password(), valid_password() + "X")
    assert "success" not in cp.result().lower()
