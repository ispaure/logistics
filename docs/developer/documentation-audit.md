# Documentation audit — 2026-10-11

## Scope and structure

This audit covers the 22 distributed packages under `Python/features`, the core
browser, Markdown/document hosting, bulk rename, launch/configuration paths and
application extension contracts. Implementation and regression fixtures are the
source of truth. commonUtils is a read-only Git submodule; optional local feature
links are outside the distributed documentation inventory.

The final navigation is:

- Root `README.md`: product overview, installation and task-oriented guide links.
- Root `USER_GUIDE.md`: application navigation and links to canonical guides.
- Root `CONFIGURATION.md`: application paths, settings and resource setup.
- `Python/features/<name>/user_docs/README.md`: canonical feature user guide.
- Existing `user_docs/index.md`: compatibility link for Settings' hard-coded help loader.
- `Python/ui_new/user_docs/README.md`: core application workflows, including the
  browser and Markdown integration; these have no separate feature package.
- `Python/ui_new/bulk_rename/user_docs/README.md`: the existing bulk rename owner's guide.
- `docs/developer/`: architecture, feature/extension contracts, shared ownership,
  storage, validation and this audit. Feature developer READMEs remain alongside code.

## Findings and corrections

| Finding | Evidence | Documentation treatment |
| --- | --- | --- |
| Existing guides already contain valuable workflows, but have appended contradictory descriptions | Feature `user_docs/index.md` files | Preserve verified workflows, remove contradictions, separate complex topics where useful |
| Feature help resolves `index.md` explicitly | `Python/ui_new/pages/settings.py` | Keep a small compatibility entry; do not change the loader |
| Git guide calls implemented hunk actions, external tools and fetch/watch preferences future work | `git/ui/hunks.py`, `git/ui/application_preferences.py`, `git/patches.py` | Describe current capability and remaining limits |
| FUSE guide describes both shared and isolated mount paths | `fuse/mounts.py:get_remote_mount_path` | Explain credential-path hashing for mounts; local sync folders still share names |
| Aviation guide says toggles last only for a session | `features/registry.py`, `features/preferences.py` | Document persisted feature choices |
| rclone transfer description does not clearly explain mirror deletion | `rclone/sync.py`, `rclone/ui/push_dialog.py` | Explain source/destination, deletion, subfolder scope, cancellation and no rollback |
| Archive guide assumes a persistent feature page | `archives/__init__.py`, `archives/ui/window.py` | Use Documents launcher/browser activation and retained per-document sessions |
| General developer material is scattered across root and feature-root documents | `DEVELOPMENT.md`, `UI_ARCHITECTURE.md`, `FILE_BROWSER.md` | Consolidate application-wide guidance under `docs/developer/`, retain entry links |
| Bulk rename mixes a user manual with Qt/API integration | `ui_new/bulk_rename/README.md` | Separate user workflow from embedding/reference material |
| Shared component guides are linked through a checkout | `.gitmodules`, commonUtils guides | Use stable GitHub paths for reusable contracts; keep Logistics integration guidance local |

## Feature evidence inventory

Every row has a feature declaration, a user guide and application regression coverage
except Obsidian and Links, whose focused behavior is primarily exercised through
integration/registry coverage. This is a source audit, not certification of live services.

| Feature | Main implementation checked | Relevant regression area |
| --- | --- | --- |
| Archives | declaration, backend, document routing, create/extract UI | archive browser/workspace/password tests |
| Aviation Tools | page, supplied data and calculation adapters | aviation tools |
| Books | contributions, reader, preferences, metadata | EPUB/pagination/reader/reading feature |
| Calibre | detection, folder widget, export planning/application | calibre |
| Comics | contributions, compression, reader, metadata/encryption | comic library/compression/encryption/readers |
| Dropbox | source detection, conflict review/deletion | dropbox |
| File Tools | browser actions, scan/delete dialogs | file tools/folder safety |
| Flight Simulator | configuration, preset writes/backups | flight sim |
| FUSE | mount arguments, readiness, credential-specific paths | fuse |
| Git | repository, hunk actions, preferences, job lifecycle | git backend/UI/preferences/merge |
| Images | dialogs, batch processing, metadata | image staging/color/alpha/folder tools |
| Links | configured catalog and URL resolution | feature registry/actions |
| Media | CSV validation, rename planning, review dialog | MKA renames |
| Minecraft | bounded detection, platform launch, properties widget | Minecraft platforms |
| Obsidian | detection, registration and launch | integration/feature declarations |
| Perforce | config detection and Linux terminal launch | perforce |
| Plex | selected credential context, package/restore | plex |
| rclone | credentials, sync arguments, push dialog/progress | rclone outcomes/progress/structured UI |
| Smart Home | bridge configuration, worker page, event scripts | smart home |
| System Tools | selected drive and battery-power restoration | system tools |
| Text Editor | service, checkpoint/recovery, file operations | editor/extensions/recovery |
| YouTube Downloader | validated settings, process execution/sync | downloader/worker UI |

## Follow-up concerns, not code changes

- rclone's query parser returns copied-file entries only. Do not describe it as a
  complete deletion preview. GUI sync is consequential and has no application rollback.
- Same-named rclone remotes still target the same managed local folder across configs,
  even though FUSE mounts are isolated. Users must select the intended account.
- FUSE's retained `mount_all_rclone_conf_remotes` helper waits without passing config
  context to its readiness call. The ordinary on-demand GUI route passes it. This
  legacy utility merits a separate regression/fix, outside this documentation task.
- Calibre export, Plex preferences/data restore and Git credential/JSON preference
  saving are multi-step operations; partial results must not be described as globally atomic.
- Aviation data/formulas and machine-specific X-Plane presets are deliberately narrow;
  this audit does not validate their domain accuracy or broaden supported workflows.
- Desktop gestures, speech engines, real mounts, credential helpers and external
  applications need native/live testing; mocked fixtures cannot establish those outcomes.

## commonUtils documentation ownership and gaps

Existing commonUtils guides cover file browsing/indexing, Markdown/code editing,
feature declarations, workspaces, archives, configuration, workers and persistence.
Logistics should link to them rather than maintain another full shared manual.
The shared UI index does not provide a focused end-user guide for text-to-speech
engine/voice troubleshooting or a dedicated notification lifecycle/API guide.
Those belong beside `commonUtils.ui` (speech and notification modules); Logistics
only documents its reader controls and application notification integration.
