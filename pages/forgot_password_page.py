import re

from pages.base_page import BasePage
from reporting import step


class ForgotPasswordPage(BasePage):
    """Reset-password request page."""

    @step("Open Forgot Password")
    def open(self):
        self.goto(self.config.forgot_path)
        return self

    def _email(self):   return self.page.get_by_placeholder(re.compile(r"email", re.I))
    def _submit(self):  return self.page.get_by_role("button", name=re.compile(r"reset\s*password", re.I))

    @step("Click Reset Password (skipped when the button stays disabled)")
    def submit(self):
        self.click_if_enabled(self._submit())
        return self

    @step("Request a reset link for '{email}'")
    def request_reset(self, email):
        self._email().fill(email)
        self.submit()
        return self

    def result(self):
        return self.toast_text()
