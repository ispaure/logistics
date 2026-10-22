# Application extension points

[Developer index](development.md)

## Workflows

A feature registers a `WorkflowContribution` with a stable workflow ID and a
lazy handler. The handler imports the feature-owned dialog only when the user
invokes the workflow.

This prevents unrelated feature UI modules from being imported together.

`desktop.actions.execute_action()` handles actions consistently for Folders,
Servers, and Debug. Disabled actions cannot execute. Workflow actions pass their
data and parent through to the feature-owned handler, whose dialog owns any
confirmation and refresh. Destructive callback actions retain the application
confirmation and refresh their owning page after the callback returns normally.

## Standalone pages

A feature registers a `PageContribution` containing a lazy `create_page`
factory. The main window does not know which feature owns the page or where
its implementation lives.

## Debug

The Debug page provides a core **Open File Browser…** button and renders
`DebugActionContribution` objects from the feature registry. The core button asks
for a folder and opens `desktop.file_browser.FileBrowserWindow`. If a Debug action references a workflow, the generic workflow
dispatcher resolves the corresponding feature-contributed workflow.

The Debug page never imports feature implementations directly.

System Tools owns its Windows repair command payloads. Its Debug actions use the
commonUtils PowerShell wrapper to start an administrator console (`Start-Process
-Verb RunAs`, `-NoExit`, and an encoded command), without repair files in `Scripts/`.
The configured CHKDSK drive is validated before launch. The action result reports
console startup after UAC, rather than completion of the repair.

## Feature settings

Features contribute settings independently of navigation/action pages. Settings
uses a category sidebar and preserves each feature’s widget layout. Factories
are lazy; enabled features can supply `refresh()` and `can_close()` on the widget.
Disabled widgets remain owned so edits and active windows are not discarded.

```python
from pathlib import Path
from features.contributions import FeatureContributions, SettingsContribution

def create_settings(parent):
    from .ui.settings import MySettingsWidget
    return MySettingsWidget(parent)

def get_contributions():
    return FeatureContributions(settings=[
        SettingsContribution('My settings', 'preferences', create_settings,
                             config_files=(Path(__file__).with_name('config.ini'),))
    ])
```

The same `settings` field is supported by unified `Feature` declarations.
`settings_id` must be unique within its feature. Set `scope='personal'` for user
settings; the default is `application`. `config_scope` can identify a different
scope for contributed files (for example personal controls with application INI
defaults). A file-only contribution can omit `create_widget`.

Settings uses the reusable commonUtils `ScopedSettings` component to show only
applicable Application Settings/Personal tabs. All `config_files` in a scope
share one INI files section with a file selector and section/key editors, plus
Source for advanced edits. `separate_tab=True` gives a custom widget its own
section only when siblings require nesting; a lone panel appears directly.
Other text files retain the plain-text editor. Conventional feature `config.ini` files are
available even while a feature is disabled. Application INI files are in
**Settings → Configuration**. Editors preserve UTF-8 BOM/newlines, save atomically,
and refuse to overwrite changes made outside the editor. Settings is distinct
from feature action pages such as Links or Smart Home.

New feature-wide settings belong directly in the feature's `config.ini`. See
[typed INI conventions](../user/configuration.md#feature-ini-settings) for suffixes
and dropdown choices. The schema lives in `commonUtils.configuration.ini_schema` and its editor in
`commonUtils.ui.settings.ini_editor`; Logistics imports it directly and explicitly
opts into typed keys. `commonUtils.formats.iniType.INIFile` remains schema-free. Keep fallback reads
when migrating an existing public key; do not rename folder-owned configs.

Contribution lists are type-checked during collection, before UI page creation.
For example, `SettingsContribution` belongs only in `settings`; remote source
lists require `RemoteFolderSourceContribution`. A misplaced entry raises a
TypeError naming the feature and category rather than reaching folder discovery.

## Folder sources and server providers

`LocalFolderSourceContribution.get_sources()` returns named local source descriptors;
`RemoteFolderSourceContribution.get_sources()` returns remote source descriptors
with a names callback and opaque context. Folder discovery pairs local folders and
remote names in `services.folders.sources`/`models.folder_entry`. Keep the selected
credential in context; do not turn it into global mutable state.

Private folder sources declare `private = True`; their paths identify backend-owned
ciphertext rather than ordinary local directories. Folder tools default to
`supports_private_folders=False` and are skipped before availability detection for
these entries. Opt in only when both detection and actions use that backend's
supported operations. rclone opts in for encrypted Pull, Push and private browsing.

`FolderFeatureContribution` supplies an availability predicate, action provider and
optional widget factory for a `FolderEntry`. Detectors/providers run in workers and
must not prompt, provision software or access widgets. Widget factories run on the
GUI thread. Use a custom widget for a library/server selector, or `UIAction` for
simple callbacks/workflows. An action specifies exactly one callback or workflow;
workflow dialogs own their confirmations, while destructive callback actions use
the generic dispatcher confirmation. `ServerProviderContribution` supplies server
descriptors to the server-page infrastructure; contributing a provider alone does
not add a new core navigation destination.

## Documents and navigation

`DocumentLauncherContribution` supplies a stable editor ID, label, icon, opener
and optional new-document callback. Windows identify their editor through
`document_editor_id`/`document_editor_name` and use the shared document host.
Keep save decisions and readiness with the owner; see
[document close outcomes](architecture.md#independent-text-documents).

A `PageContribution` requires a unique page ID and lazy parent-aware widget factory.
Its optional `navigation_icon` gives it a direct destination. Preserve
`DestinationRail.tools_menu` and the `tools`/Misc glyph for future nested destinations,
even when every current feature has its own button. This is an explicit repository
requirement, not dead-code cleanup.

## Launch chooser registrations (Logistics)

`PageContribution.navigation_icon` is the opt-in for both a feature's navigation
rail button and its focused launch card. Supply `launch_description` for a
page-specific explanation; otherwise the card uses the feature's `FEATURE_DESCRIPTION`
or its name. The declaration's existing name, page ID, factory and order remain the
source of truth. Cards reuse retained page instances; their factories do not run
again when the user selects a launch mode. Core File Browser is mandatory, with
Workspaces and Bulk Rename provided by the host.

`DocumentLauncherContribution` adds a Read & edit card through `editor_id`, `name`,
`icon`, `order`, `open_document`, optional `new_document`, and `description`.
Only Markdown is supplied by the core. Register readers/editors here rather than
creating a second top-area card. `desktop.launch_catalog.document_launchers()` is
the single document catalog used by the landing page, sidebar and workspace chooser.

Both catalogs consume enabled registry contributions and update through existing
registry subscriptions. Disabled cards disappear instead of becoming unavailable
controls. No launch-screen feature knowledge or registration belongs in commonUtils.
The view reflows one to three columns and uses a vertical scroll area for overflow.
