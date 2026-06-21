"""Telegram notifier (D6) — push new matches.

Only un-notified matches above threshold are sent; caller marks them notified after.
Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env (see .env.example).

Public surface (build step 5):
  send_matches(matches: list[dict]) -> list[int]
    Sends one Telegram message per match; returns the list of match_id values that
    were sent OK (so the caller can mark them notified). Does NOT touch the DB —
    the scheduler passes in db.unnotified_matches() and calls db.mark_notified().
    Each message includes: title, price (₹ Cr), size sqm, sector, score, owner, URL.

Setup: create a bot via @BotFather, get the token; get your chat id (e.g. @userinfobot).

Implementation notes (D1: keep simple):
  - Uses the Telegram HTTP API via stdlib urllib.request (no extra dependency).
  - Missing token/chat id -> warn and return [] (pipeline keeps working unconfigured).
  - One failed send never aborts the rest (per-message try/except).
"""

import json
import logging
import os
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is a declared dep; tolerate its absence (D1 robustness)
    pass

log = logging.getLogger(__name__)

_CRORE = 10_000_000  # 1 Cr = 10,000,000 rupees
_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 10  # seconds per HTTP call


def format_match(m: dict) -> str:
    """Build a readable message for one match row (from db.unnotified_matches())."""
    title = m.get("title") or "(untitled listing)"

    price = m.get("price")
    if price:
        price_str = f"₹{price / _CRORE:.2f} Cr"
    else:
        price_str = "price n/a"

    size = m.get("size_sqm")
    size_str = f"{size:g} sqm" if size else "size n/a"

    sector = m.get("sector") or "sector n/a"

    score = m.get("score")
    score_str = f"{score * 100:.0f}%" if score is not None else "n/a"

    owner = m.get("owner") or "—"
    url = m.get("url") or ""

    lines = [
        f"🏠 {title}",
        f"💰 {price_str}   📐 {size_str}",
        f"📍 {sector}",
        f"🎯 Match: {score_str}   👤 {owner}",
    ]
    if url:
        lines.append(url)
    return "\n".join(lines)


def _send_one(token: str, chat_id: str, text: str) -> None:
    """POST a single message to the Telegram HTTP API. Raises on failure."""
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        _API.format(token=token),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API returned not-ok: {body}")


def send_matches(matches: list[dict]) -> list[int]:
    """Send one Telegram message per match. Returns match_ids sent successfully.

    Does not call the DB. If Telegram isn't configured, logs a warning and returns
    [] so the rest of the pipeline keeps working (D1).
    """
    if not matches:
        return []

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning(
            "Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing); "
            "skipping %d match notification(s).", len(matches))
        return []

    sent: list[int] = []
    for m in matches:
        match_id = m.get("match_id")
        try:
            _send_one(token, chat_id, format_match(m))
            if match_id is not None:
                sent.append(match_id)
        except (urllib.error.URLError, RuntimeError, ValueError, OSError) as e:
            log.warning("Failed to send match_id=%s: %s", match_id, e)
            continue  # one failure must not abort the rest
    return sent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    fake_match = {
        "match_id": 1,
        "requirement_id": 1,
        "score": 0.92,
        "owner": "nitin",
        "id": 101,
        "url": "https://www.99acres.com/noida-kothi-12345",
        "title": "4 BHK Independent Kothi, Sector 50 Noida",
        "price": 42_500_000,   # ₹4.25 Cr
        "size_sqm": 162,
        "sector": "Sector 50",
    }

    print("--- format_match() sample ---")
    print(format_match(fake_match))
    print("-----------------------------")

    # Only actually send if Telegram is configured; otherwise this warns + returns [].
    result = send_matches([fake_match])
    print(f"send_matches() returned: {result}")
