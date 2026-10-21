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
| Desktop navigation, document tabs or browser hosting | `Python/ui_new/` (the current desktop shell name) | [Architecture](architecture.md), [browser ownership](browser-ownership.md) |
| Mobile navigation, storage or document lifetime | `Python/logisticsmobile/` | [Mobile host owners](mobile-runtime.md) |
| Settings, registration or a new feature | Owning feature's `__init__.py` and `config.ini` | [Feature conventions](features.md), [extension points](extension-points.md) |
| A shared Logistics policy | `Python/services/` | [Service owners](services.md) |
| Mobile builds, deployment or native bridges | `Mobile/`; application source stays under `Python/` | [Mobile handbook](mobile-handbook.md) |
| Tests for any of these | `Python/tests/` or `Mobile/tests/` | [Test selection and commands](testing.md#find-the-tests-for-your-change) |

Follow registration factories to the canonical implementation. Small modules at
older paths may only forward compatibility imports. Edit the implementation they
point to. Generated `Mobile/payload/`, `Mobile/build/`, caches and test reports are
outputs; they are not source files to tweak.

## Current development references

Read only the contracts relevant to your change. Feature-specific implementation
and test maps live in `Python/features/<feature>/docs/development/`; package
READMEs link there.

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
| IDE implementation | [IDE](../../Python/features/ide/docs/development/ide.md) |
| LM implementation | [LM](../../Python/features/lm/docs/development/lm.md) |
| PDF implementation | [PDF](../../Python/features/pdf/docs/development/development.md) |
| Encrypted copies and remote browsing | [LocalCrypt](../../Python/features/rclone/docs/development/localcrypt.md), [remote browsing](../../Python/features/rclone/docs/development/remote-browsing.md) |

## Validation and evidence

[Focused host tests](testing.md) are the everyday starting point. Device interaction
and native adapter changes additionally need native validation. These references
explain particular checks and record their scope; a past passing report does not
validate a new change.

- [UI refinement validation](ui-refinement.md)
- [Documentation viewer verification](documentation-viewer-verification.md)
- [Mobile verification evidence](mobile-evidence/mobile-evidence.md)
- [Mobile performance implementation and verification](mobile-performance.md)
- [Mobile alpha verification](mobile-alpha-verification.md)
- [Mobile UI refresh evidence](mobile-ui-refresh.md)
- [Native navigation proof](mobile-navigation-proof.md)
- [PySide6 iOS reuse proof](mobile-qt-proof.md)
- [Qt proof launchers](qt-proof-launchers.md)

## Plans and historical assessments

These pages retain proposals and migration history. Use the current code map and
owner guides above for today's layout. Check each page's implementation status
before treating an old finding as remaining work. The October 21 incremental pass below adds controller boundaries and nested test
discovery. Shell renaming and wholesale test-directory moves remain deferred;
current contracts are in the owner maps above.

- [Restructuring assessment and migration record](restructuring.md)
- [October 20 ownership audit and cleanup record](ownership-audit.md)
- [Maintenance priorities](maintenance.md)
- [Mobile architecture roadmap](mobile-architecture-roadmap.md)
- [Mobile navigation plan](mobile-navigation-plan.md)
- [rclone parity plan](../../Python/features/rclone/docs/development/rclone-parity.md)
- [Books and Comics parity](../../Python/features/books/docs/development/books-comics-parity.md)
- [October 15 repository and mobile recovery audit](mobile-repository-audit.md)
- [Historical documentation audit](documentation-audit.md)

## Documentation to update with a change

Feature desktop usage belongs in `Python/features/<owner>/docs/user/`; mobile
usage belongs in that owner's `docs/user_mobile/`, and architecture/contracts in
its `docs/development/`. Systemic guides belong in the root wiki. Core UI and
Folder Hub stay there; Bulk Rename retains its existing `ui_new` documentation.
Update the root README for setup or major capability changes.

Keep package READMEs and `user_docs/index.md` as short links. Shared commonUtils
APIs and external feature internals are documented in their owning repositories.
Follow the [hierarchy rules](documentation-hierarchy.md) and verify consequential
claims against source and tests. The [older getting-started URL](getting-started.md)
remains a compatibility entry to this guide.
