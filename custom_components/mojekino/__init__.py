"""The MojeKino integration: cinema programs from Ticketware MojeKino websites."""

from __future__ import annotations

from homeassistant.const import CONF_NAME, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Cinema, MojeKinoClient
from .const import (
    CONF_BASE_URL,
    CONF_CINEMA_ID,
    CONF_CLIENT_ID,
    CONF_LANGUAGE,
    CONF_PROGRAM_ID,
)
from .coordinator import MojeKinoConfigEntry, MojeKinoCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.IMAGE, Platform.SENSOR]


def cinema_from_data(data: dict) -> Cinema:
    """Rebuild the cinema description stored in a config entry."""
    return Cinema(
        base_url=data[CONF_BASE_URL],
        client_id=data[CONF_CLIENT_ID],
        cinema_id=data[CONF_CINEMA_ID],
        name=data[CONF_NAME],
        language=data.get(CONF_LANGUAGE, "sk"),
        program_id=data.get(CONF_PROGRAM_ID),
    )


async def async_setup_entry(hass: HomeAssistant, entry: MojeKinoConfigEntry) -> bool:
    """Set up a cinema from a config entry."""
    client = MojeKinoClient(
        async_get_clientsession(hass),
        cinema_from_data(entry.data),
        entry.data[CONF_URL],
    )
    coordinator = MojeKinoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MojeKinoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
