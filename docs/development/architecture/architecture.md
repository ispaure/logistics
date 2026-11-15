# Application architecture

### Find a code or UI owner

- [Repository and code map](code-map.md)
- [Screen and panel ownership](ui-architecture.md)
- [Desktop startup and lifecycle](desktop-lifecycle.md)
- [File browser development](file-browser.md)
- [Mobile host runtime](mobile-runtime.md)
- [Mobile workspaces and navigation](mobile-workspace-navigation.md)
- [Mobile accent controls](mobile-accent.md)
- [iOS Shortcut value widgets](shortcut-widgets.md)

### Change a shared contract

- [Document storage sessions](document-storage.md)
- [Mobile file storage and incoming shares](mobile-file-storage.md)
- [Reader progress and history](reader-state.md)
- [Configuration and compatibility](configuration-and-data.md)
- [Access and privacy](access-privacy.md)
- [Audio and capture privacy](audio-playback.md)
- [Logistics host services](services.md)

### Add or extend a feature

- [Feature organization and lifecycle](features.md)
- [Feature registry and infrastructure](feature-infrastructure.md)
- [Application extension points](extension-points.md)
- [commonUtils integration](commonutils-integration.md)
- [Optional external feature integration](optional-integration.md)

[Developer index](../development.md)

## Shell, features and services

Desktop uses Qt/PySide6. Mobile uses Toga and native controls, with an explicit
source manifest. The shell owns navigation and retained views. Features own
domain behavior and their own views. Logistics services own app policy.
commonUtils supplies reusable mechanisms. `logistics_build/` adapts the
standalone Build Deployment Manager to Logistics tests and releases.

A host composes a component. A provider supplies storage or service access.
A session retains state and resources until its owner retires them.

| Trace | Start here |
| --- | --- |
| Settings → Appearance | [Screen map](ui-architecture.md#find-a-screen-by-its-visible-name) |
| Encrypted or remote document open | [Provider to reader](document-storage.md#trace-a-mobile-provider-reader) |
| Desktop startup or rollback | [Desktop lifecycle](desktop-lifecycle.md) |
| Mobile startup | [Native startup progress](mobile-runtime.md#native-startup-progress) |
| Mobile packaging | [Mobile preparation](../build-release/mobile-preparation.md) |
