# reCamera Pro Installer

## What this app does

On start the app copies the `recamera_pro` integration bundled into its image
into `/config/custom_components/recamera_pro`. It never touches
`configuration.yaml`, never writes to the camera and never opens network ports.

The multi-architecture image is published to GitHub Container Registry by the
repository's GitHub Actions workflow. It is built from a fixed source commit and
verifies the SHA-256 of the complete source archive. HAOS downloads the finished
image; the App does not download or execute scripts when it runs.

## Install

1. Open **Settings → Apps → Install app → Repositories** (older releases may
   show **Settings → Add-ons → Add-on Store → ⋮ → Repositories**).
2. Add this repository URL:
   `https://github.com/yyling0101-a11y/recamera-pro-ha` and add it.
3. Find **reCamera Pro Installer**, press **Install**, then **Start**. The app
   runs once and stops; the log reports `reCamera Pro <version> is installed`.
4. Restart Home Assistant: **Settings → System → ⋮ → Restart Home Assistant**.
5. **Settings → Devices & Services → Add integration → reCamera Pro**, then add
   a camera. The sidebar panel appears automatically.

An MQTT broker is still required. On HA OS install the **Mosquitto broker** app
from the built-in store.

## Update

When publishing an integration update, update the fixed source commit and its
archive SHA-256 in `Dockerfile`, then set the app `version` to the integration
manifest version. Push to `main` and wait for **Publish reCamera Pro Installer
App** to complete before asking users to update. Make sure the GHCR package is
public (GitHub → Packages → `reCamera Pro Installer` → Package settings → Change visibility → Public).
Users can then update the app and start it again. The previous copy is moved to
`/config/.recamera-pro-backups/recamera_pro-<timestamp>/` instead of being
deleted. HACS users should continue updating through HACS; do not let HACS and
this app manage the same integration directory.

## Remove the integration

Uninstalling this app does **not** remove the integration, because the files
live in your Home Assistant config. Delete the folder
`/config/custom_components/recamera_pro` with the File editor, Studio Code
Server or Samba share app, then restart Home Assistant. Backups in
`/config/.recamera-pro-backups/` can be deleted at any time.

## Troubleshooting

- **The app image cannot be downloaded**: confirm the HAOS host can reach
  `ghcr.io` over HTTPS and that the published package is public. The GitHub
  Actions workflow builds the image; HAOS does not need Docker Hub access to
  build the App locally.
- **`/config is not available`**: the app needs the Home Assistant config
  mapping; reinstall it without editing its configuration.
- **Existing HACS integration**: keep updating it with HACS, or remove the
  integration through HACS before switching to this installer.
- **`belongs to another integration`**: `/config/custom_components/recamera_pro`
  holds files whose `manifest.json` has a different domain. Nothing was changed;
  inspect and remove that folder yourself.
- **Integration missing after restart**: confirm the log printed
  `is installed`, then check **Settings → System → Logs** for `recamera_pro`.
  HA installs the `aiomqtt==2.5.1` dependency on first load, which needs
  outbound network access.
