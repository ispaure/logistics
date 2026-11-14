# Feature organization and lifecycle

## Where new code belongs

Use `Python/features/<id>/` for lightweight registration, named domain modules,
`config.ini`, desktop `ui/` and optional `mobile/` with its own manifest. Keep the
stable ID. Put audience guides in `docs/features/<owner>/`; package README and
`user_docs/index.md` are compatibility links. Bulk Rename uses
`docs/features/bulk_rename/`. [Documentation hierarchy](../documentation/documentation-hierarchy.md)

## Unified feature declarations

Export lazy `register() -> Feature` from the package, using
`features.contributions.Feature`. Declare hard `requires` and optional
dependencies, deferred file types, browser bindings, pages and workflows.
The registry registers owned types before any startup hook. It validates hooks
and runs hard dependencies first. Initialization runs once per session.
Legacy browser installers still work, with one binding style per feature.
[Extension points](extension-points.md) · [Browser declarations](file-browser.md)

Keep feature defaults in its own INI. Shared app settings belong with the
host. A consumer uses its dependency's published behavior.

## Remote folder source context

`services/folders/workspaces.py` projects Local, Cloud and Home Server.
`FolderEntry` carries opaque provider context. rclone uses `.conf`, `.session`
or `CopyContext`; FUSE derives separate mount identity from the config path.
Saved credential associations keep locked copies discoverable. Match physical
local paths before adding unresolved credential placeholders.

The selected tree entry owns action scope independent of browser navigation.
Filter/source changes clear selection; refresh can restore an explicit match.
Require credential admission before detail detection, discard stale unlocks and
keep replaced browser owners until idle. Private sources require declared
backend-aware tools. Fixed Workspaces panes are resizable; use
`FoldersPage(panes_locked=False)` for detachable-layout experiments.

Desktop Local projects the Dropbox, Rclone Copies and On This Computer tabs,
defaulting to Rclone Copies. Remote credential filters start at All. Reset the
filter on source change. Loaded credentials take precedence over saved
placeholder records. Unlocking refreshes the selected account while retaining
its matching selection. Initial embedded previews are off; refresh keeps the
view's later toggle. The Files slot uses rclone's `WorkspaceUnlockView` for locked
locations. It validates passwords off-thread and publishes only while current.

## Persistent feature controls

Enable hard dependencies first. Refuse disabling a dependency with enabled
dependents. Import errors and missing requirements stay visible but unavailable.
`FEATURE_GROUP` groups toggles while keeping IDs, per-engine configuration and
type ownership. Books & Comics groups separate engines; Comics requires Images,
FUSE and Plex require rclone, and YouTube can use rclone optionally.

Disabling hides retained pages and removes future type resolution, bindings and
workflow offers. Existing jobs finish with their owners. Re-enabling restores
the bindings and type precedence. Failed enable rolls back activation state;
initializer side effects remain feature-owned. Save explicit choices as sparse
overrides. [Preferences](configuration-and-data.md)

For a registry change, run `python3 dev.py test desktop test_feature_registry.py`
and check dependency order, disabled contributions and restored type ownership.
[Runtime ownership](feature-infrastructure.md#registry-runtime-ownership)
