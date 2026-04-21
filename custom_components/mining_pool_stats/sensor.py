"""Sensors for Mining Pool Stats.

Three virtual HA devices are created:
  • Braiins Pool   — hashrate averages, balances, worker counts
  • PowerPool      — hashrate, estimated revenue, BTC balance, workers
  • Mining Combined — totals across both pools
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api_braiins import extract_braiins_hashrate_ths
from .api_powerpool import (
    pp_btc_balance,
    pp_btc_price_usd,
    pp_sha256_revenue_24h_usd,
    pp_sha256_hashrate_avg_ths,
    pp_sha256_hashrate_ths,
    pp_sha256_worker_count,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TH_S = "TH/s"
BTC = "BTC"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    async_add_entities(
        [
            # --- Braiins Pool ---
            BraiinsHashrateSensor(coordinator, config_entry, "hash_rate_5m", "Hashrate (5 min)"),
            BraiinsHashrateSensor(coordinator, config_entry, "hash_rate_60m", "Hashrate (60 min)"),
            BraiinsHashrateSensor(coordinator, config_entry, "hash_rate_24h", "Hashrate (24 h)"),
            BraiinsBalanceSensor(coordinator, config_entry, "current_balance", "Balance"),
            BraiinsBalanceSensor(coordinator, config_entry, "today_reward", "Today's Reward (BTC)"),
            BraiinsTodayRewardUSDSensor(coordinator, config_entry),
            BraiinsBalanceSensor(coordinator, config_entry, "estimated_reward", "Estimated Reward"),
            BraiinsWorkerSensor(coordinator, config_entry, "ok_workers", "Workers OK"),
            BraiinsWorkerSensor(coordinator, config_entry, "low_workers", "Workers Low Hashrate"),
            BraiinsWorkerSensor(coordinator, config_entry, "off_workers", "Workers Offline"),
            BraiinsWorkerSensor(coordinator, config_entry, "dis_workers", "Workers Disconnected"),
            # --- PowerPool ---
            PowerPoolHashrateSensor(coordinator, config_entry, "current", "Hashrate (Current)"),
            PowerPoolHashrateSensor(coordinator, config_entry, "avg", "Hashrate (Average)"),
            PowerPoolRevenueSensor(coordinator, config_entry),
            PowerPoolRevenueBTCSensor(coordinator, config_entry),
            PowerPoolBTCBalanceSensor(coordinator, config_entry),
            PowerPoolWorkerCountSensor(coordinator, config_entry),
            # --- Combined ---
            CombinedHashrateSensor(coordinator, config_entry),
            CombinedWorkersSensor(coordinator, config_entry),
            CombinedRevenueUSDSensor(coordinator, config_entry),
            CombinedRevenueBTCSensor(coordinator, config_entry),
            CombinedRevenueGBPSensor(coordinator, config_entry),
            CombinedBTCBalanceSensor(coordinator, config_entry),
        ]
    )


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

class _PoolSensorBase(CoordinatorEntity, SensorEntity):
    """Shared base for all pool sensors."""

    _device_id: str
    _device_name: str
    _device_model: str

    def __init__(self, coordinator, config_entry: ConfigEntry, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{config_entry.entry_id}_{unique_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._config_entry.entry_id}_{self._device_id}")},
            name=self._device_name,
            manufacturer=self._device_model,
            model=self._device_model,
            entry_type="service",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


# ---------------------------------------------------------------------------
# Braiins Pool sensors
# ---------------------------------------------------------------------------

class _BraiinsSensorBase(_PoolSensorBase):
    _device_id = "braiins"
    _device_name = "Braiins Pool"
    _device_model = "pool.braiins.com"

    @property
    def _profile(self) -> dict | None:
        if self.coordinator.data:
            return self.coordinator.data.get("braiins", {}).get("profile")
        return None

    @property
    def available(self) -> bool:
        return super().available and self._profile is not None


class BraiinsHashrateSensor(_BraiinsSensorBase):
    """Hashrate from a named field (5m / 60m / 24h)."""

    _attr_native_unit_of_measurement = TH_S
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator, config_entry, field: str, friendly_name: str) -> None:
        super().__init__(coordinator, config_entry, f"braiins_{field}")
        self._field = field
        self._attr_name = friendly_name

    @property
    def native_value(self) -> float | None:
        if self._profile:
            return extract_braiins_hashrate_ths(self._profile, self._field)
        return None


class BraiinsBalanceSensor(_BraiinsSensorBase):
    """BTC balance / reward field. API returns these as strings — cast to float."""

    _attr_native_unit_of_measurement = BTC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bitcoin"
    _attr_suggested_display_precision = 8

    def __init__(self, coordinator, config_entry, field: str, friendly_name: str) -> None:
        super().__init__(coordinator, config_entry, f"braiins_{field}")
        self._field = field
        self._attr_name = friendly_name

    @property
    def native_value(self) -> float | None:
        if self._profile:
            val = self._profile.get(self._field)
            if val is not None:
                return float(val)
        return None


class BraiinsWorkerSensor(_BraiinsSensorBase):
    """Worker count field (ok / low / off / dis)."""

    _attr_native_unit_of_measurement = "workers"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pickaxe"

    def __init__(self, coordinator, config_entry, field: str, friendly_name: str) -> None:
        super().__init__(coordinator, config_entry, f"braiins_{field}")
        self._field = field
        self._attr_name = friendly_name

    @property
    def native_value(self) -> int | None:
        if self._profile:
            return self._profile.get(self._field)
        return None


class BraiinsTodayRewardUSDSensor(_BraiinsSensorBase):
    """Today's reward converted to USD using the BTC spot price from PowerPool."""

    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_name = "Today's Reward (USD)"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "braiins_today_reward_usd")

    @property
    def _btc_price(self) -> float | None:
        if self.coordinator.data:
            return pp_btc_price_usd(self.coordinator.data.get("pp_pool"))
        return None

    @property
    def native_value(self) -> float | None:
        try:
            if self._profile and self._btc_price:
                btc = self._profile.get("today_reward")
                if btc is not None:
                    return round(float(btc) * self._btc_price, 2)
        except Exception:
            _LOGGER.exception("Error calculating Braiins today_reward USD")
        return None


# ---------------------------------------------------------------------------
# PowerPool sensors
# ---------------------------------------------------------------------------

class _PowerPoolSensorBase(_PoolSensorBase):
    _device_id = "powerpool"
    _device_name = "PowerPool"
    _device_model = "powerpool.io"

    @property
    def _pp_data(self) -> dict | None:
        if self.coordinator.data:
            return self.coordinator.data.get("powerpool")
        return None

    @property
    def available(self) -> bool:
        return super().available and self._pp_data is not None


class PowerPoolHashrateSensor(_PowerPoolSensorBase):
    """Current or average hashrate for SHA-256."""

    _attr_native_unit_of_measurement = TH_S
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator, config_entry, variant: str, friendly_name: str) -> None:
        super().__init__(coordinator, config_entry, f"pp_hashrate_{variant}")
        self._variant = variant
        self._attr_name = friendly_name

    @property
    def native_value(self) -> float | None:
        if self._pp_data:
            if self._variant == "current":
                return pp_sha256_hashrate_ths(self._pp_data)
            return pp_sha256_hashrate_avg_ths(self._pp_data)
        return None


class PowerPoolRevenueSensor(_PowerPoolSensorBase):
    """Estimated 24 h revenue in USD."""

    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_name = "Estimated Revenue (24 h USD)"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "pp_est_revenue_usd")

    @property
    def native_value(self) -> float | None:
        if self._pp_data:
            return pp_sha256_revenue_24h_usd(self._pp_data)
        return None


class PowerPoolRevenueBTCSensor(_PowerPoolSensorBase):
    """Estimated 24 h revenue converted to BTC using the spot price from /api/pool."""

    _attr_native_unit_of_measurement = BTC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bitcoin"
    _attr_name = "Estimated Revenue (24 h BTC)"
    _attr_suggested_display_precision = 8

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "pp_est_revenue_btc")

    @property
    def _btc_price(self) -> float | None:
        if self.coordinator.data:
            return pp_btc_price_usd(self.coordinator.data.get("pp_pool"))
        return None

    @property
    def native_value(self) -> float | None:
        try:
            if self._pp_data and self._btc_price:
                usd = pp_sha256_revenue_24h_usd(self._pp_data)
                if usd is not None:
                    return round(float(usd) / self._btc_price, 8)
        except Exception:
            _LOGGER.exception("Error calculating PowerPool revenue BTC")
        return None


class PowerPoolBTCBalanceSensor(_PowerPoolSensorBase):
    """BTC balance on PowerPool."""

    _attr_native_unit_of_measurement = BTC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bitcoin"
    _attr_name = "Balance"
    _attr_suggested_display_precision = 8

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "pp_btc_balance")

    @property
    def native_value(self) -> float | None:
        if self._pp_data:
            return pp_btc_balance(self._pp_data)
        return None


class PowerPoolWorkerCountSensor(_PowerPoolSensorBase):
    """Number of SHA-256 workers on PowerPool."""

    _attr_native_unit_of_measurement = "workers"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pickaxe"
    _attr_name = "Workers"

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "pp_worker_count")

    @property
    def native_value(self) -> int | None:
        if self._pp_data:
            return pp_sha256_worker_count(self._pp_data)
        return None


# ---------------------------------------------------------------------------
# Combined sensors
# ---------------------------------------------------------------------------

class _CombinedSensorBase(_PoolSensorBase):
    _device_id = "combined"
    _device_name = "Mining Combined"
    _device_model = "Braiins Pool + PowerPool"

    @property
    def _braiins_profile(self) -> dict | None:
        if self.coordinator.data:
            return self.coordinator.data.get("braiins", {}).get("profile")
        return None

    @property
    def _pp_data(self) -> dict | None:
        if self.coordinator.data:
            return self.coordinator.data.get("powerpool")
        return None


class CombinedHashrateSensor(_CombinedSensorBase):
    """Total SHA-256 hashrate across both pools (5-min / current average)."""

    _attr_native_unit_of_measurement = TH_S
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"
    _attr_name = "Total Hashrate"

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "combined_hashrate")

    @property
    def native_value(self) -> float | None:
        braiins_hr = (
            extract_braiins_hashrate_ths(self._braiins_profile, "hash_rate_5m")
            if self._braiins_profile
            else None
        )
        pp_hr = pp_sha256_hashrate_ths(self._pp_data) if self._pp_data else None

        parts = [v for v in (braiins_hr, pp_hr) if v is not None]
        return round(sum(parts), 4) if parts else None


class CombinedWorkersSensor(_CombinedSensorBase):
    """Total workers across both pools."""

    _attr_native_unit_of_measurement = "workers"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pickaxe"
    _attr_name = "Total Workers"

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "combined_workers")

    @property
    def native_value(self) -> int | None:
        braiins_ok = (
            self._braiins_profile.get("ok_workers", 0)
            if self._braiins_profile
            else None
        )
        pp_workers = pp_sha256_worker_count(self._pp_data) if self._pp_data else None

        parts = [v for v in (braiins_ok, pp_workers) if v is not None]
        return sum(parts) if parts else None


class CombinedRevenueUSDSensor(_CombinedSensorBase):
    """Total estimated 24 h revenue in USD across both pools.

    PowerPool provides USD directly. Braiins today_reward (BTC) is converted
    using the BTC spot price from the PowerPool public API.
    """

    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_name = "Estimated Revenue (24 h USD)"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "combined_revenue_usd")

    @property
    def _btc_price(self) -> float | None:
        if self.coordinator.data:
            return pp_btc_price_usd(self.coordinator.data.get("pp_pool"))
        return None

    @property
    def native_value(self) -> float | None:
        try:
            pp_usd = pp_sha256_revenue_24h_usd(self._pp_data) if self._pp_data else None
            btc_price = self._btc_price

            braiins_usd = None
            if self._braiins_profile and btc_price:
                btc = self._braiins_profile.get("today_reward")
                if btc is not None:
                    braiins_usd = float(btc) * btc_price

            parts = [v for v in (pp_usd, braiins_usd) if v is not None]
            return round(sum(parts), 2) if parts else None
        except Exception:
            _LOGGER.exception("Error calculating combined revenue USD")
            return None


class CombinedRevenueBTCSensor(_CombinedSensorBase):
    """Total estimated 24 h revenue in BTC across both pools.

    Braiins today_reward is already BTC. PowerPool USD figure is converted
    using the BTC spot price from the PowerPool public API.
    """

    _attr_native_unit_of_measurement = BTC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bitcoin"
    _attr_name = "Estimated Revenue (24 h BTC)"
    _attr_suggested_display_precision = 8

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "combined_revenue_btc")

    @property
    def _btc_price(self) -> float | None:
        if self.coordinator.data:
            return pp_btc_price_usd(self.coordinator.data.get("pp_pool"))
        return None

    @property
    def native_value(self) -> float | None:
        try:
            raw = self._braiins_profile.get("today_reward") if self._braiins_profile else None
            braiins_btc = float(raw) if raw is not None else None

            pp_btc = None
            btc_price = self._btc_price
            if self._pp_data and btc_price:
                usd = pp_sha256_revenue_24h_usd(self._pp_data)
                if usd is not None:
                    pp_btc = float(usd) / btc_price

            parts = [v for v in (braiins_btc, pp_btc) if v is not None]
            return round(sum(parts), 8) if parts else None
        except Exception:
            _LOGGER.exception("Error calculating combined revenue BTC")
            return None


class CombinedRevenueGBPSensor(_CombinedSensorBase):
    """Total estimated 24 h revenue in GBP.

    Converts the combined USD revenue using the live USD→GBP rate
    from the Frankfurter API (fetched each coordinator update cycle).
    """

    _attr_native_unit_of_measurement = "GBP"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_name = "Estimated Revenue (24 h GBP)"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:currency-gbp"

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "combined_revenue_gbp")

    @property
    def _usd_to_gbp(self) -> float | None:
        if self.coordinator.data:
            return self.coordinator.data.get("usd_to_gbp")
        return None

    @property
    def native_value(self) -> float | None:
        try:
            usd_to_gbp = self._usd_to_gbp
            if not usd_to_gbp:
                return None

            btc_price = pp_btc_price_usd(self.coordinator.data.get("pp_pool")) if self.coordinator.data else None

            pp_usd = pp_sha256_revenue_24h_usd(self._pp_data) if self._pp_data else None

            braiins_usd = None
            if self._braiins_profile and btc_price:
                raw = self._braiins_profile.get("today_reward")
                if raw is not None:
                    braiins_usd = float(raw) * btc_price

            usd_parts = [v for v in (pp_usd, braiins_usd) if v is not None]
            if not usd_parts:
                return None
            return round(sum(usd_parts) * usd_to_gbp, 2)
        except Exception:
            _LOGGER.exception("Error calculating combined revenue GBP")
            return None


class CombinedBTCBalanceSensor(_CombinedSensorBase):
    """Total unpaid BTC balance across both pools."""

    _attr_native_unit_of_measurement = BTC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bitcoin"
    _attr_name = "Total BTC Balance"
    _attr_suggested_display_precision = 8

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry, "combined_btc_balance")

    @property
    def native_value(self) -> float | None:
        try:
            raw = self._braiins_profile.get("current_balance") if self._braiins_profile else None
            braiins_bal = float(raw) if raw is not None else None
            pp_bal = pp_btc_balance(self._pp_data) if self._pp_data else None

            parts = [v for v in (braiins_bal, pp_bal) if v is not None]
            return round(sum(parts), 8) if parts else None
        except Exception:
            _LOGGER.exception("Error calculating combined BTC balance")
            return None
