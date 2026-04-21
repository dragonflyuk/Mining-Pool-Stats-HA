"""Config flow for Mining Pool Stats."""

import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api_braiins import BraiinsPoolAPI
from .api_powerpool import PowerPoolAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_SCHEMA = vol.Schema(
    {
        vol.Required("braiins_api_key"): str,
        vol.Required("powerpool_api_key"): str,
    }
)


class MiningPoolStatsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Mining Pool Stats."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Show the setup form and validate both API keys."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            braiins_key = user_input["braiins_api_key"].strip()
            pp_key = user_input["powerpool_api_key"].strip()

            braiins_ok, pp_ok = False, False

            try:
                braiins_ok = await BraiinsPoolAPI(session, braiins_key).validate()
            except (aiohttp.ClientError, Exception):  # noqa: BLE001
                pass

            try:
                pp_ok = await PowerPoolAPI(session, pp_key).validate()
            except (aiohttp.ClientError, Exception):  # noqa: BLE001
                pass

            if not braiins_ok and not pp_ok:
                errors["base"] = "both_invalid"
            elif not braiins_ok:
                errors["braiins_api_key"] = "invalid_auth"
            elif not pp_ok:
                errors["powerpool_api_key"] = "invalid_auth"
            else:
                await self.async_set_unique_id(
                    f"{braiins_key[:8]}_{pp_key[:8]}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Mining Pool Stats",
                    data={
                        "braiins_api_key": braiins_key,
                        "powerpool_api_key": pp_key,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SCHEMA,
            errors=errors,
            description_placeholders={},
        )
