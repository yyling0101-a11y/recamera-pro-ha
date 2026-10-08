"""Sensor entities for reCamera Pro."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import RecameraProEntity


class RecameraProLastSoundSensor(RecameraProEntity, SensorEntity):
    """Shows the last detected sound or visual class."""

    _attr_name = "Last Detection"
    _attr_icon = "mdi:bell-alert"
    _attr_should_poll = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_key}_last_detection"
        self._attr_native_value = coordinator.last_sound

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._on_event)
        )

    @callback
    def _on_event(self, event_data: dict) -> None:
        detection = event_data.get("sound") or event_data.get("class_name")
        if detection:
            self._attr_native_value = detection
            self.async_write_ha_state()


class RecameraProConfidenceSensor(RecameraProEntity, SensorEntity):
    """Shows the confidence of the last detected sound."""

    _attr_name = "Confidence"
    _attr_icon = "mdi:percent"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_key}_confidence"
        self._attr_native_value = coordinator.last_confidence

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._on_event)
        )

    @callback
    def _on_event(self, event_data: dict) -> None:
        confidence = event_data.get("confidence")
        if confidence is not None:
            self._attr_native_value = confidence
            self.async_write_ha_state()


class RecameraProLastEventSensor(RecameraProEntity, SensorEntity):
    """Shows the timestamp of the last sound event."""

    _attr_name = "Last Event"
    _attr_icon = "mdi:clock-outline"
    _attr_should_poll = False
    _attr_device_class = "timestamp"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_key}_last_event"
        if coordinator.last_event_time:
            self._attr_native_value = coordinator.last_event_time

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._on_event)
        )

    @callback
    def _on_event(self, event_data: dict) -> None:
        timestamp = event_data.get("timestamp")
        if timestamp:
            if isinstance(timestamp, (int, float)):
                parsed_timestamp = dt_util.utc_from_timestamp(float(timestamp))
            else:
                parsed_timestamp = dt_util.parse_datetime(str(timestamp))
            if parsed_timestamp is not None:
                if parsed_timestamp.tzinfo is None:
                    parsed_timestamp = parsed_timestamp.replace(
                        tzinfo=dt_util.DEFAULT_TIME_ZONE
                    )
                self._attr_native_value = parsed_timestamp
                self.async_write_ha_state()


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up reCamera Pro sensor entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RecameraProLastSoundSensor(coordinator),
        RecameraProConfidenceSensor(coordinator),
        RecameraProLastEventSensor(coordinator),
    ])
