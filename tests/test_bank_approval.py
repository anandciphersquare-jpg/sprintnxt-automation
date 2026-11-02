"""API key > Add Bank > admin accepts it in New Bank Requests > merchant dashboard.
Each run creates a real bank request on UAT (one per bank)."""
import re

import pytest

from pages.add_bank_page import AddBankPage
from pages.admin_page import BANK_APPROVAL_DETAILS, AdminPage, open_admin_window
from pages.api_access_page import ApiAccessPage
from reporting import report, tc
from utils.bank_data import BANKS, bank_details

pytestmark = [pytest.mark.bank_approval]


@pytest.mark.positive
@pytest.mark.parametrize("bank_key", list(BANKS))
@tc("BANK-E2E-001", "Add bank, admin accepts it, merchant back on dashboard", module="Add Bank",
    feature="Bank approval", types=["End-to-End", "Functional"],
    preconditions=["Activated merchant (.merchant.json or SNXT_MERCHANT_*)", "Admin credentials in .env",
                   "IDFC: all services work; HDFC: Payout only"],
    expected="Bank added (Pending Review), admin views and accepts it, merchant dashboard opens")
def test_add_bank_and_approve(logged_in_page, browser, browser_context_args, config, bank_key):
    page, spec = logged_in_page, BANKS[bank_key]

    # 1) API key first (Profile & Settings > API Access Control)
    ApiAccessPage(page, config).open().ensure_key()

    # 2) Add the bank
    data = bank_details(bank_key)
    acc = data["Bank Account Number"]
    report.data("bank", spec["name"])
    report.data("services", spec["services"])
    report.data("account number", acc)
    bank = AddBankPage(page, config).open()
    bank.select_bank(spec["name"]).choose_services(spec["services"]).continue_to_details()
    partner = bank.value("Organisation Name")
    bank.fill_details(data).submit()
    assert bank.is_added(), "No 'Bank Successfully Added!' page"
    summary = bank.summary_text()
    assert "Pending Review" in summary and acc in summary
    for service in spec["expect_services"]:
        assert service in summary, f"{service} missing from the summary"
    report.screenshot("Merchant: bank added, pending review", page)

    # 3) Admin: New Bank Requests > search partner > View > fill details > Accept
    with open_admin_window(browser, browser_context_args, config) as admin_page:
        admin = AdminPage(admin_page, config).open_login().login()
        admin.open_bank_requests().search_bank_requests(partner).view_bank_request(partner, acc)
        assert admin.request_value("Account Number") == acc
        report.data("approval details", {k: v for k, v in BANK_APPROVAL_DETAILS.items() if v})
        admin.fill_bank_approval()
        report.screenshot("Admin: bank request filled", admin_page)
        report.data("accept result", admin.accept_bank_request())
        report.screenshot("Admin: bank request accepted", admin_page)

    # 4) Merchant is still logged in: back to the dashboard
    page.bring_to_front()
    page.goto(config.base_url.rstrip("/") + "/#/dashboard")
    page.wait_for_url(re.compile(r"#/dashboard"))
    assert "/auth/" not in page.url, "Merchant session was lost"
    report.data("dashboard still asks to add a bank",
                page.get_by_role("button", name=re.compile(r"Add Bank Account")).is_visible())
    report.screenshot("Merchant: dashboard after approval", page)
