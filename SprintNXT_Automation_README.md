# SprintNXT — Registration & Account QA Automation (pytest + Playwright)

End-to-end UI automation for the SprintNXT merchant onboarding flow:
**Registration** (email + mobile OTP, password policy) → **Admin activation** →
**Login** → **Change Password** → **Forgot Password**, with positive, negative and
security (SQL injection / XSS / enumeration) coverage.

## Structure

```
sprintnxt-automation/
├── config.py                 # env-driven config (URLs, OTP, creds, policy)
├── conftest.py               # fixtures: config, browser args, logged-in merchant
├── pytest.ini                # markers + pythonpath
├── requirements.txt
├── .env.example              # copy to .env and fill in
├── pages/                    # Page Object Model
│   ├── base_page.py
│   ├── registration_page.py
│   ├── login_page.py
│   ├── change_password_page.py
│   ├── forgot_password_page.py
│   └── admin_page.py
├── utils/
│   ├── data_factory.py       # valid + invalid email / mobile / password sets
│   └── payloads.py           # SQLi / XSS payloads for defensive tests
└── tests/
    ├── test_registration.py
    ├── test_registration_security.py
    ├── test_login.py
    ├── test_change_password.py
    ├── test_forgot_password.py
    ├── test_admin_activation.py
    └── test_e2e_merchant_journey.py
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env            # then edit .env
```

## Run

```bash
pytest                                  # everything
pytest -m smoke                         # quick sanity
pytest -m positive                      # happy-path only
pytest -m negative                      # validation / error handling
pytest -m security                      # SQLi / XSS / enumeration
pytest -m "registration and negative"   # combine markers
pytest tests/test_login.py              # one module
pytest --headed --slowmo 300            # watch it run
```

Markers: `smoke, positive, negative, security, e2e, registration, login,
change_password, forgot_password, admin`.

## Configuration (.env)

| Var | Purpose |
|---|---|
| `SNXT_BASE_URL` / `SNXT_*_PATH` | app base URL + route for each page |
| `SNXT_OTP` | fixed UAT OTP for email + mobile (default `123456`) |
| `SNXT_ADMIN_URL/USER/PASS` | admin panel login (see note below) |
| `SNXT_MERCHANT_EMAIL/PASS` | a seeded, already-activated merchant for login/password tests |
| `SNXT_HEADLESS/SLOWMO/TIMEOUT_MS` | run behaviour |

Tests that need data you haven't supplied **self-skip** with a clear reason rather
than failing, so the suite stays green while you fill things in.

## Read this before the first run (assumptions)

1. **Selectors are inferred from the screenshots** (placeholder / label / role based,
   e.g. `get_by_placeholder("Enter your first name")`). They are resilient but unverified —
   run once and tune any that miss. All of them live in `pages/`, so fixes are one place.
2. **OTP is fixed to `123456`** via `SNXT_OTP`, per the UAT spec. If a run ever needs a real
   OTP, replace the body of `_fill_otp` / the verify methods with a mailbox/DB/API fetch.
3. **The OTP-modal trigger is a best guess** (`_maybe_click_trigger` in `registration_page.py`).
   If there is an explicit per-field *Verify* button/link, point that method at it.
4. **Admin login was NOT in the shared material.** `admin_page.py` and the admin/e2e tests are
   fully parameterised and skip until `SNXT_ADMIN_URL/USER/PASS` are set. Share the admin
   screenshots and the activation step can be made exact.
5. **Some negative/security assertions are deliberately tolerant** (they check "no error / no
   script fired / not navigated to dashboard"). Tighten them to the app's actual toast text and
   validation messages once you've seen a real run.
6. **Password policy** encoded from the UI: 12–15 chars, ≥1 upper, ≥1 lower, ≥1 digit, ≥1 special.
   The `INVALID_PASSWORDS` set breaks exactly one rule per case so failures are unambiguous.

## Security tests

`test_registration_security.py` and `test_forgot_no_account_enumeration` submit injection
payloads to **our own UAT app** and assert it rejects/sanitises them (no SQL error text in the
page, no JS dialog fires, no account-existence disclosure). They are defensive checks, not
attack tooling.
