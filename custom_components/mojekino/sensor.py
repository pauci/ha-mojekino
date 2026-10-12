"""Program of a cinema as a sensor, for dashboard templates."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MAX_LISTED
from .coordinator import MojeKinoConfigEntry, MojeKinoCoordinator
from .entity import MojeKinoEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeKinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the program sensor."""
    async_add_entities([MojeKinoProgram(entry.runtime_data)])


class MojeKinoProgram(MojeKinoEntity, SensorEntity):
    """Number of upcoming screenings; the ``screenings`` attribute lists them.

    The list is meant for Markdown cards (clickable film and ticket links,
    posters) and is not stored in the recorder.
    """

    _attr_translation_key = "program"
    _unrecorded_attributes = frozenset({"screenings"})

    def __init__(self, coordinator: MojeKinoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}-program"
        self._update_program()

    def _update_program(self) -> None:
        now = dt_util.utcnow()
        upcoming = [s for s in self.coordinator.data or [] if s.end > now]
        listed: list[dict[str, Any]] = []
        for screening in upcoming[:MAX_LISTED]:
            film = self.coordinator.films.get(screening.film_id)
            listed.append(
                {
                    "title": screening.title,
                    "start": dt_util.as_local(screening.start).isoformat(),
                    "end": dt_util.as_local(screening.end).isoformat(),
                    "location": screening.location,
                    "tags": list(film.tags) if film else [],
                    "tag_titles": list(film.tag_titles) if film else [],
                    "price": screening.price,
                    "currency": screening.currency,
                    "poster": self.coordinator.poster(screening),
                    "thumbnail": self.coordinator.thumbnail(screening),
                    "film_url": film.url if film else "",
                    "ticket_url": screening.ticket_url,
                }
            )
        self._attr_native_value = len(upcoming)
        self._attr_extra_state_attributes = {"screenings": listed}

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_program()
        super()._handle_coordinator_update()
