import os
import re

from pages.base_page import BasePage
from reporting import step

# Generate API Key asks for a 4-digit OTP (not the 6-digit login OTP). It only reacts to real key
# presses, so it is typed key by key; there is no Submit button.
API_KEY_OTP = os.getenv("SNXT_API_KEY_OTP", "1234")


class ApiAccessPage(BasePage):
    """Profile & Settings > API Access Control (#/account-settings/credentials/api-credential)."""

    PROFILE_PATH = "/#/account-settings/Edit_Profile"

    @step("Open Profile & Settings > API Access Control")
    def open(self):
        self.goto(self.PROFILE_PATH)
        self.page.get_by_role("link", name=re.compile(r"API Access Control", re.I)).click()
        self.page.wait_for_url(re.compile(r"credentials/api-credential"))
        self.page.get_by_text(re.compile(r"Total records:")).wait_for()
        return self

    def tabs(self):
        return [t.strip() for t in self.page.get_by_role("tab").all_inner_texts()]

    def key_count(self):
        text = self.page.get_by_text(re.compile(r"Total records:")).first.inner_text()
        return int(re.search(r"\d+", text).group())

    def active_keys(self):
        return self.page.get_by_role("row").filter(has_text=re.compile(r"\bActive\b"))

    def has_active_key(self):
        return self.active_keys().count() > 0

    @step("Generate an API key (OTP)")
    def generate_key(self, otp=API_KEY_OTP):
        before = self.key_count()
        self.page.get_by_role("button", name=re.compile(r"Generate API Key", re.I)).click()
        boxes = self.page.locator("input[maxlength='1']:visible")
        boxes.first.wait_for()
        boxes.first.click()
        self.page.keyboard.type(otp, delay=150)
        # The key secret is shown once; we don't keep it, just close the popup
        self.page.get_by_text("Client Secret").wait_for(timeout=20000)
        self.page.get_by_role("button", name=re.compile(r"^\s*Okay\s*$", re.I)).click()
        self.page.wait_for_function(
            "n => { const m = document.body.innerText.match(/Total records:\\s*(\\d+)/); return m && +m[1] > n; }",
            arg=before, timeout=15000)
        return self.active_keys().first.locator("td").first.inner_text().strip()

    @step("Make sure an active API key exists")
    def ensure_key(self):
        if not self.has_active_key():
            self.generate_key()
        return self
