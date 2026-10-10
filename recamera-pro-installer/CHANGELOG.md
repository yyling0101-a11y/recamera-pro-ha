# Changelog

## 3.9.2

- One-shot installer app that installs a commit-pinned, SHA-256-verified
  `custom_components/recamera_pro` source bundle into `/config/custom_components/recamera_pro`.
- Backs up prior versions, skips the already-installed version, and guards
  against overwriting a HACS-managed integration.
- Publishes a multi-architecture prebuilt image to GHCR so HAOS does not need
  to pull a Docker Hub builder image during installation.
