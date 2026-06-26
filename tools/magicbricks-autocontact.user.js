// ==UserScript==
// @name         prop-search · MagicBricks auto-contact
// @namespace    https://github.com/your/prop-search
// @version      1.6.0
// @description  When prop-search opens a MagicBricks listing with the ?psac= flag, click "Contact Owner" automatically, report the real result back to the prop-search tab, and close. Runs ONLY in your own logged-in browser session.
// @match        https://www.magicbricks.com/propertyDetails/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

/*
 * HOW IT FITS TOGETHER
 *  - prop-search's Contact button does:  window.open(listingUrl + "&psac=<listingId>.<nonce>")
 *  - This script runs ON magicbricks.com (the only place allowed to click its buttons —
 *    cross-origin JS from prop-search cannot, by the Same-Origin Policy).
 *  - It hooks fetch/XHR so it can SEE the real /mbcontact/initiateContact response — that
 *    network call is the ground truth that a contact actually went through.
 *  - It clicks "Contact Owner", waits for that response, then postMessage()s the outcome
 *    back to the opener (prop-search) and closes the tab. prop-search marks contacted only
 *    on a confirmed success.
 *
 * No tokens, no scraping — it just drives a click you could do by hand, in your own session.
 */
(function () {
  "use strict";

  // ---- read the prop-search flag out of MagicBricks' non-standard URL (`&id=..&psac=..`)
  const flag = /[?&]psac=([^&#]+)/.exec(location.href);
  if (!flag) return; // normal browsing — do nothing
  const [listingId, nonce] = decodeURIComponent(flag[1]).split(".");

  const TAG = "[ps-autocontact]";
  // DEBUG: while tuning, keep the tab OPEN on failure (so you can read the banner/console)
  // and dump every clickable element's text. Flip to false once auto-click works.
  const DEBUG = true;
  const CONTACT_API = "/mbcontact/initiateContact";
  const API_WAIT_MS = 25000; // how long to wait for the contact API after clicking
  const CLICK_RETRY_MS = 600; // poll interval while waiting for the button to appear
  const CLICK_GIVEUP_MS = 15000; // stop hunting for the button after this
  const log = (...a) => console.log(TAG, ...a);

  // ---------------------------------------------------------------- API interception
  // Resolve `apiDone` the moment MagicBricks' own initiateContact call comes back, with the
  // real HTTP status + parsed body. Installed at document-start so it catches the response
  // no matter when their page fires it.
  let resolveApi;
  const apiDone = new Promise((res) => (resolveApi = res));
  const settleApi = (ok, detail) => resolveApi({ ok, detail });

  const judge = (status, bodyText) => {
    let body = null;
    try { body = JSON.parse(bodyText); } catch { /* non-JSON response */ }
    // Success = 2xx and nothing in the body that looks like an error/limit. MagicBricks
    // returns a limit message ("contact limit", "exceeded") in-band on HTTP 200, so check it.
    const blob = (bodyText || "").toLowerCase();
    const limited = /limit|exceed|maximum|not allowed|please login|unauthor/i.test(blob);
    const ok = status >= 200 && status < 300 && !limited;
    return { ok, detail: body?.message || body?.msg || (limited ? blob.slice(0, 160) : `HTTP ${status}`) };
  };

  const origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (input, init) {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      if (DEBUG && url) log("fetch →", url);
      const p = origFetch.apply(this, arguments);
      if (url.includes(CONTACT_API)) {
        p.then((resp) => resp.clone().text().then((t) => {
          const v = judge(resp.status, t);
          log("initiateContact (fetch) →", resp.status, v.ok ? "OK" : "FAIL", v.detail);
          settleApi(v.ok, v.detail);
        })).catch((e) => settleApi(false, "fetch read error: " + e));
      }
      return p;
    };
  }

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    if (DEBUG && url) log("xhr →", url);
    this.__psContact = String(url || "").includes(CONTACT_API);
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    if (this.__psContact) {
      this.addEventListener("loadend", () => {
        const v = judge(this.status, this.responseText);
        log("initiateContact (xhr) →", this.status, v.ok ? "OK" : "FAIL", v.detail);
        settleApi(v.ok, v.detail);
      });
    }
    return origSend.apply(this, arguments);
  };

  // ---------------------------------------------------------------- reporting back
  let reported = false;
  function report(ok, error) {
    if (reported) return;
    reported = true;
    const msg = { source: "ps-autocontact", listingId, nonce, ok, error: error || null };
    try { if (window.opener) window.opener.postMessage(msg, "*"); } catch (e) { log("postMessage failed", e); }
    log("reported", msg);
    // Close on success always. On failure, keep the tab open while DEBUG so you can read
    // the banner + console and tell me the real button text.
    if (ok || !DEBUG) {
      setTimeout(() => { try { window.close(); } catch { /* ignore */ } }, 800);
    }
  }

  /** Log every visible clickable element's text — the list we match the CTA against. */
  function dumpClickables() {
    const rows = clickables()
      .filter(visible)
      .map((el) => `${el.tagName.toLowerCase()}${el.className ? "." + String(el.className).trim().replace(/\s+/g, ".") : ""} — ${(el.innerText || el.value || "").trim().replace(/\s+/g, " ").slice(0, 60)}`)
      .filter((r) => !r.endsWith("— "));
    // One multi-line string so it copy-pastes cleanly (console.table doesn't).
    log(`visible clickable elements (${rows.length}):\n` + rows.join("\n"));
  }

  // ---------------------------------------------------------------- the click
  // Find a visible element whose text looks like the owner-contact CTA. MagicBricks markup
  // shifts, so match on text, not a brittle class. TUNE the patterns here against the live
  // page if a listing fails to auto-click (watch the console with the banner showing).
  const CTA_RE = /\b(contact\s+(owner|agent|builder|dealer|now)|get\s+(owner|phone|contact)|view\s+phone)\b/i;

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
  };
  const clickables = () =>
    Array.from(document.querySelectorAll('button, a, [role="button"], input[type="submit"], div[onclick]'));
  const findByText = (re) =>
    clickables().find((el) => visible(el) && re.test((el.innerText || el.value || "").trim()));

  // The MAIN listing's contact CTA carries the LDP action class — prefer it over the
  // "Contact Agent" buttons inside recommended/similar-property sections (which would
  // contact the wrong listing). Fall back to a plain text match if the class moves.
  const findCta = () => {
    const main = Array.from(document.querySelectorAll(".mb-ldp__action--btn, [class*='ldp__action--btn']"))
      .find((el) => visible(el) && CTA_RE.test((el.innerText || "").trim()));
    return main || findByText(CTA_RE);
  };

  function banner(text, color) {
    let b = document.getElementById("ps-ac-banner");
    if (!b) {
      b = document.createElement("div");
      b.id = "ps-ac-banner";
      b.style.cssText =
        "position:fixed;z-index:2147483647;top:0;left:0;right:0;padding:10px 14px;" +
        "font:700 14px system-ui,sans-serif;text-align:center;color:#fff;";
      document.documentElement.appendChild(b);
    }
    b.style.background = color;
    b.textContent = "prop-search auto-contact: " + text;
  }

  async function run() {
    banner("locating Contact button…", "#2563eb");
    const start = Date.now();
    let cta = null;
    while (Date.now() - start < CLICK_GIVEUP_MS) {
      cta = findCta();
      if (cta) break;
      await new Promise((r) => setTimeout(r, CLICK_RETRY_MS));
    }
    if (!cta) {
      banner("couldn't find the Contact button — see console; click it yourself", "#b91c1c");
      dumpClickables(); // <-- paste this console output to tune CTA_RE
      return report(false, "contact button not found");
    }
    log("found + clicking CTA:", cta.tagName.toLowerCase() + "." + String(cta.className).trim().replace(/\s+/g, "."),
        "→", (cta.innerText || "").trim().slice(0, 40));
    cta.click();
    banner("contacting owner…", "#2563eb");

    // One real click on "Contact Agent" fires initiateContact directly (a confirmation popup
    // opens afterwards but is unrelated — we must NOT touch it). So we just wait for the
    // request; no submit-button hunting.

    // Wait for the real initiateContact response (ground truth), or time out.
    const timeout = new Promise((res) => setTimeout(() => res({ ok: null }), API_WAIT_MS));
    const res = await Promise.race([apiDone, timeout]);
    if (res.ok === true) { banner("contacted ✓", "#059669"); return report(true); }
    if (res.ok === false) { banner("MagicBricks declined: " + (res.detail || ""), "#b91c1c"); return report(false, res.detail || "contact rejected"); }
    banner("no confirmation from MagicBricks — verify manually", "#b45309");
    return report(false, "no initiateContact response (timed out)");
  }

  const boot = () => run().catch((e) => report(false, "script error: " + e));
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
