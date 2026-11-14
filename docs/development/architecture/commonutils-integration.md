# commonUtils integration and ownership

[Developer index](../development.md)

`Python/commonUtils` is a Git submodule pinned by the parent repository. Root
launchers use its launcher implementation; `Python` is the import root when the
application starts. Clone recursively or initialize submodules before running.
A release ZIP includes the pinned shared source. Updating the submodule is a
separate dependency change and requires both repositories' relevant checks.

| Responsibility | Shared owner | Logistics owner |
| --- | --- | --- |
| Files, directories and format resolution | filesystem abstractions and format registry | custom comic/EPUB rules and feature ownership |
| Browser search, storage charts and previews | file browser and index/cache | browser hosts, feature bindings and selected workflows |
| Markdown rendering/editing | Markdown widgets and persistence | document routing and read-only help policy |
| Text/code editing | code editor, text IO, syntax/search primitives | Text Editor service, session checkpoint/recovery and menus |
| Rename transactions | planning, exclusive publication and rollback engine | Bulk Rename UI and CSV chapter naming |
| Archives | ZIP/TAR access and reusable operations/view | archive workspace, password decisions and document lifecycle |
| INI and atomic writes | parsers, schema, settings widgets and byte publication | keys, defaults, path bases and migration compatibility |
| Workers and presentation | operations, process progress, docking, notifications | cancellation boundaries, results, confirmations and routing |
| External commands | process/terminal abstractions | tool arguments, download versions/hashes and credentials policy |

Obsidian detection, registration and launching are implemented in Logistics.
They do not make the shared Markdown widget an Obsidian application. Similarly,
Books owns EPUB pagination/metadata; Comics owns CBZ processing policy; the shared
archive browser does not own either workflow.

## Extend without duplicating

Use `Feature` declarations and shared `BrowserExtension` contracts for file types,
selection actions and activation. Pass context and retain a per-host controller;
do not teach the shared browser to import Logistics feature modules. A reusable
primitive should accept explicit data/callbacks rather than read Logistics config.
Application-specific validation, confirmation, output names and file replacement
policies stay with the caller even when publication mechanics are shared.

Before adding a utility, check these existing shared guides:

- [Feature declarations](../../../Python/commonUtils/docs/development/reference/ui/features/features.md)
- [File browser](../../../Python/commonUtils/docs/development/reference/ui/file_browser/file_browser.md)
- [Indexing](../../../Python/commonUtils/docs/development/reference/filesystem/index/index.md)
- [Markdown](../../../Python/commonUtils/docs/development/reference/ui/markdown/markdown.md)
- [Code editor](../../../Python/commonUtils/docs/development/reference/ui/code_editor/code_editor.md)
- [Configuration](../../../Python/commonUtils/docs/development/reference/configuration/configuration.md)
- [Workspaces, document hosts and notifications](../../../Python/commonUtils/docs/development/reference/ui/workspaces.md)
- [Operation progress and close handling](../../../Python/commonUtils/docs/development/reference/ui/operation_progress.md)
- [Atomic persistence](../../../Python/commonUtils/docs/development/reference/persistence/persistence.md)

These links open the shared wiki in Logistics' pinned submodule checkout.
Initialize that checkout before following them. Missing shared documentation belongs
with the owning component; keep its API manual there.

## Current import contract

The pinned shared revision now uses direct Python packages. Historical root imports
such as `commonUtils.fileUtils`, `commonUtils.fileTypes` and `commonUtils.osUtils`
are no longer supplied by an import adapter. Use the current filesystem, formats,
runtime and integration packages shown in the
[shared API guide](../../../Python/commonUtils/docs/development/public-apis.md).
Do not restore the removed compatibility hook to fix a consumer import. This is
separate from Logistics' feature hooks and persisted settings migration rules.
Settings callers import shared editors and schemas directly and request typed keys
explicitly. Feature archive and browser code likewise imports the shared owners.

## Mobile browser boundary

The mobile browser is Python. Logistics' `mobile.browser_ui.FileBrowser`
customizes the optional Toga browser in commonUtils; Toga supplies UIKit controls
on iOS and Android controls on Android. Desktop continues to use the Qt browser.

The mobile host subclasses `ui.native_browser.recycled.RecycledBrowser`.
commonUtils owns recycled iOS/Android rows, the Java list adapter, bounded tile
presentation, thumbnail retention and stale-row protection. Logistics injects its
artwork, palette and row metrics through presentation/list factories, and retains
storage headers, visibility checks and workflow menus. The small local
`recycled_file_list` adapter also supplies book-folder and conversation lists.
Shared APIs are documented in commonUtils' native browser and native UI guides.
The shared hierarchy and resource operations do not require either UI toolkit.
Logistics owns the storage selector, mirror associations, credentials, private
document sessions, action approval and routing into readers/editors.

Mobile Files and text Open/Save As await the previous browser's close before
constructing its replacement. Scrolled-out tiles may still have cooperative
storage reads retiring; removing their controls or stopping the visible browser
is not evidence that those reads finished. Keep source dependencies alive until
retirement. Credential revocation still invalidates private generations immediately.
The shared [browser lifetime guide](../../../Python/commonUtils/docs/development/reference/ui/native_browser/native_browser.md#shared-work-and-thumbnail-lifetime)
describes task ownership at the pinned shared revision.

Within mobile, Files, Move and editor Open/Save As now resolve storage through
`FilesUI.storage_provider`. Existing pulled providers are reused with their
namespace intact; display labels are not parsed into a new provider. This keeps
encrypted and ordinary workflow branching at the provider boundary.

A future common browser entry point should accept an explicit host/backend and
provider/actions, then lazily construct the relevant adapter. It should not choose
solely from the operating system: macOS can host either the desktop Qt app or a
Toga test app. A Qt-backed desktop process must not acquire a mandatory Toga
dependency, and headless data operations must not import either UI package.
Keep the two presentations while sharing provider/navigation contracts and
reusable models. Virtual archive members or a hierarchical JSON catalogue need
an adapter supplying identities, children, access and capabilities; rendering a
generic hierarchy alone does not implement those user workflows. This entry-point
proposal is not implemented by the current Logistics-local consolidation.

## Native component ownership

The local mobile architecture cleanup moves image gestures, configurable native
destination containment, Back routing and chrome restoration into the optional
`commonUtils.ui.native` package. Its API and Android bridge packaging are documented
in commonUtils itself. Logistics supplies destination definitions, close/navigation
guards, document controllers and adaptive workspace composition. Feature-specific
mobile EPUB/comic presentation is under the Books/Comics owners; catalogue storage,
private-content policy and transfer workflows remain in Logistics. See the
[mobile runtime](mobile-runtime.md) for Logistics host ownership and checks.

Failed Apple navigation construction can retain an inactive cleanup owner.
Keep the `NativeNavigationHost` available for its uninstall retry before another
install; Logistics shell extensions remain responsible for their own acquisitions
and application mutations. Shared rollback does not reverse unrecorded consumer
mutations or establish UIKit acceptance. The
[native lifetime contract](../../../Python/commonUtils/docs/development/reference/ui/native/native.md#lifetime-ownership-before-backend-changes)
documents retained cleanup and its host-fixture limits.

## Grouped shared UI imports

Logistics uses `commonUtils.ui.workspaces`, `tasks`, `readers`, `settings` and
`appearance` for their owning implementations. Former flat forwarding modules
have been removed; imports and mock patch targets use the grouped paths. Keep
application navigation and document policy in Logistics. See the [shared module map](../../../Python/commonUtils/docs/development/reference/ui/ui.md#module-organization)
for ownership and canonical paths.

## Shared mechanisms in Logistics

| Workflow | commonUtils owns | Logistics owns |
| --- | --- | --- |
| Preferences and Notes Library registry | Atomic byte publication | Serialization, schema, path, recovery and error reporting |
| Mobile startup, layout and memory | Event-loop dispatch context, native subscriptions and coalesced layout signals | Loop lifetime, host validity, geometry filtering and resource cleanup |
| Native document pickers and editors | Scoped document access, menu primitives and Find/Replace | Name, MIME and size policy, import storage, draft/session lifetime and editor menu rebinding |
| Mobile reading and appearance | Draw acknowledgement, measured progress, WebView HTML loading and reflow, native controls and painting | Loading and publication policy, document identifiers, privacy, format preferences, palette, E Ink and reader routing |
| Private copies, repeatable pulls and Calibre exports | Content snapshots, hashing and stream helpers | Persisted baseline format, revision validation, export planning and destination validation |
| Archive metadata and rclone migration | Byte manifests, archive member replacement and directory relocation | Format-specific limits and EPUB member rules, storage locations and migration triggers |
| Device-protected keys | Native key storage mechanisms | Key identifiers, protected records, ciphertext paths, backup exclusions, and forget/recovery policy |

See [mobile runtime ownership](mobile-runtime.md#owners) for the application
adapters and [mobile preparation](../build-release/mobile-preparation.md) for staging shared
dependencies. API details live in the pinned commonUtils wiki.

## Resource and lifetime ownership

Logistics now imports provider mechanisms from `commonUtils.runtime.resources`
and optional Qt resource windows from `commonUtils.ui.resources`. Removed flat
resource paths have no forwarding aliases. Native message boxes resolve through
the ordinary `commonUtils.ui.native.dialogs` package owner. Keep deferred imports,
mock patch targets and curated mobile source manifests aligned with the pin.

The shared [resource map](../../../Python/commonUtils/docs/development/reference/runtime/resources/resources.md)
and [Qt resource guide](../../../Python/commonUtils/docs/development/reference/ui/resources/resources.md)
record those APIs. The shared reader/browser, configuration, persistence, archive,
index and workspace guides describe the consolidated lifecycle and phase owners.
Logistics keeps voice preferences/privacy, source/credential identity, transfer
approval and document routing. Check these contracts in the pinned checkout when
changing a consumer or advancing the dependency.

## Delegation boundaries

Cache-backed local search now composes the shared directory index and resource
search. Logistics supplies its explicit ordinary-provider allowlist and database
location; private, remote and session-only sources continue to search in memory.

Git delegates disk-spooled process capture and best-effort diagnostic filtering,
but retains arguments, environment filtering, sensitive-operation policy and Git
errors. LM delegates data-only SSE framing; response JSON, tool interpretation and
response limits stay feature-owned.

Native document sources adapt shared callback-backed archive views. Bridge action
names, passwords, member limits, revision validation and credential retirement
remain in Logistics. Images uses shared optional Pillow encoding and exclusive
publication mechanics; Images and Comics retain quality choices, acceptance
thresholds, animation preservation, source-change checks and file deletion/moves.
Shared copy fallback retains its existing non-atomic guarantee; atomic exclusive
rename remains a different operation. API details belong in commonUtils' resource,
archive, format, process, stream and persistence guides.

`logistics_build/release_verification.py` uses the existing
`commonUtils.runtime.streams.stream_signature` to hash manifest-listed ZIP members
incrementally, checking cooperative cancellation between reads. Logistics retains
the HTTPS/download bound, published digest, source/dependency/tag checks, member
path validation and cancellation error contract. Manifest/version JSON still uses
the existing metadata reads. This reuses an available shared API without changing
the commonUtils or manager dependency pins; `test_release_verification.py` covers
bounded member reads, cancellation and digest mismatches.
