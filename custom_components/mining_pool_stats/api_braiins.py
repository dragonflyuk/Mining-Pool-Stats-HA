"""Braiins Pool API client.

Endpoints:
  GET /accounts/profile/json/btc  — user hashrate, balances, worker counts
  GET /accounts/workers/json/btc  — per-worker details
  GET /stats/json/btc             — pool-level stats

Authentication: Pool-Auth-Token header.
All responses are wrapped: {"btc": {...actual data...}}
"""

import asyncio
import logging

import aiohttp

from .const import BRAIINS_BASE_URL, HASHRATE_TO_TH

_LOGGER = logging.getLogger(__name__)


def _to_ths(value: float | None, unit: str | None) -> float | None:
    """Convert a hashrate value to TH/s."""
    if value is None or unit is None:
        return None
    multiplier = HASHRATE_TO_TH.get(unit.upper(), 1.0)
    return round(value * multiplier, 4)


class BraiinsPoolAPI:
    """Async client for pool.braiins.com."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._headers = {"Pool-Auth-Token": api_key}

    async def _get(self, endpoint: str) -> dict | None:
        url = f"{BRAIINS_BASE_URL}{endpoint}"
        try:
            async with asyncio.timeout(15):
                async with self._session.get(url, headers=self._headers) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except aiohttp.ClientResponseError as err:
            _LOGGER.warning("Braiins API HTTP error %s for %s", err.status, url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Braiins API connection error for %s: %s", url, err)
        return None

    async def get_user_profile(self) -> dict | None:
        """Return the unwrapped user profile dict, or None on failure."""
        data = await self._get("/accounts/profile/json/btc")
        if data and "btc" in data:
            return data["btc"]
        return None

    async def get_workers(self) -> dict | None:
        """Return the unwrapped workers dict, or None on failure."""
        data = await self._get("/accounts/workers/json/btc")
        if data and "btc" in data:
            return data["btc"]
        return None

    async def validate(self) -> bool:
        """Return True if the API key is valid (profile fetch succeeds)."""
        return await self.get_user_profile() is not None


def extract_braiins_hashrate_ths(profile: dict, field: str) -> float | None:
    """Extract a named hashrate field from a Braiins profile and return TH/s.

    The profile stores hashrate objects as:
        {"value": <float>, "unit": "<HashRateUnit>"}
    e.g. {"value": 150.5, "unit": "TH"}
    """
    hr = profile.get(field)
    if not isinstance(hr, dict):
        return None
    return _to_ths(hr.get("value"), hr.get("unit"))
