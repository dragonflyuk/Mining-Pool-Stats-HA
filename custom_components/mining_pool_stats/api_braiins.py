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

# Set to True temporarily to dump the raw profile to the HA log
_DEBUG_PROFILE = False


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
            profile = data["btc"]
            if _DEBUG_PROFILE:
                _LOGGER.warning(
                    "mining_pool_stats DEBUG — Braiins profile keys: %s  |  full btc dict: %s",
                    list(profile.keys()),
                    profile,
                )
            return profile
        return None

    async def get_workers(self) -> dict | None:
        """Return the unwrapped workers dict, or None on failure."""
        data = await self._get("/accounts/workers/json/btc")
        if data and "btc" in data:
            return data["btc"]
        return None

    async def get_rewards(self) -> dict | None:
        """Return the unwrapped daily rewards dict, or None on failure."""
        data = await self._get("/accounts/rewards/json/btc")
        if data and "btc" in data:
            return data["btc"]
        return None

    async def validate(self) -> bool:
        """Return True if the API key is valid (profile fetch succeeds)."""
        return await self.get_user_profile() is not None


def extract_braiins_hashrate_ths(profile: dict, field: str) -> float | None:
    """Extract a named hashrate field from a Braiins profile and return TH/s.

    Handles two possible API formats:
      1. Nested object: {"value": 150.5, "unit": "TH"}
      2. Flat float/int alongside a shared unit field
         e.g. profile["hashrate_5m"] = 150.5, profile["hash_rate_unit"] = "TH"
    """
    try:
        hr = profile.get(field)
        if hr is None:
            return None

        # --- Format 1: nested dict {"value": ..., "unit": ...} ---
        if isinstance(hr, dict):
            return _to_ths(hr.get("value"), hr.get("unit"))

        # --- Format 2: plain numeric, look for a shared unit field ---
        if isinstance(hr, (int, float)):
            unit = (
                profile.get("hash_rate_unit")
                or profile.get("hashrate_unit")
                or "TH"  # safe default — pool.braiins.com reports in TH/s
            )
            return _to_ths(float(hr), unit)

    except Exception:
        _LOGGER.exception("Error extracting Braiins hashrate field %s", field)

    return None


def extract_braiins_estimated_24h_btc(profile: dict, rewards: dict) -> float | None:
    """Estimate 24 h BTC: mean(total_reward / hash_rate_24h) × hash_rate_24h.

    The rewards API has no per-day hashrate, so hash_rate_24h is used as a
    constant proxy.  Averaging the per-TH/s rate across all returned days
    then scaling back to current average hashrate follows the same pattern
    as the PowerPool calculation.
    """
    if not rewards or not profile:
        return None

    hashrate_24h = extract_braiins_hashrate_ths(profile, "hash_rate_24h")
    if not hashrate_24h or hashrate_24h <= 0:
        return None

    daily = rewards.get("daily_rewards")
    if not isinstance(daily, list) or not daily:
        return None

    rates: list[float] = []
    for entry in daily:
        raw = entry.get("total_reward")
        if raw is None:
            continue
        try:
            btc = float(raw)
        except (TypeError, ValueError):
            continue
        if btc < 0:
            continue
        rates.append(btc / hashrate_24h)

    if not rates:
        return None

    avg_rate = sum(rates) / len(rates)
    return round(avg_rate * hashrate_24h, 8)
