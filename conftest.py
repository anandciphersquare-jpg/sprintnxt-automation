import pytest
from config import Config
from reporting import block

# HTML execution reporting: hooks, failure screenshots, console/network/API capture, reports/ output.
pytest_plugins = ["reporting.plugin"]


@pytest.fixture(scope="session")
def config():
    return Config()


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args, config, pytestconfig):
    # CLI flags (--headed, --slowmo) win over SNXT_HEADLESS / SNXT_SLOWMO
    headed = pytestconfig.getoption("--headed")
    slowmo = pytestconfig.getoption("--slowmo")
    return {**browser_type_launch_args,
            "headless": config.headless and not headed,
            "slow_mo": slowmo or config.slow_mo}


@pytest.fixture
def browser_context_args(browser_context_args, config):
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "viewport": {"width": 1440, "height": 900},
        # Record at the real window size (Playwright's default scales down to fit 800x800 -> blurry 800x500)
        "record_video_size": {"width": 1440, "height": 900},
        # App redirects to #/location-required without geolocation access
        "geolocation": {"latitude": 28.6139, "longitude": 77.2090},
        "permissions": ["geolocation"],
    }


@pytest.fixture(autouse=True)
def _default_timeout(page, config):
    page.set_default_timeout(config.default_timeout_ms)
    yield


@pytest.fixture
def merchant(config):
    """Activated merchant credentials: SNXT_MERCHANT_* from .env, else the one E2E-001 saved in .merchant.json."""
    from utils.merchant_store import load_merchant
    if config.merchant_email and config.merchant_pass:
        return {"email": config.merchant_email, "password": config.merchant_pass}
    saved = load_merchant()
    if not saved:
        block("No activated merchant: run E2E-001 (pytest -m e2e) first, or set SNXT_MERCHANT_EMAIL/PASS in .env")
    return saved


@pytest.fixture
def logged_in_page(page, config, merchant):
    """A page already logged in as the activated merchant and on the dashboard."""
    from pages.login_page import LoginPage
    login = LoginPage(page, config).open()
    login.login(merchant["email"], merchant["password"])
    if login.complete_login() is not True:
        block(f"Merchant {merchant['email']} could not reach the dashboard (url: {page.url})")
    return page
