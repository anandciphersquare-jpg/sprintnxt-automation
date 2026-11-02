import re

from pages.base_page import BasePage
from reporting import step


class LoginPage(BasePage):
    """Login page: email (placeholder 'name@company.com'), password, Sign In."""

    @step("Open the login page")
    def open(self):
        self.goto(self.config.login_path)
        return self

    def _email(self):     return self.page.locator("input[type='email']")
    def _password(self):  return self.page.get_by_placeholder(re.compile(r"password", re.I))
    def _login_btn(self): return self.page.get_by_role("button", name=re.compile(r"log\s*in|sign\s*in", re.I))

    @step("Click Sign In (skipped when the button stays disabled)")
    def submit(self):
        self.click_if_enabled(self._login_btn())
        return self

    @step("Log in as '{email}'")
    def login(self, email, password):
        self._email().fill(email)
        self._password().fill(password)
        if not self.is_enabled_soon(self._login_btn()):
            return self
        # Back-to-back logins get "Please wait N seconds before requesting another OTP" (retry_after)
        for _ in range(3):
            try:
                with self.page.expect_response(lambda r: r.url.endswith("/auth/login"), timeout=10000) as resp:
                    self._login_btn().click()
                retry_after = (resp.value.json().get("data") or {}).get("retry_after")
            except Exception:  # no login request (client-side validation) or a non-JSON reply
                retry_after = None
            if not retry_after or int(retry_after) > 60:  # long cooldowns: give up, caller blocks the test
                break
            self.page.wait_for_timeout((int(retry_after) + 2) * 1000)
        return self

    @step("Finish login (OTP / Proceed if asked)")
    def complete_login(self, timeout=45000):
        """After Sign In the portal may ask for an OTP or show a Proceed screen before the dashboard.

        Returns True on the dashboard, or 'change-password' when a first login forces a new password.
        """
        deadline = self.page.evaluate("Date.now()") + timeout
        while self.page.evaluate("Date.now()") < deadline:
            if re.search(r"dashboard", self.page.url, re.I):
                return True
            if "auth/change-password" in self.page.url:
                return "change-password"
            boxes = self.page.locator("input[maxlength='1']:visible")
            if boxes.count() >= 6 and not boxes.first.input_value():
                for i, ch in enumerate(self.config.otp):
                    boxes.nth(i).fill(ch)
                self.click_if_enabled(self.page.get_by_role(
                    "button", name=re.compile(r"verify|submit|continue|sign\s*in|login", re.I)).last)
            proceed = self.page.get_by_role("button", name=re.compile(r"proceed|continue|okay|ok\b", re.I))
            if proceed.count() and proceed.first.is_visible():
                proceed.first.click()
            self.page.wait_for_timeout(1000)
        return bool(re.search(r"dashboard", self.page.url, re.I))

    @step("Go to Forgot password")
    def goto_forgot(self):
        self.page.get_by_role("link", name=re.compile(r"forgot", re.I)).click()
        return self

    def error(self):
        return self.toast_text()
