# Developing Logistics

Start with [setup and your first change](testing.md). It covers running the app,
choosing a code owner, running focused checks and updating the right guide.
The [worked LM attachment contribution](testing.md#worked-contribution-desktop-lm-attachments)
traces a complete change through registration, implementation and tests.
The commands below run from the repository root; use `py` instead of `python3`
on Windows.

```sh
python3 dev.py doctor
python3 dev.py owners
python3 dev.py --help
python3 dev.py test desktop test_feature_registry.py
python3 dev.py lint
```

## Find the place to edit

| Change | Start here | Guide |
| --- | --- | --- |
| A feature's controls or behavior | `Python/features/<feature>/`; desktop presentation in `ui/`, mobile adapters in `mobile/` | [Code and owner map](code-map.md) |
| Desktop navigation, document tabs or browser hosting | `Python/desktop/` | [Architecture](architecture.md), [browser ownership](browser-ownership.md) |
| Mobile navigation, storage or document lifetime | `Python/mobile/` | [Mobile host owners](mobile-runtime.md) |
| Settings, registration or a new feature | Owning feature's `__init__.py` and `config.ini` | [Feature conventions](features.md), [extension points](extension-points.md) |
| A shared Logistics policy | `Python/services/` | [Service owners](services.md) |
| Mobile build tooling ownership | `mobile_build/` | [Build tooling map](build-tooling.md) |
| Mobile builds, deployment or native bridges | `mobile_build/`; application source stays under `Python/` | [Mobile handbook](mobile-handbook.md) |
| Tests for any of these | `Python/tests/` or `mobile_build/tests/` | [Test selection and commands](testing.md#find-the-tests-for-your-change) |

Follow registration factories to the canonical implementation. Feature redirectors
have been removed; import the owning module directly. The application feature
runtime is `features.application.registry`. Generated `mobile_build/payload/`, `mobile_build/build/`, caches and test reports are
outputs; they are not source files to tweak.

## Current development references

Read only the contracts relevant to your change. Feature-specific implementation and test maps live in
`docs/features/<feature>/development/`; source-package READMEs link there.

| Topic | Reference |
| --- | --- |
| Feature discovery and infrastructure exceptions | [Feature infrastructure](feature-infrastructure.md) |
| Desktop presentation ownership | [UI architecture](ui-architecture.md) |
| Browser actions, formats and activation | [Browser extensions](file-browser.md) |
| Paths, settings and stored data | [Configuration and data](configuration-and-data.md) |
| Logistics versus reusable library code | [commonUtils boundary](commonutils-integration.md) |
| Documentation locations and compatibility links | [Documentation hierarchy](documentation-hierarchy.md) |
| Mobile payload manifests and portable imports | [Mobile preparation](mobile-preparation.md) |
| Mobile file/conversation drawers and paired panes | [Workspace navigation](mobile-workspace-navigation.md) |
| Mobile build/deployment reference | [Mobile launchers](mobile-launchers.md) |
| Paired iPhone/iPad installation | [Device deployment](mobile-device-deployment.md) |
| TestFlight archives and uploads | [TestFlight](mobile-testflight.md) |
| Desktop and mobile release gates | [Releasing](releasing.md), [platform checks](platform-checks.md) |
| Optional external feature hosting | [Integration boundary](optional-integration.md) |
| IDE implementation | [IDE](../features/ide/development/ide.md) |
| LM implementation | [LM](../features/lm/development/lm.md) |
| PDF implementation | [PDF](../features/pdf/development/development.md) |
| Encrypted copies and remote browsing | [LocalCrypt](../features/rclone/development/localcrypt.md), [remote browsing](../features/rclone/development/remote-browsing.md) |

## Validation and evidence

[Focused host tests](testing.md) are the everyday starting point. Device interaction
and native adapter changes additionally need native validation. These references
explain particular checks and record their scope; a past passing report does not
validate a new change.

- [UI refinement validation](ui-refinement.md)
- [Documentation viewer verification](documentation-viewer-verification.md)
- [Local validation artifacts](validation-artifacts.md)
- [Mobile performance implementation and verification](mobile-performance.md)
- [Mobile alpha verification](mobile-alpha-verification.md)
- [Mobile UI refresh evidence](mobile-ui-refresh.md)
- [Native navigation proof](mobile-navigation-proof.md)
- [PySide6 iOS reuse proof](mobile-qt-proof.md)
- [Qt proof launchers](qt-proof-launchers.md)

## Plans and historical assessments

Use the [current audit implementation status](maintenance/remaining-work-audit.md)
for completed units and the remaining native acceptance gate. The
[history index](maintenance/history/history.md) preserves dated assessments and
implementation evidence; old proposed next steps are not today's backlog.
Current code and test owners are linked above. Host source lives in
`Python/desktop/` and `Python/mobile/`; build tooling lives in `mobile_build/`.

- [October 22 readability and shared-mechanism validation](restructuring.md#october-22-readability-and-shared-mechanism-pass)
- [Restructuring assessment and migration record](restructuring.md)
- [October 20 ownership audit and cleanup record](ownership-audit.md)
- [Ecosystem maintenance audit and progress](maintenance/maintenance.md)
- [Maintenance priorities](maintenance.md)
- [Mobile architecture roadmap](mobile-architecture-roadmap.md)
- [Mobile navigation plan](mobile-navigation-plan.md)
- [rclone parity plan](../features/rclone/development/rclone-parity.md)
- [Books and Comics parity](../features/books/development/books-comics-parity.md)
- [October 15 repository and mobile recovery audit](mobile-repository-audit.md)
- [Historical documentation audit](documentation-audit.md)

## Documentation to update with a change

Keep all substantive guides in this root wiki. Feature desktop usage belongs in
`docs/features/<owner>/user/`, mobile usage in `user_mobile/`, and architecture in
`development/` under the same feature section. Systemic guides keep their existing
root audience branches. Update the root README for setup or major capabilities.
Package READMEs and `user_docs/index.md` remain short compatibility links.
Shared commonUtils APIs and external feature internals stay in their own wikis.
Follow the [hierarchy rules](documentation-hierarchy.md) and verify consequential
claims against source/tests. The [older getting-started URL](getting-started.md)
remains a compatibility entry to this guide.

## Refactored owner contracts

The current guides cover application composition and lifetimes rather than the
former flat modules:

- [Mobile composition, transitions, reading and settings](mobile-runtime.md#composition-and-explicit-host-capabilities)
- [Detached desktop/mobile Folder Hub projection](services.md#detached-folder-hub-projection)
- [Desktop launch catalog](architecture.md#desktop-launch-and-destination-projection)
- [Feature runtime owners](feature-infrastructure.md#registry-runtime-ownership)
- [LM generation lifecycle](../features/lm/development/development.md#shared-desktop-and-mobile-generation)
- [Transfer review approval](../features/rclone/development/development.md#review-session-and-execution-handoff)
- [Git captured command requests](../features/git/development/development.md#captured-command-boundary)

Shared provider, speech, transfer, archive, index and workspace APIs are documented
in commonUtils; use the [integration boundary](commonutils-integration.md).
