"""Event entity for reCamera Pro sound detection.

This entity fires events that show up in the HA automation UI as triggers.
Users can select which sound type to trigger on (glass_break, dog_bark, etc.).
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import callback

from .const import DOMAIN
from .entity import RecameraProEntity


class RecameraProSoundEvent(RecameraProEntity, EventEntity):
    """Event entity that fires when a sound is detected.

    In the HA automation UI, users can select this entity as a trigger
    and choose which sound type to trigger on.
    """

    _attr_name = "Sound Event"
    _attr_icon = "mdi:bell-ring"
    _attr_should_poll = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_key}_sound_event"
        self._attr_event_types = list(dict.fromkeys([*coordinator.sound_types, "detection"]))

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._on_event)
        )

    @callback
    def _on_event(self, event_data: dict) -> None:
        event_type = event_data.get("sound") or event_data.get("event_type")
        if event_type and event_type in self._attr_event_types:
            self._trigger_event(event_type, {
                "confidence": event_data.get("confidence"),
                "timestamp": event_data.get("timestamp"),
                "image": event_data.get("image"),
                "message": event_data.get("message"),
                "class_name": event_data.get("class_name"),
                "rule_id": event_data.get("rule_id"),
                "rule_name": event_data.get("rule_name"),
            })


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the reCamera Pro event entity from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RecameraProSoundEvent(coordinator),
    ])
