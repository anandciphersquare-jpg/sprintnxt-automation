from playwright.sync_api import Page, expect


class BasePage:
    def __init__(self, page: Page, config):
        self.page = page
        self.config = config

    @staticmethod
    def is_enabled_soon(locator, timeout=3000) -> bool:
        """True once the button is enabled; forms re-validate a moment after the last input."""
        try:
            expect(locator).to_be_enabled(timeout=timeout)
            return True
        except AssertionError:
            return False

    def click_if_enabled(self, locator, timeout=3000) -> bool:
        """The portal keeps submit buttons disabled while a form is invalid; clicking one would time out."""
        if self.is_enabled_soon(locator, timeout):
            locator.click()
            return True
        return False

    def goto(self, path: str):
        url = self.config.base_url.rstrip("/") + path
        self.page.goto(url)
        return self

    def toast_text(self, timeout=8000) -> str:
        """Read a toast/alert message. Adjust the selector to the real toast container."""
        toast = self.page.locator(
            "[class*='toast'], [class*='Toastify'], [role='alert'], [class*='snackbar']"
        ).first
        try:
            toast.wait_for(state="visible", timeout=timeout)
            return toast.inner_text().strip()
        except Exception:
            return ""

    def page_text(self) -> str:
        try:
            return self.page.locator("body").inner_text().lower()
        except Exception:
            return ""
