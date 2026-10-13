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
| `documents.py` | Explicit absolute app-private root; UUID file identities; 1 MiB bounded Unicode text; original encoding/endings; atomic files and recovery JSON; stale/deleted-file rejection and safe copies |
| `access.py` | Scoped binary imports; Android content URIs are handled by ContentResolver streams; iOS URLs retain security-scoped access until reading finishes; every handle/scope is closed on failure |
| `pickers.py` | Android ACTION_OPEN_DOCUMENT and iOS UIDocumentPicker open mode; native grants are consumed immediately to import a private copy; no broad storage permission or persisted external write access |
| `app.py` | Native selection, title editing, multiline text, New/Import/Save/copy; checkpoints on edit, focus loss and normal exit |
| `smoke.py` | Fresh-interpreter desktop-dependency rejection, real runtime identity, exact test inventory and structured evidence |
| `Mobile/tools.py` | Whitelisted Logistics sources, tracked/clean shared Python sources, licenses, source SHAs and dirty-state records; strict emulator/simulator evidence verification |

The host's `paths.data` supplies private storage. Caller-provided names remain
metadata; they never become filesystem paths. UUIDs are validated before deriving
paths, and linked document files are rejected. Saved bytes and the last source
snapshot stay separate from the draft record. The record contains the original
bytes and edited text so an externally changed or deleted private file cannot
silently overwrite recovered edits. A failed save preserves the draft; a failed
record publication preserves its previous record. Publication after an already
successful file save can leave a recoverable conflict on reopening, requiring a
copy rather than assuming both operations committed together.

Import creates a copy, preserving the selected external source. Android grants
and iOS scoped URLs need not survive app termination because later edits use the
private copy. Editing/exporting the original provider document would require a
separate permission, bookmark and provider-write contract; it is not implemented.
The iOS picker delegate is retained until selection/cancellation. Android activity
results use the pinned Toga backend's `start_activity` hook. These backend/native
interfaces must be rechecked before upgrading Toga.

Draft writes currently occur on each edit. This favors simple recovery in the
small prototype; larger documents need performance work before expanding the
1 MiB limit. Focus/exit hooks supplement these checkpoints. Physical-device tests
must still check forced termination, suspension, permission denial/revocation,
providers with slow I/O, keyboard resizing and accessible touch layouts.

## Selected features and dependencies

The native app includes text/Markdown and uses Toga 0.5.7 backends with Briefcase
0.4.5. It installs no desktop PySide, image or archive dependencies. Staging copies
only whitelisted Logistics Python modules plus tracked shared Python sources and
licenses. It never follows the local external feature link or copies private INIs,
Git metadata or untracked shared files. Local dirty payloads are labelled and
cannot produce accepted mobile runtime evidence.

The testbed payload additionally selects portable EPUB metadata/resource reading,
comic page bytes/ComicInfo updates and generated fixtures. These are headless data
operations. Image decoding, encrypted archives, mobile EPUB/comic rendering,
other desktop tools, external export/share and app-store distribution remain
future work. No desktop capability is enabled by a prototype build.

## Validation gates

[Native builds](../../.github/workflows/mobile-build.yml) create an Android debug
APK and an unsigned iOS Simulator app archive, with bounded build jobs and retained
source manifests/logs. Build success proves packaging, not native UI interactions.

[Document runtime checks](../../.github/workflows/mobile-runtime.yml) use the
already established CPython 3.14.7 testbeds, pinned at
`823f0323ee6ec1402088b73bce1a38473cac36dc`. Android builds x86_64 on Ubuntu 24.04;
iOS builds arm64 Simulator on macOS 15. The existing iOS resource-copy workaround
is retained. Thirteen cases run inside each actual interpreter:

- Eight private document, recovery, encoding, conflict and scoped-import contracts.
- Three existing EPUB/comic/Markdown fixture scenarios.
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

The new Logistics 13-case host harness, packaging/verifier tests and Toga dummy
widget workflow pass locally. Native iOS project generation and dependency
installation succeeded, but the local Xcode storyboard build failed with
`iOS 26.5 Platform Not Installed`; no simulator devices were available. Hosted
native builds and actual Logistics document runtime checks are the next evidence
gates. No physical-device or actual native picker result is claimed here.

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
