"""Foreign-exchange rate helpers.

Uses the free Frankfurter API (https://www.frankfurter.app/) — no key required.
"""

import asyncio
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

_FX_URL = "https://api.frankfurter.app/latest"


async def get_usd_to_gbp(session: aiohttp.ClientSession) -> float | None:
    """Return the current USD → GBP conversion rate, or None on failure.

    Calls GET https://api.frankfurter.app/latest?from=USD&to=GBP
    Response: {"amount": 1.0, "base": "USD", "rates": {"GBP": 0.789...}}
    """
    try:
        async with asyncio.timeout(10):
            async with session.get(
                _FX_URL, params={"from": "USD", "to": "GBP"}
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                rate = data.get("rates", {}).get("GBP")
                if rate is not None:
                    return float(rate)
                _LOGGER.warning("Frankfurter response had no GBP rate: %s", data)
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.warning("FX rate fetch failed: %s", err)
    except Exception:
        _LOGGER.exception("Unexpected error fetching FX rate")
    return None
