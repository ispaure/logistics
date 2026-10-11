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
separate from Logistics' retained feature hooks and settings wrappers, which still
have their own explicit compatibility contracts.
