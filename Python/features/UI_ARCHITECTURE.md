# Feature UI Ownership

Feature-specific UI belongs to the feature that owns the behavior.

Typical structure:

```text
features/<feature>/
├── backend modules
├── ui_contributions.py
└── ui/
    ├── page.py
    └── dialogs.py
```

The generic `ui_new` package owns only application-level presentation:

- Main window / tab host.
- Generic Folders page.
- Generic Servers page.
- Generic Debug page.
- Generic workflow dispatch.
- Shared UI primitives that are not feature-specific.

## Workflows

A feature registers a `WorkflowContribution` with a stable workflow ID and a
lazy handler. The handler imports the feature-owned dialog only when the user
invokes the workflow.

This prevents unrelated feature UI modules from being imported together.

## Standalone pages

A feature registers a `PageContribution` containing a lazy `create_page`
factory. The main window does not know which feature owns the page or where
its implementation lives.

## Debug

The Debug page only renders `DebugActionContribution` objects from the feature
registry. If a Debug action references a workflow, the generic workflow
dispatcher resolves the corresponding feature-contributed workflow.

The Debug page never imports feature implementations directly.


## Configuration ownership

Feature-specific configuration belongs inside the feature package:

```text
features/<feature>/config.ini
```

A value should remain in the root Logistics configuration only when it is
application-level/core configuration or when multiple independent features
directly read the same setting.

A feature depending on another feature does not make the dependency's private
configuration shared. The owning feature remains responsible for exposing the
behavior or data needed by dependent features.


## Remote folder source context

Remote features may contribute multiple selectable Folders sources through
`RemoteFolderSourceContribution`.

The generic Folders page always owns a `Local` source. A remote source supplies
remote names plus opaque backend context. That context is carried through the
generic `FolderEntry` model and interpreted only by the feature that owns it.

For rclone, the context is the selected credential `.conf` path. The context
does not become part of logical folder identity or filesystem layout.


## Shared file types

Features may expose `register_file_types()` to register their own `File` subclasses
with `commonUtils.fileTypes.registry.register_file_type`. Logistics calls these
hooks for available features before running any feature initializer. The registry
is process-wide: registrations apply to all subsequent `Directory.list_files()`
and `file_from_path()` calls, including calls in other modules and pre-existing
Directory instances. Other projects should register their types during startup,
before their first shared listing/browser use; commonUtils recommends this order
but does not enforce it. Late registration still affects future resolutions.
Domain types remain in their owning project; commonUtils owns the mechanism.


## Reusable filesystem browsing

`commonUtils.ui.file_browser.FileBrowser` owns file/folder views, navigation,
selection, generic details and filesystem actions. Its model resolves shared
File/Directory objects through the process-wide registry. Specialized File classes
contribute BrowserPanel/BrowserAction descriptors, thumbnail hooks and activation;
shared UI never imports project types. Applications embed the widget, retain their
surrounding controls, and supply action services or directory action providers.
Panel/thumbnail loaders run in workers; actions and activation run on the GUI
thread. Project constructors/detectors should not parse metadata during listing.
