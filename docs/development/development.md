# Developing Logistics

| I want to… | Start here |
| --- | --- |
| Set up a checkout and run Logistics | [Set up and run](#set-up-and-run) |
| Find and change a feature or screen | [Application and feature code](#application-and-feature-code), [documents and mobile](#documents-and-mobile) |
| Choose, run or add a test | [Choose and run tests](#choose-and-run-tests) |
| Trace a build, validation or release workflow | [Testing, builds and delivery](#testing-builds-and-delivery) |
| Update a guide | [Documentation](#documentation) |

## Set up and run

Follow the [contributor walkthrough](getting-started.md) to install the locked
desktop environment, launch the app and trace your first change. Run
`python3 dev.py doctor` from the repository root (`py` on Windows) to check
prerequisites. It also checks mobile host tools, so a desktop-only setup can
report missing mobile dependencies.

## Application and feature code

For an existing feature, find its entry in the [feature catalog](../features/features.md)
and open its Development guide.

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

### Worked lookups

| Task | Where to start |
| --- | --- |
| Edit the desktop rclone transfer window | Follow the [desktop transfer controls](../features/rclone/development/transfers.md#find-desktop-transfer-controls) to the Qt view and its progress adapter. |
| Change a shared visual default | Use the [appearance ownership map](ui-architecture.md#appearance-and-shared-control-edit-points) to locate the shared Qt theme, Logistics native palette or transfer WebView CSS. |
| Validate RMDOC editing or reMarkable transfers | Run the [focused notebook test](#choose-and-run-tests). For physical checks, use [notebook hardware acceptance](../features/notebooks/development/hardware-acceptance.md) or the [SSH transfer qualification procedure](../features/notebooks/development/ssh-transfers.md#evidence-and-exact-device-work-needed). |

## Documents and mobile

| If you are changing… | Start here |
| --- | --- |
| Document resources, imports, editor integration or storage | [Document storage](document-storage.md) |
| Reading positions, bookmarks, favourites or history | [Reader state](reader-state.md) |
| Access, resume authentication or private sessions | [Access and privacy](access-privacy.md) |
| Audio consent, capture privacy or playback | [Audio playback](audio-playback.md) |
| Mobile host composition, callbacks or session lifetime | [Mobile runtime](mobile-runtime.md) |
| Workspaces, file drawers, paired panes or adaptive shell | [Mobile workspace navigation](mobile-workspace-navigation.md) |
| Mobile theme accents | [Mobile accent](mobile-accent.md) |
| Startup, scrolling or reader responsiveness | [Mobile performance](mobile-performance.md) |
| Native phone/Watch widgets or Shortcuts | [Shortcut value widgets](shortcut-widgets.md) |

### Plans and outstanding checks

- [Duo feedback plan](iphone-duo-feedback-plan.md) records implementation handoffs and remaining checks.

## Choose and run tests

Use [test selection](testing.md#find-the-tests-for-your-change) to find the suite
that covers your change. For a focused synthetic notebook check, run this from
the repository root using the desktop environment set up in the walkthrough.
On Windows, use `py` in place of `python3`.

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_notebooks.py
```

Add `--dry-run` to inspect the selected file and interpreter before running it.

| Task | Reference |
| --- | --- |
| Select and run checks for a change | [Testing](testing.md), including a [worked contribution](testing.md#worked-contribution-desktop-lm-attachments) |
| Add a regression or diagnose a failing test | [Adding tests](adding-tests.md) |
| Run platform-specific checks | [Platform checks](platform-checks.md) |
| Store reports or run an isolated probe | [Local validation artifacts](validation-artifacts.md) |

## Testing, builds and delivery

To trace a Logistics workflow through Build Manager, start with the
[combined journey contracts](build-manager-journeys.md). Follow the declaration
in `build-project.json` to `LogisticsProject.make_journey` in
`logistics_build/build_project.py` and the planner in
`logistics_build/manager_journeys.py`. For a validation plan, use
[`build-tests.json` suite discovery](build-manager-journeys.md#shared-tests-and-suite-discovery)
to see how the manager resolves the project’s test inventory.

| Task | Reference |
| --- | --- |
| Find the owner of build or deployment logic | [Build and deployment ownership](build-deployment-audit.md), [mobile tooling map](build-tooling.md) |
| Change the Logistics adapter or evidence workflow | [Build manager adapter](build-manager.md) |
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
