"""Reporter showcase - runs fully offline against a mocked app (no UAT traffic, no OTP rate limits).

    pytest examples/reporting_demo --report-name demo-showcase

Produces every status (PASS / FAIL / BLOCKED / SKIPPED), a flaky retry, failure screenshots,
video + trace, API request/response logs, console errors and network failures.
Not part of the real suite (pytest.ini testpaths = tests).
"""
import json
import re

import pytest
from playwright.sync_api import Page, expect

from reporting import block, report, step, tc

APP = "https://demo.sprintnxt.local"

LOGIN_HTML = """<!doctype html><html><head><title>SprintNXT demo</title>
<style>body{font-family:system-ui;margin:40px;background:#f4f6fb}form,.panel{background:#fff;padding:24px;border-radius:12px;max-width:380px;box-shadow:0 2px 10px #0001}
input{display:block;width:100%;margin:8px 0 14px;padding:10px;border:1px solid #ccd;border-radius:8px}button{padding:10px 16px;border:0;border-radius:8px;background:#2a78d6;color:#fff}
#msg{margin-top:12px;color:#b00020}</style></head><body>
<h1>Merchant login</h1>
<form id="f"><label>Email<input id="email" placeholder="name@company.com"></label>
<label>Password<input id="password" type="password" placeholder="Password"></label>
<button id="login">Log in</button><div id="msg" role="alert"></div></form>
<script src="/static/analytics.js"></script>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email: email.value, password: password.value})});
  const body = await r.json();
  if (r.ok) { document.body.innerHTML = '<div class="panel"><h1>Dashboard</h1><p id="welcome">Welcome, ' + body.user.name + '</p><div id="profile"></div></div>';
              fetch('/api/profile').then(p => { if (!p.ok) console.error('Profile widget failed: HTTP ' + p.status); }); }
  else { document.getElementById('msg').textContent = body.message; console.error('Login failed: ' + r.status + ' ' + body.message); }
});
</script></body></html>"""


def _handle(route):
    url, req = route.request.url, route.request
    if url.rstrip("/") == APP or url == APP + "/login":
        return route.fulfill(status=200, content_type="text/html", body=LOGIN_HTML)
    if url.endswith("/static/analytics.js"):
        return route.fulfill(status=404, body="not found")
    if url.endswith("/api/auth/login"):
        creds = json.loads(req.post_data or "{}")
        email = creds.get("email", "")
        if "ratelimit" in email:
            return route.fulfill(status=429, headers={"Retry-After": "2640"},
                                 json={"message": "Too many attempts from this network. Please try again in 44 minutes."})
        if creds.get("password") == "Correct@12345":
            return route.fulfill(status=200, json={"access_token": "eyJhbGciOi.demo.token", "user": {"name": "QA Merchant", "email": email}})
        return route.fulfill(status=401, json={"message": "Invalid email or password"})
    if url.endswith("/api/profile"):
        return route.fulfill(status=500, json={"message": "Internal server error", "traceId": "a1b2c3"})
    return route.fulfill(status=404, body="")


class DemoLoginPage:
    """A miniature page object showing @step on page-object methods."""

    def __init__(self, page: Page):
        self.page = page

    @step("Open the login page")
    def open(self):
        self.page.goto(APP + "/login")
        return self

    @step("Log in as {email}")
    def login(self, email: str, password: str):
        self.page.get_by_placeholder("name@company.com").fill(email)
        self.page.get_by_placeholder("Password").fill(password)
        self.page.get_by_role("button", name=re.compile("log in", re.I)).click()
        return self

    @step("Read the error message")
    def error(self) -> str:
        msg = self.page.get_by_role("alert")
        expect(msg).not_to_be_empty(timeout=5000)
        return msg.inner_text()


@pytest.fixture
def demo(page: Page) -> DemoLoginPage:
    page.context.route(f"{APP}/**", _handle)
    page.context.route(APP, _handle)
    page.set_default_timeout(4000)
    return DemoLoginPage(page).open()


@pytest.fixture
def broken_backend(page: Page):
    raise ConnectionError("Seed-data service unreachable: POST http://seed.local/merchants -> ECONNREFUSED")


# ------------------------------------------------------------------------- PASS
@pytest.mark.smoke
@pytest.mark.login
@tc("DEMO-001", "Merchant logs in with valid credentials", feature="Merchant login",
    types=["Functional", "Smoke"], preconditions=["Merchant account is active", "Login page is open"],
    expected="Dashboard opens and greets the merchant by name")
def test_login_success(demo):
    report.data("email", "qa.merchant@sprintnxt.in")
    demo.login("qa.merchant@sprintnxt.in", "Correct@12345")
    with step("Verify the dashboard greeting"):
        expect(demo.page.locator("#welcome")).to_have_text(re.compile("Welcome, QA Merchant"))
    report.actual("Dashboard opened with 'Welcome, QA Merchant'")


@pytest.mark.negative
@pytest.mark.login
@pytest.mark.parametrize("email,reason", [("plainaddress", "no-at"), ("user@", "missing-domain"),
                                          ("", "empty")], ids=["no-at", "missing-domain", "empty"])
@tc("DEMO-002", "Login rejects a malformed email", feature="Merchant login",
    types=["Negative", "Validation"], expected="An error message is shown and no dashboard opens")
def test_login_invalid_email(demo, email, reason):
    demo.login(email, "Whatever@123")
    assert "invalid" in demo.error().lower()


# ------------------------------------------------------------------------- FAIL (assertion)
@pytest.mark.login
@tc("DEMO-003", "Wrong password shows a lockout warning", feature="Merchant login",
    types=["Negative", "Security"], expected="Message warns about remaining attempts before lockout")
def test_wrong_password_warns_about_lockout(demo):
    demo.login("qa.merchant@sprintnxt.in", "Wrong@123456")
    message = demo.error()
    assert "attempts remaining" in message.lower(), f"Expected a lockout warning, got: {message!r}"


# ------------------------------------------------------------------------- FAIL (locator timeout + 5xx)
@pytest.mark.login
@tc("DEMO-004", "Dashboard shows the merchant profile widget", feature="Dashboard",
    types=["Functional", "UI/UX"], expected="Profile widget shows the merchant's business name")
def test_dashboard_profile_widget(demo):
    demo.login("qa.merchant@sprintnxt.in", "Correct@12345")
    with step("Wait for the profile widget"):
        demo.page.locator("#profile .business-name").wait_for(timeout=2500)


# ------------------------------------------------------------------------- FAIL (rate limited)
@pytest.mark.registration
@tc("DEMO-005", "Send OTP for email verification", module="Registration", feature="Email OTP",
    types=["Functional", "API"], expected="OTP is sent and the OTP dialog opens")
def test_send_otp_rate_limited(demo):
    demo.login("ratelimit.user@sprintnxt.in", "Correct@12345")
    expect(demo.page.locator("#welcome")).to_be_visible(timeout=2500)


# ------------------------------------------------------------------------- BLOCKED / SKIPPED
@pytest.mark.admin
@tc("DEMO-006", "Admin activates a newly registered merchant", feature="Merchant activation",
    types=["Functional", "Integration"], preconditions=["Admin credentials configured"])
def test_admin_activation(demo):
    block("Admin URL/credentials not provided (SNXT_ADMIN_URL / SNXT_ADMIN_USER / SNXT_ADMIN_PASS)")


@pytest.mark.registration
@tc("DEMO-007", "Bulk-import merchants from CSV", module="Registration", feature="Bulk import",
    types=["Functional", "Regression"])
def test_bulk_import(demo):
    pytest.skip("Bulk import is not part of release 4.2")


@pytest.mark.registration
@tc("DEMO-008", "Seeded merchant data is available", module="Registration", feature="Test data seeding",
    types=["Integration"])
def test_needs_seed_service(broken_backend):
    pass


# ------------------------------------------------------------------------- flaky (passes on retry)
_attempts = {"banner": 0}


@pytest.mark.flaky(reruns=2)
@pytest.mark.login
@tc("DEMO-009", "Session banner appears after login", feature="Session",
    types=["UI/UX", "Regression"], expected="Banner is visible within 2s")
def test_session_banner_flaky(demo):
    _attempts["banner"] += 1
    demo.login("qa.merchant@sprintnxt.in", "Correct@12345")
    report.note(f"Attempt {_attempts['banner']} of the banner check")
    assert _attempts["banner"] >= 2, "Banner did not render in time (simulated race condition)"


# ------------------------------------------------------------------------- xfail
@pytest.mark.xfail(reason="BUG-1432: password field accepts 16 characters", strict=False)
@pytest.mark.registration
@tc("DEMO-010", "Password longer than 15 characters is rejected", module="Registration",
    feature="Password policy", types=["Boundary", "Validation"])
def test_password_max_length(demo):
    assert len("Ab@1234567890123") <= 15
