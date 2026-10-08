"""Constants for the reCamera Pro integration."""

DOMAIN = "recamera_pro"
DEVICE_IDENTIFIER = "recamera_pro"
DEVICE_NAME = "reCamera Pro"
MANUFACTURER = "Seeed Studio"
MODEL = "reCamera Pro"

PLATFORMS = ["sensor", "event"]

CONF_DEVICE_NAME = "device_name"
CONF_HOST = "host"
CONF_DEVICE_USERNAME = "device_username"
CONF_DEVICE_PASSWORD = "device_password"
DEFAULT_BROKER_HOST = "127.0.0.1"
DEFAULT_BROKER_PORT = 1883
DEFAULT_BROKER_USERNAME = "admin"
DEFAULT_BROKER_PASSWORD = "admin"
DEFAULT_EVENT_TOPIC = "results/data"

LEGACY_ENTITY_IDS = (
    "recamera_pro.last_sound",
    "recamera_pro.confidence",
    "recamera_pro.last_event",
    "recamera_pro.sound_event",
    "recamera_pro.listening",
    "recamera_pro.confidence_threshold",
)

# Bus event fired for every incoming/outgoing message (chat panel uses this).
EVENT_MESSAGE = f"{DOMAIN}_message"

# Default sound types that can be detected.
DEFAULT_SOUND_TYPES = [
    "glass_break",
    "dog_bark",
    "knock",
    "baby_cry",
    "smoke_alarm",
    "doorbell",
    "scream",
    "help",
]
