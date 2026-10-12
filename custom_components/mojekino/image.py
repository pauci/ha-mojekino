"""Poster of a cinema's next film."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MojeKinoConfigEntry, MojeKinoCoordinator
from .entity import MojeKinoEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeKinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the poster image."""
    async_add_entities([MojeKinoPoster(hass, entry.runtime_data)])


class MojeKinoPoster(MojeKinoEntity, ImageEntity):
    """Poster of the film screening now or next."""

    _attr_translation_key = "next_film"

    def __init__(self, hass: HomeAssistant, coordinator: MojeKinoCoordinator) -> None:
        MojeKinoEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}-next_film"
        self._update_poster()

    def _update_poster(self) -> None:
        screening = self.coordinator.next_screening()
        url = (self.coordinator.poster(screening) or None) if screening else None
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._attr_image_last_updated = dt_util.utcnow()
            self._cached_image = None
        film = self.coordinator.films.get(screening.film_id) if screening else None
        self._attr_extra_state_attributes = {
            "film": screening.title if screening else None,
            "start_time": dt_util.as_local(screening.start).isoformat()
            if screening
            else None,
            "film_url": film.url if film else None,
            "tags": list(film.tags) if film else [],
            "tag_titles": list(film.tag_titles) if film else [],
            "ticket_url": (screening.ticket_url or None) if screening else None,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_poster()
        super()._handle_coordinator_update()
