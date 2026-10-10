# File browser development

This is the Logistics integration guide for adding information panels, thumbnails,
right-click actions and double-click behavior. Reusable APIs and standalone examples
live in the [commonUtils feature guide](../commonUtils/FEATURES.md) and
[browser reference](../commonUtils/ui/README.md). Keep feature READMEs focused on
their domain rules and link here for browser wiring.

## Ownership and entry points

`commonUtils.ui.file_browser.FileBrowser` owns views, root-bounded navigation,
selection, generic File Information, filesystem actions and background preview/scan
workers. `ui_new/file_browser.py:BrowserView` hosts it and installs enabled
Logistics contributions through `registry.get_browser_extensions()`. Feature-owned
hosts can add their own controls around the same component.

Declare new capabilities in the feature's `register() -> Feature`, importing
`Feature` from `features.contributions`. That Logistics declaration extends the
shared declaration with folder/server sources, workflows, pages and Debug actions.
Do not import feature implementations into the generic host or add format checks
there. Built-in Markdown activation explicitly permits editing; documentation
buttons using `open_markdown(path)` get preview-only windows by default (holding Alt enables editing centrally). Pass
`allow_edit=True` only when the caller intends to offer editing. Link navigation
retains the originating window's mode. See [UI architecture](UI_ARCHITECTURE.md#unified-feature-declarations) for
application discovery and initialization.

## Add a format, panel and context action

In `features/<feature>/files.py`, keep constructors cheap and put format-specific
loading behind file hooks:

```python
from commonUtils.fileUtils import File
from commonUtils.filesystem import BrowserDetails, BrowserPanel

class ProjectFile(File):
    def browser_panels(self):
        return (BrowserPanel('project.details', 'Project Details', self.details),)

    def details(self):
        return BrowserDetails(fields=(('Name', self.file_name),))

    # Optional: set browser_has_thumbnail = True and implement
    # browser_thumbnail(size), where size uses physical display pixels.
```

In `features/<feature>/ui_contributions.py`, declare rules and operations separately:

```python
from commonUtils.dirUtils import Directory
from commonUtils.features import BrowserExtension, FileActivation, FileType, SelectionAction
from features.contributions import Feature

PROJECT_TYPE = 'features.project.files:ProjectFile'

def edit_selection(context):
    # Replace with your feature-owned dialog; import Qt/UI lazily.
    # context.paths contains only the accepted selection.
    print('Edit:', context.paths)

def open_project(context):
    print('Open:', context.path)

def folder_fields(directory, stats):
    return (('Project files', stats.extension_counts.get('project', 0)),)

def register():
    return Feature(
        id='project', label='Project',
        file_types=[FileType(PROJECT_TYPE, extensions=('project',))],
        browser=BrowserExtension(
            actions=[SelectionAction('edit', 'Edit Project Data',
                                     (PROJECT_TYPE, Directory), edit_selection)],
            activation=[FileActivation(PROJECT_TYPE, open_project)],
            folder_fields=folder_fields,
        ),
    )
```

Export `register` from the feature's `__init__.py`. Deferred `module:Class` references
allow discovery before dependencies/UI imports. The registry registers owned types
before initialization; the general browser installs the declaration automatically.
For replacing an existing type rather than introducing a format, use the separate
[`file_type_overrides` declaration](../commonUtils/fileTypes/README.md#replace-an-existing-type-with-your-subclass)
with a subclass of the original type.

## Panels, selection and activation

All applicable panels appear as tabs alongside generic File Information. Return
`BrowserDetails` from loaders, not widgets. Panel/thumbnail loaders execute on
browser workers and must not access Qt widgets or prompt for user input. Report
unavailable/locked previews through returned details; prompt only from an explicit
GUI action. Use shared folder scan results for counts instead of scanning again.

`SelectionAction` declares accepted file classes and/or `Directory`; mixed selections
are filtered before the handler runs. Right-clicking an unselected item targets it
alone. Folder expansion/recursion, deduplication and domain validation remain the
handler's responsibility. Action IDs are unique within the feature; the framework
namespaces them and groups entries under its label. An `is_available(context)`
predicate can hide an action when required configuration is absent; execution
still needs validation because state may change after menu construction.

The shared browser provides inline Rename and Cut/Copy/Paste by default. Logistics
adds Bulk Rename beside Rename for files and folders. Menus put opening and
clipboard actions first, then rename commands, feature tools, and Reveal last.
`SelectionAction.order` (default 100) controls feature/command ordering;
`category='rename'` places a contribution in the rename group. Comic metadata
editing precedes comic compression/encryption; archive and image tools follow,
with folder-maintenance commands last.

`FileActivation` handles matching files, with first matching declaration winning;
folders keep navigation behavior. Panels/thumbnails do not require activation or
an action. For generic built-in browser controls and direct hook signatures, use
[the shared reference](../commonUtils/ui/README.md).

## Controllers, toggles and closing

Use `BrowserExtension.create_controller(host)` for state owned by one window;
handlers receive it as `context.controller`. `context.host` is the dialog parent
and `context.browser` the shared component. Do not put widgets or worker state in
the globally cached feature declaration. A feature-specific host may pass its
existing controller to `Feature.install_browser`; retain the returned binding.
The [shared guide](../commonUtils/FEATURES.md) documents explicit installation.

Session toggles deactivate owned type rules, actions, activation and folder fields.
Cached browser objects are re-resolved after registry revisions; existing file
instances retain their class. Bindings/controllers remain owned by the host so
open dialogs and jobs can finish, and enabling reuses them. Disabling does not
undo initialization or cancel operations. Legacy installers/hooks remain supported;
new declarations must not mix `browser` with legacy `browser_extensions`.

Actions and activation run on the GUI thread. Capture validated inputs there,
then use shared workers for expensive operations. Refresh the browser after writes.
Hosts must call controller/binding `prepare_close()` and browser `stop()`, ignore
close while work remains, and retry on `idle`. Keep windows and worker owners alive
until completion. The general `FileBrowserWindow` implements this protocol; adding
a custom host requires equivalent handling. See [worker lifecycle and cancellation](UI_ARCHITECTURE.md#long-running-workflows-and-safe-closing).

## Validation

Use disposable fixtures and the [project test commands](../../README.md#development).
`test_file_browser_window.py` checks general host installation, toggles and closing;
`test_feature_registry.py` checks discovery/ownership. CommonUtils tests cover
shared selection, panels, registry revisions and declarations. Feature tests should
check their handlers, format data, validation and failure behavior instead of
repeating the shared browser contract. Manually check native menus/previews and
window shutdown on the platforms affected by UI changes.


The embedded `FileBrowserPage` and standalone `FileBrowserWindow` wrap BrowserViews
in `commonUtils.ui.workspace.Workspace`. Feature bindings/controllers belong to
one view and move with its dock when detached or reattached. Each view independently
subscribes to feature toggles and participates in cooperative shutdown. Browser
search and storage dialogs use shared directory metadata snapshots/cache; their
workers are included in `FileBrowser.stop()` and `idle` handling.


Archive inspection uses shared `ArchiveFile`/`ZIPFile` information hooks on the
existing preview worker. The [Archives feature](archives/README.md) installs its
manager and extraction actions through `SelectionAction`, its ZIP/TAR opening
through `FileActivation`, and per-view routing through `create_controller`.
CBZ activation remains with Comics. Successful writes invalidate the affected
file and reconcile its parent through the existing browser refresh APIs; the
generic host performs no archive-specific dispatch or password prompting.
