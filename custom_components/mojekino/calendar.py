"""Calendar of a cinema's screenings."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Screening
from .coordinator import MojeKinoConfigEntry, MojeKinoCoordinator
from .entity import MojeKinoEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeKinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the program calendar."""
    async_add_entities([MojeKinoCalendar(entry.runtime_data)])


class MojeKinoCalendar(MojeKinoEntity, CalendarEntity):
    """All screenings of one cinema."""

    _attr_name = None

    def __init__(self, coordinator: MojeKinoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.config_entry.unique_id

    def _to_event(self, screening: Screening) -> CalendarEvent:
        film = self.coordinator.films.get(screening.film_id)
        details: list[str] = []
        if film and film.original_title and film.original_title != film.title:
            details.append(film.original_title)
        badges = list(film.tags) if film else []
        if screening.price:
            price = f"{screening.price:g}".replace(".", ",")
            badges.append(
                f"{price} €"
                if screening.currency == "EUR"
                else f"{price} {screening.currency}".strip()
            )
        if badges:
            details.append(" · ".join(badges))
        if screening.ticket_url:
            details.append(screening.ticket_url)
        if film:
            details.append(film.url)
        if screening.synopsis:
            details.append("")
            details.append(screening.synopsis)
        return CalendarEvent(
            start=dt_util.as_local(screening.start),
            end=dt_util.as_local(screening.end),
            summary=screening.title or (film.title if film else ""),
            description="\n".join(details) or None,
            location=screening.location or None,
            uid=screening.uid,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """The screening in progress, or the next one."""
        screening = self.coordinator.next_screening()
        return self._to_event(screening) if screening else None

    @property
    def entity_picture(self) -> str | None:
        """Poster of the screening in progress, or the next one."""
        screening = self.coordinator.next_screening()
        return (self.coordinator.poster(screening) or None) if screening else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Screenings overlapping the given range."""
        return [
            self._to_event(screening)
            for screening in self.coordinator.data or []
            if screening.start < end_date and screening.end > start_date
        ]
