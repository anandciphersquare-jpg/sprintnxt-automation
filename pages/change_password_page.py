import re

from pages.base_page import BasePage
from reporting import step


class ChangePasswordPage(BasePage):
    """Change Password (Manage > Account Settings). Fields order: current, new, confirm."""

    @step("Open Change Password")
    def open(self):
        # assumes an authenticated session in the same browser context
        self.goto(self.config.change_pw_path)
        return self

    def _fields(self):  return self.page.get_by_placeholder("Password")  # [0]current [1]new [2]confirm
    def _submit(self):  return self.page.get_by_role("button", name=re.compile(r"change\s*password", re.I))

    @step("Change password (current -> new)")
    def change(self, current, new, confirm=None):
        confirm = new if confirm is None else confirm
        f = self._fields()
        f.nth(0).fill(current)
        f.nth(1).fill(new)
        f.nth(2).fill(confirm)
        self._submit().click()
        return self

    def result(self):
        return self.toast_text()

    # ---------- first login: forced "Create New Password" (#/auth/change-password) ----------
    def is_create_new_password(self):
        return "auth/change-password" in self.page.url

    @step("Create a new password on first login")
    def create_new_password(self, new_password):
        self.page.get_by_text(re.compile(r"create new password", re.I)).first.wait_for()
        f = self._fields()  # [0] new [1] confirm
        f.nth(0).fill(new_password)
        f.nth(1).fill(new_password)
        self.click_if_enabled(self.page.get_by_role("button", name=re.compile(r"submit", re.I)))
        # Success popup (if any) -> OK, then the portal leaves the change-password route
        ok = self.page.locator(".swal2-popup.swal2-show .swal2-confirm")
        try:
            ok.wait_for(timeout=8000)
            ok.click()
        except Exception:
            pass
        self.page.wait_for_url(lambda url: "auth/change-password" not in url, timeout=20000)
        return self
