# Developing the rclone feature

The rclone feature loads credential ZIPs, browses online files, and runs explicit
Push and Pull transfers. It also supports LocalCrypt, an offline copy whose files
stay encrypted on disk. Desktop uses the rclone CLI. Android and iOS use the
embedded Go bridge in `mobile_build/rclone_bridge/`.

## Try a change to credential import

On desktop, open **Settings → rclone → Credential packages → Import credential ZIP…**.
`Python/features/rclone/ui_contributions.py:get_contributions` registers the
panel. `ui/page.py:RclonePage._import_credential_zip` passes the selected file to
`Python/features/rclone/credentials.py:import_credential_package`.

For example, revise the error message when an import would replace a different
ZIP with the same name. Keep the existing file and the retry path. The
offscreen fixture creates a synthetic ZIP and directs imports into a temporary
folder. Run from the repository root with the desktop environment set up:

```sh
python3 dev.py test desktop --exact-file Python/tests/resources/test_credential_import_ui.py
```

Expect the first import to select the copied ZIP without unlocking it, an
identical reimport to reuse that copy, and a collision to preserve the existing
bytes. This file also checks cancellation and retry, including a failed refresh
that preserves the previous selection. The fixtures exercise the desktop import
and unlock UI without a live service.

## Find the owner of a change

| I want to change… | Start here |
| --- | --- |
| Desktop or mobile credential import, unlock, lock, forget or retained ZIPs | [Credential loading and lifetime](credentials.md), including [mobile credential import](credentials.md#mobile-credential-import) |
| Push or Pull review, approval, progress or execution | [Transfer planning, review and execution](transfers.md), including [focused tests](transfers.md#checks-for-a-change) |
| Encrypted copy mapping, offline reads or verified saves | [LocalCrypt ownership and data flow](localcrypt.md) |
| Workspaces Cloud, the remote browser or online readers | [Read-only remote browsing](remote-browsing.md) |
| Selected-item Pull from the mobile Cloud File Browser | [Mobile downloads](#selected-remote-item-downloads-on-mobile) |

For controls and setup, see the [desktop guide](../user/user.md) and
[mobile guide](../user_mobile/user_mobile.md). See the
[commonUtils boundary](../../../development/commonutils-integration.md) for
shared library documentation.

## Registration and lifetime

Desktop `__init__.py:register` exposes Workspaces sources, actions, workflows
and settings through `ui_contributions.py`. The mobile feature switch is declared
in `Python/services/mobile_features.py`. The feature's `mobile_sources.json`
lists the Python sources packaged for Android and iOS.

A credential package is the original ZIP containing remote configuration TXT
entries. A saved credential is a desktop `.conf` or native device-protected
configuration. A retained ZIP is kept for a later password unlock. A grant
authorizes one unlocked credential generation. After lock or replacement,
reopen the browser or reader to obtain a new grant. Closing a browser releases
its lease while separately opened documents keep theirs. Locking preserves
offline copy data. Transfer cancellation preserves writes already completed.

## Mobile ownership

`mobile/service.py` composes credential and remote services. `CloudController`
and `TransferController` expose existing application entry points.
Workflows own state, cancellation and rejection of stale results through
presentation protocols such as `RemoteBrowserPresentation`,
`CredentialPresentation`, `ReviewPresentation` and `TransferPresentation`.
Their adapters turn those effects into controls and navigation.

## Selected remote-item downloads on mobile

`mobile/remote_downloads.py` captures a selected remote path and kind, then uses
`mobile.editor_picker` for an app-owned or unlocked LocalCrypt destination.
The captured connection generation and identities are checked before native I/O
and publication. Downloads use the existing transfer execution, progress and
cancellation owner.

A `mirror_sync` request with `download=true` selects `download_sync.go`.
Folder Pull uses rclone Sync. File Pull copies the named object. Native staging
must be empty and independent. LocalCrypt applies the destination cipher to the
staging folder and writes ciphertext. The Python owner exclusively renames the
completed staged item to the requested name. Collisions preserve the destination,
failure or cancellation cleans the operation's staging folder, and no persistent
mirror mapping is added. The source stays in place.

`test_remote_downloads.py` covers selection, picker roots, confirmation, collision,
credential changes, cancellation and cleanup. Native `TestDownload*` fixtures
cover the wire request, single-item scope, crypt sources, encrypted destinations
and rejection of changed identities or nonempty staging.

## Adjacent integrations

The [Dropbox feature](../../dropbox/development/development.md) discovers local
desktop Dropbox-client folders and reviews conflict copies.
[FUSE](../../fuse/development/development.md) adds a desktop mount action for
saved rclone credential contexts. It uses platform drivers and detached mounts
with their own credential binding.
