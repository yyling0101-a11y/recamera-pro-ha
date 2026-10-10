#!/usr/bin/with-contenv bashio
# ==============================================================================
# Copy the bundled reCamera Pro integration into /config/custom_components
# ==============================================================================

declare DOMAIN="recamera_pro"
declare PAYLOAD="/payload/${DOMAIN}"
declare COMPONENTS_DIR="/config/custom_components"
declare TARGET="${COMPONENTS_DIR}/${DOMAIN}"
declare BACKUP_ROOT="/config/.recamera-pro-backups"
declare STAGE="${COMPONENTS_DIR}/.recamera_pro.install.$$"
declare APP_MARKER=".recamera-pro-managed"

declare backup=""
declare version=""
declare installed_version=""
declare install_complete="false"
declare hacs_component="/config/custom_components/hacs"

fail() {
  bashio::log.error "$1"
  exit 1
}

cleanup() {
  if [ "${install_complete}" != "true" ] && [ -n "${backup}" ] && [ -e "${backup}" ]; then
    if [ -e "${TARGET}" ]; then
      rm -rf "${TARGET}"
    fi
    if mv "${backup}" "${TARGET}"; then
      bashio::log.warning "Incomplete installation rolled back; previous integration restored"
    else
      bashio::log.error "CRITICAL: automatic restore failed; previous integration remains at ${backup}"
    fi
  fi
  rm -rf "${STAGE}"
}

[ -d /config ] || fail "/config is not available; the app must map the Home Assistant config directory"
[ -f "${PAYLOAD}/manifest.json" ] || fail "the bundled integration payload is missing"
grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' "${PAYLOAD}/manifest.json" \
  || fail "the bundled payload is not the recamera_pro integration"

version="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${PAYLOAD}/manifest.json" | head -n 1)"
[ -n "${version}" ] || fail "cannot read the integration version from manifest.json"

if [ -e "${TARGET}" ] && [ -d "${hacs_component}" ] && [ ! -f "${TARGET}/${APP_MARKER}" ]; then
  fail "an existing recamera_pro integration was found while HACS is installed. Keep managing it with HACS, or remove it through HACS before using this installer; no files were changed"
fi

if [ -f "${TARGET}/${APP_MARKER}" ] && [ -f "${TARGET}/manifest.json" ]; then
  installed_version="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${TARGET}/manifest.json" | head -n 1)"
  if [ "${installed_version}" = "${version}" ]; then
    bashio::log.info "reCamera Pro ${version} is already installed; no files changed"
    exit 0
  fi
fi

bashio::log.info "Installing reCamera Pro ${version} into ${TARGET}"

mkdir -p "${COMPONENTS_DIR}" "${BACKUP_ROOT}" || fail "cannot write to ${COMPONENTS_DIR}"
[ ! -e "${STAGE}" ] || fail "temporary path ${STAGE} already exists"
mkdir -p "${STAGE}" || fail "cannot create ${STAGE}"
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

cp -a "${PAYLOAD}/." "${STAGE}/" || fail "copying the integration failed"
printf '%s\n' "Managed by the reCamera Pro installer app" > "${STAGE}/${APP_MARKER}"

# Validate the complete staged copy before moving the existing installation.
[ -f "${STAGE}/manifest.json" ] \
  || fail "staged manifest.json is missing; the existing integration was left untouched"
grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' "${STAGE}/manifest.json" \
  || fail "staged manifest.json has the wrong domain; the existing integration was left untouched"
installed_version="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${STAGE}/manifest.json" | head -n 1)"
[ "${installed_version}" = "${version}" ] \
  || fail "staged manifest.json has the wrong version; the existing integration was left untouched"
[ -s "${STAGE}/__init__.py" ] && [ -s "${STAGE}/config_flow.py" ] \
  || fail "staged integration files are incomplete; the existing integration was left untouched"

if [ -e "${TARGET}" ]; then
  [ -f "${TARGET}/manifest.json" ] \
    || fail "the existing ${TARGET} has no manifest.json; refusing to replace it"
  grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' "${TARGET}/manifest.json" \
    || fail "the existing ${TARGET} belongs to another integration"
  backup="${BACKUP_ROOT}/recamera_pro-$(date +%Y%m%d-%H%M%S)-$$"
  [ ! -e "${backup}" ] || fail "backup path already exists: ${backup}"
  mv "${TARGET}" "${backup}" || fail "cannot move the previous version to ${backup}"
  bashio::log.info "Previous version moved to ${backup}"
fi

if ! mv "${STAGE}" "${TARGET}"; then
  if [ -n "${backup}" ]; then
    mv "${backup}" "${TARGET}" || bashio::log.error "CRITICAL: automatic restore failed; previous integration remains at ${backup}"
  fi
  fail "install failed; the previous version was restored"
fi
trap - EXIT HUP INT TERM

[ -f "${TARGET}/manifest.json" ] \
  && grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' "${TARGET}/manifest.json" \
  && grep -Eq '"version"[[:space:]]*:[[:space:]]*"'"${version}"'"' "${TARGET}/manifest.json" \
  || {
    rm -rf "${TARGET}"
    if [ -n "${backup}" ]; then
      mv "${backup}" "${TARGET}" || bashio::log.error "CRITICAL: automatic restore failed; previous integration remains at ${backup}"
    fi
    fail "post-install validation failed; the previous integration was restored when available"
  }

install_complete="true"

bashio::log.info "reCamera Pro ${version} is installed"
bashio::log.info "1) Restart Home Assistant: Settings > System > top right menu > Restart Home Assistant"
bashio::log.info "2) Add a camera: Settings > Devices & Services > Add integration > reCamera Pro"
bashio::log.info "An MQTT broker is required: install the Mosquitto broker app if you do not have one"
