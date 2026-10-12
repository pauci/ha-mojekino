"""Base entity for MojeKino."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MojeKinoCoordinator


class MojeKinoEntity(CoordinatorEntity[MojeKinoCoordinator]):
    """An entity of one cinema.

    Besides coordinator updates, it refreshes when the current screening
    ends, so "next screening" values move on without waiting for a poll.
    """

    _attr_has_entity_name = True
    _unsub_rollover: CALLBACK_TYPE | None = None

    def __init__(self, coordinator: MojeKinoCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model="MojeKino",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.client.cinema.home_url,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule_rollover()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_rollover:
            self._unsub_rollover()
            self._unsub_rollover = None
        await super().async_will_remove_from_hass()

    @callback
    def _schedule_rollover(self) -> None:
        if self._unsub_rollover:
            self._unsub_rollover()
            self._unsub_rollover = None
        if screening := self.coordinator.next_screening():
            self._unsub_rollover = async_track_point_in_utc_time(
                self.hass, self._rollover, screening.end
            )

    @callback
    def _rollover(self, _now: datetime) -> None:
        self._unsub_rollover = None
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule_rollover()
        super()._handle_coordinator_update()
