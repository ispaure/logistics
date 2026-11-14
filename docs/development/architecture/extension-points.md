# Application extension points

Register lazy, owner-scoped declarations through [Feature](features.md#unified-feature-declarations).

| Add | Declaration |
| --- | --- |
| Workflow | `WorkflowContribution` with stable ID and lazy handler. `desktop.actions.execute_action()` passes data/parent. Workflow handlers own confirmation and refresh. Destructive callbacks use host confirmation. |
| Standalone page | `PageContribution` with unique ID and parent-aware factory. `navigation_icon` opts into rail and focus chooser. `launch_description` overrides the card description. |
| Folder source or server | `LocalFolderSourceContribution`, `RemoteFolderSourceContribution` or `ServerProviderContribution`. Keep provider context opaque. [Folder scope](features.md#remote-folder-source-context) |
| Folder actions | `FolderFeatureContribution` with worker-safe detector/actions and optional GUI factory. Opt into private sources only with backend-aware handlers. |
| Document opener | `DocumentLauncherContribution` with stable editor ID, icon, Open and optional New. Publish `document_editor_id` and `document_editor_name` on the retained window. [Close contract](architecture.md#independent-text-documents) |

## Debug

Use `DebugActionContribution` for feature actions. The core Debug page renders
them and dispatches contributed workflows. Its own Open File Browser action
starts a standalone browser. System Tools keeps its PowerShell repair commands
feature-owned and reports console startup after UAC.

## Feature settings

Declare `SettingsContribution` with a unique `settings_id`, lazy widget factory
or `config_files`. Use `scope='personal'` for user settings and `config_scope`
if the files belong to a different scope. The scope host groups INIs, preserves
dirty/close behavior and retains disabled widgets. Put feature defaults in the
owner's `config.ini`. Keep legacy key reads when migrating.
[Typed INI conventions](../../user/configuration.md#feature-ini-settings)

For a desktop settings change, follow the feature's registration to its
factory and open it under the declared scope. Test with
`python3 dev.py test desktop test_settings_page.py`. Expect lazy construction,
independent scoped edits and close vetoes for dirty forms. Configuration holds
application INIs; feature defaults are visible even when the feature is
disabled. CommonUtils preserves UTF-8 BOM and newline style, writes atomically
and refuses external-change conflicts.

Validate contribution types before constructing widgets. Action descriptors
specify exactly one callback or workflow. A server source supplies entries to
the shared host. A direct destination also needs a page contribution.
