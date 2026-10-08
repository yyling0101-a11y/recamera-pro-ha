"""reCamera Pro integration.

A bidirectional MQTT bridge for Home Assistant with:
- Sound event detection with native HA event triggers
- Sensor entities (last sound, confidence, event time)
- Switch entity (enable/disable listening)
- Number entity (confidence threshold)
- Chat panel with image display and JSON template parsing
- HTTP API for image upload
- Runtime MQTT settings (broker, auth, topics) configurable via UI

v2.2.0: Added settings API, MQTT reconnection, template management.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import secrets
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import aiomqtt
import aiohttp
import voluptuous as vol
from aiohttp import web

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from .acoustics import AcousticsDecodeError, decode_inference_envelope
from .broker_config import load_managed_broker_config
from .device_api import RecameraDeviceClient
from .templates import apply_template, get_template_list, get_builtin_template_info

from .const import (
    CONF_DEVICE_NAME,
    CONF_DEVICE_PASSWORD,
    CONF_DEVICE_USERNAME,
    CONF_HOST,
    DEFAULT_BROKER_HOST,
    DEFAULT_BROKER_PORT,
    DEFAULT_BROKER_USERNAME,
    DEFAULT_BROKER_PASSWORD,
    DEFAULT_EVENT_TOPIC,
    DEFAULT_SOUND_TYPES,
    DOMAIN,
    EVENT_MESSAGE,
    LEGACY_ENTITY_IDS,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("broker", default=DEFAULT_BROKER_HOST): str,
                vol.Required("port", default=DEFAULT_BROKER_PORT): cv.port,
                vol.Optional("username", default=DEFAULT_BROKER_USERNAME): str,
                vol.Optional("password", default=DEFAULT_BROKER_PASSWORD): str,
                vol.Required("topic_in", default=DEFAULT_EVENT_TOPIC): str,
                vol.Optional("message_field", default=""): str,
                vol.Optional("max_history", default=200): cv.positive_int,
                vol.Optional("threshold", default=90.0): vol.Coerce(float),
                vol.Optional("sound_types", default=DEFAULT_SOUND_TYPES): [str],
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


class RecameraProCoordinator:
    """Owns the MQTT connection, event state, and message history."""

    def __init__(self, hass: HomeAssistant, conf: dict, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry_id = entry.entry_id
        self.device_name = conf.get(CONF_DEVICE_NAME) or entry.title
        self.host = (conf.get(CONF_HOST) or "").strip()
        self.device_username = conf.get(CONF_DEVICE_USERNAME, "admin")
        self.device_password = conf.get(CONF_DEVICE_PASSWORD, "")
        self.device_model = conf.get("device_model") or "reCamera Pro"
        self.sensor_model = conf.get("sensor_model")
        self.firmware_version = conf.get("firmware_version")
        self.device_key = (
            self.host.replace(".", "_").replace(":", "_")
            if self.host
            else entry.entry_id
        )
        self.broker = conf.get("broker", DEFAULT_BROKER_HOST)
        self.port = conf.get("port", DEFAULT_BROKER_PORT)
        self.username = conf.get("username", DEFAULT_BROKER_USERNAME)
        self.password = conf.get("password", DEFAULT_BROKER_PASSWORD)
        self.topic_in = conf.get("topic_in", DEFAULT_EVENT_TOPIC)
        self.message_field = (conf.get("message_field") or "").strip()
        self.max_history = conf.get("max_history", 200)
        self.sound_types = conf.get("sound_types", DEFAULT_SOUND_TYPES)
        self.threshold = conf.get("threshold", 90.0)

        self.history: deque = deque(maxlen=self.max_history)

        self._client = None
        self._task = None
        self._acoustics_task = None
        self._connected = False
        self._mqtt_error = None
        self._last_mqtt_message_monotonic = 0.0
        self.last_mqtt_message_at = None
        self.device_online_timeout = 90.0
        self._recent_msgs = deque(maxlen=20)
        self._image_seq = 0

        self.last_sound = None
        self.last_confidence = None
        self.last_event_time = None
        self.listening_enabled = True
        self.current_threshold = self.threshold

        self._listeners = []

        self.selected_template = "detection"
        self.custom_templates = {}
        self.event_rules = []
        self._event_cooldowns = {}  # rule_id -> last fire timestamp

        # Settings file for runtime configuration
        self._settings_file = hass.config.path(
            f"recamera_pro_{entry.entry_id}.json"
        )
        self._legacy_settings_file = hass.config.path("recamera_pro_settings.json")

        self.mqtt_enabled = True
        self.acoustics_connected = False
        self.acoustics_scores = []
        self.acoustics_sequence = None
        self.acoustics_head_id = None
        self.acoustics_head_version = None
        self.acoustics_updated_at = None
        self.acoustics_event_rules = []
        self._acoustics_rule_cooldowns = {}
        self._webrtc_tickets: dict[str, float] = {}

    def load_persisted_settings(self) -> None:
        """Load per-device settings without letting legacy data change identity."""
        using_legacy = False
        if (
            not os.path.exists(self._settings_file)
            and os.path.exists(self._legacy_settings_file)
        ):
            self._settings_file = self._legacy_settings_file
            using_legacy = True
        self._load_settings(allow_connection=not using_legacy)
        self._load_toggle_state()

    def _load_event_rules(self):
        try:
            if os.path.exists(self._settings_file):
                with open(self._settings_file, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    if "event_rules" in s:
                        self.event_rules = s["event_rules"]
        except Exception:
            pass

    def _load_toggle_state(self):
        try:
            if os.path.exists(self._settings_file):
                with open(self._settings_file, "r") as f:
                    s = json.load(f)
                    if "mqtt_enabled" in s:
                        self.mqtt_enabled = s["mqtt_enabled"]
        except Exception:
            pass

    async def set_mqtt_enabled(self, enabled: bool):
        self.mqtt_enabled = enabled
        self._save_settings()
        if enabled:
            if not self._task or self._task.done():
                self.start()
        else:
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._client = None
            self._connected = False

    # --- Settings persistence ---

    def _load_settings(self, allow_connection: bool = True):
        """Load settings, keeping Config Entry connection data authoritative for legacy files."""
        try:
            if os.path.exists(self._settings_file):
                with open(self._settings_file, "r") as f:
                    s = json.load(f)
                if allow_connection:
                    if "broker" in s:
                        self.broker = s["broker"]
                    if "port" in s:
                        self.port = s["port"]
                    if "username" in s:
                        self.username = s["username"] or None
                    if "password" in s:
                        self.password = s["password"] or None
                    if "topic_in" in s:
                        saved_topic = str(s["topic_in"] or "").strip()
                        # Migrate only the topic generated by pre-3.8 releases.
                        # A genuinely custom topic must never be overwritten.
                        legacy_topic = f"recamera/{self.host}/to_ha"
                        self.topic_in = (
                            DEFAULT_EVENT_TOPIC
                            if saved_topic == legacy_topic
                            else saved_topic
                        )
                if "selected_template" in s:
                    selected = str(s["selected_template"])
                    self.selected_template = (
                        selected
                        if selected in {"detection", "classification", "segmentation"}
                        else "detection"
                    )
                if "event_rules" in s:
                    self.event_rules = s["event_rules"]
                    for rule in self.event_rules:
                        event_name = str(rule.get("event_name", "")).strip().lower()
                        if event_name and not event_name.startswith("recamera_"):
                            rule["event_name"] = f"recamera_{event_name}"
                if "acoustics_event_rules" in s:
                    self.acoustics_event_rules = s["acoustics_event_rules"]
                _LOGGER.info("reCamera Pro: loaded settings from %s", self._settings_file)
        except Exception:
            _LOGGER.exception("reCamera Pro: failed to load settings")

    def _save_settings(self):
        """Schedule settings persistence outside Home Assistant's event loop."""
        settings = {
            "broker": self.broker,
            "port": self.port,
            "username": self.username or "",
            "password": self.password or "",
            "topic_in": self.topic_in,
            "selected_template": self.selected_template,
            "mqtt_enabled": self.mqtt_enabled,
            "event_rules": self.event_rules,
            "acoustics_event_rules": self.acoustics_event_rules,
        }
        self.hass.add_job(
            self.hass.async_add_executor_job,
            self._write_settings,
            settings,
        )

    def _write_settings(self, settings: dict) -> None:
        """Write settings from an executor worker."""
        temporary = f"{self._settings_file}.tmp-{secrets.token_hex(8)}"
        try:
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self._settings_file)
        except Exception:
            _LOGGER.exception("reCamera Pro: failed to save settings")
            try:
                os.unlink(temporary)
            except OSError:
                pass

    def issue_webrtc_ticket(self) -> str:
        """Issue a short-lived token for the browser signaling proxy."""
        now = time.monotonic()
        self._webrtc_tickets = {
            ticket: expires
            for ticket, expires in self._webrtc_tickets.items()
            if expires > now
        }
        ticket = secrets.token_urlsafe(32)
        self._webrtc_tickets[ticket] = now + 60
        return ticket

    def validate_webrtc_ticket(self, ticket: str) -> bool:
        """Validate a short-lived WebRTC signaling ticket."""
        expires = self._webrtc_tickets.pop(ticket, 0)
        return bool(ticket and expires > time.monotonic())

    @property
    def mqtt_device_connected(self) -> bool:
        """Return whether the reCamera itself is actively publishing MQTT."""
        if not self.mqtt_enabled or not self._connected:
            return False
        return (
            self._last_mqtt_message_monotonic > 0
            and time.monotonic() - self._last_mqtt_message_monotonic
            <= self.device_online_timeout
        )

    async def reconnect(self, broker, port, username, password, topic_in):
        """Update MQTT settings and reconnect."""
        self.broker = broker
        self.port = int(port)
        self.username = username or None
        self.password = password or None
        self.topic_in = topic_in
        self._save_settings()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._client = None
        self._connected = False
        self._mqtt_error = None
        self.start()

    @staticmethod
    async def validate_mqtt_settings(
        broker: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        """Verify Broker reachability and credentials before saving settings."""
        kwargs = {"hostname": broker, "port": port}
        if username:
            kwargs["username"] = username
            kwargs["password"] = password
        async with asyncio.timeout(8):
            async with aiomqtt.Client(**kwargs):
                return

    # --- Listener management ---

    @callback
    def async_add_listener(self, callback_func):
        self._listeners.append(callback_func)

        @callback
        def remove_listener():
            if callback_func in self._listeners:
                self._listeners.remove(callback_func)

        return remove_listener

    @callback
    def _notify_listeners(self, event_data: dict) -> None:
        for listener in self._listeners:
            try:
                listener(event_data)
            except Exception:
                _LOGGER.exception("Error in entity listener")

    # --- MQTT connection ---

    def start(self) -> None:
        if self.mqtt_enabled and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._mqtt_loop())
        if (
            self.host
            and self.device_password
            and (self._acoustics_task is None or self._acoustics_task.done())
        ):
            self._acoustics_task = asyncio.create_task(self._acoustics_loop())

    async def stop(self, _event=None) -> None:
        tasks = [task for task in (self._task, self._acoustics_task) if task]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._acoustics_task = None
        self._connected = False
        self.acoustics_connected = False

    async def _mqtt_loop(self) -> None:
        while True:
            try:
                kwargs = {"hostname": self.broker, "port": self.port}
                if self.username:
                    kwargs["username"] = self.username
                    kwargs["password"] = self.password
                async with aiomqtt.Client(**kwargs) as client:
                    self._client = client
                    self._connected = True
                    self._mqtt_error = None
                    await client.subscribe(self.topic_in)
                    _LOGGER.info(
                        "reCamera Pro connected to %s:%s, subscribed to %s",
                        self.broker, self.port, self.topic_in,
                    )
                    async for message in client.messages:
                        await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except aiomqtt.MqttError as err:
                self._mqtt_error = str(err)
                _LOGGER.warning(
                    "reCamera Pro MQTT disconnected: %s; retrying in 5s", err
                )
            except Exception:
                self._mqtt_error = "unexpected_error"
                _LOGGER.exception("reCamera Pro MQTT loop error")
            self._client = None
            self._connected = False
            await asyncio.sleep(5)

    async def _acoustics_loop(self) -> None:
        """Subscribe to the authenticated AcousticsLab inference stream."""
        while True:
            device_client = RecameraDeviceClient(
                self.host, self.device_username, self.device_password
            )
            try:
                await device_client.async_connect()
                websocket = await device_client.async_open_websocket(
                    "/extension/acousticslab/stream/infer",
                    protocols=("acousticslab.v1",),
                )
                self.acoustics_connected = True
                _LOGGER.info(
                    "reCamera Pro AcousticsLab connected for %s", self.host
                )
                async for message in websocket:
                    if message.type == aiohttp.WSMsgType.BINARY:
                        try:
                            inference = decode_inference_envelope(message.data)
                        except AcousticsDecodeError as err:
                            _LOGGER.warning(
                                "Invalid AcousticsLab frame from %s: %s",
                                self.host,
                                err,
                            )
                            continue
                        if inference is not None:
                            self._handle_acoustics_inference(inference)
                    elif message.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug(
                    "reCamera Pro AcousticsLab disconnected for %s: %s",
                    self.host,
                    err,
                )
            finally:
                self.acoustics_connected = False
                await device_client.async_close()
            await asyncio.sleep(5)

    @callback
    def _handle_acoustics_inference(self, inference) -> None:
        """Update realtime scores and fire matching user-defined HA events."""
        self.acoustics_sequence = inference.sequence
        self.acoustics_head_id = inference.head_id
        self.acoustics_head_version = inference.head_version
        if inference.publish_time_us:
            published = datetime.fromtimestamp(
                inference.publish_time_us / 1_000_000, tz=timezone.utc
            )
        else:
            published = datetime.now(timezone.utc)
        self.acoustics_updated_at = published.isoformat()
        self.acoustics_scores = [
            {
                "class_idx": score.class_idx,
                "label": score.label,
                "confidence": round(score.probability, 6),
            }
            for score in inference.scores
        ]

        scores_by_label = {
            score["label"]: score["confidence"] for score in self.acoustics_scores
        }
        now = time.monotonic()
        for rule in self.acoustics_event_rules:
            if not rule.get("enabled", True):
                continue
            label = str(rule.get("label", ""))
            confidence = scores_by_label.get(label)
            threshold = float(rule.get("threshold", 0.8))
            if confidence is None or confidence < threshold:
                continue
            rule_id = str(rule.get("id", ""))
            cooldown = max(0.0, float(rule.get("cooldown", 5.0)))
            if now - self._acoustics_rule_cooldowns.get(rule_id, 0.0) < cooldown:
                continue
            self._acoustics_rule_cooldowns[rule_id] = now
            self.hass.bus.async_fire(
                rule["event_type"],
                {
                    "entry_id": self.entry_id,
                    "device_name": self.device_name,
                    "host": self.host,
                    "label": label,
                    "confidence": confidence,
                    "threshold": threshold,
                    "sequence": inference.sequence,
                    "head_id": inference.head_id,
                    "head_version": inference.head_version,
                    "timestamp": self.acoustics_updated_at,
                    "rule_id": rule_id,
                    "rule_name": rule.get("name") or label,
                },
            )

    def upsert_acoustics_rule(self, data: dict) -> dict:
        """Create or update one sound confidence rule."""
        rule_id = str(data.get("id") or uuid.uuid4().hex)
        rule = {
            "id": rule_id,
            "name": str(data.get("name") or data["label"]).strip(),
            "label": str(data["label"]).strip(),
            "threshold": float(data["threshold"]),
            "event_type": str(data["event_type"]).strip(),
            "cooldown": float(data.get("cooldown", 5.0)),
            "enabled": bool(data.get("enabled", True)),
        }
        self.acoustics_event_rules = [
            existing
            for existing in self.acoustics_event_rules
            if existing.get("id") != rule_id
        ]
        self.acoustics_event_rules.append(rule)
        self._save_settings()
        return rule

    def delete_acoustics_rule(self, rule_id: str) -> bool:
        """Delete one sound confidence rule."""
        old_length = len(self.acoustics_event_rules)
        self.acoustics_event_rules = [
            rule
            for rule in self.acoustics_event_rules
            if rule.get("id") != rule_id
        ]
        self._acoustics_rule_cooldowns.pop(rule_id, None)
        if len(self.acoustics_event_rules) != old_length:
            self._save_settings()
            return True
        return False

    # --- Message handling ---

    def _is_duplicate(self, topic: str, raw: str) -> bool:
        now = time.monotonic()
        fp = (topic, raw)
        while self._recent_msgs and now - self._recent_msgs[0][0] > 3.0:
            self._recent_msgs.popleft()
        for _, f in self._recent_msgs:
            if f == fp:
                return True
        self._recent_msgs.append((now, fp))
        return False

    def _build_entry(self, direction: str, topic: str, raw: str, image=None) -> dict:
        data = None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            data = None
        text = self._extract_text(data, raw)
        if data is not None and self.selected_template:
            template_id = self.selected_template
            task_name = str(data.get("task_type_name", "")).lower()
            if (
                template_id
                in {"detection", "classification", "segmentation"}
                and task_name
                and template_id != task_name
            ):
                template_id = task_name
            parsed = apply_template(data, template_id, self.custom_templates)
            if parsed:
                text = parsed
        task_type = ""
        source_timestamp = None
        if isinstance(data, dict):
            task_type = str(
                data.get("task_type_name") or data.get("task_type") or ""
            ).lower()
            if not task_type:
                task_type = next(
                    (
                        key
                        for key in (
                            "detection",
                            "classification",
                            "segmentation",
                        )
                        if isinstance(data.get(key), dict)
                    ),
                    "",
                )
            source_timestamp = data.get("timestamp")
        return {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "dir": direction,
            "topic": topic,
            "raw": raw,
            "data": data,
            "text": text,
            "image": image,
            "task_type": task_type,
            "source_timestamp": source_timestamp,
        }

    def _extract_text(self, data, raw: str) -> str:
        if data is None:
            return raw
        if self.message_field:
            if isinstance(data, dict) and self.message_field in data:
                return str(data[self.message_field])
            return raw
        if isinstance(data, dict):
            for key in ("message", "text", "payload", "msg", "content"):
                if key in data:
                    return str(data[key])
        return json.dumps(data, ensure_ascii=False)

    def _save_image_bytes(self, image_bytes, ext="jpg"):
        try:
            self._image_seq += 1
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{self._image_seq:04d}.{ext}"
            image_dir = os.path.join(
                self.hass.config.path("www"), "recamera_pro", "images"
            )
            os.makedirs(image_dir, exist_ok=True)
            filepath = os.path.join(image_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            url = f"/local/recamera_pro/images/{filename}"
            return url
        except Exception:
            _LOGGER.exception("reCamera Pro: failed to save image")
            return None

    def _save_base64_image(self, b64_data):
        try:
            if "," in b64_data and b64_data.startswith("data:"):
                b64_data = b64_data.split(",", 1)[1]
            image_bytes = base64.b64decode(b64_data)
            return self._save_image_bytes(image_bytes)
        except Exception:
            _LOGGER.exception("reCamera Pro: failed to decode base64 image")
            return None

    async def _handle_message(self, message) -> None:
        payload = message.payload
        if isinstance(payload, (bytes, bytearray)):
            raw = payload.decode("utf-8", errors="replace")
        else:
            raw = str(payload)
        topic_str = str(message.topic)
        self._last_mqtt_message_monotonic = time.monotonic()
        self.last_mqtt_message_at = datetime.now(timezone.utc)
        if self._is_duplicate(topic_str, raw):
            return

        entry = self._build_entry("in", topic_str, raw)
        data = entry.get("data")

        # Check event rules against AI inference data
        if isinstance(data, dict) and self.event_rules:
            self._check_event_rules(data)

        if isinstance(data, dict):
            sound = data.get("sound") or data.get("event_type")
            confidence = data.get("confidence")

            if sound:
                self.last_sound = sound
                if confidence is not None:
                    try:
                        self.last_confidence = float(confidence)
                    except (ValueError, TypeError):
                        pass
                self.last_event_time = datetime.now()

                self._notify_listeners({
                    "sound": sound,
                    "confidence": self.last_confidence,
                    "timestamp": self.last_event_time.isoformat(timespec="seconds"),
                    "image": entry.get("image"),
                    "message": entry.get("text"),
                })

            b64 = data.get("image_base64") or data.get("image_data")
            if b64:
                img_url = self._save_base64_image(b64)
                if img_url:
                    entry["image"] = img_url
                    if not entry["text"] or entry["text"] == raw:
                        entry["text"] = "[\u56fe\u7247]"

        self.history.append(entry)
        self.hass.bus.async_fire(EVENT_MESSAGE, {"entry": entry})

    def _check_event_rules(self, data: dict) -> None:
        """Check incoming AI inference data against user-defined event rules.
        If a rule matches, fire recamera_pro_trigger event on HA event bus."""
        # Extract all entries from various task types
        all_entries = []
        task_type = data.get("task_type_name", "")
        for key in ("detection", "classification", "segmentation"):
            section = data.get(key)
            if isinstance(section, dict):
                entries = section.get("entries", [])
                for e in entries:
                    if isinstance(e, dict):
                        all_entries.append({
                            "class_name": (
                                e.get("class_name")
                                or e.get("label")
                                or e.get("name")
                                or e.get("class")
                                or ""
                            ),
                            "score": (
                                e.get("score")
                                if e.get("score") is not None
                                else e.get(
                                    "confidence",
                                    e.get("probability", 0),
                                )
                            ),
                            "task_type": key,
                            "entry": e,
                        })

        if not all_entries:
            return

        for rule in self.event_rules:
            if not rule.get("enabled", True):
                continue
            rule_class = rule.get("class_name", "*")
            rule_min_conf = float(rule.get("min_confidence", 0))
            rule_task_type = str(rule.get("task_type", "*")).strip().lower() or "*"
            event_name = rule.get("event_name", "").strip()
            if event_name and not event_name.startswith("recamera_"):
                event_name = f"recamera_{event_name}"

            for entry_info in all_entries:
                if (
                    rule_task_type != "*"
                    and entry_info["task_type"] != rule_task_type
                ):
                    continue
                cls = entry_info["class_name"]
                score = entry_info["score"]
                try:
                    score_f = float(score)
                except (ValueError, TypeError):
                    score_f = 0

                # Match: "*" matches any class, otherwise exact match (case-insensitive)
                class_match = (rule_class == "*" or
                               cls.lower() == rule_class.lower())
                conf_match = score_f >= rule_min_conf

                if class_match and conf_match:
                    # Cooldown: don't fire the same rule more than once per cooldown period
                    cooldown = float(rule.get("cooldown", 3))
                    now_ts = time.monotonic()
                    last_fire = self._event_cooldowns.get(rule.get("id", ""), 0)
                    if now_ts - last_fire < cooldown:
                        continue
                    self._event_cooldowns[rule.get("id", "")] = now_ts

                    fire_data = {
                        "class_name": cls,
                        "confidence": score_f,
                        "task_type": entry_info["task_type"],
                        "task_type_name": task_type,
                        "rule_id": rule.get("id", ""),
                        "rule_name": rule.get("event_name", ""),
                        "timestamp": data.get("timestamp", datetime.now().isoformat(timespec="seconds")),
                        "raw_data": data,
                    }
                    self.last_sound = cls
                    self.last_confidence = score_f
                    self.last_event_time = datetime.now()
                    self._notify_listeners({
                        **fire_data,
                        "event_type": "detection",
                    })
                    # Always fire the default event type
                    event_type = "recamera_pro_trigger"
                    self.hass.bus.async_fire(event_type, fire_data)
                    _LOGGER.warning(
                        "reCamera Pro: fired event %s, class=%s conf=%.2f rule=%s",
                        event_type, cls, score_f, rule.get("id", ""),
                    )
                    # If event_name is provided, also fire a custom event type
                    if event_name:
                        self.hass.bus.async_fire(event_name, fire_data)
                        _LOGGER.warning(
                            "reCamera Pro: fired custom event %s, class=%s conf=%.2f rule=%s",
                            event_name, cls, score_f, rule.get("id", ""),
                        )
                    break  # One fire per rule per message

    async def add_image_entry(self, image_url, message_text=""):
        entry = self._build_entry("in", "http_upload", "", image=image_url)
        if message_text:
            entry["text"] = message_text
        else:
            entry["text"] = "[\u56fe\u7247]"
        entry["raw"] = ""
        self.history.append(entry)
        self.hass.bus.async_fire(EVENT_MESSAGE, {"entry": entry})
        return entry

    def clear_history(self) -> None:
        self.history.clear()


# --- HTTP Views ---

class MessagesView(HomeAssistantView):
    url = "/api/recamera_pro/messages"
    name = "api:recamera_pro:messages"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def get(self, request):
        return self.json({"messages": list(self._coordinator.history)})


class UploadView(HomeAssistantView):
    url = "/api/recamera_pro/upload"
    name = "api:recamera_pro:upload"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def post(self, request):
        data = await request.json()
        b64 = data.get("image_base64", "")
        message_text = data.get("message", "")
        if not b64:
            return self.json({"error": "no image_base64"}, status_code=400)
        image_url = self._coordinator._save_base64_image(b64)
        if not image_url:
            return self.json({"error": "failed to save image"}, status_code=500)
        entry = await self._coordinator.add_image_entry(image_url, message_text)
        return self.json({"entry": entry, "image_url": image_url})


class UploadFileView(HomeAssistantView):
    url = "/api/recamera_pro/upload_file"
    name = "api:recamera_pro:upload_file"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def post(self, request):
        reader = await request.multipart()
        image_bytes = None
        filename = "image.jpg"
        message_text = ""
        async for part in reader:
            if part.name == "image":
                image_bytes = await part.read(decode=False)
                if part.filename:
                    filename = part.filename
            elif part.name == "message":
                message_text = (await part.text()).strip()
        if not image_bytes:
            return self.json({"error": "no image file"}, status_code=400)
        ext = "jpg"
        if "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()
            if ext in ("jpeg",):
                ext = "jpg"
        image_url = self._coordinator._save_image_bytes(image_bytes, ext)
        if not image_url:
            return self.json({"error": "failed to save image"}, status_code=500)
        entry = await self._coordinator.add_image_entry(image_url, message_text)
        return self.json({"entry": entry, "image_url": image_url})


class StatusView(HomeAssistantView):
    url = "/api/recamera_pro/status"
    name = "api:recamera_pro:status"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def get(self, request):
        return self.json({
            "mqtt_connected": self._coordinator.mqtt_device_connected,
            "mqtt_broker_connected": self._coordinator._connected,
            "mqtt_enabled": self._coordinator.mqtt_enabled,
            "broker": self._coordinator.broker,
            "port": self._coordinator.port,
            "topic_in": self._coordinator.topic_in,
            "history_count": len(self._coordinator.history),
            "last_sound": self._coordinator.last_sound,
            "last_confidence": self._coordinator.last_confidence,
            "last_event_time": self._coordinator.last_event_time.isoformat(timespec="seconds") if self._coordinator.last_event_time else None,
            "listening_enabled": self._coordinator.listening_enabled,
            "threshold": self._coordinator.current_threshold,
            "selected_template": self._coordinator.selected_template,
            "templates": get_template_list(self._coordinator.custom_templates),
            "custom_templates": self._coordinator.custom_templates,
            "event_rules": self._coordinator.event_rules,
        })


class ClearView(HomeAssistantView):
    url = "/api/recamera_pro/clear"
    name = "api:recamera_pro:clear"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def post(self, request):
        self._coordinator.clear_history()
        return self.json({"cleared": True})

class ToggleView(HomeAssistantView):
    url = "/api/recamera_pro/toggle"
    name = "api:recamera_pro:toggle"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def get(self, request):
        return self.json({"mqtt_enabled": self._coordinator.mqtt_enabled})

    async def post(self, request):
        data = await request.json()
        enabled = data.get("enabled", True)
        await self._coordinator.set_mqtt_enabled(enabled)
        return self.json({"mqtt_enabled": self._coordinator.mqtt_enabled})


class EventRulesView(HomeAssistantView):
    url = "/api/recamera_pro/event_rules"
    name = "api:recamera_pro:event_rules"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def get(self, request):
        return self.json({"event_rules": self._coordinator.event_rules})

    async def post(self, request):
        data = await request.json()
        action = data.get("action", "add")
        if action == "add":
            import uuid
            rid = f"rule_{uuid.uuid4().hex[:8]}"
            event_name = str(data.get("event_name", "")).strip().lower()
            if event_name and not event_name.startswith("recamera_"):
                event_name = f"recamera_{event_name}"
            rule = {
                "id": rid,
                "class_name": data.get("class_name", "*"),
                "min_confidence": float(data.get("min_confidence", 0)),
                "event_name": event_name,
                "enabled": data.get("enabled", True),
                "cooldown": float(data.get("cooldown", 3)),
            }
            self._coordinator.event_rules.append(rule)
            self._coordinator._save_settings()
            return self.json({"rule": rule})
        elif action == "delete":
            rid = data.get("id", "")
            self._coordinator.event_rules = [
                r for r in self._coordinator.event_rules if r.get("id") != rid
            ]
            self._coordinator._save_settings()
            return self.json({"deleted": rid})
        elif action == "toggle":
            rid = data.get("id", "")
            for r in self._coordinator.event_rules:
                if r.get("id") == rid:
                    r["enabled"] = not r.get("enabled", True)
                    break
            self._coordinator._save_settings()
            return self.json({"toggled": rid})
        return self.json({"error": "unknown action"}, status_code=400)


class SettingsView(HomeAssistantView):
    url = "/api/recamera_pro/settings"
    name = "api:recamera_pro:settings"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def get(self, request):
        return self.json({
            "broker": self._coordinator.broker,
            "port": self._coordinator.port,
            "username": self._coordinator.username or DEFAULT_BROKER_USERNAME,
            "password": "",
            "has_password": bool(self._coordinator.password),
            "topic_in": self._coordinator.topic_in,
        })

    async def post(self, request):
        data = await request.json()
        await self._coordinator.reconnect(
            data.get("broker", DEFAULT_BROKER_HOST),
            int(data.get("port", DEFAULT_BROKER_PORT)),
            data.get("username", DEFAULT_BROKER_USERNAME),
            data.get("password") or self._coordinator.password or DEFAULT_BROKER_PASSWORD,
            data.get("topic_in", DEFAULT_EVENT_TOPIC),
        )
        return self.json({"reconnecting": True})


class TemplatesView(HomeAssistantView):
    url = "/api/recamera_pro/templates"
    name = "api:recamera_pro:templates"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def get(self, request):
        return self.json({
            "templates": get_template_list(self._coordinator.custom_templates),
            "selected": self._coordinator.selected_template,
            "custom_templates": self._coordinator.custom_templates,
        })

    async def post(self, request):
        data = await request.json()
        template_id = data.get("template_id", "")
        self._coordinator.selected_template = template_id
        self._coordinator._save_settings()
        return self.json({"selected": template_id})


class CustomTemplateView(HomeAssistantView):
    url = "/api/recamera_pro/custom_template"
    name = "api:recamera_pro:custom_template"
    requires_auth = True

    def __init__(self, coordinator):
        self._coordinator = coordinator

    async def post(self, request):
        data = await request.json()
        action = data.get("action", "add")
        if action == "add":
            tid = data.get("id", "")
            if not tid:
                import uuid
                tid = f"custom_{uuid.uuid4().hex[:8]}"
            self._coordinator.custom_templates[tid] = {
                "name": data.get("name", tid),
                "description": data.get("description", ""),
                "template_str": data.get("template_str", ""),
            }
            self._coordinator._save_settings()
            return self.json({"id": tid, "template": self._coordinator.custom_templates[tid]})
        elif action == "delete":
            tid = data.get("id", "")
            if tid in self._coordinator.custom_templates:
                del self._coordinator.custom_templates[tid]
                if self._coordinator.selected_template == tid:
                    self._coordinator.selected_template = ""
                self._coordinator._save_settings()
            return self.json({"deleted": tid})
        return self.json({"error": "unknown action"}, status_code=400)


def _safe_device_payload(entry: ConfigEntry, coordinator) -> dict:
    """Return device data that is safe to expose to the authenticated panel."""
    return {
        "entry_id": entry.entry_id,
        "name": entry.title,
        "host": entry.data.get(CONF_HOST, ""),
        "username": entry.data.get(CONF_DEVICE_USERNAME, "admin"),
        "has_password": bool(entry.data.get(CONF_DEVICE_PASSWORD)),
        "mqtt_connected": bool(
            coordinator and coordinator.mqtt_device_connected
        ),
        "mqtt_broker_connected": bool(coordinator and coordinator._connected),
        "mqtt_enabled": bool(coordinator and coordinator.mqtt_enabled),
        "acoustics_connected": bool(
            coordinator and coordinator.acoustics_connected
        ),
        "last_detection": coordinator.last_sound if coordinator else None,
        "last_confidence": coordinator.last_confidence if coordinator else None,
        "model": entry.data.get("device_model", "reCamera Pro"),
        "firmware_version": entry.data.get("firmware_version"),
        "web_url": (
            f"https://{entry.data[CONF_HOST]}/"
            if entry.data.get(CONF_HOST)
            else None
        ),
    }


class DevicesView(HomeAssistantView):
    """List and add reCamera Pro devices for the custom panel."""

    url = "/api/recamera_pro/devices"
    name = "api:recamera_pro:devices"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request):
        entries = self._hass.config_entries.async_entries(DOMAIN)
        coordinators = self._hass.data.get(DOMAIN, {})
        return self.json(
            {
                "devices": [
                    _safe_device_payload(entry, coordinators.get(entry.entry_id))
                    for entry in entries
                ]
            }
        )

    async def post(self, request):
        data = await request.json()
        device_name = str(data.get(CONF_DEVICE_NAME, "")).strip()
        host = str(data.get(CONF_HOST, "")).strip().lower()
        username = str(data.get(CONF_DEVICE_USERNAME, "admin")).strip() or "admin"
        password = str(data.get(CONF_DEVICE_PASSWORD, ""))
        if not device_name or not host:
            return self.json({"error": "required_fields"}, status_code=400)

        from .device_api import RecameraAuthenticationError, async_validate_device

        try:
            device_info = await async_validate_device(host, username, password)
        except RecameraAuthenticationError:
            return self.json({"error": "invalid_auth"}, status_code=401)
        except Exception:
            _LOGGER.exception("Unable to connect to reCamera Pro at %s", host)
            return self.json({"error": "cannot_connect"}, status_code=400)

        entries = self._hass.config_entries.async_entries(DOMAIN)
        for existing in entries:
            if existing.data.get(CONF_HOST) == host:
                return self.json({"error": "already_configured"}, status_code=409)

        entry_data = {
            CONF_DEVICE_NAME: device_name,
            CONF_HOST: host,
            CONF_DEVICE_USERNAME: username,
            CONF_DEVICE_PASSWORD: password,
            "broker": DEFAULT_BROKER_HOST,
            "port": DEFAULT_BROKER_PORT,
            "username": DEFAULT_BROKER_USERNAME,
            "password": DEFAULT_BROKER_PASSWORD,
            "topic_in": DEFAULT_EVENT_TOPIC,
            "device_model": device_info.base_plate_model or "reCamera Pro",
            "sensor_model": device_info.sensor_model,
            "firmware_version": device_info.firmware_version,
        }

        result = await self._hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={
                CONF_DEVICE_NAME: device_name,
                CONF_HOST: host,
                CONF_DEVICE_USERNAME: username,
                CONF_DEVICE_PASSWORD: password,
            },
        )
        result_type = getattr(result.get("type"), "value", result.get("type"))
        if result_type != "create_entry":
            return self.json(
                {"error": result.get("reason") or "create_failed"},
                status_code=400,
            )
        entry_id = result["result"].entry_id
        return self.json({"entry_id": entry_id, "created": True})


class DeviceView(HomeAssistantView):
    """Delete one physical reCamera Pro config entry."""

    url = "/api/recamera_pro/devices/{entry_id}"
    name = "api:recamera_pro:device"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def delete(self, request, entry_id):
        entry = self._hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            return self.json({"error": "not_found"}, status_code=404)
        user = request["hass_user"] if "hass_user" in request else None
        if user is None or not user.is_admin:
            return self.json({"error": "admin_required"}, status_code=403)
        await self._hass.config_entries.async_remove(entry_id)
        return self.json({"deleted": True, "entry_id": entry_id})


class DeviceDetailView(HomeAssistantView):
    """Per-device MQTT/status endpoint used by the device detail page."""

    url = "/api/recamera_pro/devices/{entry_id}/{resource}"
    name = "api:recamera_pro:device_detail"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def _coordinator(self, request):
        return self._hass.data.get(DOMAIN, {}).get(request.match_info["entry_id"])

    async def get(self, request, entry_id, resource):
        coordinator = self._coordinator(request)
        if coordinator is None:
            return self.json({"error": "not_found"}, status_code=404)
        if resource == "status":
            return self.json(
                {
                    "mqtt_connected": coordinator.mqtt_device_connected,
                    "mqtt_broker_connected": coordinator._connected,
                    "mqtt_enabled": coordinator.mqtt_enabled,
                    "mqtt_error": coordinator._mqtt_error,
                    "broker": coordinator.broker,
                    "port": coordinator.port,
                    "username": coordinator.username or DEFAULT_BROKER_USERNAME,
                    "has_password": bool(coordinator.password),
                    "topic_in": coordinator.topic_in,
                    "last_mqtt_message_at": (
                        coordinator.last_mqtt_message_at.isoformat()
                        if coordinator.last_mqtt_message_at
                        else None
                    ),
                    "history_count": len(coordinator.history),
                    "last_detection": coordinator.last_sound,
                    "last_confidence": coordinator.last_confidence,
                    "last_event_time": (
                        coordinator.last_event_time.isoformat(timespec="seconds")
                        if coordinator.last_event_time
                        else None
                    ),
                    "listening_enabled": coordinator.listening_enabled,
                    "threshold": coordinator.current_threshold,
                    "selected_template": coordinator.selected_template,
                    "templates": get_template_list(coordinator.custom_templates),
                    "custom_templates": coordinator.custom_templates,
                    "event_rules": coordinator.event_rules,
                }
            )
        if resource == "messages":
            return self.json({"messages": list(coordinator.history)})
        if resource == "settings":
            return self.json(
                {
                    "broker": coordinator.broker,
                    "port": coordinator.port,
                    "username": coordinator.username or DEFAULT_BROKER_USERNAME,
                    "password": "",
                    "has_password": bool(coordinator.password),
                    "topic_in": coordinator.topic_in,
                }
            )
        if resource == "templates":
            return self.json(
                {
                    "templates": get_template_list(coordinator.custom_templates),
                    "selected": coordinator.selected_template,
                    "custom_templates": coordinator.custom_templates,
                }
            )
        if resource == "event-rules":
            return self.json({"event_rules": coordinator.event_rules})
        if resource == "acoustics":
            return self.json(
                {
                    "connected": coordinator.acoustics_connected,
                    "scores": coordinator.acoustics_scores,
                    "sequence": coordinator.acoustics_sequence,
                    "head_id": coordinator.acoustics_head_id,
                    "head_version": coordinator.acoustics_head_version,
                    "updated_at": coordinator.acoustics_updated_at,
                    "rules": coordinator.acoustics_event_rules,
                }
            )
        return self.json({"error": "unknown_resource"}, status_code=404)

    async def post(self, request, entry_id, resource):
        coordinator = self._coordinator(request)
        if coordinator is None:
            return self.json({"error": "not_found"}, status_code=404)
        data = await request.json()
        if resource == "messages":
            if data.get("action") == "clear":
                coordinator.clear_history()
                return self.json({"cleared": True})
            return self.json({"error": "unknown_action"}, status_code=400)
        if resource == "toggle":
            await coordinator.set_mqtt_enabled(bool(data.get("enabled", True)))
            return self.json({"mqtt_enabled": coordinator.mqtt_enabled})
        if resource == "settings":
            broker = str(data.get("broker", "")).strip()
            topic_in = str(data.get("topic_in", "")).strip()
            try:
                port = int(data.get("port", 1883))
            except (TypeError, ValueError):
                return self.json({"error": "invalid_port"}, status_code=400)
            if not broker or not topic_in or not str(data.get("username", "")).strip() or not 1 <= port <= 65535:
                return self.json({"error": "invalid_settings"}, status_code=400)
            username = str(data.get("username", "")).strip()
            password = data.get("password") or coordinator.password or ""
            try:
                await coordinator.validate_mqtt_settings(
                    broker, port, username, password
                )
            except (aiomqtt.MqttError, TimeoutError, OSError) as err:
                message = str(err).lower()
                error = (
                    "mqtt_auth_failed"
                    if "author" in message or "code:135" in message
                    else "mqtt_connect_failed"
                )
                return self.json({"error": error}, status_code=400)
            await coordinator.reconnect(
                broker,
                port,
                username,
                password,
                topic_in,
            )
            return self.json({"reconnecting": True})
        if resource == "templates":
            template_id = str(data.get("template_id", ""))
            valid_ids = {
                template["id"]
                for template in get_template_list(coordinator.custom_templates)
            }
            if template_id and template_id not in valid_ids:
                return self.json({"error": "unknown_template"}, status_code=400)
            coordinator.selected_template = template_id
            coordinator._save_settings()
            return self.json({"selected": template_id})
        if resource == "custom-template":
            action = str(data.get("action", "add"))
            template_id = str(data.get("id", "")).strip()
            if action == "add":
                name = str(data.get("name", "")).strip()
                template_str = str(data.get("template_str", "")).strip()
                if not name or not template_str:
                    return self.json({"error": "required_fields"}, status_code=400)
                template_id = template_id or f"custom_{uuid.uuid4().hex[:8]}"
                coordinator.custom_templates[template_id] = {
                    "name": name,
                    "description": str(data.get("description", "")).strip(),
                    "template_str": template_str,
                }
                coordinator._save_settings()
                return self.json(
                    {
                        "id": template_id,
                        "template": coordinator.custom_templates[template_id],
                    }
                )
            if action == "delete":
                coordinator.custom_templates.pop(template_id, None)
                if coordinator.selected_template == template_id:
                    coordinator.selected_template = ""
                coordinator._save_settings()
                return self.json({"deleted": template_id})
            return self.json({"error": "unknown_action"}, status_code=400)
        if resource == "event-rules":
            action = str(data.get("action", "add"))
            if action == "add":
                class_name = str(data.get("class_name", "*")).strip() or "*"
                task_type = str(data.get("task_type", "*")).strip().lower() or "*"
                event_name = str(data.get("event_name", "")).strip().lower()
                if event_name and not event_name.startswith("recamera_"):
                    event_name = f"recamera_{event_name}"
                try:
                    min_confidence = float(data.get("min_confidence", 0))
                    cooldown = float(data.get("cooldown", 3))
                except (TypeError, ValueError):
                    return self.json({"error": "invalid_number"}, status_code=400)
                if (
                    not 0 <= min_confidence <= 1
                    or not 0 <= cooldown <= 3600
                    or task_type
                    not in {
                        "*",
                        "detection",
                        "classification",
                        "segmentation",
                    }
                    or (event_name and not re.fullmatch(r"[a-z0-9_]+", event_name))
                ):
                    return self.json({"error": "invalid_rule"}, status_code=400)
                rule = {
                    "id": f"rule_{uuid.uuid4().hex[:8]}",
                    "class_name": class_name,
                    "task_type": task_type,
                    "min_confidence": min_confidence,
                    "event_name": event_name,
                    "enabled": bool(data.get("enabled", True)),
                    "cooldown": cooldown,
                }
                coordinator.event_rules.append(rule)
                coordinator._save_settings()
                return self.json({"rule": rule})
            rule_id = str(data.get("id", ""))
            if action == "delete":
                coordinator.event_rules = [
                    rule
                    for rule in coordinator.event_rules
                    if rule.get("id") != rule_id
                ]
                coordinator._event_cooldowns.pop(rule_id, None)
                coordinator._save_settings()
                return self.json({"deleted": rule_id})
            if action == "toggle":
                for rule in coordinator.event_rules:
                    if rule.get("id") == rule_id:
                        rule["enabled"] = not rule.get("enabled", True)
                        coordinator._save_settings()
                        return self.json({"rule": rule})
                return self.json({"error": "not_found"}, status_code=404)
            return self.json({"error": "unknown_action"}, status_code=400)
        if resource == "webrtc-ticket":
            stream = str(data.get("stream", "main"))
            if stream not in ("main", "sub"):
                return self.json({"error": "invalid_stream"}, status_code=400)
            ticket = coordinator.issue_webrtc_ticket()
            return self.json(
                {
                    "path": (
                        f"/api/recamera_pro/webrtc/{coordinator.entry_id}"
                        f"?ticket={ticket}&stream={stream}"
                    ),
                    "expires_in": 60,
                }
            )
        if resource == "acoustics":
            action = str(data.get("action", "upsert_rule"))
            if action == "delete_rule":
                deleted = coordinator.delete_acoustics_rule(str(data.get("id", "")))
                return self.json({"deleted": deleted})
            if action == "toggle_rule":
                rule_id = str(data.get("id", ""))
                for rule in coordinator.acoustics_event_rules:
                    if rule.get("id") == rule_id:
                        rule["enabled"] = not rule.get("enabled", True)
                        coordinator._save_settings()
                        return self.json({"rule": rule})
                return self.json({"error": "not_found"}, status_code=404)
            if action == "upsert_rule":
                label = str(data.get("label", "")).strip()
                event_type = str(data.get("event_type", "")).strip().lower()
                if not label or not event_type:
                    return self.json(
                        {"error": "required_fields"}, status_code=400
                    )
                if not re.fullmatch(r"[a-z0-9_]+", event_type):
                    return self.json(
                        {"error": "invalid_event_type"}, status_code=400
                    )
                if not event_type.startswith("recamera_"):
                    event_type = f"recamera_{event_type}"
                try:
                    threshold = float(data.get("threshold", 0.8))
                    cooldown = float(data.get("cooldown", 5.0))
                except (TypeError, ValueError):
                    return self.json(
                        {"error": "invalid_number"}, status_code=400
                    )
                if not 0 <= threshold <= 1 or not 0 <= cooldown <= 3600:
                    return self.json(
                        {"error": "invalid_number"}, status_code=400
                    )
                rule = coordinator.upsert_acoustics_rule(
                    {
                        **data,
                        "label": label,
                        "event_type": event_type,
                        "threshold": threshold,
                        "cooldown": cooldown,
                    }
                )
                return self.json({"rule": rule})
            return self.json({"error": "unknown_action"}, status_code=400)
        return self.json({"error": "unknown_resource"}, status_code=404)


class WebRTCProxyView(HomeAssistantView):
    """Proxy authenticated go2rtc signaling without exposing device credentials."""

    url = "/api/recamera_pro/webrtc/{entry_id}"
    name = "api:recamera_pro:webrtc"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request, entry_id):
        coordinator = self._hass.data.get(DOMAIN, {}).get(entry_id)
        ticket = request.query.get("ticket", "")
        if coordinator is None or not coordinator.validate_webrtc_ticket(ticket):
            return web.json_response({"error": "invalid_ticket"}, status=401)

        stream = request.query.get("stream", "main")
        if stream not in ("main", "sub"):
            return web.json_response({"error": "invalid_stream"}, status=400)

        device_client = RecameraDeviceClient(
            coordinator.host,
            coordinator.device_username,
            coordinator.device_password,
        )
        try:
            await device_client.async_connect()
            upstream = await device_client.async_open_websocket(
                f"/go2rtc/api/ws?src={stream}"
            )
        except Exception:
            await device_client.async_close()
            _LOGGER.exception(
                "Unable to open reCamera Pro WebRTC signaling for %s",
                coordinator.host,
            )
            return web.json_response({"error": "device_unavailable"}, status=502)

        browser = web.WebSocketResponse(heartbeat=30, max_msg_size=4 * 1024 * 1024)
        await browser.prepare(request)

        async def browser_to_device() -> None:
            async for message in browser:
                if message.type == aiohttp.WSMsgType.TEXT:
                    await upstream.send_str(message.data)
                elif message.type == aiohttp.WSMsgType.BINARY:
                    await upstream.send_bytes(message.data)
                elif message.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break

        async def device_to_browser() -> None:
            async for message in upstream:
                if message.type == aiohttp.WSMsgType.TEXT:
                    await browser.send_str(message.data)
                elif message.type == aiohttp.WSMsgType.BINARY:
                    await browser.send_bytes(message.data)
                elif message.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break

        relay_tasks = {
            asyncio.create_task(browser_to_device()),
            asyncio.create_task(device_to_browser()),
        }
        try:
            _, pending = await asyncio.wait(
                relay_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            for task in relay_tasks:
                if not task.done():
                    task.cancel()
            await upstream.close()
            await device_client.async_close()
            if not browser.closed:
                await browser.close()
        return browser


# --- Setup ---

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the self-contained panel, APIs, and static resources."""
    hass.data.setdefault(DOMAIN, {})
    if not hass.data.get(f"{DOMAIN}_panel_registered"):
        frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/recamera_pro_static",
                    frontend_dir,
                    cache_headers=True,
                )
            ]
        )
        frontend.add_extra_js_url(
            hass, "/recamera_pro_static/recamera-icons-v2.js"
        )
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path="recamera-pro",
            webcomponent_name="recamera-pro",
            sidebar_title="reCamera Pro",
            sidebar_icon="recamera:pro",
            module_url="/recamera_pro_static/panel-v36.js?v=3.9.1",
            require_admin=True,
        )
        hass.data[f"{DOMAIN}_panel_registered"] = True
    hass.http.register_view(DevicesView(hass))
    hass.http.register_view(DeviceView(hass))
    hass.http.register_view(DeviceDetailView(hass))
    hass.http.register_view(WebRTCProxyView(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up reCamera Pro from a Home Assistant config entry."""
    conf = dict(entry.data)
    legacy_topic = f"recamera/{str(conf.get(CONF_HOST, '')).strip().lower()}/to_ha"
    if conf.get("topic_in") == legacy_topic:
        conf["topic_in"] = DEFAULT_EVENT_TOPIC
        hass.config_entries.async_update_entry(entry, data=conf)
    managed_broker = await hass.async_add_executor_job(
        load_managed_broker_config,
        hass.config.path("recamera_pro_broker", "credentials.json"),
    )
    for key, value in managed_broker.items():
        # A managed sidecar owns the bootstrap credentials. Replace only the
        # integration defaults; explicit user settings for an existing broker
        # remain authoritative.
        if key not in conf or conf.get(key) in (
            None,
            "",
            DEFAULT_BROKER_USERNAME if key == "username" else DEFAULT_BROKER_PASSWORD
            if key == "password" else DEFAULT_BROKER_HOST,
        ):
            conf[key] = value
    coordinator = RecameraProCoordinator(hass, conf, entry)
    await hass.async_add_executor_job(coordinator.load_persisted_settings)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    coordinator.start()
    hass.bus.async_listen_once("homeassistant_stop", coordinator.stop)

    if not hass.data.get(f"{DOMAIN}_legacy_api_registered"):
        hass.data[f"{DOMAIN}_legacy_api_registered"] = True
        hass.http.register_view(MessagesView(coordinator))
        hass.http.register_view(UploadView(coordinator))
        hass.http.register_view(UploadFileView(coordinator))
        hass.http.register_view(StatusView(coordinator))
        hass.http.register_view(ClearView(coordinator))
        hass.http.register_view(SettingsView(coordinator))
        hass.http.register_view(TemplatesView(coordinator))
        hass.http.register_view(CustomTemplateView(coordinator))
        hass.http.register_view(ToggleView(coordinator))
        hass.http.register_view(EventRulesView(coordinator))

    entity_registry = er.async_get(hass)
    for entity_id in LEGACY_ENTITY_IDS:
        if entity_registry.async_get(entity_id) is not None:
            entity_registry.async_remove(entity_id)

    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload reCamera Pro and its entity platforms."""
    if not await hass.config_entries.async_unload_platforms(
        entry, [Platform(platform) for platform in PLATFORMS]
    ):
        return False

    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.stop()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove per-device persisted settings after the config entry is deleted."""
    settings_file = hass.config.path(f"recamera_pro_{entry.entry_id}.json")
    if os.path.exists(settings_file):
        await hass.async_add_executor_job(os.remove, settings_file)

