# Documentation audit — 2026-10-11

This is a historical audit of the pre-migration documentation. For the current
layout and help contracts, see [documentation hierarchy](documentation-hierarchy.md).

## Scope and structure

This audit covers the 22 distributed packages under `Python/features`, the core
browser, Markdown/document hosting, bulk rename, launch/configuration paths and
application extension contracts. Implementation and regression fixtures are the
source of truth. commonUtils is a read-only Git submodule; optional local feature
links are outside the distributed documentation inventory.

The pre-migration navigation recorded below is historical. In particular,
`user_docs/README.md` and the hard-coded help-loader references below are
superseded by feature `docs/` wikis and `services.documentation`; follow the
current hierarchy guide when editing documentation.

The navigation proposed at the time was:

- Root `README.md`: product overview, installation and task-oriented guide links.
- Root `docs/user/user.md`: application navigation and links to canonical guides.
- Root `docs/user/configuration.md`: application paths, settings and resource setup.
- `Python/features/<name>/user_docs/README.md`: canonical feature user guide.
- Existing `user_docs/index.md`: compatibility link for Settings' hard-coded help loader.
- `docs/user/files-and-documents.md`: core application workflows, including the
  browser and Markdown integration; these have no separate feature package.
- `Python/desktop/bulk_rename/docs/user/user.md`: the existing bulk rename owner's guide.
- `docs/development/`: architecture, feature/extension contracts, shared ownership,
  storage, validation and this audit. Feature developer READMEs remain alongside code.

## Findings and corrections

| Finding | Evidence | Documentation treatment |
| --- | --- | --- |
| Existing guides already contain valuable workflows, but have appended contradictory descriptions | Feature `user_docs/index.md` files | Preserve verified workflows, remove contradictions, separate complex topics where useful |
| Feature help resolves `index.md` explicitly | `Python/desktop/pages/settings.py` | Keep a small compatibility entry; do not change the loader |
| Git guide calls implemented hunk actions, external tools and fetch/watch preferences future work | `git/ui/hunks.py`, `git/ui/application_preferences.py`, `git/patches.py` | Describe current capability and remaining limits |
| FUSE guide describes both shared and isolated mount paths | `fuse/mounts.py:get_remote_mount_path` | Explain credential-path hashing for mounts; local sync folders still share names |
| Aviation guide says toggles last only for a session | `features/registry.py`, `features/preferences.py` | Document persisted feature choices |
| rclone transfer description does not clearly explain mirror deletion | `rclone/sync.py`, `rclone/ui/push_dialog.py` | Explain source/destination, deletion, subfolder scope, cancellation and no rollback |
| Archive guide assumes a persistent feature page | `archives/__init__.py`, `archives/ui/window.py` | Use Documents launcher/browser activation and retained per-document sessions |
| General developer material is scattered across root and feature-root documents | `docs/development/getting-started.md`, `UI_ARCHITECTURE.md`, `FILE_BROWSER.md` | Consolidate application-wide guidance under `docs/development/`, retain entry links |
| Bulk rename mixes a user manual with Qt/API integration | `desktop/bulk_rename/README.md` | Separate user workflow from embedding/reference material |
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
A focused platform-by-platform text-to-speech engine/voice troubleshooting guide
is not present in the shared UI index. That belongs beside `commonUtils.ui.speech`;
Logistics documents its reader controls without recreating engine setup guidance.
Notification lifecycle and document hosting already have shared workspace guidance.
The optional local external feature is audited/documented separately in its owning
repository following the user's additional scope instruction.

## Validation and delivery

- All 22 distributed feature packages have canonical user guides and retained
  in-app help entry links. Core browser/Markdown and Bulk Rename keep their actual
  owners; no implementation packages were moved or added.
- Markdown path/anchor checks passed for 306 local links across 95 Logistics
  Markdown files. Another 46 commonUtils GitHub documentation targets were checked
  against the local shared checkout; this was not an HTTP availability test.
- 41 focused tests passed: `test_settings_page`, `test_feature_registry`,
  `test_feature_preferences`, `test_document_launchers`. Qt's CPU probe failed in
  the sandbox; the same tests passed outside it with `QT_QPA_PLATFORM=offscreen`.
- `git diff --check` passed. Only Markdown is included in the documentation commits;
  application behavior, dependency files and commonUtils source/pointer were unchanged
  in those documentation commits. Concurrent commonUtils documentation work was
  observed and deliberately excluded.
- Audit/plan commit: `fdc7feb`; feature and core user-guide commit: `fdbd57d`.
  navigation/developer consolidation: `f348634`. A subsequent requested publication
  recorded the shared documentation revision in `b8fcb22`; later implementation
  work updated direct imports and the shared pin in `6303cdf`.

No full application, native platform or live external-service suite was run for
this documentation-only change. Separate external-project documentation and its
validation live in that project's checkout, not the Logistics feature inventory.

## Second pass — 2026-10-11

Rechecked the current tree after the direct-import commonUtils refactor. Corrections:

- Point user-facing browser and Markdown links at the new shared user manuals.
- Explain comic metadata batch replacement, partial saves, suggestion indexing/cache,
  encrypted-cache exclusions and session-only reader position.
- State editor file-size and restored-layout limits and reconcile native/CI test wording.
- Explain Git's default-enabled discard backups and file watching, default-disabled
  periodic fetch, and configurable preview limit; remove speculative rail guidance.
- Remove the remaining obsolete Archives rail wording and explain in-place edit recovery.
- Document actual EPUB uncompressed archive/resource limits and direct shared imports.

The shared Markdown user guide now explains speech controls and unavailable engines;
platform-specific engine installation/voice troubleshooting remains the narrower gap.
The prior FUSE legacy bulk-helper concern remains present; no source fix was made.
External feature follow-ups are recorded only in its owning repository.

Second-pass validation: 81 focused tests passed (`test_comic_catalog`,
`test_comic_library`, `test_git_preferences`, `test_text_editor_recovery`,
`test_books_epub`) with headless Qt outside the sandbox. All 308 local links across
95 Markdown files and 47 shared documentation targets passed local checks.
`git diff --check` passed. Changes remain documentation-only; native applications
and external services were not exercised.
