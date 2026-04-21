"""PowerPool.io API client.

Endpoints:
  GET https://api.powerpool.io/api/pool             — public pool stats
  GET https://api.powerpool.io/api/user?apiKey=<k>  — private user stats

User response is keyed by username:
  {
    "<username>": {
      "hashrate":  { "<algo>": { "hashrate": float, "hashrate_units": str,
                                 "hashrate_avg": float, "hashrate_avg_units": str } },
      "balances":  [ { "coinTicker": str, "balance": float }, ... ],
      "workers":   { "<algo>": [ { "name": str, "hashrate": float, ... } ] },
      "earnings":  { "<algo>": [ { "coin_balance": float, "speed": float,
                                   "earning_timestamp": str, ... } ] },
      "payments":  [ ... ]
    }
  }
"""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from .const import HASHRATE_TO_TH, POWERPOOL_BASE_URL, SHA256_ALIASES

_LOGGER = logging.getLogger(__name__)

# Set True temporarily to dump raw earnings entries to the HA log for debugging
_DEBUG_EARNINGS = False


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


def _parse_ts(value) -> datetime | None:
    """Try to parse a timestamp string or number into an aware datetime."""
    if value is None:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, AttributeError):
        pass
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        pass
    return None


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


def pp_sha256_estimated_24h_btc(user: dict) -> float | None:
    """Estimate 24 h BTC earnings from historical payment rate × average hashrate.

    Algorithm:
      For each earnings entry the pool records the BTC paid (coin_balance) and
      the contributing hashrate (speed).  Dividing gives the rate in BTC per
      TH/s per earnings period.  The median gap between consecutive entry
      timestamps tells us the period length, from which we compute how many
      periods fit in 24 h.  Multiplying rate × periods_per_day × hashrate_avg
      gives the estimated daily BTC at the current average hashrate.
    """
    # Average hashrate used for the final scaling step
    hr_dict = user.get("hashrate", {})
    key = find_algo_key(hr_dict, SHA256_ALIASES)
    if not key:
        return None
    algo = hr_dict[key]
    hashrate_avg_ths = _to_ths(algo.get("hashrate_avg"), algo.get("hashrate_avg_units"))
    if not hashrate_avg_ths or hashrate_avg_ths <= 0:
        return None

    # Earnings entries
    earnings_dict = user.get("earnings", {})
    ekey = find_algo_key(earnings_dict, SHA256_ALIASES)
    if not ekey:
        return None
    entries = earnings_dict.get(ekey)
    if not isinstance(entries, list) or not entries:
        return None

    if _DEBUG_EARNINGS:
        _LOGGER.warning(
            "mining_pool_stats DEBUG earnings — count=%d first_3=%s",
            len(entries),
            entries[:3],
        )

    # Parse each entry: (timestamp | None, btc_earned, speed_ths)
    parsed: list[tuple[datetime | None, float, float]] = []
    for entry in entries:
        coin_balance = entry.get("coin_balance")
        speed = entry.get("speed")
        if coin_balance is None or speed is None:
            continue
        try:
            btc = float(coin_balance)
            spd = float(speed)
        except (TypeError, ValueError):
            continue
        if spd <= 0 or btc < 0:
            continue
        # Speed unit — try several field names, default to TH
        speed_unit = (
            entry.get("speed_unit")
            or entry.get("hashrate_units")
            or "TH"
        )
        spd_ths = _to_ths(spd, speed_unit)
        if spd_ths is None or spd_ths <= 0:
            spd_ths = spd  # assume already TH/s
        ts = _parse_ts(entry.get("earning_timestamp"))
        parsed.append((ts, btc, spd_ths))

    if not parsed:
        return None

    # --- Path A: use timestamps to determine period length ---
    dated = [(ts, btc, spd) for ts, btc, spd in parsed if ts is not None]

    if len(dated) >= 2:
        dated.sort(key=lambda x: x[0])
        gaps_h = [
            (dated[i + 1][0] - dated[i][0]).total_seconds() / 3600
            for i in range(len(dated) - 1)
        ]
        # Median gap is the typical period length
        median_gap_h = sorted(gaps_h)[len(gaps_h) // 2]
        if median_gap_h >= (1 / 60):  # at least 1 minute — filter out duplicates
            avg_rate = sum(btc / spd for _, btc, spd in dated) / len(dated)
            periods_per_day = 24.0 / median_gap_h
            return round(avg_rate * periods_per_day * hashrate_avg_ths, 8)

    # --- Path B: no usable timestamps — assume entries span exactly 24 h ---
    # This is a rough fallback; accuracy depends on what window the API returns.
    total_btc = sum(btc for _, btc, spd in parsed)
    avg_spd = sum(spd for _, btc, spd in parsed) / len(parsed)
    if avg_spd <= 0:
        return None
    rate_per_ths = total_btc / avg_spd
    return round(rate_per_ths * hashrate_avg_ths, 8)


def pp_btc_balance(user: dict) -> float | None:
    """BTC balance from the balances list, or None."""
    try:
        balances = user.get("balances", [])
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
