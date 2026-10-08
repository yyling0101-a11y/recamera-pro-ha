"""Shared entity model for the reCamera Pro integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER


class RecameraProEntity(Entity):
    """Base class that associates every entity with one physical device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        self._coordinator = coordinator

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the physical reCamera represented by this config entry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.device_key)},
            name=self._coordinator.device_name,
            manufacturer=MANUFACTURER,
            model=self._coordinator.device_model,
            sw_version=self._coordinator.firmware_version,
            hw_version=self._coordinator.sensor_model,
            configuration_url=(
                f"https://{self._coordinator.host}"
                if self._coordinator.host
                else None
            ),
        )
