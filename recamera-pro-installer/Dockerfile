# https://developers.home-assistant.io/docs/apps/configuration#app-dockerfile
#
# The integration is bundled from a fixed commit. BuildKit verifies the complete
# source archive before any file is used.
FROM ghcr.io/home-assistant/base:latest

ARG INTEGRATION_COMMIT=3ec70c59b99129b0e0b86c6123785ce9d12efdef
ARG INTEGRATION_ARCHIVE_SHA256=e32136d60eeb38197bff33c69728ea4fd6096f063b8c2d8c7c3d072cb9ba38c0

ADD --checksum=sha256:${INTEGRATION_ARCHIVE_SHA256} \
    "https://codeload.github.com/yyling0101-a11y/recamera-pro-ha/tar.gz/${INTEGRATION_COMMIT}" \
    /tmp/source.tar.gz

RUN set -eux \
    && mkdir -p /tmp/source /payload \
    && tar -xzf /tmp/source.tar.gz --strip-components=1 -C /tmp/source \
    && test -d /tmp/source/custom_components/recamera_pro \
    && cp -a /tmp/source/custom_components/recamera_pro /payload/recamera_pro \
    && rm -rf /tmp/source /tmp/source.tar.gz \
    && grep -Eq '"domain"[[:space:]]*:[[:space:]]*"recamera_pro"' /payload/recamera_pro/manifest.json \
    && grep -Eq '"version"[[:space:]]*:[[:space:]]*"3\.9\.2"' /payload/recamera_pro/manifest.json \
    && test -s /payload/recamera_pro/__init__.py \
    && test -s /payload/recamera_pro/config_flow.py

COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
    io.hass.type="app" \
    io.hass.version="3.9.2" \
    io.hass.arch="aarch64|amd64" \
    org.opencontainers.image.title="Home Assistant App: reCamera Pro Installer" \
    org.opencontainers.image.description="Installs the reCamera Pro custom integration into Home Assistant without a terminal or HACS." \
    org.opencontainers.image.source="https://github.com/yyling0101-a11y/recamera-pro-ha" \
    org.opencontainers.image.licenses="Apache-2.0"

CMD [ "/run.sh" ]
