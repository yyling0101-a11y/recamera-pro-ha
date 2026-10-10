# reCamera Pro Installer (Home Assistant App)

A one-shot Home Assistant App (formerly “add-on”) that installs the `recamera_pro`
custom integration into `/config/custom_components/`. It is for Home Assistant
OS and other Supervisor Apps installations, not a plain Home Assistant
Container. The App is only the installer; camera management, MQTT, WebRTC, device
setup and the sidebar panel remain features of the Custom Integration.

The integration is bundled into the app image at build time from a fixed source
commit. BuildKit verifies the SHA-256 digest of the complete source archive
before unpacking it. The app does not execute a downloaded script.

Add this repository to Home Assistant:

[![Open your Home Assistant instance and add this app repository.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fyyling0101-a11y%2Frecamera-pro-ha)

Then install **reCamera Pro Installer**, press **Start** once, and restart
Home Assistant Core from its web interface. The app does not request Supervisor
API permissions and does not restart Core itself. Details, updates and removal:
[DOCS.md](DOCS.md).

If `recamera_pro` already exists and HACS is installed, the installer stops to
avoid having two update managers write to the same integration folder. Continue
managing that integration with HACS.
