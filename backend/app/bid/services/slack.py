from __future__ import annotations

import logging

import httpx

from app.bid.settings import get_bid_settings

logger = logging.getLogger(__name__)


async def send_payout_slack(
    *,
    bidder_name: str,
    crypto_address: str,
    passed_count: int,
    amount: float,
    week_start: str,
    week_end: str,
) -> tuple[bool, str]:
    url = (get_bid_settings().slack_webhook_url or "").strip()
    if not url:
        return False, "SLACK_WEBHOOK_URL is not set"
    text = (
        f"*Bid Manage payout*\n"
        f"Bidder: {bidder_name}\n"
        f"Crypto address: {crypto_address or 'N/A'}\n"
        f"Review passed: {passed_count}\n"
        f"Amount: ${amount:,.2f}\n"
        f"Week: {week_start} → {week_end}"
    )
    payload = {"text": text}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(url, json=payload)
            if res.status_code >= 300:
                msg = f"Slack HTTP {res.status_code}: {res.text[:300]}"
                logger.warning(msg)
                return False, msg
    except Exception as exc:  # noqa: BLE001
        logger.warning("Slack payout failed: %s", exc)
        return False, str(exc)
    return True, ""
