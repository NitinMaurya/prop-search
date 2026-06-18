"""One-time interactive MagicBricks login (D22).

Opens a REAL browser window using the scraper's persistent profile (PROFILE_DIR). Log in
to magicbricks.com normally (mobile OTP and all), then CLOSE the window. The session is
saved in the profile, so the headless scraper is logged in on every later run — no cookie
pasting, no keychain hacks. Run:  python mb_login.py
"""

import os
import sys

from scrapers.magicbricks import HOMEPAGE, PROFILE_DIR
from scrapers.nineacres import _HAVE_PLAYWRIGHT, USER_AGENT, VIEWPORT, sync_playwright


def main() -> int:
    if not _HAVE_PLAYWRIGHT or sync_playwright is None:
        print("Playwright isn't installed. Run: pip install playwright && "
              "playwright install chromium")
        return 1
    os.makedirs(PROFILE_DIR, exist_ok=True)
    marker = os.path.join(PROFILE_DIR, ".mb_logged_in")
    auth_markers = ("USERAUTHSESSIONID", "ACEGI_SECURITY_HASHED_REMEMBER_ME_COOKIE")
    print("Opening MagicBricks — log in (mobile OTP). The window closes automatically "
          "once login is detected; or close it yourself when done.")
    logged_in = False
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, user_agent=USER_AGENT, viewport=VIEWPORT,
            locale="en-IN", args=["--disable-blink-features=AutomationControlled"])
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(HOMEPAGE, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001
            print(f"(navigation warning: {e})")
        # Poll up to ~15 min for the login cookie; stop early if the user closes the window.
        for _ in range(450):
            try:
                names = {c["name"] for c in context.cookies("https://www.magicbricks.com")}
            except Exception:  # noqa: BLE001 - window closed
                break
            if names & set(auth_markers):
                logged_in = True
                break
            try:
                page.wait_for_timeout(2000)
            except Exception:  # noqa: BLE001 - window closed
                break
        try:
            context.close()
        except Exception:  # noqa: BLE001
            pass
    if logged_in:
        with open(marker, "w") as f:
            f.write("ok")
        print("LOGIN_OK — session saved. You can refresh listings now.")
        return 0
    if os.path.exists(marker):
        os.remove(marker)
    print("LOGIN_NOT_DETECTED — no login cookie found. Re-run and complete the login.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
