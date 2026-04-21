"""PowerPool.io API client.

Endpoints:
  GET https://api.powerpool.io/api/pool             — public pool stats
  GET https://api.powerpool.io/api/user?apiKey=<k>  — private user stats

User response is keyed by username:
  {
    "<username>": {
      "hashrate":  { "<algo>": { "hashrate": float, "hashrate_units": str, ... } },
      "balances":  [ { "coinTicker": str, "balance": float }, ... ],
      "workers":   { "<algo>": [ { "name": str, "hashrate": float, ... } ] },
      "earnings":  { "<algo>": [ { "usd_value": float, ... } ] },
      "payments":  [ ... ]
    }
  }
"""

import asyncio
import logging

import aiohttp

from .const import HASHRATE_TO_TH, POWERPOOL_BASE_URL, SHA256_ALIASES

_LOGGER = logging.getLogger(__name__)


def _to_ths(value: float | None, unit: str | None) -> float | None:
    """Convert a hashrate value to TH/s."""
    if value is None or unit is None:
        return None
    multiplier = HASHRATE_TO_TH.get(unit.upper(), 1.0)
    return round(value * multiplier, 4)


def find_algo_key(data: dict, aliases: frozenset) -> str | None:
    """Return the first key in *data* whose normalised form appears in *aliases*."""
    for key in data:
        if key.lower().replace("-", "").replace(" ", "") in aliases:
            return key
    return next(iter(data), None)  # fallback: first key


class PowerPoolAPI:
    """Async client for api.powerpool.io."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        url = f"{POWERPOOL_BASE_URL}{endpoint}"
        try:
            async with asyncio.timeout(15):
                async with self._session.get(url, params=params) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except aiohttp.ClientResponseError as err:
            _LOGGER.warning("PowerPool API HTTP error %s for %s", err.status, url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("PowerPool API connection error for %s: %s", url, err)
        return None

    async def get_user_data(self) -> dict | None:
        """Return the inner per-user dict (first user in response), or None."""
        data = await self._get("/api/user", params={"apiKey": self._api_key})
        if not data:
            return None
        # Response is { "<username>": { ... } }
        for _username, user_data in data.items():
            return user_data
        return None

    async def validate(self) -> bool:
        """Return True if the API key is valid."""
        return await self.get_user_data() is not None


# ---------------------------------------------------------------------------
# Extraction helpers (operate on the inner user dict returned by get_user_data)
# ---------------------------------------------------------------------------

def pp_sha256_hashrate_ths(user: dict) -> float | None:
    """Current hashrate (TH/s) for SHA-256, or None."""
    hr_dict = user.get("hashrate", {})
    key = find_algo_key(hr_dict, SHA256_ALIASES)
    if not key:
        return None
    algo = hr_dict[key]
    return _to_ths(algo.get("hashrate"), algo.get("hashrate_units"))


def pp_sha256_hashrate_avg_ths(user: dict) -> float | None:
    """Average hashrate (TH/s) for SHA-256, or None."""
    hr_dict = user.get("hashrate", {})
    key = find_algo_key(hr_dict, SHA256_ALIASES)
    if not key:
        return None
    algo = hr_dict[key]
    return _to_ths(algo.get("hashrate_avg"), algo.get("hashrate_avg_units"))


def pp_sha256_est_revenue_usd(user: dict) -> float | None:
    """Estimated 24h USD revenue for SHA-256, or None."""
    hr_dict = user.get("hashrate", {})
    key = find_algo_key(hr_dict, SHA256_ALIASES)
    if not key:
        return None
    return hr_dict[key].get("estimated_24h_usd_revenue")


def pp_btc_balance(user: dict) -> float | None:
    """BTC balance from the balances list, or None."""
    for entry in user.get("balances", []):
        if entry.get("coinTicker", "").upper() == "BTC":
            return entry.get("balance")
    return None


def pp_sha256_worker_count(user: dict) -> int | None:
    """Number of workers on the SHA-256 algorithm, or None."""
    workers_dict = user.get("workers", {})
    key = find_algo_key(workers_dict, SHA256_ALIASES)
    if not key:
        return None
    workers = workers_dict[key]
    return len(workers) if isinstance(workers, list) else None
