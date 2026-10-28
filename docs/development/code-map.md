# Finding your way around the code

[Developer index](development.md)

Start with [your first contribution](getting-started.md), then use this map to find the
owner of your change. Paths below describe the current checkout, not a proposed
directory layout. The [feature conventions](features.md#where-new-code-belongs) explain where to
put new code. The [restructuring record](restructuring.md) retains migration history.

## Repository map

| Path | What belongs here |
| --- | --- |
| `Python/launch.py` | Desktop startup and shutdown composition |
| `Python/desktop/` | Desktop application shell: destinations, documents, menus, settings and browser hosting |
| `Python/features/<id>/` | Feature behavior, registration, configuration and feature-specific presentation |
| `Python/features/{discovery,registry,feature_runtime,contributions,settings,preferences}.py` | Application feature infrastructure, rather than individual tools; see its [ownership map](feature-infrastructure.md) |
| `Python/models/` | Host-level models, including folder identities |
| `Python/services/` | Logistics policies and host services; see the [domain map](services.md) |
| `Python/mobile/` | Toga mobile host and composed workflows; see the [module and test map](mobile-runtime.md) |
| `Python/commonUtils/` | Separate Git submodule for reusable machinery; maintain its implementation and API docs in that repository |
| `mobile_build/` | Mobile packaging, deployment, native bridges and validation; the app source is under `Python/` |
| `Python/tests/` | Desktop regressions plus portable/mobile contracts and packaging checks |
| `mobile_build/tests/` | Mobile host, workflow and deployment-tool tests |
| `mobile_build/native_tests/` | Acceptance scenarios and probes packaged for native mobile runtimes |
| `logistics_build/` | Logistics source/build/test/release policy and adapters for the standalone manager |
| `.github/workflows/`, `.github/scripts/` | CI, release gates and release packaging |
| `docs/development/` | Cross-cutting contracts and development guides |

`mobile_build/build/`, `mobile_build/payload/`, caches and test results are generated outputs,
not the source to edit. Root platform launchers remain desktop entry points.

## Directory names and native compatibility

The desktop shell is `Python/desktop/`, the mobile shell is `Python/mobile/`,
and mobile packaging/deployment is `mobile_build/`. These replace the former
`Python/ui_new/`, `Python/logisticsmobile/` and root `Mobile/` locations.
Imports use `desktop`, `mobile` and `mobile_build` respectively. Feature-owned
`ui/` and `mobile/` directories retain their existing names.

Briefcase retains the `logisticsmobile` app key and the installed
`io.github.ispaure.logisticsmobile` identity. Payload staging generates a tiny
`logisticsmobile` launcher that calls `mobile.app.main`; application sources,
offline help and native licenses are packaged under `mobile/`. Generated
`build/logisticsmobile/` projects and `tests.logisticsmobile` native acceptance
entry points retain their names. There are no old desktop/mobile source-package
aliases; external extensions must update their host imports.

## Find the owner by task

| I want to change… | Start here | Read next |
| --- | --- | --- |
| Desktop startup | `Python/launch.py` | [Architecture](architecture.md) |
| Rail, landing chooser or destination hosting | `Python/desktop/navigation/catalog.py`, `Python/desktop/{main_window,sidebar,landing}.py` | [Architecture](architecture.md) |
| Open document tabs or cooperative close | `Python/desktop/documents.py` | [Architecture](architecture.md#independent-text-documents) |
| Feature discovery, enablement or dependencies | `Python/features/feature_runtime.py`, `runtime/{preferences,dependencies,activation,catalog}.py`; application instance in `application.py` | [Feature lifecycle](features.md) |
| Register a feature page, settings group or launcher | The feature's `__init__.py` and any delegated contribution module | [Extension points](extension-points.md) |
| Browser actions, previews or file activation | Feature registration and handlers; `Python/desktop/file_browser.py` for host integration | [Browser extensions](file-browser.md) |
| Desktop Workspaces | `Python/desktop/pages/folders.py`, `Python/services/folders/{catalog,sources,workspaces}.py` | [Feature lifecycle](features.md#remote-folder-source-context) |
| Git commands versus Git presentation | `Python/features/git/ui/commands/`, `repository.py`; presentation in `ui/repository_view.py` | [Git developer guide](../features/git/development/development.md) |
| LM transport, saved data or desktop chat | `Python/features/lm/{transport,storage,session}.py`, `Python/features/lm/ui/` | [LM integration](../features/lm/development/lm.md) |
| EPUB or comic format behavior | `Python/features/books/`, `Python/features/comics/` | The owning feature's `README.md` |
| Mobile app composition and navigation | `Python/mobile/composition/`, `Python/mobile/{app,workspace,workspace_navigation}.py` | [Mobile workspace](mobile-workspace-navigation.md) |
| Mobile Workspaces discovery and refresh state | `Python/mobile/{folder_discovery,folder_controller,folder_hub}.py` | [Discovery ownership](mobile-runtime.md#workspaces-folder-discovery) |
| Mobile main/workspace folder listing requests | `Python/mobile/folder_listing.py`; adapters in `files_ui.py`, `workspace_navigation.py` | [Listing ownership](mobile-runtime.md#folder-listing-ownership) |
| Mobile create, rename, move and delete | `Python/mobile/file_operations.py`, `composition.presentation.file_operations`; forms in `files_ui.py` | [File operation ownership](mobile-runtime.md#file-operation-ownership) |
| Mobile folders and file operations | `Python/mobile/{folder_hub,folder_hub_ui,files_ui}.py` | [Mobile workspace](mobile-workspace-navigation.md) |
| Mobile text Open/Save As | `Python/mobile/editor_picker.py`; `app.editor_picker()` owns the instance | [Mobile host owners](mobile-runtime.md) |
| Saved-import inventory/deletion | `Python/mobile/saved_files_ui.py`; `app.saved_files()` owns the instance | [Mobile host owners](mobile-runtime.md) |
| Mobile Close/Back decisions and host replacement | `Python/mobile/session_workflows/`, `application_lifecycle.py` | [Session transitions](mobile-runtime.md#session-transition-decisions) |
| Mobile surface publication and settings | `Python/mobile/reading/`, `Python/mobile/settings/` | [Mobile runtime](mobile-runtime.md#reader-publication-boundary) |
| Mobile reader sessions and host access | `Python/mobile/{reader_sessions,private_sessions,reader_host,provider_document,provider_opening,provider_view}.py` | [Mobile architecture](mobile-architecture-roadmap.md) |
| Mobile format presentation or cloud integration | `Python/features/{books,comics}/mobile/`, rclone `mobile/` and workflow-owned `*/mobile/` | [Mobile preparation](mobile-preparation.md) |
| Which sources reach a mobile build | Owning `mobile_sources.json`; `mobile_build/tools.py` aggregates `APP_MODULES` and `DOCUMENT_MODULES` | [Mobile preparation](mobile-preparation.md) |
| Defaults, private state or resource roots | Owning feature's `config.ini`, `Python/features/settings.py`, `Python/config.py` | [Configuration and data](configuration-and-data.md) |

Feature desktop presentation is feature-owned: Git, LM, Blender, Books, IDE and Text Editor use `ui/`; substantial Blender/rclone workflows nest their own platform presentation. Books, Comics, LM and Text Editor have mobile adapters. Follow the actual
registration factory to find the presentation; do not assume every feature has
the same tree. Bulk Rename deliberately remains in `desktop/bulk_rename`.

## Trace one behavior before editing it

Desktop flow: platform launcher → `Python/launch.py` → feature registry →
declared contribution → application host → feature handler/controller → owned
domain logic and shared machinery. Factories keep toolkit imports lazy.

Mobile flow: `Python/mobile/__main__.py` → `app.main()` →
`LogisticsMobile.startup()` → host navigation/session → feature adapter →
portable format or resource code. Mobile does not start the desktop registry.
`mobile_build/tools.py` stages selected sources, so adding a file or changing imports
also requires checking the payload manifest.

For a first contribution:

1. Read the owning user guide and developer guide to understand the behavior.
2. Find its registration factory or mobile host callback and trace it to the
   implementation. Check who owns saved state, background work and closing.
3. Locate tests by owner and behavior: for example `test_feature_registry.py`,
   `test_git_ui.py`, `test_lm_ui.py` or `test_mobile_packaging.py` in `Python/tests/`.
   Use the [test folder map](testing.md#desktop-test-folders) to find each owner;
   search `mobile_build/tests/` too for mobile work.
4. Run the focused tests using the [validation guide](testing.md). For example,
   from the repository root on macOS/Linux:

   ```sh
   python3 dev.py test desktop test_feature_registry.py
   ```

   Use `py` instead of `python3` on Windows. The helper selects the environment
   and import paths; see setup in the validation guide.

5. Update the owning user guide for behavior changes, or the developer contract
   for architecture changes. Native interaction needs native validation.

Keep application policy in Logistics and reusable mechanisms in commonUtils;
see [shared ownership](commonutils-integration.md). Optional externally supplied
feature sources are separately owned and may be absent from a normal clone.

## Mobile source ownership

Supported features and host/services declare curated payload sources in `mobile_sources.json`. `mobile_build/tools.py` validates staged imports and hashes manifests with the payload. Feature manifests never start desktop discovery. Host services are grouped under `services/documents/`, `services/folders/` and `services/editors/`; platform presentation lives under `ui/` or feature `mobile/`.

## Canonical imports

The inventoried feature redirectors have been removed. `features.application.registry`
is the application-owned `FeatureRegistry` instance; callers invoke it directly.
Independent hosts/tests construct `FeatureRegistry` from `features.feature_runtime`.
Feature-owned implementations and shared native speech use their canonical imports.
`python3 dev.py compatibility` remains an inventory check; it currently has no
forwarding entries. Migrate callers, patch targets and payload manifests together
when changing owners rather than adding another redirector.

## Presentation ownership after maintenance

Desktop folder tree projection lives in `desktop/pages/folder_tree.py`; its page
retains discovery, selection and browser lifetime. LM conversation/folder actions
live in `features/lm/ui/conversation_actions.py`, coordinated with the existing
page session. Shared browser construction and workspace headers are documented in
commonUtils itself. Provider document preparation and publication live in
`mobile/provider_opening.py`, with unpublished controls built by
`mobile/provider_view.py` and lifetime retained by `ProviderDocumentSession`.

The removed feature redirectors have no remaining first-party consumers. New
callers import canonical owners, including `features.application.registry` for
the explicit application feature runtime.
