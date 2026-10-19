"""Instagram authentication, local session persistence, and yt-dlp cookie export."""

import os
import json
import time
import logging
from mediadhob.config import configure_runtime, redact_sensitive, write_private_text
from pathlib import Path
from datetime import datetime, timedelta

try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        LoginRequired,
        ChallengeRequired,
        TwoFactorRequired,
        BadPassword,
        PleaseWaitFewMinutes,
        RecaptchaChallengeForm,
        FeedbackRequired,
        ChallengeUnknownStep,
        SelectContactPointRecoveryForm,
    )
    HAS_INSTAGRAPI = True
except ImportError:
    HAS_INSTAGRAPI = False


logger = logging.getLogger(__name__)


class InstagramAuth:
    """
    Professional Instagram authentication using Private API.

    Features:
        - Login via username/password (no browser)
        - Session persistence (session.json) — avoids re-login on every run
        - Automatic session validation and refresh
        - 2FA support (TOTP / SMS)
        - Exports cookies in Netscape format for yt-dlp compatibility
        - Anti-detection: random delays, device fingerprint persistence
        - Challenge resolver for suspicious login attempts

    Usage:
        auth = InstagramAuth(
            username="your_user",
            password="your_pass",
            cookies_file="cookies.txt",       # Netscape output for yt-dlp
            session_file="ig_session.json",   # persistent session
        )
        success = auth.login()
        if success:
            # cookies.txt is now ready for yt-dlp
            pass
    """

    def __init__(
        self,
        username: str,
        password: str,
        cookies_file: str = "cookies.txt",
        session_file: str = "ig_session.json",
        proxy: str = None,
        locale: str = "en_US",
        timezone_offset: int = 14400,  # UTC+4 (Gulf)
        ui=None,
    ):
        if not HAS_INSTAGRAPI:
            raise ImportError(
                "instagrapi is required. Install it:\n"
                "  pip install instagrapi"
            )

        self.username = username
        self.password = password
        self.cookies_file = cookies_file
        self.session_file = session_file
        self.proxy = proxy or os.environ.get("IG_PROXY")
        self.locale = locale
        self.timezone_offset = timezone_offset
        self.ui = ui  # UIHelper instance (optional, for rich output)

        self.client = Client()
        self.client.delay_range = [1, 3]  # anti-detection: random delay between requests

        if self.proxy:
            self.client.set_proxy(self.proxy)
            self._log("info", "proxy configured")

        # Set locale/timezone to look like a real device
        self.client.set_locale(self.locale)
        self.client.set_timezone_offset(self.timezone_offset)

    # ── Logging helper ────────────────────────────────────────────────────

    def _log(self, level: str, msg: str):
        """Log to both file and optional UI."""
        for value in (self.password, self.proxy):
            if value:
                msg = msg.replace(value, "[REDACTED]")
        msg = redact_sensitive(msg)
        getattr(logger, level, logger.info)(msg)
        if self.ui:
            ui_method = getattr(self.ui, level, self.ui.info)
            ui_method(msg)

    # ── Main login flow ───────────────────────────────────────────────────

    def login(self, verification_code: str = None) -> bool:
        """
        Complete login flow with session reuse.

        Priority:
            1. Load existing session → validate → use if valid
            2. Fresh login → save session → export cookies
        """
        self._log("info", "starting instagram authentication …")

        # Step 1: Try loading saved session
        if self._try_load_session():
            self._log("info", "existing session is valid — skipping login")
            self._export_cookies_netscape()
            return True

        # Step 2: Fresh login
        self._log("info", "no valid session found — performing fresh login …")
        return self._fresh_login(verification_code)

    def _try_load_session(self) -> bool:
        """Load session from file and validate it."""
        if not os.path.exists(self.session_file):
            return False

        try:
            self._log("info", f"loading session from {self.session_file} …")
            self.client.load_settings(self.session_file)
            self.client.login(self.username, self.password)

            # Validate session with a lightweight API call
            try:
                self.client.get_timeline_feed()
                self._log("info", "session validated successfully")
                return True
            except LoginRequired:
                self._log("info", "session expired — need fresh login")
                # Reset session state before fresh login
                old_settings = self.client.get_settings()
                self.client.set_settings({})
                self.client.set_uuids(old_settings["uuids"])
                return False

        except (LoginRequired, BadPassword, ChallengeRequired) as e:
            self._log("warn", f"session load failed: {e}")
            return False
        except Exception as e:
            self._log("warn", f"unexpected session load error: {e}")
            return False

    def _fresh_login(self, verification_code: str = None) -> bool:
        """Perform a fresh login with full error handling."""
        try:
            login_kwargs = {
                "username": self.username,
                "password": self.password,
                "relogin": True,
            }
            if verification_code:
                login_kwargs["verification_code"] = verification_code

            self.client.login(**login_kwargs)

            # Save session for future use
            self._save_session()
            self._log("info", f"session saved → {self.session_file}")

            # Export cookies for yt-dlp
            self._export_cookies_netscape()

            self._log("info", "login successful")
            return True

        except TwoFactorRequired:
            self._log("warn", "2FA required — provide verification code")
            return self._handle_2fa()

        except ChallengeRequired:
            self._log("warn", "challenge required — attempting to resolve …")
            return self._handle_challenge()

        except BadPassword:
            self._log("error", "wrong password — check INSTA_PASS")
            return False

        except PleaseWaitFewMinutes:
            self._log("error", "rate limited — wait a few minutes and try again")
            return False

        except RecaptchaChallengeForm:
            self._log("error",
                "recaptcha challenge triggered — try again later or use a proxy"
            )
            return False

        except FeedbackRequired as e:
            self._log("error", f"instagram feedback required: {e}")
            return False

        except Exception as e:
            self._log("error", f"login failed: {e}")
            logger.exception("full login error traceback:")
            return False

    # ── 2FA handling ──────────────────────────────────────────────────────

    def _handle_2fa(self) -> bool:
        """Handle two-factor authentication."""
        code = None
        if self.ui:
            code = self.ui.ask("enter 2FA code from your authenticator app")
        else:
            code = input("Enter 2FA code: ").strip()

        if not code:
            self._log("error", "no 2FA code provided")
            return False

        try:
            self.client.login(
                self.username, self.password,
                verification_code=code
            )
            self._save_session()
            self._export_cookies_netscape()
            self._log("info", "2FA login successful")
            return True
        except Exception as e:
            self._log("error", f"2FA login failed: {e}")
            return False

    # ── Challenge handling ────────────────────────────────────────────────

    def _handle_challenge(self) -> bool:
        """Handle Instagram security challenge (email/SMS verification)."""
        try:
            # Get challenge info
            challenge_url = self.client.last_json.get("challenge", {}).get("api_path")
            if not challenge_url:
                self._log("error", "no challenge URL found")
                return False

            # Request challenge code
            self.client.challenge_resolve(self.client.last_json)

            # Ask user for the code
            code = None
            if self.ui:
                code = self.ui.ask(
                    "instagram sent a verification code to your email/phone — enter it"
                )
            else:
                code = input("Enter the verification code sent to your email/phone: ").strip()

            if not code:
                self._log("error", "no verification code provided")
                return False

            # Submit code
            self.client.challenge_code(code)
            self._save_session()
            self._export_cookies_netscape()
            self._log("info", "challenge resolved — login successful")
            return True

        except ChallengeUnknownStep as e:
            self._log("error", f"unknown challenge step: {e}")
            return False
        except SelectContactPointRecoveryForm:
            self._log("error",
                "instagram requires contact point recovery — "
                "log in manually on the app first, then try again"
            )
            return False
        except Exception as e:
            self._log("error", f"challenge resolution failed: {e}")
            return False

    # ── Cookie export (Netscape format for yt-dlp) ────────────────────────

    def _save_session(self):
        write_private_text(self.session_file, json.dumps(self.client.get_settings(), indent=4))

    def _export_cookies_netscape(self):
        """
        Convert instagrapi session cookies to Netscape format.
        This is the key bridge: instagrapi handles auth,
        yt-dlp uses the cookies for downloading.

        instagrapi v2.4+ stores sessionid in authorization_data,
        not in the cookies dict. We extract from multiple sources.
        """
        try:
            settings = self.client.get_settings()
            expiry_1y = str(int((datetime.now() + timedelta(days=365)).timestamp()))

            # Collect all cookies from every available source
            all_cookies = {}  # name -> {domain, path, secure, expiry, value}

            # Source 1: authorization_data (primary — contains sessionid)
            auth_data = settings.get("authorization_data", {})
            if auth_data:
                for name, value in auth_data.items():
                    if value:
                        all_cookies[name] = {
                            "domain": ".instagram.com",
                            "path": "/",
                            "secure": "TRUE",
                            "expiry": expiry_1y,
                            "value": str(value),
                        }

            # Source 2: session settings cookies dict
            cookies_dict = settings.get("cookies", {})
            for name, value in cookies_dict.items():
                if name not in all_cookies:
                    if isinstance(value, dict):
                        all_cookies[name] = {
                            "domain": value.get("domain", ".instagram.com"),
                            "path": value.get("path", "/"),
                            "secure": "TRUE" if value.get("secure", True) else "FALSE",
                            "expiry": str(int(value.get("expires", 0))),
                            "value": value.get("value", str(value)),
                        }
                    else:
                        all_cookies[name] = {
                            "domain": ".instagram.com",
                            "path": "/",
                            "secure": "TRUE",
                            "expiry": expiry_1y,
                            "value": str(value),
                        }

            # Source 3: ig_u_rur, ig_www_claim, mid from settings root
            for key in ["ig_u_rur", "ig_www_claim", "mid"]:
                val = settings.get(key)
                if val and key not in all_cookies:
                    all_cookies[key] = {
                        "domain": ".instagram.com",
                        "path": "/",
                        "secure": "TRUE",
                        "expiry": expiry_1y,
                        "value": str(val),
                    }

            # Source 4: requests session jar (runtime cookies)
            if hasattr(self.client, 'private') and hasattr(self.client.private, 'cookies'):
                for cookie in self.client.private.cookies:
                    if cookie.name not in all_cookies:
                        domain = cookie.domain or ".instagram.com"
                        if not domain.startswith('.'):
                            domain = '.' + domain
                        all_cookies[cookie.name] = {
                            "domain": domain,
                            "path": cookie.path or "/",
                            "secure": "TRUE" if cookie.secure else "FALSE",
                            "expiry": str(int(cookie.expires)) if cookie.expires else expiry_1y,
                            "value": cookie.value or "",
                        }

            if not all_cookies:
                self._log("error", "no cookies available to export from any source")
                return

            # Build Netscape format file
            lines = [
                "# Netscape HTTP Cookie File",
                "# Generated by MEDIADHOB InstagramAuth",
                f"# Date: {datetime.now().isoformat()}",
                "",
            ]

            for name, info in all_cookies.items():
                domain = info["domain"]
                if not domain.startswith('.'):
                    domain = '.' + domain
                line = "\t".join([
                    domain,
                    "TRUE",  # include subdomains
                    info["path"],
                    info["secure"],
                    info["expiry"],
                    name,
                    info["value"],
                ])
                lines.append(line)

            write_private_text(self.cookies_file, '\n'.join(lines) + '\n')

            cookie_count = len(all_cookies)
            has_sessionid = "sessionid" in all_cookies

            if has_sessionid:
                self._log("info",
                    f"cookies exported -> {self.cookies_file} "
                    f"({cookie_count} cookies, sessionid found)"
                )
            else:
                self._log("warn",
                    f"cookies exported but sessionid not found -- "
                    f"downloads may fail ({cookie_count} cookies)"
                )

        except Exception as e:
            self._log("error", f"cookie export failed: {e}")
            logger.exception("cookie export traceback:")

    # ── Session info ──────────────────────────────────────────────────────

    def get_session_info(self) -> dict:
        """Return session status information."""
        info = {
            "session_file": self.session_file,
            "session_exists": os.path.exists(self.session_file),
            "cookies_file": self.cookies_file,
            "cookies_exist": os.path.exists(self.cookies_file),
            "username": self.username,
        }

        if info["session_exists"]:
            try:
                mtime = os.path.getmtime(self.session_file)
                info["session_age_hours"] = round(
                    (time.time() - mtime) / 3600, 1
                )
            except Exception:
                pass

        if info["cookies_exist"]:
            try:
                with open(self.cookies_file, 'r') as f:
                    content = f.read()
                info["has_sessionid"] = "sessionid" in content
                info["cookie_count"] = len([
                    l for l in content.splitlines()
                    if l.strip() and not l.startswith('#')
                ])
            except Exception:
                pass

        return info

    def force_refresh(self) -> bool:
        """
        Force a complete re-login (delete session and re-authenticate).
        Use when cookies are stale or downloads fail.
        """
        self._log("info", "forcing complete re-authentication …")

        # Delete existing session
        for f in [self.session_file, self.cookies_file]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                    self._log("info", f"deleted {f}")
                except Exception as e:
                    self._log("warn", f"could not delete {f}: {e}")

        # Reset client
        self.client = Client()
        self.client.delay_range = [1, 3]
        if self.proxy:
            self.client.set_proxy(self.proxy)
        self.client.set_locale(self.locale)
        self.client.set_timezone_offset(self.timezone_offset)

        return self._fresh_login()


# ══════════════════════════════════════════════════════════════════════════════
#  Standalone test
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    configure_runtime()

    username = os.environ.get("INSTA_USER")
    password = os.environ.get("INSTA_PASS")

    if not username or not password:
        print("Set INSTA_USER and INSTA_PASS in .env file")
        sys.exit(1)

    auth = InstagramAuth(
        username=username,
        password=password,
        cookies_file="cookies.txt",
        session_file="ig_session.json",
    )

    print(f"\n{'='*50}")
    print(f"  Instagram Auth — No Browser Required")
    print(f"{'='*50}\n")

    success = auth.login()

    if success:
        info = auth.get_session_info()
        print(f"\n  Login successful")
        print(f"  Cookies: {info.get('cookie_count', '?')} exported")
        print(f"  sessionid: {'found' if info.get('has_sessionid') else 'MISSING'}")
        print(f"  File: {info['cookies_file']}")
    else:
        print(f"\n  Login failed — check logs")

    print()
