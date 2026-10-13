# Mobile document host and validation

Logistics has an independent native text/Markdown prototype in
`Python/logisticsmobile`, with Briefcase configuration and tooling under
[`Mobile/`](../../Mobile/README.md). The desktop Qt launcher and its dependency
pins remain separate. The shared Qt facade retains its desktop capability gate:
the mobile host uses Toga and portable commonUtils persistence rather than
importing desktop initialization, menus or dialogs.

## Ownership and contracts

| Module | Contract |
| --- | --- |
| `documents.py` | Explicit absolute app-private root; UUID file identities; 1 MiB bounded Unicode text; original encoding/endings; exclusive creation, atomic saves and recovery JSON; stale/deleted-file rejection and safe copies |
| `access.py` | Scoped binary imports; Android content URIs are handled by ContentResolver streams; iOS URLs retain security-scoped access until reading finishes; every handle/scope is closed on failure |
| `pickers.py` | Android ACTION_OPEN_DOCUMENT and iOS UIDocumentPicker open mode; native grants are consumed immediately to import a private copy; no broad storage permission or persisted external write access |
| `app.py` | Native Home/Documents/Settings shell; selection, title editing, multiline text, New/Import/Save/copy/export/preview; checkpoints on edit, focus loss and normal exit |
| `preferences.py` | Immutable defaults and bounded private INI; validation, atomic replace, malformed-file preservation and concurrent-edit rejection |
| `preview.py` | Bounded basic Markdown HTML; escaped raw input, inert links and offline CSP |
| `smoke.py` | Fresh-interpreter desktop-dependency rejection, real runtime identity, exact test inventory and structured evidence |
| `Mobile/tools.py` | Whitelisted Logistics sources, tracked/clean shared Python sources, licenses, source SHAs and dirty-state records; strict emulator/simulator evidence verification |

The host's `paths.data` supplies private storage. Caller-provided names remain
metadata; they never become filesystem paths. UUIDs are validated before deriving
paths, and linked document files are rejected. Saved bytes and the last source
snapshot stay separate from the draft record. New UUID files are reserved exclusively and flushed before their recovery record
is published, avoiding hard links rejected by Android app sandboxes. Incomplete
new data cannot enter the visible document list without that record.
The record contains the original
bytes and edited text so an externally changed or deleted private file cannot
silently overwrite recovered edits. A failed save preserves the draft; a failed
record publication preserves its previous record. Publication after an already
successful file save can leave a recoverable conflict on reopening, requiring a
copy rather than assuming both operations committed together.

Import creates a copy, preserving the selected external source. Android grants
and iOS scoped URLs need not survive app termination because later edits use the
private copy. Editing the original provider document would require a
separate permission, bookmark and provider-write contract; it is not implemented.
The iOS picker delegate is retained until selection/cancellation. Platform choice uses the shared classifier, including older Android Python
runtimes that report Linux with `getandroidapilevel`. Android activity
results use the pinned Toga backend's `start_activity` hook. These backend/native
interfaces must be rechecked before upgrading Toga.

Draft writes currently occur on each edit. This favors simple recovery in the
small prototype; larger documents need performance work before expanding the
1 MiB limit. Focus/exit hooks supplement these checkpoints. Physical-device tests
must still check forced termination, suspension, permission denial/revocation,
providers with slow I/O, keyboard resizing and accessible touch layouts.

## Selected features and dependencies

The native app includes text/Markdown and EPUB/comic readers and uses Toga 0.5.7 backends with Briefcase
0.4.5. It installs no desktop PySide, image or archive dependencies. Staging copies
only whitelisted Logistics Python modules plus tracked shared Python sources and
licenses. It never follows the local external feature link or copies private INIs,
Git metadata or untracked shared files. Local dirty payloads are labelled and
cannot produce accepted mobile runtime evidence.

Native payloads select the portable EPUB/comic modules too. The testbed additionally
selects generated fixtures, including EPUB metadata/resource reading and comic
page bytes/ComicInfo updates. Encrypted archives, other desktop tools, external
sharing and app-store distribution remain future work. No desktop capability is enabled by a prototype build.

## Validation gates

[Native builds](../../.github/workflows/mobile-build.yml) create an Android debug
APK and an unsigned iOS Simulator app archive, with bounded build jobs and retained
source manifests/logs. Build success proves packaging, not native UI interactions.

[Document runtime checks](../../.github/workflows/mobile-runtime.yml) use the
already established CPython 3.14.7 testbeds, pinned at
`823f0323ee6ec1402088b73bce1a38473cac36dc`. Android builds x86_64 on Ubuntu 24.04;
iOS builds arm64 Simulator on macOS 15. The existing iOS resource-copy workaround
is retained. Twenty-one cases run inside each actual interpreter:

- Nine private document, recovery, encoding, conflict and scoped-import contracts.
- Three existing EPUB/comic/Markdown fixture scenarios.
- Three mobile preference and offline-preview contracts.
- Four mobile library, reading, sanitization, progress and image-bound contracts.
- Runtime identity and a desktop-dependency import boundary.

The verifier requires one report, expected native `sys.platform`, actual emulator
or simulator classification, both clean source SHAs, the exact inventory/count,
zero failures/errors and zero skips. Host runs are explicitly `desktop-harness`
and cannot pass the mobile verifier. Scoped-import unit cases use provider objects
to check lifetime/error contracts; they do not prove actual picker permissions.
Reports explicitly record `native_picker_tested: false`.

Source paths on alpha trigger the corresponding mobile jobs; manual target
controls become available once the workflows are on the default branch. New
mobile push runs supersede older mobile push runs. Existing desktop release
validation remains independent. Native artifacts are development outputs, not
store uploads or physical-device signing.

## Evidence status

The shared foundation previously passed Android and iOS in
[run 38277821906](https://github.com/ispaure/commonUtils/actions/runs/38277821906),
with seven cases per runtime. Its
[mobile test guide](../../Python/commonUtils/docs/developer/mobile-testing.md)
records those source/runtime details; this is separate from Logistics validation.

The new Logistics 14-case host harness, packaging/verifier tests and Toga dummy
widget workflow pass locally. Native iOS project generation and dependency
installation succeeded, but the local Xcode storyboard build failed with
`iOS 26.5 Platform Not Installed`; no simulator devices were available. Both [hosted native builds](https://github.com/ispaure/logistics/actions/runs/38353619087)
passed at `a02a4ba`, producing an Android debug APK and iOS Simulator app; see
[build evidence](mobile-evidence/2026-10-13-native-initial.json). The
[first Logistics runtime run](https://github.com/ispaure/logistics/actions/runs/38353619071)
passed all 13 initial cases on iOS, recorded in
[iOS evidence](mobile-evidence/2026-10-13-ios-initial.json). Android ran all 13 but
reported seven errors because its sandbox rejected hard-link publication of new
files; [the failed record](mobile-evidence/2026-10-13-android-initial.json) is retained.
New private files now use exclusive creation followed by publication of a durable
recovery record, and the suite has a fourteenth case enforcing that contract.
The [corrected runtime run](https://github.com/ispaure/logistics/actions/runs/38354610543)
passed all 14 cases with zero failures, errors or skips on both Android and iOS at
`5c4a528`; retained reports are [Android](mobile-evidence/2026-10-13-android-corrected.json)
and [iOS](mobile-evidence/2026-10-13-ios-corrected.json). Both corrected native builds
also passed in [run 38354610510](https://github.com/ispaure/logistics/actions/runs/38354610510);
see [build evidence](mobile-evidence/2026-10-13-native-corrected.json).
No physical-device or actual native picker result is claimed here.

Source releases require both mobile native builds and document runtime checks
alongside the desktop platform checks before packaging and publication. The same
commit supplies every called workflow and source payload; standalone branch runs
do not substitute for this release gate.

## Next work

1. Validate the hosted native artifacts and document runtime results, then run the
   app on simulators/emulators and physical devices with real provider selections.
2. Exercise keyboard/touch/accessibility and suspend/termination recovery before
   adding reader or IDE features.
3. Add explicit export/share and provider writeback, with stale-source checks and
   permission/bookmark handling appropriate to each platform.
4. Select target-native image/archive dependencies before enabling those features;
   then introduce signing, distribution and store metadata.

The [mobile user guide](../../Python/logisticsmobile/user_docs/README.md) describes
the implemented document flow, and [build instructions](../../Mobile/README.md)
list the independent environment and host checks.

## Phase roadmap

The authorized implementation order is phase 1 (hub/preferences/text/Markdown),
phase 2 (EPUB and comic readers), phase 3 (LM chat), and phase 4 (rclone credential
packages and feasible remote access). Each phase is committed with its phase
prefix, pushed, released on alpha only after every platform gate passes, and the
successful release commit is promoted to main for a release request. Physical
device validation and signed distribution remain distinct from source releases.

Phase 1 adds Home/Documents/Settings navigation, private INI preferences,
platform export-copy pickers and an offline basic Markdown preview. Android's
pinned WebView needs the declared Chaquopy static proxy for navigation handlers.
HTML is capped below its 2 MiB default content limit. Active HTML is never passed
through; default-src none and navigation refusal prevent preview network access.
System provider export is explicit; neither original-source writeback nor external
sharing is implied. Picker cancellation and stream cleanup are tested contracts,
not actual native-provider evidence. Static CI runs the official Toga dummy widget
and picker contracts before release, while real mobile testbeds cover the added
portable preference and preview cases.

## Phase 2 reader contracts

`library.py` streams bounded imports into private storage, validates archive member
paths/counts/sizes and refuses encryption before reusing portable EPUBBook and
ComicPages. UUID identities and checksums protect record/path associations.
`reading.py` renders an allowlist of XHTML tags with source attributes/styles and
active content removed; small validated PNG/JPEG images use data URLs under an
offline CSP. Native comic inputs have byte/dimension/pixel limits before decoding.
`library_ui.py` runs archive operations off the event-loop thread and exposes
reading-order chapter/page selection, bookmarks and optimistic progress updates.
Progress is chapter/page-granular; precise EPUB scroll restoration is future work.

Native build jobs now capture the normal app before a separate Briefcase
`--test` rebuild. Test mode runs seven actual native UI cases against generated
files and private cache data; its exit marker and JSON report must agree with the
expected backend, case inventory and exact root/shared commits. It exercises real
WebView DOM rendering and native image decoding, but supplies fixture providers
rather than opening OS pickers. The test entry point calls `_exit` only after
printing its result; it is excluded from normal app source paths. Retained native
artifacts are the pre-test normal APK/Simulator archive. Native UI evidence is a
required build-job result; packaging cannot bypass it. Physical-device pickers,
keyboard/touch/accessibility and suspension remain independent validation work.
