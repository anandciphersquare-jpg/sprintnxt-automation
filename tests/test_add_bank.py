"""Add Bank form: bank list, service selection, mandatory fields and validation. Nothing is submitted
(every form here is invalid or reset), so these tests create no bank requests."""
import pytest

from pages.add_bank_page import AddBankPage
from pages.login_page import LoginPage
from reporting import block, current, report, tc
from utils.bank_data import (BANKS, FIELDS, GST_PAN_MISMATCH, INPUT_TRANSFORMS, INVALID_INPUTS,
                             MANDATORY_FIELDS, MSG_REQUIRED, PREFILLED_FIELDS, SELF_RESTORING_FIELDS, SERVICE_CARDS,
                             account_number, gst_for, valid_pan)
from utils.merchant_store import load_merchant

pytestmark = [pytest.mark.add_bank]

MODULE = "Add Bank"
LOGGED_IN = "Activated merchant is logged in"
ON_FORM = "Add Bank > IDFC First Bank > Payout > Fill Details is open"
IDFC, HDFC = BANKS["IDFC"]["name"], BANKS["HDFC"]["name"]


@pytest.fixture(scope="module")
def page(browser, config):
    """One logged-in merchant page for the whole module. The session lives in sessionStorage, so it can't
    be reused through storage_state, and logging in for every test would send an OTP each time."""
    creds = ({"email": config.merchant_email, "password": config.merchant_pass}
             if config.merchant_email and config.merchant_pass else load_merchant())
    if not creds:
        block("No activated merchant: run E2E-001 first, or set SNXT_MERCHANT_EMAIL/PASS in .env")
    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900},
                              geolocation={"latitude": 28.6139, "longitude": 77.2090}, permissions=["geolocation"])
    pg = ctx.new_page()
    pg.set_default_timeout(config.default_timeout_ms)
    login = LoginPage(pg, config).open()
    login.login(creds["email"], creds["password"])
    if login.complete_login() is not True:
        ctx.close()
        block(f"Merchant {creds['email']} could not reach the dashboard (url: {pg.url})")
    pg.merchant = creds
    yield pg
    ctx.close()


@pytest.fixture(autouse=True)
def _watch(page):
    """Hook the shared page into this test's report (failure screenshot, console, API calls)."""
    if (collector := current()) is not None:
        collector.watch_context(page.context)


@pytest.fixture
def bank(page, config):
    return AddBankPage(page, config).open()


@pytest.fixture
def form(bank):
    return bank.select_bank(IDFC).choose_services(["Payout"]).continue_to_details()


# ---------------------------------------------------------------- step 1: select bank
@pytest.mark.smoke
@tc("BANK-001", "Working banks are listed", module=MODULE, feature="Select bank",
    types=["Functional", "Smoke"], preconditions=[LOGGED_IN], expected="IDFC First Bank and HDFC Bank are listed")
def test_working_banks_listed(bank):
    assert bank.is_bank_listed(IDFC), "IDFC First Bank missing"
    assert bank.is_bank_listed(HDFC), "HDFC Bank missing"


@tc("BANK-002", "Bank search filters the list", module=MODULE, feature="Select bank",
    types=["Functional"], preconditions=[LOGGED_IN], expected="Searching 'HDFC' shows HDFC Bank and hides IDFC")
def test_bank_search(bank):
    bank.search("HDFC")
    assert bank.is_bank_listed(HDFC)
    assert not bank.is_bank_listed(IDFC), "IDFC still visible after searching HDFC"


# ---------------------------------------------------------------- step 2: services
@tc("BANK-003", "Service types are offered", module=MODULE, feature="Choose services",
    types=["Functional"], preconditions=[LOGGED_IN], expected="Payout, UPI Collection, VID Collection, All Services")
def test_service_cards(bank):
    bank.select_bank(IDFC)
    assert bank.service_cards() == SERVICE_CARDS


@pytest.mark.negative
@tc("BANK-004", "Continue needs at least one service", module=MODULE, feature="Choose services",
    types=["Negative", "Validation"], preconditions=[LOGGED_IN], expected="Continue stays disabled")
def test_continue_disabled_without_service(bank):
    bank.select_bank(IDFC)
    assert not bank.is_continue_enabled(), "Continue enabled with no service selected"


@pytest.mark.positive
@tc("BANK-005", "HDFC: Payout can be chosen", module=MODULE, feature="Choose services",
    types=["Functional"], preconditions=[LOGGED_IN, "On UAT only Payout works for HDFC"],
    expected="Selecting Payout enables Continue and opens Fill Details")
def test_hdfc_payout(bank):
    bank.select_bank(HDFC).choose_services(["Payout"])
    assert bank.is_continue_enabled()
    bank.continue_to_details()


# ---------------------------------------------------------------- step 3: details
@tc("BANK-006", "Profile details are prefilled", module=MODULE, feature="Fill details",
    types=["Functional"], preconditions=[ON_FORM],
    expected="Organisation name, registered mobile and email come from the merchant profile")
def test_prefilled(form, page):
    for label in PREFILLED_FIELDS:
        assert form.value(label), f"{label} is not prefilled"
    assert form.value("Registered Email ID") == page.merchant["email"]


@pytest.mark.negative
@pytest.mark.parametrize("label", [f for f in MANDATORY_FIELDS if f not in SELF_RESTORING_FIELDS])
@tc("BANK-007", "Mandatory field cannot be empty", module=MODULE, feature="Mandatory fields",
    types=["Negative", "Validation"], preconditions=[ON_FORM], expected=f"'{MSG_REQUIRED}' under the field")
def test_mandatory(form, label):
    form.clear(label).submit()
    assert MSG_REQUIRED in form.field_error(label), f"{label}: got '{form.field_error(label)}'"


@pytest.mark.negative
@pytest.mark.parametrize("label", SELF_RESTORING_FIELDS)
@tc("BANK-016", "Registered mobile cannot be left empty", module=MODULE, feature="Mandatory fields",
    types=["Negative", "Validation"], preconditions=[ON_FORM],
    expected=f"The profile value comes back, or '{MSG_REQUIRED}' is shown")
def test_mandatory_self_restoring(form, label):
    form.clear(label).submit()
    restored, error = form.value(label), form.field_error(label)
    report.data("value after clearing", restored)
    assert restored or MSG_REQUIRED in error, f"{label} empty and no error"


@pytest.mark.positive
@tc("BANK-008", "GST number is optional", module=MODULE, feature="Mandatory fields",
    types=["Validation"], preconditions=[ON_FORM], expected="No error under GST Number when it is empty")
def test_gst_optional(form):
    form.clear("GST Number").submit()
    assert form.field_error("GST Number") == ""


@pytest.mark.negative
@pytest.mark.parametrize("label,value,message", [c[:3] for c in INVALID_INPUTS], ids=[c[3] for c in INVALID_INPUTS])
@tc("BANK-009", "Invalid value shows its error", module=MODULE, feature="Field validation",
    types=["Negative", "Validation"], preconditions=[ON_FORM], expected="The field's validation message")
def test_invalid_input(form, label, value, message):
    if label == "Confirm Account No":
        form.fill_details({"Bank Account Number": account_number()})
    form.fill_details({label: value}).submit()
    assert message in form.field_error(label), f"{label}='{value}': got '{form.field_error(label)}'"


@pytest.mark.parametrize("label,typed,kept", [c[:3] for c in INPUT_TRANSFORMS], ids=[c[3] for c in INPUT_TRANSFORMS])
@tc("BANK-010", "Field length limit and upper-casing", module=MODULE, feature="Field validation",
    types=["Validation", "Boundary"], preconditions=[ON_FORM], expected="Field keeps the trimmed / upper-cased value")
def test_input_transform(form, label, typed, kept):
    form.fill_details({label: typed})
    assert form.value(label) == kept
    assert len(form.value(label)) <= FIELDS[label]["max"]


@pytest.mark.negative
@tc("BANK-011", "GST number must contain the PAN", module=MODULE, feature="Field validation",
    types=["Negative", "Validation"], preconditions=[ON_FORM], expected=GST_PAN_MISMATCH)
def test_gst_must_contain_pan(form):
    form.fill_details({"PAN Number": valid_pan(), "GST Number": gst_for(valid_pan())}).submit()
    assert GST_PAN_MISMATCH in form.field_error("GST Number")


@pytest.mark.negative
@tc("BANK-012", "Account number rejects letters", module=MODULE, feature="Field validation",
    types=["Negative", "Validation"], preconditions=[ON_FORM],
    expected="An error under Bank Account Number (UAT 2026-10-16: 'abcdefghij' was accepted)")
def test_account_number_letters(form):
    form.fill_details({"Bank Account Number": "abcdefghij"}).submit()
    assert form.field_error("Bank Account Number"), "Letters accepted as an account number"


@pytest.mark.negative
@tc("BANK-013", "Organisation name rejects symbols only", module=MODULE, feature="Field validation",
    types=["Negative", "Validation"], preconditions=[ON_FORM],
    expected="An error under Organisation Name (UAT 2026-10-16: '@@##' was accepted)")
def test_organisation_symbols(form):
    form.fill_details({"Organisation Name": "@@##"}).submit()
    assert form.field_error("Organisation Name"), "'@@##' accepted as organisation name"


@tc("BANK-014", "Reset clears the form", module=MODULE, feature="Fill details",
    types=["Functional"], preconditions=[ON_FORM], expected="Every field is empty after Reset")
def test_reset(form):
    form.fill_details({"Bank Account Number": account_number(), "PAN Number": valid_pan()}).reset()
    assert all(form.value(label) == "" for label in FIELDS), {label: form.value(label) for label in FIELDS}


@tc("BANK-015", "Back returns to service selection", module=MODULE, feature="Fill details",
    types=["Functional"], preconditions=[ON_FORM], expected="Choose Service Types is shown again")
def test_back(form, page):
    page.get_by_role("button", name="Back").last.click()
    page.get_by_text("Choose Service Types").wait_for()
