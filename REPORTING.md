# Test execution reporting

Every `pytest` run produces a self-contained, timestamped HTML report (plus PDF, JSON and CSV) with
per-test evidence: steps, test data, failure screenshot, video, Playwright trace, API request/response
logs, console errors and network failures. No extra command: the plugin runs on every invocation,
locally and in CI.

```
pytest -m registration                 # -> reports/runs/<timestamp>_registration/html/index.html
.\run_modules.ps1                      # one report per module + reports/index.html listing them
pytest examples/reporting_demo         # offline showcase of every status (no UAT traffic)
```

---

## 1. Folder structure

```
sprintnxt-automation/
├── reporting/                      # the reporting framework (reusable, no project-specific imports required)
│   ├── __init__.py                 # public API: tc, step, report, block
│   ├── plugin.py                   # pytest hooks + fixtures (the "reporter")
│   ├── collector.py                # per-test collector, @step, report.* facade
│   ├── capture.py                  # browser listeners: console, page errors, HTTP 4xx/5xx, API calls
│   ├── classify.py                 # status mapping + failure categories
│   ├── metadata.py                 # @tc catalogue metadata + smart fallbacks
│   ├── models.py                   # typed records (dataclasses)
│   ├── redact.py                   # secret masking
│   ├── settings.py                 # env/CLI configuration, CI detection
│   ├── storage.py                  # run folders, history, latest copy, retention
│   ├── exporters.py                # JSON, CSV, PDF
│   ├── html_report.py              # renders the single-file HTML + reports/index.html
│   └── templates/                  # report.html, report.css, report.js (charts, filters, modal …)
├── examples/reporting_demo/        # offline demo suite
├── run_modules.ps1                 # module-wise runner
├── ci/github-actions-ui-tests.yml  # CI example
└── reports/                        # generated (safe to delete)
    ├── index.html                  # every run, newest first
    ├── history/history.json        # trend + per-test history
    ├── latest/                     # copy of the most recent run
    └── runs/2026-10-15_14-30-05_registration/
        ├── html/index.html         # the report
        ├── html/report.pdf  html/summary.pdf
        ├── json/results.json  json/results.csv
        ├── screenshots/  videos/  traces/  attachments/
        └── logs/execution.log  logs/browser.log
```

Each execution gets its own folder, so module-wise runs never overwrite each other. `reports/latest`
is a *copy* (not a symlink) so it works on Windows without admin rights and inside CI artifacts.

## 2. What each test row contains

| Requirement | Where it comes from |
|---|---|
| Test Case ID, Name | `@tc("REG-001", "…")`; otherwise auto ID `<MODULE>-<hash>` and the docstring / function name |
| Module, Feature/Flow | `@tc(module=…, feature=…)`; otherwise the module marker (`registration` → Registration) and file name |
| Type of test case | `@tc(types=[…])`; otherwise markers (`smoke`→Smoke, `negative`→Negative, `security`→Security …) |
| Preconditions | `@tc(preconditions=[…])`; otherwise derived from fixtures used (`logged_in_page` → "Seeded merchant is logged in") |
| Test data used | `parametrize` values automatically + `report.data(key, value)` + arguments of `@step` methods |
| Steps executed | `@step` on page-object methods / `with step("…")`, nested, timed, with failing step marked; navigations logged automatically |
| Expected / Actual result | `@tc(expected=…)`; actual is derived from the outcome or set with `report.actual("…")` |
| Final status | PASS / FAIL / BLOCKED / SKIPPED (see §5) |
| Failure reason, stack trace | Exception message (Playwright "Call log" trimmed) + full traceback |
| Screenshot on failure | Taken at the moment of failure while the page is alive; thumbnail + full-size modal |
| Video, trace | pytest-playwright `--video/--tracing retain-on-failure`, moved into the run folder |
| Start / end / duration | Per test (setup → teardown) |
| Browser, environment, executed by, build | Browser name + version from Playwright; the rest from env / CI (see §6) |
| API request/response logs | Every XHR/fetch: method, URL, status, timing, headers, bodies (JSON pretty-printed, secrets masked) |
| Console errors | `console.error/warning` and uncaught page exceptions |
| Network failures | HTTP 4xx/5xx and transport failures (`net::ERR_*`) |

## 3. Integration (already done in this repo)

1. **Register the plugin** in the root `conftest.py`:
   ```python
   pytest_plugins = ["reporting.plugin"]
   ```
   That alone gives you the report, failure screenshots, console/network/API capture, history and exports.
2. **Record steps in page objects** (once per method; every test using it benefits):
   ```python
   from reporting import step

   class RegistrationPage(BasePage):
       @step("Enter email '{email}'")          # {placeholders} are filled from the arguments
       def fill_email(self, email): ...
   ```
   Inside a test you can also write `with step("Verify the toast"): ...`.
3. **Add catalogue metadata to tests** (optional but recommended):
   ```python
   from reporting import tc, report

   @tc("REG-001", "Register a new merchant with valid details", feature="Merchant signup",
       types=["Functional", "Smoke"], preconditions=["Signup page is open"],
       expected="'Registration Successful' page is shown")
   def test_register_happy_path(reg):
       report.data("person", person)           # shows in the Test Data table
       ...
   ```
   Parametrized tests get the param id appended: `REG-003[missing-at]`.
4. **Mark precondition gaps as BLOCKED** instead of SKIPPED:
   ```python
   from reporting import block
   if not config.admin_user:
       block("Admin credentials not configured")
   ```
5. **Extra evidence when useful**: `report.screenshot("After submit")`, `report.attach("payload", body=json_text, mime="application/json")`, `report.note("…")`. The `reporter` fixture returns the same object, the equivalent of Playwright Test's `test.info()`.

### Playwright Test → pytest mapping

| Playwright Test (TS) | Here |
|---|---|
| `test.beforeEach` / `afterEach` | `pytest_runtest_setup` / `pytest_runtest_makereport` hooks in `reporting/plugin.py` |
| Custom reporter (`onTestEnd`, `onEnd`) | `pytest_runtest_logfinish`, `pytest_sessionfinish` |
| `test.info()`, `testInfo.attach()` | `reporter` fixture / `report.attach()` |
| `test.step()` | `@step` / `with step()` |
| fixtures | pytest fixtures; the plugin wraps `new_context` to attach listeners |
| `screenshot/video/trace: 'retain-on-failure'` | `--video/--tracing retain-on-failure` in `pytest.ini` + own failure screenshot |
| `retries` | `--reruns N` (pytest-rerunfailures), attempts merged into one row |
| `workers` | `-n auto` (pytest-xdist), worker results merged by the controller |

## 4. Running

```powershell
pytest                                     # full suite -> run name "full-suite"
pytest -m registration                     # run name = marker expression
pytest tests/test_login.py --report-name "Login smoke"
pytest -m login --reruns 2                 # retries recorded per attempt; flaky tests flagged
pytest -n auto                             # parallel; one merged report
pytest --report-no-pdf                     # skip PDF (saves ~3 s)
pytest --no-html-report                    # disable the reporter entirely
pytest --video=off --tracing=off           # faster local loop (pytest.ini enables both on failure)
.\run_modules.ps1 -Modules registration,login -Workers 2 -Reruns 1
```

The terminal prints the report path at the end of every run.

## 5. Status and failure rules

| Status | When |
|---|---|
| PASS | Test body passed (an `xfail` that unexpectedly passes is also PASS) |
| FAIL | Assertion or error in the test body, or a teardown error |
| BLOCKED | A fixture/setup step errored (page didn't open, seed service down …), `block("…")` was called, or a test module failed to import |
| SKIPPED | `pytest.skip(...)`, skip markers, or `xfail` (expected failure, reason shown) |

Pass percentage = passed ÷ (total − skipped).

Failure categories (chart + Failures tab): Assertion Failure, Element Not Found / Not Actionable,
Timeout, Rate Limited (HTTP 429), Server Error (5xx), Navigation / Network, Setup / Precondition,
Precondition Not Met, Teardown Error, Collection / Import Error, Script / Unexpected Error.

## 6. Configuration (env vars or `.env`)

| Variable | Default | Purpose |
|---|---|---|
| `SNXT_ENV` | derived from the base URL (`uat` → UAT) | Environment label |
| `SNXT_BUILD_VERSION` | CI build number, else `local` | Build / release version |
| `SNXT_EXECUTED_BY` | CI actor, else OS user | Executed by |
| `SNXT_PROJECT_NAME` | `SprintNXT` | Report title |
| `SNXT_REPORT_DIR` | `reports` | Output root (`--report-dir` overrides) |
| `SNXT_REPORT_PDF` | `true` | Server-side PDF (`--report-no-pdf` overrides) |
| `SNXT_REPORT_EMBED_SCREENSHOTS` | `false` | Inline screenshots as base64 → HTML is one portable file |
| `SNXT_REPORT_FULL_PAGE` | `true` | Full-page failure screenshots |
| `SNXT_REPORT_COPY_LATEST` | `true` | Refresh `reports/latest` |
| `SNXT_REPORT_KEEP_RUNS` | `0` (keep all) | Delete older run folders beyond N |
| `SNXT_REPORT_KEEP_MEDIA` | `1` (latest only) | Only the newest N runs keep `screenshots/` and `videos/`; older ones are deleted after each run (`0` = keep all). Their `summary.pdf` keeps the embedded example screenshots |
| `SNXT_REPORT_HISTORY` | `30` | Runs kept for the trend chart |
| `SNXT_REPORT_TEST_HISTORY` | `10` | Per-test history dots |
| `SNXT_REPORT_MAX_EVENTS` | `200` | Max console/network/API entries per test |
| `SNXT_REPORT_API_BODY_LIMIT` | `4000` | Characters kept per request/response body |
| `SNXT_REPORT_API_FILTER` | all XHR/fetch | Regex: only log matching API URLs (e.g. `/api/`) |
| `SNXT_REPORT_IGNORE_ABORTED` | `true` | Ignore `ERR_ABORTED` (requests cancelled by navigation) |

**Secrets.** Values of any env var whose name contains PASS / PASSWORD / SECRET / TOKEN / API_KEY are
replaced with `••••••` everywhere in the report, logs and exports. `Authorization`, `Cookie` and similar
headers, and JSON keys such as `access_token`, are masked too. Generated test data (random emails,
invalid passwords under test) is **not** masked, because it is the evidence.

CI metadata (build number, actor, pipeline link) is detected automatically on GitHub Actions,
Azure DevOps, GitLab CI and Jenkins.

## 7. The HTML report

* **Dashboard**: pass percentage, total / passed / failed / blocked / skipped, duration, modules,
  browser, environment, build, executed by. Click a tile to filter.
* **Charts** (pure SVG/CSS, no CDN, works offline): result distribution donut, module-wise stacked
  bars, failure categories, pass-rate trend across runs. Every chart has hover tooltips and a *Table* toggle.
* **Test cases**: search (`/` focuses it; matches ID, name, module, error text and test data),
  status chips (Ctrl-click = only that status), module / type / feature / failure-category filters,
  7 sort orders, group by module, expand/collapse all, per-test history dots, deep links (`#test=<nodeid>`).
  Rows render lazily, so suites with thousands of tests stay fast.
* **Test details**: preconditions, test data, expected vs actual, failure reason + category,
  execution facts, then tabs for steps, screenshots & media (thumbnail → full-screen modal with ←/→),
  stack trace, API calls, console errors, network failures, captured output, attempts.
* **Failures**: grouped by category with reason and screenshot thumbnail.
* **Retries & flaky**: per-attempt outcomes, tests that passed on retry, tests whose status keeps
  changing across runs.
* **Run details**: environment, versions, command line, CI link, full run history with links.
* **Dark / light theme** (follows the OS, toggle persists).
* **Shareable PDF**: `html/summary.pdf` (about 10–15 pages, under 1 MB) contains the run overview, module table,
  grouped failure reasons, every test with its status and the step it failed at, and one screenshot per
  failure reason. Send it to people who don't need the interactive report. To rebuild it for an older run:
  `python -m reporting.summary_pdf reports/runs/<run>`.
* **Exports**: PDF (generated `report.pdf`, the full print layout with failures expanded), HTML (single
  file), CSV of the current filtered view, full JSON. `json/results.csv` holds every test.

## 8. Playwright traces

Failed tests keep `traces/<id>_a1_1.zip`. The report shows a copy-ready command:

```
playwright show-trace "reports/runs/<run>/traces/<id>_a1_1.zip"
```

Or drop the zip on https://trace.playwright.dev (it runs locally in the browser).

## 9. CI/CD

See `ci/github-actions-ui-tests.yml`: a matrix job per module, `if: always()` upload of `reports/latest`,
and an optional cache of `reports/history` so the trend chart spans pipeline runs. For Jenkins or
Azure DevOps, archive `reports/latest/**` (or the whole `reports/` folder) as a build artifact.
The report never changes pytest's exit code.

## 10. Troubleshooting

* **No API calls / console entries**: they're captured for contexts created through pytest-playwright's
  `page` / `context` / `new_context` fixtures. A browser you launch manually isn't watched; call
  `reporter.watch_context(ctx)` for it.
* **PDF missing**: PDF needs Playwright Chromium (`python -m playwright install chromium`). A PDF
  failure is logged and never breaks the run.
* **`reports/latest` not refreshed on Windows**: a file in it was open (e.g. the video). Close it and
  re-run; the timestamped run folder is always complete.
* **Screenshots missing when sharing a single HTML file**: set `SNXT_REPORT_EMBED_SCREENSHOTS=true`,
  or share the whole run folder.
