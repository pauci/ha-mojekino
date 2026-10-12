"""Data update coordinator for MojeKino."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import Film, MojeKinoClient, MojeKinoError, Screening, thumbnail_url
from .const import DOMAIN, KEEP_PAST, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type MojeKinoConfigEntry = ConfigEntry[MojeKinoCoordinator]


class MojeKinoCoordinator(DataUpdateCoordinator[list[Screening]]):
    """Reads the cinema's program; data is all screenings sorted by start."""

    config_entry: MojeKinoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MojeKinoConfigEntry, client: MojeKinoClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.films: dict[int, Film] = {}

    async def _async_update_data(self) -> list[Screening]:
        try:
            films = await self.client.get_films()
        except MojeKinoError as err:
            raise UpdateFailed(f"Could not read the program: {err}") from err

        results = await asyncio.gather(
            *(self.client.get_screenings(film) for film in films),
            return_exceptions=True,
        )
        previous = self.data or []
        screenings: dict[str, Screening] = {}
        failed = 0
        for film, result in zip(films, results, strict=True):
            if isinstance(result, MojeKinoError):
                failed += 1
                _LOGGER.debug("Could not read %s: %s", film.url, result)
                # Keep what we knew about this film.
                result = [s for s in previous if s.film_id == film.id]
            elif isinstance(result, BaseException):
                raise result
            for screening in result:
                screenings[screening.uid] = screening
        if films and failed == len(films):
            raise UpdateFailed("Could not read any film page")

        now = dt_util.utcnow()
        for screening in previous:
            # Started screenings disappear from the film pages; keep them a while.
            if screening.start <= now < screening.end + KEEP_PAST:
                screenings.setdefault(screening.uid, screening)

        self.films = {film.id: film for film in films}
        return sorted(screenings.values(), key=lambda s: (s.start, s.title))

    def next_screening(self) -> Screening | None:
        """The screening in progress, or the next one."""
        now = dt_util.utcnow()
        return next((s for s in self.data or [] if s.end > now), None)

    def poster(self, screening: Screening) -> str:
        """Poster URL of a screening's film."""
        film = self.films.get(screening.film_id)
        return (film.poster if film else "") or screening.image

    def thumbnail(self, screening: Screening) -> str:
        """Small poster of a screening's film."""
        film = self.coordinator_film(screening)
        return (film.thumbnail if film else "") or thumbnail_url(self.poster(screening))

    def coordinator_film(self, screening: Screening) -> Film | None:
        return self.films.get(screening.film_id)
