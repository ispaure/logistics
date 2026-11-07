# Developing Logistics

Start with the [contributor walkthrough](getting-started.md) to set up your
checkout, trace a behavior to its owner and validate your first change. For a
change to an existing feature, find its entry in the [feature catalog](../features/features.md)
and open its Development guide.

Run these commands from the repository root. On Windows, use `py` in place of
`python3`.

```sh
python3 dev.py doctor
python3 dev.py owners
python3 dev.py test desktop test_feature_registry.py
python3 dev.py lint
```

## Application and feature code

| If you are changing… | Start here |
| --- | --- |
| An existing behavior and need to find its owner | [Repository and code map](code-map.md) |
| Desktop startup, destinations, document tabs or lifetimes | [Desktop architecture](architecture.md) |
| Desktop or mobile settings presentation | [Screen and panel ownership](ui-architecture.md) |
| Preference schemas, persistence or migrations | [Configuration and data](configuration-and-data.md) |
| Feature declarations and discovery | [Feature conventions](features.md), [registry and import boundaries](feature-infrastructure.md) |
| A workflow, provider, settings section or other registration | [Extension points](extension-points.md) |
| Browser actions, formats and activation | [File browser](file-browser.md) |
| Shared Logistics policy and cross-host composition | [Service owners](services.md) |
| A shared library call or an optional external feature | [commonUtils boundary](commonutils-integration.md), [optional integration boundary](optional-integration.md) |

## Documents and mobile

| If you are changing… | Start here |
| --- | --- |
| Document resources, imports, editor integration or storage | [Document storage](document-storage.md) |
| Reading positions, bookmarks, favourites or history | [Reader state](reader-state.md) |
| Access, resume authentication or private sessions | [Access and privacy](access-privacy.md) |
| Audio consent, capture privacy or playback | [Audio playback](audio-playback.md) |
| Mobile host composition, callbacks or session lifetime | [Mobile runtime](mobile-runtime.md) |
| Workspaces, file drawers, paired panes or adaptive shell | [Mobile workspace navigation](mobile-workspace-navigation.md) |
| Active Duo feedback and outstanding checks | [Duo feedback plan](iphone-duo-feedback-plan.md) |
| Mobile theme accents | [Mobile accent](mobile-accent.md) |
| Startup, scrolling or reader responsiveness | [Mobile performance](mobile-performance.md) |
| Native phone/Watch widgets or Shortcuts | [Shortcut value widgets](shortcut-widgets.md) |

## Testing, builds and delivery

| Task | Reference |
| --- | --- |
| Select and run checks for a change | [Testing](testing.md), including a [worked contribution](testing.md#worked-contribution-desktop-lm-attachments) |
| Add a regression or diagnose a failing test | [Adding tests](adding-tests.md) |
| Run platform-specific checks | [Platform checks](platform-checks.md) |
| Store reports or run an isolated probe | [Local validation artifacts](validation-artifacts.md) |
| Find the owner of build or deployment logic | [Build and deployment ownership](build-deployment-audit.md), [mobile tooling map](build-tooling.md) |
| Change a Logistics plan or evidence and delivery workflow | [Build manager adapter](build-manager.md), [combined journey contracts](build-manager-journeys.md) |
| Stage mobile source, dependencies or resources | [Mobile preparation](mobile-preparation.md), [open-source notices](open-source-notices.md) |
| Set up, build or debug the mobile app | [Mobile handbook](mobile-handbook.md), [mobile commands](mobile-launchers.md) |
| Install an app build on a device | [Device deployment](mobile-device-deployment.md) |
| Reproduce the experimental PySide6 iOS fixture | [Qt proof setup](qt-proof-launchers.md) |
| Prepare a release | [Release gates](releasing.md), [TestFlight](mobile-testflight.md) |

## Documentation

Update the guide for the reader affected by your change. The
[documentation hierarchy](documentation-hierarchy.md) defines audience and
feature ownership, packaging and compatibility links. See
[documentation viewer checks](documentation-viewer-verification.md) for desktop
and mobile validation.
