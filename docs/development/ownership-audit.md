# Feature ownership and cleanup audit

Status: historical October 20 assessment with subsequent implementation records.
The [developer index](development.md) and owning guides describe current contracts.
See [the October 21 implementation record](restructuring.md#october-21-developer-maintainability-pass)
for the incremental developer-tooling and controller changes.

[Developer index](development.md) · [Earlier restructuring](restructuring.md) ·
[Shared ownership](commonutils-integration.md)

Assessment: October 20, 2026, against the local working tree, including existing
uncommitted changes. The original findings below are retained as an audit baseline; the local
implementation status records the subsequent cleanup.

## Local implementation status

The cleanup was applied in the migration sequence below, without committing,
pushing, resetting or staging existing work. Both repositories retain their local
changes; the commonUtils submodule pointer was not advanced. Existing modified
and untracked files were copied to a temporary recovery checkpoint before edits.

- Git publication uses the shared atomic writer; Calibre/Minecraft widgets are
  nested under their feature UI owners, with compatibility imports.
- Portable collection scans and decoder-name policy live under Comics
  `collection/`; Books owns mixed metadata mapping/indexing and mobile library
  presentation. Comic batch workflows have an explicit composed state owner.
- Books speech controls use injected presentation services. Reusable speech,
  native voice engines/listeners, private WebViews and image-header probes live
  in commonUtils, with shared API documentation and focused regressions.
- Text Editor owns Notes Library presentation. Books/Comics format controllers
  own search/navigation, page preparation and layout tasks while the host retains
  storage, credentials and workspace lifecycle. Prepared-view publication uses
  setters so it respects composed state ownership.
- The custom-path font adapter is under editor services. PDF backends are nested
  behind the stable facade. LM lock/context adapters can be injected independently.

The remaining large cloud, workspace and application modules were reassessed as
host coordination; this pass did not split them by line count or rename the shell
and test infrastructure. Native-device validation is separate from host tests.

## Result and scope

The most useful cleanup is completing ownership boundaries around mobile reading,
collections and Notes Libraries. Most desktop feature presentation is already in
the right feature. Moving more files without changing state and dependencies
would leave the main maintenance problems intact.

The inventory examined 583 production Python modules under `Python`, excluding
commonUtils, tests and the external feature link. It covered 26 feature packages,
the mobile host, desktop shell, services and models. Detailed source review and
focused execution concentrated on Books, Comics, Calibre, PDF, Images, Notes
Libraries and their host/shared-library integration. Other features received an
inventory/import pass, not an exhaustive behavioral review. Build tooling and
native Java/Objective-C behavior were not comprehensively audited.

Existing work already supplies feature-owned desktop readers, portable EPUB/CBZ
metadata plans, shared archive rewriting, native UI primitives, composed mobile
controllers and owner-declared mobile payloads. Preserve these gains. The older
assessment's completed migrations are not new cleanup candidates.

The checkout contains substantial uncommitted mobile, Books and commonUtils work.
Stabilize that work before overlapping migrations; do not attribute its changes
to this audit or reset them to obtain a clean starting point.

## Prioritized findings

Priority here means maintenance order, not a claim of a user-visible defect.

| Order | Finding and source evidence | Proposed owner and outcome |
| --- | --- | --- |
| 1 | Books speech presentation imports the application it is meant to serve: `ReadAloudPanel` imports `logisticsmobile.control_icons`, `appearance` and `speech_overlay` in [speech_view.py](../../Python/features/books/mobile/speech_view.py). [Markdown speech](../../Python/logisticsmobile/markdown_speech.py) and Settings also use Books' speech implementation. | First inject presentation, voice preferences and overlay factories through explicit services. Then extract reusable utterance/session/native-engine mechanics into commonUtils. Keep document text extraction, highlight mapping, preference keys and privacy decisions with their Logistics owners. |
| 2 | [PrivateWebView](../../Python/features/books/mobile/private_view.py) implements nonpersistent WebKit/Android behavior, but [Notes Library browsing](../../Python/logisticsmobile/obsidian.py) also consumes it. This is a shared native component housed inside an EPUB feature. | A proposed commonUtils native private-WebView component should own backend construction, bounded memory-only content and disposal. Books retains EPUB HTML/bridge policy; Notes retains vault routing and link containment. Inject bounds and neutral messages rather than carrying book-specific limits/errors into the shared API. |
| 3 | [reader_ui.py](../../Python/logisticsmobile/reader_ui.py) combines library presentation, importing, unlock prompts, EPUB events/search/location saving and comic navigation. [provider_ui.py](../../Python/logisticsmobile/provider_ui.py) repeats those format responsibilities for provider-backed documents alongside private editor/session handling. | Introduce feature-owned Books and Comics presentation controllers using a small host contract. Retain provider identity, credential revocation, writer ownership, workspace routing and publication approval in the host. Move one complete workflow with its state/cancellation owner at a time. |
| 4 | [comics/mobile/collection.py](../../Python/features/comics/mobile/collection/__init__.py) contains portable scans and metadata batch execution, but also dispatches EPUB metadata through `features.books.mobile.metadata`. [index.py](../../Python/features/comics/mobile/index.py) indexes mixed ordinary imports. Neither module imports a native toolkit. | Nest comic scanning/batch logic under a portable Comics collection package. Put mixed Books & Comics catalogue coordination under a Books library package; supply per-format metadata loaders instead of making the comic engine dispatch EPUBs. Split portable EPUB catalogue mapping from its mobile form adapter. |
| 5 | [library_ui.py](../../Python/logisticsmobile/library_ui.py) handles mixed metadata indexing and comic batch editing; [files_ui.py](../../Python/logisticsmobile/files_ui.py) hosts provider/local comic batch workflows. These workflows are not general file-browser operations. | Move batch form orchestration to Comics mobile collection presentation. Move mixed library filtering/catalogue presentation to Books mobile library presentation. The host supplies storage access, current-generation checks, navigation and publication callbacks. |
| 6 | [obsidian.py](../../Python/logisticsmobile/obsidian.py) owns a full Notes Library browser with history, preview, links and editing; [notes_actions.py](../../Python/logisticsmobile/notes_actions.py) also resolves storage and cloud locations. Desktop Notes Library UI and its portable model already belong to Text Editor. | Move browser presentation beside `features/text_editor/mobile/`, with an explicit host contract. Keep storage/location resolution and credential lifetimes in the mobile host. Retain Obsidian detection as the existing supported library-entry convention; do not merge Text Editor with the external Obsidian launcher feature. |
| 7 | [images/validation.py](../../Python/features/images/validation.py) is already shared by EPUB, comic and Markdown rendering, but hard-codes mobile byte/dimension/animation policy in the parser. | Candidate for a toolkit-independent commonUtils image-header probe. Keep allowed formats, 8 MiB/16 MP/8192-edge bounds and animation acceptance in caller policy wrappers. This is header inspection, not complete image integrity validation; do not expand its promises during extraction. |
| 8 | [Git preferences](../../Python/features/git/preferences.py) still implement a JSON temporary-file/fsync/replace writer while [commonUtils persistence](../../Python/commonUtils/persistence/__init__.py) already supplies atomic byte publication. | Serialize the exact existing Git payload locally and delegate publication mechanics to the existing shared API. Retain indentation, escaping, legacy custom-path fields, malformed-file protection and sparse INI migration policy. This needs a compatibility check, not a new generic settings framework. |
| 9 | [code_font.py](../../Python/features/code_font.py) sits in feature infrastructure, is used by Git/IDE/Text Editor, and imports Text Editor preferences. Default font coordination already delegates to commonUtils styling; the local coordinator handles custom paths. | Move the remaining consumer-specific adapter to `services/editors/ui/`, preserving custom-path behavior and patch/import compatibility where required. Reuse shared styling for defaults. Do not move Text Editor preference schemas into commonUtils. |
| 10 | Calibre's [folder_widget.py](../../Python/features/calibre/folder_widget.py) and Minecraft's [folder_widget.py](../../Python/features/minecraft/folder_widget.py) remain at package root while both packages have recognizable domain owners. | Nest these widgets under their feature `ui/` owners and update lazy contribution factories. Retain compatibility imports where consumers need them. Useful consistency work, but less valuable than the ownership fixes above. Keep Calibre detection, export naming and device policy separate from generic EPUB reading. |
| 11 | [pdf/document.py](../../Python/features/pdf/document.py) combines bounded input, document lifetime and Qt/Apple/Android rasterizers. [LM storage](../../Python/features/lm/storage.py) lazily calls Qt locks; LM's [IDE context adapter](../../Python/features/lm/ui/ide_context.py) discovers concrete IDE widgets globally. | Split PDF backend adapters behind the current document facade. Inject LM lease/context providers if these components need independent reuse. These are follow-ups, not evidence that merely importing PDF/LM storage currently loads every toolkit. Keep application lock/conflict policy local. |

## Books and Comics nesting

Keep stable `books` and `comics` runtime identities and their shared Settings
group. Calibre remains a separate external-application integration. A proposed
destination for the substantial remaining workflows is:

```text
features/books/
    epub.py, locations.py, metadata.py, mutations.py
    library/                 # mixed Books & Comics catalogue coordination
    ui/                      # existing desktop reader and metadata presentation
    mobile/
        library/             # mixed library presentation and filtering
        ...                  # EPUB-specific content, navigation and bridge
features/comics/
    collection/              # portable scan and batch contracts
    ui/                      # existing desktop reader and metadata presentation
    mobile/
        collection/          # comic batch forms and workflow presentation
        ...                  # comic page presentation and navigation
features/text_editor/
    notes.py                 # existing portable Notes Library rules
    mobile/
        notes_library.py     # presentation extracted from the host
services/documents/
    ...                      # host storage, publication and lifecycle contracts
```

These are proposed paths, not new feature IDs or mandatory empty folders. An
aggregate Books library may consume Comics through explicit loaders; the Comics
domain must no longer call Books to understand EPUB metadata. Existing reciprocal
registration/UI integration should remain lazy and be reviewed separately from
the domain dependency. Registration strings are not all captured by a normal
Python import scan.

Do not relocate the whole [LibraryStore](../../Python/logisticsmobile/library.py)
and [LibraryEdits](../../Python/logisticsmobile/library_edits.py) into Books. They
own UUID/checksum records, recovery journals, conflict detection and durable
publication. Those are Logistics storage contracts. A move into neutral document
services is reasonable only after extracting their current host dependencies and
proving recovery behavior. The existing storage location and record schema need
not change.

Likewise, [LocalComicSource](../../Python/logisticsmobile/comic_source.py) is not
automatically a Comics feature candidate because of its name. It supplies a native
archive transport over a host client. Either leave it at the host boundary or
move/generalize it beside document archive adapters after checking the supported
archive operations. Comic page ordering and metadata are already elsewhere.

## What belongs in commonUtils

| Candidate | Reusable contract | Logistics must retain |
| --- | --- | --- |
| Speech core/native engines | Explicit text/ranges, engine events, bounded utterances, playback clock and disposal | EPUB/Markdown text sources, preferences, scene ownership, locked-session policy and title redaction |
| Native private WebView | Backend-selected nonpersistent view, bounded content loading, deterministic disposal | Allowed URLs, EPUB bridge, Notes Library containment, provider/credential validity and document limits |
| Image header probing | Bytes in, detected format/dimensions/animation information out, bounded parsing | Per-workflow format/size acceptance and user messages |
| Existing atomic byte publication | Reuse its current API for remaining local writers | Serialization, schema, migrations, conflict checks and backup policy |

Inspect the pinned shared implementation before introducing new APIs. For speech,
commonUtils already owns the desktop
[read-aloud implementation](../../Python/commonUtils/ui/readers/read_aloud.py).
Extract a portable core only where semantics can be shared; desktop chunking and
mobile UTF-16 range callbacks have different contracts today. Sharing a complete
widget across Qt and Toga is not the immediate target. Native speech extraction
also requires coordinated Java/resource/manifest packaging, not just Python moves.

The shared library already owns archive access/rebuilding, verified streams,
atomic publication, temporary workspaces, native navigation and image gestures.
Do not propose those completed extractions again. In particular, Books and Comics
[mutation wrappers](../../Python/services/documents/metadata.py) correctly retain
format policy around a common archive-rewrite mechanism. Their small size is not
a reason to delete the format boundary.

Keep Comics' [archive verification/publication](../../Python/features/comics/archive_io.py)
local for now. Generalize another primitive only when a real second consumer needs
the same permission, overwrite, encryption and verification contract. Different
stat tuple layouts are not interchangeable merely because they all represent
revisions. Preserve EPUB mimetype ordering, backups, compression decisions,
Calibre export pruning and destructive-operation confirmations with their owners.

## Host cleanup beyond reading

The largest modules remain the mobile composition root (1,336 lines), provider
presentation (1,287), rclone cloud presentation (1,182), LM desktop page (1,001),
Folder Hub presentation (876), workspace navigation (867) and desktop Folders
page (843). Counts describe this working-tree snapshot and are not split limits.

For the reading work, separate library/import coordination, format presentation,
private document lifecycle and private text editing. Reuse existing
[reader host services](../../Python/logisticsmobile/reader_host.py) and
[composed workflows](../../Python/logisticsmobile/host_services.py); avoid replacing
the remaining inheritance with controllers that still forward an unrestricted
application object. Each controller should enumerate its dependencies and own its
tasks, cancellation, generation and disposal state.

The later cloud/LM/Folder Hub/workspace pass should use the same criterion:
extract an independently changing workflow, not an arbitrary block of methods.
LM already has a conversation session and Git already has job/history owners.
Review their remaining page coordination before introducing additional layers.

Keep `ui_new`, flat test discovery and feature infrastructure import paths stable
during these moves. Preserve `DestinationRail.tools_menu` and the reserved Misc
glyph. The external feature checkout is excluded from this cleanup and public
documentation navigation. No root README expansion is needed for these internal
ownership changes.

## Migration order and completion checks

1. Establish a checkpoint for existing reader/mobile/shared changes and retain the
   focused baseline below. No source files were moved during this audit.
2. Apply the small Git publication and Calibre/Minecraft presentation changes in
   independent patches. This gives reviewable early changes without entangling
   active reader state.
3. Move portable collection/batch behavior out of `mobile/`; extract per-format
   catalogue adapters and then relocate mixed library presentation. Keep record
   schemas, index privacy exclusions and output ordering unchanged.
4. Remove Books speech imports of `logisticsmobile` through explicit services.
   Extract private WebView and reusable speech/image primitives into commonUtils
   with their shared tests and owning API documentation. Publish an available
   shared commit before advancing the Logistics submodule pointer.
5. Extract Notes Library presentation, then EPUB and comic presentation from the
   reader/provider host. Preserve host lifecycle services rather than moving
   credentials, journals or global navigation into features.
6. Reassess PDF backends, LM context/leases and the remaining large host workflows
   after these changes. Defer broad naming and test-layout churn.

Each move must update lazy contribution references, imports/patch targets,
`mobile_sources.json`, native source/resource staging and owner documentation as
applicable. Completion requires focused behavior checks plus payload staging and
headless imports; a module move compiling successfully is insufficient. Exercise
superseded loads, cancelled batches, credential revocation, failed publication,
multi-window writer ownership, disposal and late speech callbacks at the boundary
being changed. Native adapter changes additionally need iOS/Android evidence.

## Cleanup verification

The local implementation was checked one step at a time, then against the broad
host suites. Final per-file reports passed for all 161 desktop files (1,533 cases,
six native-bridge skips) and all 127 mobile host files (876 cases, two optional
Node/Playwright DOM skips). The first broad desktop run had one Bulk Rename worker
timeout; its independent full-file rerun passed. The first combined mobile run
exceeded its time limit and denied localhost fixtures; separate processes with
localhost access completed the suite.

Two mobile layout fixtures simulated Android without the action-bar API added by
the pre-existing toolbar work. Their test doubles were updated; production toolbar
behavior was preserved and its dedicated tests passed. Other focused regression
fixes during extraction covered composed state handoff and canonical mock targets.

Seven focused commonUtils files passed (36 cases). The optional independent Toga
consumer case also passed when rerun using the mobile environment, where Toga is
installed. Shared checks covered image headers, speech cancellation/ranges/timers,
desktop read-aloud, native components/gestures, portability and payload staging.
A freshly staged dirty development payload included the new shared Python/Java
sources and passed portable imports with neither Qt nor Toga loaded. The shared
and compatibility Android speech listener classes compiled against the installed
Android 36 SDK using Java 8 source/target settings. Correctness
lint, documentation hierarchy/links and both repositories' whitespace checks passed.

The six desktop skips require rebuilt host native bridges. The two mobile skips
require Node/Playwright. Android/iOS app builds and physical-device speech/WebView
acceptance were not rerun; host checks do not certify native-device behavior.

The starting checkpoint retained copies of 73 modified/untracked files. They
remain present, including overlapping Books/app edits; ongoing unrelated shared
and rclone edits were preserved. Both repositories' staged diffs still match the
checkpoint. No commits or pushes were performed, and the shared dependency pointer
was left unchanged.

## Follow-up implementation review

The follow-up review checked controller dependencies, composed state handoffs,
reader/private cleanup, compatibility imports and mobile source selection. It
found a remaining ownership leak: Comics folder batches still used the Books
metadata dispatcher for comic-only snapshots. Snapshot extraction now lives in
`features/comics/collection/metadata.py`; Books imports that adapter, and Comics
batch workflows use it directly. Mixed and legacy dispatch remain compatible.
The mobile source manifest includes the new module.

All 19 focused test files passed (105 cases), covering collections, reader/private
sessions, Notes Library, reader memory, packaging, font/preferences adapters, PDF,
documentation and shared speech/image headers. A Git UI watcher test timed out
inside the sandbox and passed on a full-file rerun with native watcher access.
An isolated import check also loaded Comics batch workflows and extracted metadata
with Books, Qt and Toga blocked. Correctness lint and whitespace checks passed.
Native-device acceptance remains outside this review. Existing uncommitted work
was retained; no commits or pushes were performed.

## Verification for this assessment

All 16 selected test files passed after environment corrections: 179 outer test
cases, including a portability wrapper that ran another 58 headless checks.
This is a focused local baseline, not a full release/platform certification.

| Runtime | Isolated test files |
| --- | --- |
| Desktop `.venv` | `test_books_epub`, `test_books_reader`, `test_comics`, `test_calibre`, `test_mobile_collection`, `test_mobile_collection_index`, `test_notes_library_desktop`, `test_mobile_speech_typography`, `test_mobile_speech_timer`, `test_mobile_packaging`, `test_mobile_portability` |
| Mobile `Mobile/.venv` | `test_obsidian`, `test_notes_library`, `test_collection_parity`, `test_reader_cohesion`, `test_markdown_speech` |

The common invocation was `QT_QPA_PLATFORM=offscreen PYTHONPATH=Python
<interpreter> Python/tests/run_regressions.py <suite> --pattern <file.py>`, with
one process per file. Comics initially failed because disposable workspaces tried
to use the sandbox-restricted default Application Support directory; it passed
with `COMMONUTILS_STORAGE_ROOT` set to an isolated temporary directory. Reader
cohesion passed with `PYTHONPATH=Python:.`, required for its `Mobile` fixture
import. The portability harness initially failed its two synthetic chat fixtures
because localhost binding was denied; it passed when run with localhost access.
Those initial failures are environment findings, not demonstrated product bugs.

All five documentation-layout checks also passed, covering wiki hierarchy,
relative links, compatibility entries and the root README acknowledgement.
`git diff --check` passed.

No user libraries, remote transfers or external application/device workflows were
exercised. Existing uncommitted source changes were preserved. Shared API
documentation remains authoritative in commonUtils; this page records consumer
ownership and proposed work only.
