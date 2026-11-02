import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central config, overridable via environment / .env (see .env.example)."""

    def __init__(self):
        # --- URLs (adjust to the actual environment / routes) ---
        self.base_url = os.getenv("SNXT_BASE_URL", "https://uat.sprintnxt.in/NexGenV4Front")
        self.signup_path = os.getenv("SNXT_SIGNUP_PATH", "/#/auth/sign-up")
        self.login_path = os.getenv("SNXT_LOGIN_PATH", "/#/auth/login")
        self.forgot_path = os.getenv("SNXT_FORGOT_PATH", "/#/auth/forget-password")
        self.change_pw_path = os.getenv("SNXT_CHANGE_PW_PATH", "/#/manage/change-password")

        # --- Admin: NOT part of the shared screenshots. Fill via .env to enable admin tests. ---
        self.admin_url = os.getenv("SNXT_ADMIN_URL", "")
        self.admin_user = os.getenv("SNXT_ADMIN_USER", "")
        self.admin_pass = os.getenv("SNXT_ADMIN_PASS", "")

        # --- A seeded, already-activated merchant for login / password tests ---
        self.merchant_email = os.getenv("SNXT_MERCHANT_EMAIL", "")
        self.merchant_pass = os.getenv("SNXT_MERCHANT_PASS", "")

        # --- OTP (fixed UAT OTP per the test spec) ---
        self.otp = os.getenv("SNXT_OTP", "123456")

        # --- Behaviour ---
        self.headless = os.getenv("SNXT_HEADLESS", "true").lower() == "true"
        self.slow_mo = int(os.getenv("SNXT_SLOWMO", "0"))
        self.default_timeout_ms = int(os.getenv("SNXT_TIMEOUT_MS", "15000"))

        # --- Password policy (from the UI: 12-15 chars, 1 upper, 1 lower, 1 digit, 1 special) ---
        self.pw_min_len = 12
        self.pw_max_len = 15
