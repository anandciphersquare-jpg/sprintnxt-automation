import re

from pages.base_page import BasePage
from reporting import step
from utils.bank_data import FIELDS


class AddBankPage(BasePage):
    """
    Add Bank V2 (#/add-bank): 1. Select Bank > 2. Choose Service Types > 3. Fill Details > Submit
    > #/add-bank/thanks ("Bank Successfully Added!", status Pending Review until admin accepts it).
    """

    PATH = "/#/add-bank"

    @step("Open Add Bank")
    def open(self):
        # The wizard keeps its step on the same #/add-bank URL; leave it first so step 1 shows again
        if "add-bank" in self.page.url:
            self.goto("/#/dashboard")
            self.page.wait_for_url(re.compile(r"#/dashboard"))
        self.goto(self.PATH)
        self.page.get_by_role("heading", name="All Banks").wait_for()
        return self

    @step("Dashboard: click Add Bank Account")
    def open_from_dashboard(self):
        self.page.get_by_role("button", name=re.compile(r"Add Bank Account", re.I)).click()
        self.page.get_by_role("heading", name="All Banks").wait_for()
        return self

    # ---------- step 1: select bank ----------
    def _search(self):
        return self.page.get_by_placeholder(re.compile(r"Search bank name", re.I))

    @step("Search bank '{text}'")
    def search(self, text):
        self._search().fill(text)
        self.page.wait_for_timeout(800)
        return self

    def bank_tile(self, name):
        return self.page.get_by_text(name, exact=True)

    def is_bank_listed(self, name):
        tiles = self.bank_tile(name)
        return any(tiles.nth(i).is_visible() for i in range(tiles.count()))

    @step("Select bank '{name}'")
    def select_bank(self, name):
        self.bank_tile(name).first.click()
        self.page.get_by_text("Choose Service Types").wait_for()
        return self

    # ---------- step 2: services ----------
    def _continue(self):
        return self.page.get_by_role("button", name=re.compile(r"Continue", re.I))

    def service_cards(self):
        self.page.get_by_text("Payout", exact=True).first.wait_for()
        return [c for c in ("Payout", "UPI Collection", "VID Collection", "All Services")
                if self.page.get_by_text(c, exact=True).first.is_visible()]

    def is_continue_enabled(self):
        return self._continue().is_enabled()

    @step("Choose services {services}")
    def choose_services(self, services):
        for name in services:
            self.page.get_by_text(name, exact=True).first.click()
        return self

    @step("Continue to Fill Details")
    def continue_to_details(self):
        self._continue().click()
        self.page.get_by_role("heading", name="Bank Account Details").wait_for()
        return self

    # ---------- step 3: details ----------
    def field(self, label):
        return self.page.get_by_placeholder(FIELDS[label]["placeholder"])

    def value(self, label):
        return self.field(label).input_value()

    def field_error(self, label):
        """Error text inside the field's .bf-field box ('' when none): everything except the label."""
        box = self.page.locator(".bf-field").filter(has=self.field(label)).first
        return box.inner_text().replace(box.locator("label").inner_text(), "", 1).strip()

    @step("Fill bank details {data}")
    def fill_details(self, data):
        for label, val in data.items():
            self.field(label).fill(val)
        return self

    @step("Clear '{label}'")
    def clear(self, label):
        self.field(label).fill("")
        self.field(label).blur()
        return self

    @step("Click Submit")
    def submit(self):
        self.page.get_by_role("button", name=re.compile(r"^\s*Submit\s*$")).click()
        self.page.wait_for_timeout(600)
        return self

    @step("Click Reset")
    def reset(self):
        self.page.get_by_role("button", name=re.compile(r"^\s*Reset\s*$")).click()
        self.page.wait_for_timeout(600)
        return self

    @step("Wait for 'Bank Successfully Added!'")
    def is_added(self, timeout=20000):
        try:
            self.page.wait_for_url(re.compile(r"#/add-bank/thanks"), timeout=timeout)
            self.page.get_by_text("Bank Successfully Added!").wait_for(timeout=timeout)
            return True
        except Exception:
            return False

    def summary_text(self):
        return self.page.locator("body").inner_text()

    @step("Add bank '{bank}' with services {services}")
    def add_bank(self, bank, services, data):
        self.select_bank(bank).choose_services(services).continue_to_details()
        self.fill_details(data).submit()
        return self.is_added()
