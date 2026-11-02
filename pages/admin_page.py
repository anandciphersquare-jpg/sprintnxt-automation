import os
import re
from contextlib import contextmanager

from dotenv import load_dotenv

from pages.base_page import BasePage
from reporting import block, current, step

load_dotenv()

# Admin settings live here (credentials stay in .env: SNXT_ADMIN_USER / SNXT_ADMIN_PASS)
ADMIN_URL = os.getenv("SNXT_ADMIN_URL") or "https://uat.sprintnxt.in/NexGenAdminFront/#/auth/login"
ADMIN_OTP = os.getenv("SNXT_ADMIN_OTP", "123456")
ACTIVATION_REMARKS = os.getenv("SNXT_ACTIVATION_REMARKS", "Activated by QA automation")

# Business Banking > New Bank Requests (#/cib) > View (#/cib/cib-details/<id>): fields the admin fills
# before Accept. Label -> value; empty values are left untouched. Override with SNXT_BANK_<FIELD>.
BANK_REQUESTS_URL = ADMIN_URL.split("#")[0] + "#/cib"
BANK_APPROVAL_DETAILS = {
    label: os.getenv("SNXT_BANK_" + re.sub(r"\W+", "_", label).upper(), "")
    for label in ("VID Prefix", "VID IFSC", "Profile Id", "VPA Id", "SUB VPA", "QR Type", "BC Id", "Passcode")
}


@contextmanager
def open_admin_window(browser, browser_context_args, config):
    """A second window with its own context (sessions don't mix) for the admin portal, next to the merchant page."""
    if not (config.admin_user and config.admin_pass):
        block("Set SNXT_ADMIN_USER and SNXT_ADMIN_PASS in .env for admin tests")
    args = {k: v for k, v in browser_context_args.items() if k not in ("record_video_dir", "record_video_size")}
    ctx = browser.new_context(**args)
    if (collector := current()) is not None:
        collector.watch_context(ctx)  # admin console/network/API logs + screenshots in the report
    page = ctx.new_page()
    page.set_default_timeout(config.default_timeout_ms)
    try:
        yield page
    finally:
        ctx.close()


class AdminPage(BasePage):
    """
    Nex-Gen Admin Portal (SNXT_ADMIN_URL, default .../NexGenAdminFront/#/auth/login).

    Activation flow: Business Partner Details > Register Partner (#/partner/partner-list) >
    "Search by user details" > Search > click the row's Status switch > SweetAlert
    "You want to activate this partner" > remarks > "Yes, update it!".
    """

    @step("Open the admin login")
    def open_login(self):
        self.page.goto(ADMIN_URL)
        return self

    # ---------- login ----------
    def _otp_boxes(self):
        return self.page.locator("input[maxlength='1']:visible")

    @step("Log in to the admin panel")
    def login(self, user=None, password=None):
        user = user or self.config.admin_user
        password = password or self.config.admin_pass
        self.page.locator("input[type='email']").fill(user)
        self.page.locator("input[type='password']").fill(password)
        self.click_if_enabled(self.page.get_by_role("button", name=re.compile(r"sign\s*in", re.I)))
        self._enter_otp_if_asked()
        self.page.wait_for_url(re.compile(r"#/(dashboard|main-menu)"), timeout=30000)
        return self

    def _enter_otp_if_asked(self):
        """Admin 2FA is optional (auth/2fa/status); enter SNXT_ADMIN_OTP only when the OTP screen appears."""
        try:
            self.page.wait_for_function(
                "() => location.hash.includes('dashboard') || "
                "document.querySelectorAll(\"input[maxlength='1']\").length >= 6", timeout=20000)
        except Exception:
            return
        boxes = self._otp_boxes()
        if boxes.count() < 6:
            return
        for i, ch in enumerate(ADMIN_OTP):
            boxes.nth(i).fill(ch)
        self.click_if_enabled(
            self.page.get_by_role("button", name=re.compile(r"verify|submit|continue|sign\s*in", re.I)).last)

    def is_logged_in(self):
        return "/auth/" not in self.page.url

    # ---------- Register Partner ----------
    @step("Open Register Partner")
    def open_register_partner(self):
        self.page.get_by_role("link", name=re.compile(r"register partner", re.I)).click()
        self.page.wait_for_url(re.compile(r"#/partner/partner-list"))
        return self

    def _row(self, email):
        return self.page.get_by_role("row").filter(has_text=email).first

    @step("Search partner '{email}'")
    def search_partner(self, email):
        self.page.get_by_placeholder(re.compile(r"search by user", re.I)).fill(email)
        self.page.get_by_role("button", name=re.compile(r"^\s*search\s*$", re.I)).click()
        self._row(email).wait_for(timeout=20000)
        return self

    def partner_status(self, email):
        return self._row(email).locator(".status-pill").inner_text().strip()

    @step("Activate partner '{email}' with remarks '{remarks}'")
    def activate_partner(self, email, remarks=ACTIVATION_REMARKS):
        self._row(email).locator("label.status-switch").click()
        dialog = self.page.locator(".swal2-popup")
        dialog.wait_for()
        dialog.locator("#swal2-input").fill(remarks)
        dialog.get_by_role("button", name=re.compile(r"yes", re.I)).click()
        # A second SweetAlert (success icon) follows; it stays until OK is clicked
        result = self.page.locator(".swal2-popup.swal2-show:is(.swal2-icon-success, .swal2-icon-error)")
        result.wait_for(timeout=20000)
        message = result.inner_text().strip()
        result.locator(".swal2-confirm").click()
        result.wait_for(state="hidden", timeout=10000)
        assert "error" not in message.lower(), f"Activation failed: {message}"
        return self

    # ---------- New Bank Requests ----------
    @step("Open New Bank Requests")
    def open_bank_requests(self):
        self.page.goto(BANK_REQUESTS_URL)
        self.page.get_by_role("combobox", name=re.compile(r"Name, firm name", re.I)).wait_for()
        return self

    @step("Search bank requests of partner '{partner}'")
    def search_bank_requests(self, partner):
        """Search User is an autocomplete: type, pick the suggestion, then Search."""
        box = self.page.get_by_role("combobox", name=re.compile(r"Name, firm name", re.I))
        box.press_sequentially(partner, delay=80)
        self.page.locator("ng-autocomplete li").filter(has_text=re.compile(re.escape(partner), re.I)).first.click()
        self.page.get_by_role("button", name=re.compile(r"search", re.I)).last.click()
        self.page.get_by_role("row").filter(has_text=partner).first.wait_for(timeout=20000)
        return self

    def bank_request_row(self, partner, account_no):
        return self.page.get_by_role("row").filter(has_text=partner).filter(has_text=account_no).first

    @step("View bank request {account_no}")
    def view_bank_request(self, partner, account_no):
        self.bank_request_row(partner, account_no).locator("td").last.locator("button, a, i, span").first.click()
        self.page.get_by_text(re.compile(r"^\s*View\s*$")).first.click()
        self.page.wait_for_url(re.compile(r"#/cib/cib-details/\d+"))
        self.page.get_by_role("button", name=re.compile(r"^\s*Accept\s*$")).wait_for()
        return self

    def _detail_field(self, label):
        return self.page.locator(
            f"xpath=//label[normalize-space()='{label}']/following::*[self::input or self::select][1]")

    def request_value(self, label):
        return self._detail_field(label).input_value()

    @step("Fill approval details")
    def fill_bank_approval(self, details=None):
        for label, val in (details or BANK_APPROVAL_DETAILS).items():
            if not val:
                continue
            field = self._detail_field(label)
            if field.evaluate("e => e.tagName") == "SELECT":
                field.select_option(label=val)
            else:
                field.fill(val)
        return self

    @step("Accept the bank request")
    def accept_bank_request(self):
        self.page.get_by_role("button", name=re.compile(r"^\s*Accept\s*$")).click()
        # SweetAlert: an optional confirm first, then the result popup that stays until OK
        popup = self.page.locator(".swal2-popup.swal2-show")
        popup.wait_for(timeout=20000)
        if not popup.locator(".swal2-icon-success, .swal2-icon-error").count() and \
                not re.search(r"success|error|fail", popup.inner_text(), re.I):
            popup.locator(".swal2-confirm").click()
            popup = self.page.locator(".swal2-popup.swal2-show:is(.swal2-icon-success, .swal2-icon-error)")
            popup.wait_for(timeout=20000)
        message = popup.inner_text().strip()
        if popup.locator(".swal2-confirm").is_visible():
            popup.locator(".swal2-confirm").click()
        assert not re.search(r"error|fail", message, re.I), f"Accept failed: {message}"
        return message

    @step("Wait for partner '{email}' to show Active")
    def wait_until_active(self, email, timeout=20000):
        pill = self._row(email).locator(".status-pill")
        try:
            pill.filter(has_text=re.compile(r"^\s*active\s*$", re.I)).wait_for(timeout=timeout)
        except Exception:
            # Grid may not refresh by itself after the update; search again
            self.search_partner(email)
            pill.filter(has_text=re.compile(r"^\s*active\s*$", re.I)).wait_for(timeout=timeout)
        return self.partner_status(email)
