"""Config flow for MojeKino."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    Cinema,
    MojeKinoClient,
    MojeKinoConnectionError,
    MojeKinoNotSupportedError,
)
from .const import (
    CONF_BASE_URL,
    CONF_CINEMA_ID,
    CONF_CLIENT_ID,
    CONF_LANGUAGE,
    CONF_PROGRAM_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        )
    }
)


def _normalize(url: str) -> str:
    url = url.strip()
    return url if "://" in url else f"https://{url}"


class MojeKinoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MojeKino."""

    VERSION = 1

    async def _validate(self, url: str) -> tuple[Cinema | None, dict[str, str]]:
        session = async_get_clientsession(self.hass)
        try:
            cinema = await MojeKinoClient.discover(session, url)
            films = await MojeKinoClient(session, cinema, url).get_films()
        except MojeKinoNotSupportedError:
            return None, {"base": "not_supported"}
        except MojeKinoConnectionError:
            return None, {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error reading %s", url)
            return None, {"base": "unknown"}
        if not films and cinema.program_id is None:
            return None, {"base": "no_program"}
        return cinema, {}

    @staticmethod
    def _data(url: str, cinema: Cinema) -> dict[str, Any]:
        return {
            CONF_URL: url,
            CONF_NAME: cinema.name,
            CONF_BASE_URL: cinema.base_url,
            CONF_CLIENT_ID: cinema.client_id,
            CONF_CINEMA_ID: cinema.cinema_id,
            CONF_LANGUAGE: cinema.language,
            CONF_PROGRAM_ID: cinema.program_id,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the cinema's website."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize(user_input[CONF_URL])
            cinema, errors = await self._validate(url)
            if cinema is not None:
                await self.async_set_unique_id(f"{cinema.client_id}-{cinema.cinema_id}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=cinema.name, data=self._data(url, cinema)
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the page the program is read from."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize(user_input[CONF_URL])
            cinema, errors = await self._validate(url)
            if cinema is not None:
                await self.async_set_unique_id(f"{cinema.client_id}-{cinema.cinema_id}")
                self._abort_if_unique_id_mismatch(reason="wrong_cinema")
                data = self._data(url, cinema) | {CONF_NAME: entry.data[CONF_NAME]}
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )
