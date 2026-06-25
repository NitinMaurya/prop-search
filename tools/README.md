# prop-search tools

## MagicBricks auto-contact userscript

`magicbricks-autocontact.user.js` lets the **Contact** button on a match card initiate the
real MagicBricks "Contact Owner" action — in *your own* logged-in browser session — and mark
the listing contacted only when MagicBricks actually confirms it.

### Why a userscript (and not the app itself)

Browsers forbid one site from clicking buttons on another (Same-Origin Policy). prop-search
can *open* a MagicBricks tab but cannot click anything inside it. Only code running **on**
magicbricks.com can — that's what this userscript is. It clicks the same button you'd click
by hand, in your session, on your IP, with your account. No tokens, no scraping, no server.

### How it works

1. The card's **Contact** button opens the listing in a new tab with a `?psac=<id>.<nonce>` flag.
2. This script (running on magicbricks.com) sees the flag, clicks **Contact Owner**, and
   watches the real `/mbcontact/initiateContact` network call for the true result.
3. It `postMessage`s success/failure back to prop-search and closes the tab.
4. prop-search marks the listing **✅ Contacted** only on a confirmed success.

### Install (one-time, per browser)

1. Install a userscript manager: **[Tampermonkey](https://www.tampermonkey.net/)** (Chrome/Edge/Firefox/Safari) or Violentmonkey.
2. Open `tools/magicbricks-autocontact.user.js` in this repo and copy its contents
   (or drag the file onto the Tampermonkey dashboard → **Utilities → Import**).
3. Tampermonkey dashboard → **+ (Create a new script)** → paste → **File → Save**.
4. Make sure you're **logged into magicbricks.com** in the same browser.

That's it. Click **Contact** on a card — a MagicBricks tab opens, auto-clicks, and closes;
the card flips to **✅ Contacted**.

### Without the script installed

Nothing breaks. The MagicBricks tab still opens; you just click **Contact Owner** yourself.
prop-search shows a one-time hint and leaves the card as-is (it only marks contacted on a
confirmed auto-contact). Re-clicking after a confirmed contact does nothing (status only).

### Tuning

MagicBricks changes its markup periodically. If a listing fails to auto-click, watch the
on-page banner + the browser console (`[ps-autocontact]` logs) and adjust the `CTA_RE` /
`SUBMIT_RE` text patterns near the top of the script. The success signal (the
`initiateContact` response) rarely changes, so detection stays reliable.
