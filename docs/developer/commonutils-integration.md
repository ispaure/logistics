# commonUtils integration and ownership

[Developer index](README.md)

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

- [Feature declarations](https://github.com/ispaure/commonUtils/blob/main/ui/features/README.md)
- [File browser](https://github.com/ispaure/commonUtils/blob/main/ui/file_browser/README.md)
- [Indexing](https://github.com/ispaure/commonUtils/blob/main/filesystem/index/README.md)
- [Markdown](https://github.com/ispaure/commonUtils/blob/main/ui/markdown/README.md)
- [Code editor](https://github.com/ispaure/commonUtils/blob/main/ui/code_editor/README.md)
- [Configuration](https://github.com/ispaure/commonUtils/blob/main/configuration/README.md)
- [Workspaces, document hosts and notifications](https://github.com/ispaure/commonUtils/blob/main/ui/workspaces.md)
- [Operation progress and close handling](https://github.com/ispaure/commonUtils/blob/main/ui/operation_progress.md)
- [Atomic persistence](https://github.com/ispaure/commonUtils/blob/main/persistence/README.md)

These links follow the shared project's main branch. For an API change, inspect
the actual pinned checkout as well. Missing shared documentation should be recorded
against the owning component, not recreated as a second Logistics API manual.
See the [audit follow-ups](documentation-audit.md#commonutils-documentation-ownership-and-gaps).

## Current import contract

The pinned shared revision now uses direct Python packages. Historical root imports
such as `commonUtils.fileUtils`, `commonUtils.fileTypes` and `commonUtils.osUtils`
are no longer supplied by an import adapter. Use the current filesystem, formats,
runtime and integration packages shown in the
[shared API guide](https://github.com/ispaure/commonUtils/blob/main/docs/developer/public-apis.md).
Do not restore the removed compatibility hook to fix a consumer import. This is
separate from Logistics' feature hooks and persisted settings migration rules.
Settings callers import shared editors and schemas directly and request typed keys
explicitly. Feature archive and browser code likewise imports the shared owners.

## Mobile browser boundary

The mobile browser is Python. Logistics' `logisticsmobile.browser_ui.FileBrowser`
customizes the optional Toga browser in commonUtils; Toga supplies UIKit controls
on iOS and Android controls on Android. Desktop continues to use the Qt browser.
The shared hierarchy and resource operations do not require either UI toolkit.
Logistics owns the storage selector, mirror associations, credentials, private
document sessions, action approval and routing into readers/editors.

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
[architecture roadmap](mobile-architecture-roadmap.md) for the baseline assessment
and validation sequence.

## Grouped shared UI imports

Logistics uses `commonUtils.ui.workspaces`, `tasks`, `readers`, `settings` and
`appearance` for their owning implementations. Former flat forwarding modules
have been removed; imports and mock patch targets use the grouped paths. Keep
application navigation and document policy in Logistics. See the [shared module map](https://github.com/ispaure/commonUtils/blob/main/ui/README.md#module-organization)
for ownership and canonical paths.

## Consumer consolidation

Feature preference and Obsidian registry writers use shared atomic byte publication.
Logistics still owns their serialization, schemas, paths, recovery and error messages.
Registry writes preserve compact UTF-8 JSON and the trailing newline.

Mobile startup binds its cooperative loop through `commonUtils.ui.native.event_loop`.
The shared helper owns dispatch context restoration; Logistics owns loop lifetime.

Native memory/configuration subscriptions use shared `ui.native.memory`. Logistics
guards active hosts and chooses resource cleanup/theme refresh; subscriptions
suppress queued callbacks after disposal.

System document selection and scoped byte access live in shared native documents
and runtime document-access adapters. `logisticsmobile.pickers` retains document
name validation, text export limits and MIME policy; Logistics owns import storage.

Native menu construction and presentation helpers now use shared `ui.native`
components. Logistics' action adapters retain editor rebinding, session checks,
transfer guards and coroutine scheduling. Editor disposal retires its native menu.

Mobile editors bind shared native Find/Replace to explicit editor/container widgets.
TextEditorView still owns text-change notification, draft retention and session saves.

Mobile browser byte labels use shared `filesystem.format_size` with binary units.

Repeatable pulls and private-copy revisions use shared verified content snapshots.
Persisted baselines retain relative names and SHA-256 hex; private revisions retain
their original five-field stat tuple and digest bytes. Calibre hashing uses shared
streams; its export plan and destination validation remain feature-owned.

Shared archive rebuilding owns byte manifests and member replacement. Logistics'
metadata service retains comic/EPUB plans, the processing limit and EPUB mimetype
ordering/storage rules. Native archive shortcuts still avoid decoding whole files.

Legacy rclone migration delegates directory relocation/link rebasing to shared
filesystem relocation. Application Support locations and migration triggers remain
in `features.rclone.storage`. Neither repository changes existing stored paths.
