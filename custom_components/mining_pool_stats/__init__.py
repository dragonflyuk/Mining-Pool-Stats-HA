"""Mining Pool Stats — combines Braiins Pool and PowerPool.io into HA sensors."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_braiins import BraiinsPoolAPI
from .api_powerpool import PowerPoolAPI
from .const import DOMAIN, PLATFORMS, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mining Pool Stats from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    braiins = BraiinsPoolAPI(session, entry.data["braiins_api_key"])
    powerpool = PowerPoolAPI(session, entry.data["powerpool_api_key"])

    async def async_update_data() -> dict:
        """Fetch data from both pools simultaneously."""
        braiins_profile, braiins_workers, pp_user = await asyncio.gather(
            braiins.get_user_profile(),
            braiins.get_workers(),
            powerpool.get_user_data(),
        )

        if braiins_profile is None and pp_user is None:
            raise UpdateFailed("Could not reach either pool API.")

        return {
            "braiins": {
                "profile": braiins_profile,   # unwrapped btc dict
                "workers": braiins_workers,    # unwrapped btc dict
            },
            "powerpool": pp_user,              # inner per-user dict
        }

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_coordinator",
        update_method=async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
