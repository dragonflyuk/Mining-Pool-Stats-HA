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
from datetime import datetime, timedelta, timezone

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

    async def get_pool_data(self) -> dict | None:
        """Return the public pool data (includes prices), or None."""
        return await self._get("/api/pool")

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


def _parse_ts(value) -> datetime | None:
    """Try to parse a timestamp string or number into an aware datetime."""
    if value is None:
        return None
    # ISO string (with or without trailing Z / offset)
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, AttributeError):
        pass
    # Unix numeric timestamp
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        pass
    return None


def pp_sha256_revenue_24h_usd(user: dict) -> float | None:
    """Best available SHA-256 daily revenue in USD.

    Priority order:
    1. estimated_24h_usd_revenue from the hashrate dict — this is what the
       PowerPool dashboard displays and is the most accurate live figure.
    2. If that is zero or missing (miner offline / hashrate dropped to zero),
       fall back to the most recent earnings entry so the value stays stable
       rather than collapsing to zero and corrupting kWh calculations.
    3. Return None only when both sources are entirely absent.
    """
    # --- 1. Server-side estimate (matches the website) ---
    hr_dict = user.get("hashrate", {})
    key = find_algo_key(hr_dict, SHA256_ALIASES)
    if key:
        estimated = hr_dict[key].get("estimated_24h_usd_revenue")
        if estimated is not None:
            try:
                val = float(estimated)
                if val > 0:
                    return round(val, 2)
            except (TypeError, ValueError):
                pass

    # --- 2. Fallback: most recent earnings entry (keeps value stable offline) ---
    earnings_dict = user.get("earnings", {})
    ekey = find_algo_key(earnings_dict, SHA256_ALIASES)
    if not ekey:
        return None

    entries = earnings_dict.get(ekey)
    if not isinstance(entries, list) or not entries:
        return None

    dated: list[tuple[datetime, float]] = []
    undated: list[float] = []

    for entry in entries:
        usd = entry.get("usd_value")
        if usd is None:
            continue
        ts = _parse_ts(entry.get("earning_timestamp"))
        if ts is not None:
            dated.append((ts, float(usd)))
        else:
            undated.append(float(usd))

    if dated:
        dated.sort(key=lambda x: x[0], reverse=True)
        return round(dated[0][1], 2)

    if undated:
        return round(undated[-1], 2)  # last entry in list

    return None


def pp_btc_balance(user: dict) -> float | None:
    """BTC balance from the balances list, or None."""
    try:
        balances = user.get("balances", [])
        # Gracefully handle both list and dict formats
        if isinstance(balances, dict):
            balances = balances.values()
        for entry in balances:
            if isinstance(entry, dict) and entry.get("coinTicker", "").upper() == "BTC":
                return entry.get("balance")
    except Exception:
        _LOGGER.exception("Error reading PowerPool BTC balance")
    return None


def pp_btc_price_usd(pool_data: dict) -> float | None:
    """Extract the BTC/USD spot price from the public pool response."""
    try:
        if not pool_data:
            return None
        prices = pool_data.get("prices", {})
        if not isinstance(prices, dict):
            return None
        for ticker, price in prices.items():
            if str(ticker).upper() == "BTC":
                return float(price)
        _LOGGER.debug(
            "mining_pool_stats DEBUG — pp_pool prices keys: %s", list(prices.keys())
        )
    except Exception:
        _LOGGER.exception("Error reading PowerPool BTC price")
    return None


def pp_sha256_worker_count(user: dict) -> int | None:
    """Number of workers on the SHA-256 algorithm, or None."""
    workers_dict = user.get("workers", {})
    key = find_algo_key(workers_dict, SHA256_ALIASES)
    if not key:
        return None
    workers = workers_dict[key]
    return len(workers) if isinstance(workers, list) else None
