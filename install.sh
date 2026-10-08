#!/bin/sh
# Safe installer/uninstaller for Home Assistant Core and official HA Container.
set -eu

DOMAIN="recamera_pro"
BROKER_CONTAINER="recamera-pro-mqtt"
BROKER_IMAGE="eclipse-mosquitto:2.0.22"
BROKER_LABEL="io.seeed.recamera-pro.managed"
BROKER_CONFIG_LABEL="io.seeed.recamera-pro.config"
BROKER_TOPIC="results/data"
CREATED_MANAGED_BROKER=0
MANAGED_BEGIN="# BEGIN recamera-pro managed"
MANAGED_END="# END recamera-pro managed"

ACTION="install"
MQTT_MODE=""
CONFIG_ARG=""
BROKER_HOST_ARG=""

if [ "$#" -gt 0 ]; then
  case "$1" in
    install|uninstall|status|credentials)
      ACTION="$1"
      shift
      ;;
  esac
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mqtt=auto|--mqtt=existing|--mqtt=create|--mqtt=skip|--mqtt=keep|--mqtt=remove)
      MQTT_MODE=${1#--mqtt=}
      ;;
    --mqtt)
      shift
      [ "$#" -gt 0 ] || {
        echo "reCamera Pro: --mqtt requires auto, existing, create, skip, keep, or remove" >&2
        exit 1
      }
      MQTT_MODE="$1"
      ;;
    --broker-host=*)
      BROKER_HOST_ARG=${1#--broker-host=}
      ;;
    --broker-host)
      shift
      [ "$#" -gt 0 ] || {
        echo "reCamera Pro: --broker-host requires an IP address or hostname" >&2
        exit 1
      }
      BROKER_HOST_ARG="$1"
      ;;
    --help|-h)
      cat <<'EOF'
Usage:
  ./install.sh install [HA_CONFIG] [--mqtt=auto|existing|create|skip]
  ./install.sh status [HA_CONFIG]
  ./install.sh credentials [HA_CONFIG]
  ./install.sh uninstall [HA_CONFIG] [--mqtt=keep|remove]

Install defaults to --mqtt=auto. Uninstall defaults to --mqtt=keep.
EOF
      exit 0
      ;;
    -*)
      echo "reCamera Pro: unknown option: $1" >&2
      exit 1
      ;;
    *)
      [ -z "$CONFIG_ARG" ] || {
        echo "reCamera Pro: more than one Home Assistant config path was supplied" >&2
        exit 1
      }
      CONFIG_ARG="$1"
      ;;
  esac
  shift
done

case "$ACTION" in
  install) MQTT_MODE=${MQTT_MODE:-auto} ;;
  uninstall) MQTT_MODE=${MQTT_MODE:-keep} ;;
  status|credentials) MQTT_MODE=${MQTT_MODE:-skip} ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_DIR="$SCRIPT_DIR/custom_components/$DOMAIN"

die() {
  echo "reCamera Pro: $*" >&2
  exit 1
}

docker_ready() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

find_docker_config() {
  docker_ready || return 1
  found=""
  for container in $(docker ps --format '{{.ID}} {{.Image}}' 2>/dev/null |
    awk '$2 ~ /home-assistant/ {print $1}'); do
    source_path=$(docker inspect -f \
      '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}' \
      "$container" 2>/dev/null || true)
    [ -n "$source_path" ] || continue
    [ -z "$found" ] ||
      die "more than one Home Assistant /config mount was found; pass the config path explicitly"
    found="$source_path"
  done
  [ -n "$found" ] || return 1
  printf '%s\n' "$found"
}

resolve_config() {
  if [ -n "$CONFIG_ARG" ]; then
    candidate="$CONFIG_ARG"
  elif [ -f /config/configuration.yaml ]; then
    candidate="/config"
  else
    candidate=$(find_docker_config) ||
      die "cannot locate Home Assistant config; pass /path/to/config explicitly"
  fi
  [ -d "$candidate" ] || die "config directory does not exist: $candidate"
  (CDPATH= cd -- "$candidate" && pwd -P)
}

HA_CONFIG=$(resolve_config)
YAML="$HA_CONFIG/configuration.yaml"
TARGET_DIR="$HA_CONFIG/custom_components/$DOMAIN"
BACKUP_ROOT="$HA_CONFIG/.recamera-pro-backups"
BROKER_ROOT="$HA_CONFIG/recamera_pro_broker"
BROKER_MARKER="$BROKER_ROOT/.recamera-pro-managed"
BROKER_CREDENTIALS="$BROKER_ROOT/credentials.json"

validate_paths() {
  case "$TARGET_DIR" in
    "$HA_CONFIG"/custom_components/"$DOMAIN") ;;
    *) die "refusing unsafe integration target: $TARGET_DIR" ;;
  esac
  case "$BROKER_ROOT" in
    "$HA_CONFIG"/recamera_pro_broker) ;;
    *) die "refusing unsafe broker target: $BROKER_ROOT" ;;
  esac
}

managed_broker_label() {
  docker inspect -f \
    '{{ index .Config.Labels "io.seeed.recamera-pro.managed" }}' \
    "$BROKER_CONTAINER" 2>/dev/null || true
}

managed_broker_config_label() {
  docker inspect -f \
    '{{ index .Config.Labels "io.seeed.recamera-pro.config" }}' \
    "$BROKER_CONTAINER" 2>/dev/null || true
}

port_1883_in_use() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '$4 ~ /:1883$/ { found=1 } END { exit !found }'
    return
  fi
  awk '$2 ~ /:075B$/ && $4 == "0A" { found=1 } END { exit !found }' \
    /proc/net/tcp /proc/net/tcp6 2>/dev/null
}

ha_mqtt_entry_present() {
  entries="$HA_CONFIG/.storage/core.config_entries"
  [ -f "$entries" ] || return 1
  grep -Eq '"domain"[[:space:]]*:[[:space:]]*"mqtt"' "$entries"
}

plugin_broker_config_present() {
  for settings in "$HA_CONFIG"/recamera_pro_*.json; do
    [ -f "$settings" ] || continue
    grep -Eq '"broker"[[:space:]]*:' "$settings" && return 0
  done
  return 1
}

other_broker_container_present() {
  docker_ready || return 1
  docker ps -a --format '{{.Names}}|{{.Image}}' 2>/dev/null |
    grep -Eiq 'mosquitto|emqx|hivemq|vernemq|nanomq'
}

detect_broker() {
  if docker_ready; then
    label=$(managed_broker_label)
    config_label=$(managed_broker_config_label)
    if [ "$label" = "true" ] && [ "$config_label" = "$BROKER_ROOT" ]; then
      printf '%s\n' "managed"
      return
    fi
    if docker inspect "$BROKER_CONTAINER" >/dev/null 2>&1; then
      printf '%s\n' "existing"
      return
    fi
  fi
  if plugin_broker_config_present ||
    ha_mqtt_entry_present ||
    other_broker_container_present ||
    port_1883_in_use; then
    printf '%s\n' "existing"
  elif docker_ready; then
    printf '%s\n' "none"
  else
    printf '%s\n' "unknown"
  fi
}

detect_broker_host() {
  if [ -n "$BROKER_HOST_ARG" ]; then
    printf '%s\n' "$BROKER_HOST_ARG"
    return
  fi
  if command -v ip >/dev/null 2>&1; then
    host=$(ip route get 1.1.1.1 2>/dev/null |
      awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')
    [ -z "$host" ] || {
      printf '%s\n' "$host"
      return
    }
  fi
  if command -v hostname >/dev/null 2>&1; then
    host=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "$host" ] || {
      printf '%s\n' "$host"
      return
    }
  fi
  die "cannot determine the host LAN address; pass --broker-host=IP"
}

random_secret() {
  od -An -N24 -tx1 /dev/urandom | tr -d ' \n'
}

install_managed_broker() {
  docker_ready || die "Docker is unavailable; cannot create the MQTT sidecar"
  label=$(managed_broker_label)
  config_label=$(managed_broker_config_label)
  if [ "$label" = "true" ] && [ "$config_label" = "$BROKER_ROOT" ]; then
    docker start "$BROKER_CONTAINER" >/dev/null 2>&1 || true
    echo "Managed MQTT broker already exists; reusing $BROKER_CONTAINER."
    return
  fi
  if docker inspect "$BROKER_CONTAINER" >/dev/null 2>&1; then
    die "container name $BROKER_CONTAINER is owned by another installation"
  fi
  port_1883_in_use &&
    die "host port 1883 is already in use; refusing to create another broker"
  if [ -e "$BROKER_ROOT" ] && [ ! -f "$BROKER_MARKER" ]; then
    die "broker directory exists without the project marker: $BROKER_ROOT"
  fi

  broker_host=$(detect_broker_host)
  case "$broker_host" in
    *[!A-Za-z0-9._:-]*) die "broker host contains unsupported characters" ;;
  esac

  echo "No existing MQTT broker was detected."
  echo "Creating isolated sidecar $BROKER_CONTAINER on $broker_host:1883."
  docker image inspect "$BROKER_IMAGE" >/dev/null 2>&1 ||
    docker pull "$BROKER_IMAGE"

  umask 077
  mkdir -p "$BROKER_ROOT/config" "$BROKER_ROOT/data"
  # Keep the first-run credentials aligned with the integration defaults so a
  # freshly created sidecar can be used immediately. Users should change these
  # credentials before exposing the broker outside the trusted LAN.
  ha_username="recamera_ha_$(random_secret | cut -c1-12)"
  device_username="recamera_device_$(random_secret | cut -c1-12)"
  ha_password=$(random_secret)
  device_password=$(random_secret)

  {
    echo "listener 1883 0.0.0.0"
    echo "allow_anonymous false"
    echo "password_file /mosquitto/config/passwords"
    echo "acl_file /mosquitto/config/acl"
    echo "persistence true"
    echo "persistence_location /mosquitto/data/"
    echo "log_dest stdout"
    echo "connection_messages true"
    echo "sys_interval 10"
  } > "$BROKER_ROOT/config/mosquitto.conf"
  {
    echo "user $ha_username"
    echo "topic read $BROKER_TOPIC"
    echo "user $device_username"
    echo "topic write $BROKER_TOPIC"
  } > "$BROKER_ROOT/config/acl"

  run_uid=$(id -u)
  run_gid=$(id -g)
  if [ "$run_uid" = "0" ]; then
    run_uid=${SUDO_UID:-1883}
    run_gid=${SUDO_GID:-1883}
  fi
  chown -R "$run_uid:$run_gid" "$BROKER_ROOT"
  docker run --rm \
    --user "$run_uid:$run_gid" \
    --entrypoint mosquitto_passwd \
    -v "$BROKER_ROOT/config:/mosquitto/config" \
    "$BROKER_IMAGE" \
    -b -c /mosquitto/config/passwords "$ha_username" "$ha_password"
  docker run --rm \
    --user "$run_uid:$run_gid" \
    --entrypoint mosquitto_passwd \
    -v "$BROKER_ROOT/config:/mosquitto/config" \
    "$BROKER_IMAGE" \
    -b /mosquitto/config/passwords "$device_username" "$device_password"

  {
    echo "{"
    echo "  \"managed\": true,"
    echo "  \"host\": \"$broker_host\","
    echo "  \"port\": 1883,"
    echo "  \"ha_username\": \"$ha_username\","
    echo "  \"ha_password\": \"$ha_password\","
    echo "  \"device_username\": \"$device_username\","
    echo "  \"device_password\": \"$device_password\""
    echo "}"
  } > "$BROKER_CREDENTIALS"
  echo "Managed by reCamera Pro install.sh" > "$BROKER_MARKER"
  chmod 600 "$BROKER_CREDENTIALS" "$BROKER_ROOT/config/passwords"

  if ! docker run -d \
    --name "$BROKER_CONTAINER" \
    --restart unless-stopped \
    --label "$BROKER_LABEL=true" \
    --label "io.seeed.recamera-pro.config=$BROKER_ROOT" \
    --user "$run_uid:$run_gid" \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    -p 1883:1883 \
    -v "$BROKER_ROOT/config:/mosquitto/config:ro" \
    -v "$BROKER_ROOT/data:/mosquitto/data" \
    "$BROKER_IMAGE" >/dev/null; then
    rm -f "$BROKER_CREDENTIALS" "$BROKER_MARKER"
    rm -rf "$BROKER_ROOT"
    die "broker container failed to start; newly-created broker files were rolled back"
  fi
  running=$(docker inspect -f '{{.State.Running}}' "$BROKER_CONTAINER")
  [ "$running" = "true" ] || die "broker container is not running"

  echo "Managed MQTT broker created successfully."
  CREATED_MANAGED_BROKER=1
  echo "Credentials are stored with mode 600 in $BROKER_CREDENTIALS"
  if [ -t 1 ]; then
    echo "Device Broker: $broker_host:1883"
    echo "Device username: $device_username"
    echo "Device password: $device_password"
  fi
}

rollback_created_broker() {
  [ "$CREATED_MANAGED_BROKER" = "1" ] || return 0
  docker_ready || return 0
  label=$(managed_broker_label)
  config_label=$(managed_broker_config_label)
  if [ "$label" = "true" ] && [ "$config_label" = "$BROKER_ROOT" ]; then
    docker rm -f "$BROKER_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ -d "$BROKER_ROOT" ]; then
    rm -rf "$BROKER_ROOT"
  fi
}

remove_managed_broker() {
  docker_ready || die "Docker is unavailable; cannot verify broker ownership"
  label=$(managed_broker_label)
  config_label=$(managed_broker_config_label)
  [ "$label" = "true" ] && [ "$config_label" = "$BROKER_ROOT" ] ||
    die "no broker container managed by reCamera Pro was found"
  [ -f "$BROKER_MARKER" ] ||
    die "broker marker is missing; refusing to remove the container"
  case "$BROKER_ROOT" in
    "$HA_CONFIG"/recamera_pro_broker) ;;
    *) die "refusing unsafe broker directory: $BROKER_ROOT" ;;
  esac
  docker stop "$BROKER_CONTAINER" >/dev/null
  docker rm "$BROKER_CONTAINER" >/dev/null
  mkdir -p "$BACKUP_ROOT"
  backup="$BACKUP_ROOT/broker-uninstalled-$(date +%Y%m%d-%H%M%S)"
  mv "$BROKER_ROOT" "$backup"
  echo "Managed MQTT broker removed. Recoverable data backup: $backup"
  echo "The Docker image was retained and no user-owned broker was changed."
}

report_broker_status() {
  state=$(detect_broker)
  case "$state" in
    managed)
      running=$(docker inspect -f '{{.State.Running}}' "$BROKER_CONTAINER" 2>/dev/null || echo false)
      echo "MQTT: project-managed broker ($BROKER_CONTAINER), running=$running"
      ;;
    existing)
      echo "MQTT: an existing user-managed MQTT configuration, listener, or broker container was detected"
      ;;
    none)
      echo "MQTT: no existing broker was detected"
      ;;
    unknown)
      echo "MQTT: broker state is unknown because Docker could not be inspected"
      ;;
  esac
}

handle_mqtt_install() {
  case "$MQTT_MODE" in
    skip)
      echo "MQTT: skipped by request."
      ;;
    existing)
      echo "MQTT: using an existing broker; no container or broker files were created."
      ;;
    create)
      install_managed_broker
      ;;
    auto)
      state=$(detect_broker)
      case "$state" in
        managed)
          install_managed_broker
          ;;
        existing)
          echo "MQTT auto-detection found an existing MQTT environment."
          echo "No broker container or broker configuration was created."
          ;;
        none)
          install_managed_broker
          ;;
        unknown)
          echo "MQTT auto-detection was inconclusive."
          echo "For safety, no broker was installed. Use --mqtt=create after checking the host."
          ;;
      esac
      ;;
    *)
      die "invalid MQTT mode for install: $MQTT_MODE"
      ;;
  esac
}

preflight_mqtt_install() {
  [ "$MQTT_MODE" = "create" ] || return 0
  state=$(detect_broker)
  case "$state" in
    managed|none)
      return 0
      ;;
    existing)
      die "an existing MQTT environment was detected; refusing --mqtt=create"
      ;;
    unknown)
      die "Docker or MQTT state cannot be verified; refusing --mqtt=create"
      ;;
  esac
}

remove_managed_yaml() {
  yaml="$YAML"
  [ -f "$yaml" ] || return 0
  temporary="$yaml.recamera-pro.$$"
  awk -v begin="$MANAGED_BEGIN" -v end="$MANAGED_END" '
    $0 == begin { managed=1; next }
    $0 == end { managed=0; next }
    !managed { print }
  ' "$yaml" > "$temporary"
  chmod --reference="$yaml" "$temporary" 2>/dev/null || true
  mv -f "$temporary" "$yaml"
}

install_integration() {
  [ -f "$SOURCE_DIR/manifest.json" ] ||
    die "integration source is missing: $SOURCE_DIR"
  grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' \
    "$SOURCE_DIR/manifest.json" ||
    die "source manifest domain is not recamera_pro"

  mkdir -p "$HA_CONFIG/custom_components" "$BACKUP_ROOT"
  stage="$HA_CONFIG/custom_components/.recamera_pro.install.$$"
  [ ! -e "$stage" ] || die "temporary install path already exists: $stage"
  trap 'rm -rf "$stage"; rollback_created_broker' EXIT HUP INT TERM
  mkdir "$stage"
  cp -R "$SOURCE_DIR"/. "$stage"/
  echo "Managed by reCamera Pro install.sh" > "$stage/.recamera-pro-managed"

  backup=""
  if [ -e "$TARGET_DIR" ]; then
    [ -f "$TARGET_DIR/manifest.json" ] ||
      die "existing target has no manifest; refusing to replace it"
    grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' \
      "$TARGET_DIR/manifest.json" ||
      die "existing target belongs to another integration"
    backup="$BACKUP_ROOT/recamera_pro-$(date +%Y%m%d-%H%M%S)"
    mv "$TARGET_DIR" "$backup"
  fi
  if ! mv "$stage" "$TARGET_DIR"; then
    [ -z "$backup" ] || mv "$backup" "$TARGET_DIR"
    die "install failed; the previous integration was restored"
  fi
  if ! grep -Eq '^[[:space:]]*recamera_pro:[[:space:]]*$' "$YAML"; then
    temporary="$YAML.recamera-pro.$$"
    if ! cp -p "$YAML" "$temporary" || ! {
      printf '\n%s\n' "$MANAGED_BEGIN"
      echo "recamera_pro:"
      echo "$MANAGED_END"
    } >> "$temporary" || ! mv -f "$temporary" "$YAML"; then
      rm -f "$temporary"
      rm -rf "$TARGET_DIR"
      [ -z "$backup" ] || mv "$backup" "$TARGET_DIR"
      die "configuration.yaml update failed; the previous integration was restored"
    fi
  fi
  echo "reCamera Pro installed in $TARGET_DIR"
  [ -z "$backup" ] || echo "Previous version backed up to $backup"
}

uninstall_integration() {
  if [ ! -e "$TARGET_DIR" ]; then
    remove_managed_yaml
    echo "reCamera Pro is not installed; managed YAML was cleaned up."
    return
  fi
  [ -f "$TARGET_DIR/.recamera-pro-managed" ] ||
    die "target was not installed by this script; use HACS or remove it manually"
  [ -f "$TARGET_DIR/manifest.json" ] ||
    die "target manifest is missing; refusing to remove files"
  grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' \
    "$TARGET_DIR/manifest.json" ||
    die "target belongs to another integration"
  mkdir -p "$BACKUP_ROOT"
  backup="$BACKUP_ROOT/uninstalled-$(date +%Y%m%d-%H%M%S)"
  mv "$TARGET_DIR" "$backup"
  remove_managed_yaml
  echo "reCamera Pro uninstalled. Recoverable backup: $backup"
}

validate_paths
[ -f "$YAML" ] || die "configuration.yaml was not found in $HA_CONFIG"

case "$ACTION" in
  install)
    preflight_mqtt_install
    trap 'rollback_created_broker' EXIT HUP INT TERM
    handle_mqtt_install
    if ! install_integration; then
      rollback_created_broker
      exit 1
    fi
    CREATED_MANAGED_BROKER=0
    trap - EXIT HUP INT TERM
    echo "Restart Home Assistant to load the integration."
    ;;
  uninstall)
    uninstall_integration
    case "$MQTT_MODE" in
      keep|skip|auto)
        echo "MQTT broker was retained. Use --mqtt=remove only for the project-managed broker."
        ;;
      remove)
        remove_managed_broker
        ;;
      *)
        die "uninstall accepts only --mqtt=keep or --mqtt=remove"
        ;;
    esac
    echo "Restart Home Assistant to finish."
    ;;
  status)
    if [ -f "$TARGET_DIR/manifest.json" ]; then
      echo "reCamera Pro is installed in $TARGET_DIR"
    else
      echo "reCamera Pro is not installed in $HA_CONFIG"
    fi
    report_broker_status
    ;;
  credentials)
    [ -f "$BROKER_MARKER" ] ||
      die "no project-managed broker credentials were found"
    [ -f "$BROKER_CREDENTIALS" ] ||
      die "managed broker credentials file is missing"
    cat "$BROKER_CREDENTIALS"
    ;;
esac
