# Changelog

Every change to this project, newest first. Times are IST (UTC+05:30).

Format for each entry:

```
## YYYY-MM-DD HH:MM — Short title
**Files:** files changed
**Why:** the problem
**Change:** what was done
**Status:** verified / not yet verified
```

---

## 2026-10-16 12:40 — Failure screenshots survive media cleanup; mobile "required" was not a bug
**Files:** `reporting/html_report.py`, `utils/bank_data.py`, `tests/test_add_bank.py`

**Why:**
- Failure screenshots were missing from reports. They were taken, but the next run's `prune_media` (`SNXT_REPORT_KEEP_MEDIA=1`) deleted the old run's `screenshots/` folder. The HTML only linked to those files.
- For example, the passing 11:28 API run wiped the Add Bank failure screenshots from 11:08 and 11:14.

**Change:**
- Screenshots of every non-PASS test (FAIL, BLOCKED and so on) are now always embedded in the HTML as `data:` URIs, so a report keeps its failure evidence after cleanup.
- Screenshots of passing tests stay linked files. `SNXT_REPORT_EMBED_SCREENSHOTS=true` still embeds everything.
- A failure screenshot showed that clearing Registered Mobile Number refills the profile mobile, so the field is never empty. BANK-007 had reported that as a "missing Field is required" error, which was wrong.
- The mobile field moved to the new BANK-016, which passes if the value comes back or "Field is required" is shown (`SELF_RESTORING_FIELDS`).

**Status:** Verified:
- Demo runs `12-18-10_demo-embed-a` / `b`: after B deleted A's `screenshots/`, A's HTML still showed its 4 non-pass screenshots.
- `12-33-53_add-bank-failures`: 3 screenshots embedded, about 105 KB each.
- `12-36-47_add-bank-mobile-check`: BANK-016 passed (mobile back as `8829314130`).
- Still failing as real app gaps: BANK-012 (account number accepts letters) and BANK-013 (organisation name accepts `@@##`).
- The 11:08 and 11:14 reports can't be repaired: their screenshot files were already deleted.

## 2026-10-16 11:30 — Next module: API key, Add Bank (validation), admin bank approval
**Files:**
- New: `utils/bank_data.py`, `pages/api_access_page.py`, `pages/add_bank_page.py`
- New tests: `tests/test_api_access.py`, `tests/test_add_bank.py`, `tests/test_bank_approval.py`
- Changed: `pages/admin_page.py`, `pages/login_page.py`, `pytest.ini`, `run_modules.ps1`
- `.merchant.json` (local only)

**Why:** Requested: reuse the already-activated merchant, log in, then automate the next module:
1. Profile → API Access Control → Generate Key
2. Add Bank: IDFC with all services, HDFC with Payout only; check validation and which fields are mandatory
3. Admin: New Bank Requests → search partner → View → fill details → Accept
4. Back to the merchant dashboard

**Change:**
- **`.merchant.json`** holds the merchant activated in run `2026-10-15_18-23-44_e2e`: `qa.auto+1792068835260190@gmail.com` (Chauhan LLC). Its first-login password was recovered from that run's report data, so no new registration or admin activation is needed.
- **`utils/bank_data.py`** keeps all Add Bank data in one place:
  - the banks: IDFC First Bank `IDFB0040101` (all services); HDFC Bank `HDFC0000001` (Payout)
  - the 8 form fields with placeholder, mandatory flag and maxlength
  - the invalid inputs and the exact messages from UAT
  - generators for account number, PAN and GST
- **`ApiAccessPage`:** `open()` goes through Profile & Settings → API Access Control. `generate_key()` and `ensure_key()` use the **4-digit OTP `1234`** (`SNXT_API_KEY_OTP`). It has to be typed key by key and there is no Submit button. The key secret popup is closed and nothing is stored.
- **`AddBankPage`:** handles all 3 steps: Select Bank (search) → Choose Service Types (Continue stays disabled until one is chosen) → Fill Details → `#/add-bank/thanks`, which shows "Pending Review". `field_error()` reads the error inside the field's `.bf-field` box.
- **`AdminPage`:**
  - `open_bank_requests()` opens Business Banking → New Bank Requests (`#/cib`). The other menu item, `#/bank-requests`, doesn't list Add Bank V2 requests.
  - `search_bank_requests(partner)`: the search box is an autocomplete, so it types the name and picks the suggestion.
  - `view_bank_request()` uses Action ⋮ → View, which opens `#/cib/cib-details/<id>`.
  - Then `fill_bank_approval()` and `accept_bank_request()`.
  - The approval values are `BANK_APPROVAL_DETAILS` (env `SNXT_BANK_VID_PREFIX`, `_VID_IFSC`, `_PROFILE_ID`, `_VPA_ID`, `_SUB_VPA`, `_QR_TYPE`, `_BC_ID`, `_PASSCODE`). Empty values are skipped.
- **`LoginPage.login()`:** back-to-back logins got "Please wait N seconds before requesting another OTP" (`retry_after`). It now waits and retries when N ≤ 60 s. Longer cooldowns end the attempt, so the test gets BLOCKED instead of hanging. One earlier run waited 533 s.
- **Tests:**
  - API-001/002
  - BANK-001…015: 37 cases, nothing submitted. One shared logged-in page per module, because the session lives in `sessionStorage` and `storage_state` can't reuse it.
  - BANK-E2E-001 [IDFC, HDFC]
  - New markers: `api_access`, `add_bank`, `bank_approval`. They are also added to `run_modules.ps1`.

**Status:**
- API Access `2026-10-16_11-28-30_api-access`: 2 passed.
- Add Bank `2026-10-16_11-08-31` + `11-14-46`: everything passes except 3 failures that are **app validation gaps** on UAT (the tests are left failing on purpose):
  - BANK-007[Registered Mobile Number]: an empty mobile shows no "Field is required"
  - BANK-012: the account number accepts letters (`abcdefghij`)
  - BANK-013: the organisation name accepts `@@##`
- Manual, through the UI: an IDFC bank request (all services, acc `592128349067`) was submitted and appears in admin `#/cib` as request 1044. **It has not been accepted yet.**
- BANK-E2E-001 has not been run: it needs the admin approval values.

## 2026-10-15 18:25 — E2E: register → admin activates (remarks) → merchant first login → dashboard
**Files:**
- `pages/admin_page.py`: rewritten. All admin logic lives here.
- `pages/change_password_page.py`: `create_new_password`
- `pages/login_page.py`: `complete_login`
- `tests/test_e2e_merchant_journey.py`, `tests/test_admin_activation.py`
- `.env` (local only)

**Why:** Requested: after registration, log in to the admin portal, open Register Partner, search for the new email, activate it with remarks, then log in as the merchant and continue. Both windows stay open, and every run produces a report.

**Change:**
- **`admin_page.py`** holds everything admin, including its own settings:
  - `ADMIN_URL`: default `https://uat.sprintnxt.in/NexGenAdminFront/#/auth/login`
  - `ADMIN_OTP`: default `123456`, entered only if the 2FA screen appears
  - `ACTIVATION_REMARKS`: default "Activated by QA automation"
  - `open_admin_window()`: a second browser window with its own context, logged in the report
- **Activation:** Register Partner (`#/partner/partner-list`) → "Search by user details" → Search → the row's `label.status-switch` → SweetAlert "You want to activate this partner" → remarks in `#swal2-input` → "Yes, update it!" → success popup → OK. The status pill must then read "Active".
- **Merchant first login:** the portal redirects to `#/auth/change-password` ("Create New Password"). `ChangePasswordPage.create_new_password()` sets a new password, then the test logs in again with it. `LoginPage.complete_login()` also enters an OTP or clicks Proceed if either appears.
- **E2E-001:** register (merchant window) → admin window opens → activate → merchant window: login → create new password → login → dashboard. It takes 4 screenshots for the report.
- **Admin tests:** ADM-001 (login), ADM-002 (Register Partner list), ADM-003 (activate `SNXT_MERCHANT_EMAIL`, BLOCKED without it).
- **Credentials:** `superadmin@gmail.com` and its password are in `.env` only, which is not committed.

**Status:** Verified in headed mode:
- E2E `2026-10-15_18-23-44_e2e`: PASS. Merchant `qa.auto+1792068835260190@gmail.com` was activated and reached the dashboard ("KYC Approved").
- Admin + E2E `2026-10-15_18-12-41_admin-e2e`: ADM-001 and ADM-002 passed, ADM-003 blocked.

Fixes along the way:
- Run `18-15-45`: the success popup needed its OK button clicked.
- Run `18-17-19`: the popup's state classes (`swal2-show`, `swal2-icon-success`) sit on the popup element itself, so the selector was wrong.
- Run `18-19-28`: the forced "Create New Password" step on first login wasn't handled yet.

## 2026-10-15 17:14 — Login / forgot password: real email locator, skip disabled submit; success-page check
**Files:** `pages/base_page.py` (`is_enabled_soon`, `click_if_enabled`), `pages/login_page.py`, `pages/forgot_password_page.py`, `pages/registration_page.py`, `tests/test_login.py`, `tests/test_forgot_password.py`
**Why:**
- Login's email field has the placeholder `name@company.com`, so `get_by_placeholder("email")` never matched. 12 login tests timed out on `fill`.
- Sign In and Reset Password stay disabled for invalid input, the same as Sign Up, so negative tests timed out clicking them.
- With no `SNXT_MERCHANT_EMAIL`, `test_forgot_valid_email` sent a new, unregistered email and correctly got "The provided information is not valid!".
- E2E reached `#/auth/info-register-successfully` but `is_registration_success()` returned False.

**Change:**
- Login uses `input[type='email']`.
- New `BasePage.click_if_enabled()` waits up to 3 s for the button and skips the click if it stays disabled. Sign Up, Sign In and Reset Password all use it.
- `test_forgot_valid_email` is BLOCKED without `SNXT_MERCHANT_EMAIL`.
- The success check uses `.first` and also accepts the success URL.

**Status:** Verified in headed mode:
- Login `2026-10-15_17-07-19_login`: 12 passed, 1 blocked (needs merchant credentials).
- Forgot Password `2026-10-15_17-09-15_forgot-password`: 11 passed, 1 blocked.
- E2E `2026-10-15_17-12-16_e2e` was BLOCKED by the UAT send-otp limit (about 10 OTPs this session), so the success-page fix is not yet verified. A rerun is scheduled after the block expires.

## 2026-10-15 17:02 — Registration: stop OTP rate-limit, fix disabled Sign Up and business names
**Files:** `pages/registration_page.py`, `tests/test_registration.py`, `tests/test_registration_security.py`, `utils/data_factory.py`
**Why:**
- The portal sends an OTP as soon as a valid email or mobile is typed. The 14 security tests each typed both, sending 28 OTPs per run, so UAT blocked the network (HTTP 429).
- Negative tests clicked a disabled Sign Up button and timed out.
- Faker business names with commas were rejected, so REG-001 could never pass.

**Change:**
- Security tests no longer fill email or mobile, so they send no OTPs.
- `RegistrationPage` watches `send-otp` responses. After the first 429, every later OTP test stops as BLOCKED (`require_otp_available()`) instead of sending more OTPs.
- `submit()` waits up to 3 s for Sign Up to become enabled and skips the click if it stays disabled.
- REG-002 now asserts that Sign Up is disabled or an error is shown. Negative tests wait 4 s for the success page instead of 15 s.
- `valid_person()` business names contain only letters and spaces.

**Status:** Verified in headed mode, with no 429s:
- run `2026-10-15_16-40-58_registration-headed`: 41 of 42 passed. REG-001 failed because Sign Up was checked before the form enabled it; the 3 s wait above fixes that.
- rerun `2026-10-15_16-51-11_registration-reg-001-rerun`: REG-001 passed.

## 2026-10-15 16:02 — Shareable summary PDF
**Files:** `reporting/summary_pdf.py` (new), `reporting/plugin.py`, `REPORTING.md`, `requirements.txt` (+`pillow`, optional)
**Why:** `report.pdf` for the full suite was 64 MB and 335 pages (every log and stack trace), too big to send and hard for someone else to read.
**Change:** Every run now also writes `html/summary.pdf`, which contains:
- the run overview and module table
- failure reasons, grouped
- every test with its status and the step it failed at
- one downscaled screenshot per failure reason

To rebuild it for an existing run: `python -m reporting.summary_pdf reports/runs/<run>`.
**Status:** Verified. The full-suite run's summary is 0.6 MB and 13 pages. I rendered pages and checked them.

## 2026-10-15 16:02 — Keep screenshots/videos only for the latest run
**Files:** `reporting/storage.py` (`prune_media`), `reporting/settings.py` (`SNXT_REPORT_KEEP_MEDIA`, default `1`), `reporting/plugin.py`, `REPORTING.md`
**Why:** Requested: old screenshots and videos should be deleted and only the latest kept.
**Change:** After each run, `screenshots/` and `videos/` are deleted from every older run folder. Their HTML/JSON/CSV/PDF reports, traces and logs stay. Set `SNXT_REPORT_KEEP_MEDIA=N` to keep N runs, or `0` to keep all.
**Status:** Verified. After the demo run `2026-10-15_16-01-08_demo-media-check`, all 4 older runs have 0 screenshots and 0 videos, and the newest has 5 of each. Older HTML reports now show missing images. Their `summary.pdf` (where present) still has its embedded screenshots.

## 2026-10-15 16:02 — Record videos at the real window size
**Files:** `conftest.py`
**Why:** Videos were 800×500, because Playwright scales recordings down to fit 800×800, while the browser window is 1440×900. They looked small and blurry compared with the portal.
**Change:** `browser_context_args` now sets `record_video_size` to 1440×900.
**Status:** Verified: the new video is 1440×900.

## 2026-10-15 14:24 — Copy `reports/latest` after the final log line
**Files:** `reporting/plugin.py`
**Why:** `refresh_latest()` ran before "Report written" was logged, so `reports/latest/logs/execution.log` was missing the end of the run.
**Change:** `refresh_latest()` now runs last in session finish, after `render_index`, `prune_runs` and the final log line.
**Status:** Verified: after the demo run (`2026-10-15_14-23-42_demo-log-order-check`), `latest/logs/execution.log` ends with "Report written".

## 2026-10-15 14:22 — `--headed` / `--slowmo` override the env settings
**Files:** `conftest.py`
**Why:** `browser_type_launch_args` always used `SNXT_HEADLESS` / `SNXT_SLOWMO`, so `pytest --headed --slowmo 300` (as the README shows) still ran headless.
**Change:** `--headed` now forces headless off, and a non-zero `--slowmo` replaces `SNXT_SLOWMO`. With neither flag, the env values apply as before.
**Status:** Verified: `headless=True slow_mo=0` without flags, and `headless=False slow_mo=50` with `--headed --slowmo 50`.

## 2026-10-15 14:08 — Changelog: log the reporting work
**Files:** `CHANGELOG.md`
**Why:** The reporting framework (12:42–13:41) was built without changelog entries.
**Change:** Added the four entries below and refreshed the open-issues list.
**Status:** Done.

## 2026-10-15 13:38 — Reporting docs, module runner and CI example
**Files:** `REPORTING.md` (new), `README.md`, `run_modules.ps1` (new), `ci/github-actions-ui-tests.yml` (new)
**Why:** Teams need to know how to run the suite, read the report and publish it from CI.
**Change:**
- `REPORTING.md` covers folder layout, report fields, integration (`@tc`, `@step`, `report.*`, `block`), status rules, env vars, traces, CI and troubleshooting.
- `README.md` links to it and now uses the correct `SNXT_SLOWMO` name.
- `run_modules.ps1` runs each module separately (`-Modules`, `-Workers`, `-Reruns`), giving one report per module plus `reports/index.html`.
- The GitHub Actions example runs a matrix job per module, always uploads `reports/latest` and caches `reports/history`.

**Status:** Docs written. `run_modules.ps1` and the CI file have not been run yet.

## 2026-10-15 13:34 — Report metadata in page objects and tests
**Files:** `pages/registration_page.py`, `pages/login_page.py`, `pages/forgot_password_page.py`, `pages/change_password_page.py`, `pages/admin_page.py`, `tests/test_registration.py`, `tests/test_login.py`, `tests/test_admin_activation.py`, `conftest.py`
**Why:** Without metadata, report rows only had function names and no steps.
**Change:**
- Page-object methods are decorated with `@step(...)`, so every test lists its steps with timings.
- Registration, login and admin tests carry `@tc(...)` IDs, expected results and types.
- In `logged_in_page` and the admin test, missing credentials now call `block(...)`, so the test shows as BLOCKED instead of SKIPPED.

**Status:** All 81 tests still collect (`pytest --collect-only`). They have not run against UAT yet because of the HTTP 429 rate limit.

## 2026-10-15 13:29 — HTML execution reporting framework
**Files:** `reporting/` (new: `plugin.py`, `collector.py`, `capture.py`, `classify.py`, `metadata.py`, `models.py`, `redact.py`, `settings.py`, `storage.py`, `exporters.py`, `html_report.py`, `templates/report.{html,css,js}`), `conftest.py` (`pytest_plugins = ["reporting.plugin"]`), `pytest.ini` (`--video/--tracing retain-on-failure`), `requirements.txt` (+`pytest-rerunfailures`, `pytest-xdist`)
**Why:** We needed a shareable execution report with evidence for each test.
**Change:**
- Every pytest run writes `reports/runs/<timestamp>_<name>/` containing:
  - an HTML report (dashboard, charts, filters, details for each test)
  - a PDF, plus JSON and CSV exports
  - failure screenshots, videos and traces
  - API, console and network logs, with secrets masked
- Each test gets one of four statuses: PASS, FAIL, BLOCKED or SKIPPED. Failures are sorted into categories (for example timeout, HTTP 429, element not found).
- Retries and xdist workers are merged into one report.
- Run history and the trend chart are kept in `reports/history/history.json`.
- `reports/latest` holds a copy of the newest run, and `reports/index.html` lists all runs.

**Status:** Verified with the offline demo below, in both sequential and `-n 2` runs. Both gave identical results: 12 tests, 5 pass, 3 fail, 2 blocked, 2 skipped, 1 flaky.

## 2026-10-15 13:25 — Offline reporting demo suite
**Files:** `examples/reporting_demo/test_reporting_demo.py` (new)
**Why:** We needed a way to exercise every report status without sending traffic to the rate-limited UAT server.
**Change:** Added 12 demo tests covering pass, fail, blocked, skipped, flaky on retry, HTTP 429 and parametrized cases. Run them with `pytest examples/reporting_demo`.
**Status:** Verified (runs `2026-10-15_13-40-41_demo-sequential`, `2026-10-15_13-41-13_demo-parallel`).

## 2026-10-15 12:16 — OTP popup: wait for the per-field Verify button
**Files:** `pages/registration_page.py`
**Why:** `_maybe_click_trigger()` checked once for any "Verify" button without waiting and silently skipped the click if it wasn't there yet, so the OTP popup sometimes never opened in headed / slow-mo runs.
**Change:** Replaced it with `_open_otp_modal(trigger_name, title)`, which waits for and clicks the specific **Verify email** / **Verify mobile number** button unless the popup is already open. `verify_email_otp()` and `verify_mobile_otp()` now use it.
**Status:** Not fully verified. The UAT server started returning HTTP 429 ("Too many attempts from this network. Please try again in 44 minutes.") on `send-otp`, so OTP tests couldn't be rerun.

## 2026-10-15 12:00 — Grant browser location access
**Files:** `conftest.py`
**Why:** Without location access the app redirects every page to `#/location-required`, so all 30 registration tests failed on the first step.
**Change:** `browser_context_args` now sets `geolocation` (New Delhi, 28.6139 / 77.2090) and `permissions: ["geolocation"]`.
**Status:** Verified: the signup form now loads.

## 2026-10-15 11:59 — Fix app routes in config
**Files:** `config.py`
**Why:** `#/signup`, `#/login` and `#/forgot-password` don't exist; the app redirects them to the login page.
**Change:** Default routes changed to the real ones:
- `SNXT_SIGNUP_PATH`: `/#/signup` → `/#/auth/sign-up`
- `SNXT_LOGIN_PATH`: `/#/login` → `/#/auth/login`
- `SNXT_FORGOT_PATH`: `/#/forgot-password` → `/#/auth/forget-password`

**Status:** Verified: each route loads its page.

## 2026-10-15 11:55 — Install dependencies
**Files:** none (environment only)
**Why:** Tests failed to import because `faker` was missing.
**Change:** Installed `requirements.txt` and Playwright Chromium (`python -m playwright install chromium`).
**Status:** Verified.

---

## Open issues (not changed yet)
- **Failure screenshots can show an empty form (not confirmed).** The step logs record a second navigation to the same route about 7.5 s after the page opens (LOGIN-002, REG-002). That looks like the portal reloading the route and clearing the fields, so the screenshot taken at failure shows an empty form. Check this in a trace (`playwright show-trace`).
- **UAT allows only about 10 send-otp calls per block window.** A full run sends about 7 (REG-001: 2, REG-007: 1, REG-008: 2–3, E2E: 2), so back-to-back runs hit HTTP 429. Leave about 45 minutes between full runs.
- **Change Password, ADM-003, LOGIN-001, FPW valid-email are BLOCKED.** Set `SNXT_MERCHANT_EMAIL` / `SNXT_MERCHANT_PASS` to an activated merchant in `.env`. E2E-001 creates one, but its new password isn't saved anywhere.
- **Bank approval values unknown.** The admin View screen (VID Prefix, VID IFSC, Profile Id, VPA Id, SUB VPA, QR Type, BC Id, Passcode) needs UAT values before BANK-E2E-001 can accept a request.
- **Reports store passwords in plain text.** Test data and `auth/login` request bodies in `results.json` contain them (that's how the merchant password was recovered). Masking them is not done yet.
