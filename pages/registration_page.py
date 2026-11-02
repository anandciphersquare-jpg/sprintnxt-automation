import re

from pages.base_page import BasePage
from reporting import block, step

# Set for the rest of the session once UAT answers send-otp with HTTP 429, so later OTP tests
# stop as BLOCKED instead of sending more OTPs and extending the network block.
_otp_rate_limited = {"url": None}


class RegistrationPage(BasePage):
    """
    Signup form + email/mobile OTP + password policy.

    All locators are derived from the shared screenshots (placeholder/label/role based).
    Verify them against the real DOM and tune in one place if needed.

    The portal sends an OTP as soon as a valid email or mobile is typed, so only tests that
    really need OTP should fill a valid email/mobile.
    """

    def __init__(self, page, config):
        super().__init__(page, config)
        page.on("response", self._watch_otp_response)

    @staticmethod
    def _watch_otp_response(response):
        if "send-otp" in response.url and response.status == 429:
            _otp_rate_limited["url"] = response.url

    def require_otp_available(self):
        """Stop the test as BLOCKED if UAT has already rate-limited send-otp in this session."""
        if _otp_rate_limited["url"]:
            block("UAT rate-limited send-otp (HTTP 429, 'Too many attempts from this network'). "
                  "Re-run OTP tests after the block expires.")

    @step("Open the signup page")
    def open(self):
        self.goto(self.config.signup_path)
        return self

    # ---------- field locators ----------
    def _first_name(self):     return self.page.get_by_placeholder("Enter your first name")
    def _last_name(self):      return self.page.get_by_placeholder("Enter your last name")
    def _business_name(self):  return self.page.get_by_placeholder("Enter your company name")
    def _email(self):          return self.page.get_by_placeholder(re.compile(r"name@company", re.I))
    def _mobile(self):         return self.page.get_by_placeholder(re.compile(r"98765", re.I))
    def _passwords(self):      return self.page.get_by_placeholder("Password")  # [0]=create [1]=confirm
    def _signup_btn(self):     return self.page.get_by_role("button", name=re.compile(r"sign\s*up", re.I))

    # ---------- fill helpers ----------
    @step("Enter name '{first} {last}' and business '{business}'")
    def fill_basic(self, first, last, business):
        self._first_name().fill(first)
        self._last_name().fill(last)
        self._business_name().fill(business)
        return self

    @step("Enter email '{email}'")
    def fill_email(self, email):
        self._email().fill(email)
        return self

    @step("Enter mobile '{mobile}'")
    def fill_mobile(self, mobile):
        self._mobile().fill(mobile)
        return self

    @step("Enter password and confirm password")
    def fill_passwords(self, password, confirm=None):
        confirm = password if confirm is None else confirm
        pw = self._passwords()
        pw.nth(0).fill(password)
        pw.nth(1).fill(confirm)
        return self

    def signup_enabled(self, timeout=3000):
        return self.is_enabled_soon(self._signup_btn(), timeout)

    @step("Click Sign Up (skipped when the button stays disabled)")
    def submit(self):
        self.click_if_enabled(self._signup_btn())
        return self

    # ---------- OTP ----------
    def _otp_boxes(self):
        return self.page.locator("input[maxlength='1']")

    def _fill_otp(self, code):
        boxes = self._otp_boxes()
        try:
            boxes.first.wait_for(state="visible", timeout=8000)
        except Exception:
            pass
        if boxes.count() >= len(code):
            for i, ch in enumerate(code):
                boxes.nth(i).fill(ch)
        else:  # fallback: single OTP input
            self.page.locator(
                "input[placeholder*='otp' i], input[name*='otp' i]"
            ).first.fill(code)

    def _click_verify_otp(self):
        self.page.get_by_role("button", name=re.compile(r"verify\s*otp", re.I)).click()

    def _open_otp_modal(self, trigger_name, title):
        """Click the per-field Verify button (waits for it) unless the OTP modal is already open."""
        modal_title = self.page.get_by_text(re.compile(title, re.I))
        if not modal_title.is_visible():
            self.page.get_by_role("button", name=re.compile(trigger_name, re.I)).click()
        try:
            modal_title.wait_for(timeout=10000)
        except Exception:
            self.require_otp_available()  # a 429 means the modal never opens: BLOCKED, not FAIL
            raise
        self.require_otp_available()

    @step("Verify email with OTP")
    def verify_email_otp(self, code=None):
        code = code or self.config.otp
        self.require_otp_available()
        self._open_otp_modal(r"verify\s*email", r"Verify your Email")
        self._fill_otp(code)
        self._click_verify_otp()
        return self

    @step("Verify mobile with OTP")
    def verify_mobile_otp(self, code=None):
        code = code or self.config.otp
        self.require_otp_available()
        self._open_otp_modal(r"verify\s*mobile", r"Verify your Mobile")
        self._fill_otp(code)
        self._click_verify_otp()
        return self

    # ---------- state ----------
    def email_verified(self):
        return self.page.get_by_text(re.compile(r"verified", re.I)).first.is_visible()

    def email_verified_safe(self):
        try:
            return self.email_verified()
        except Exception:
            return False

    @step("Check for the 'Registration Successful' page")
    def is_registration_success(self, timeout=15000):
        try:
            self.page.get_by_text(re.compile(r"Registration Success", re.I)).first.wait_for(timeout=timeout)
            return True
        except Exception:
            # Success route: #/auth/info-register-successfully
            return "register-success" in self.page.url

    def has_validation_error(self):
        body = self.page_text()
        return any(t in body for t in
                   ["required", "invalid", "valid", "do not match", "must ", "already"])

    # ---------- full flow ----------
    @step("Register merchant '{email}' / '{mobile}'")
    def register(self, first, last, business, email, mobile, password, confirm=None,
                 verify_email=True, verify_mobile=True):
        if verify_email or verify_mobile:
            self.require_otp_available()
        self.fill_basic(first, last, business)
        self.fill_email(email)
        if verify_email:
            self.verify_email_otp()
        self.fill_mobile(mobile)
        if verify_mobile:
            self.verify_mobile_otp()
        self.fill_passwords(password, confirm)
        self.submit()
        return self
