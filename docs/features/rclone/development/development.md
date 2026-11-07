# Developing the rclone feature

Start here to find the owner of a change. The feature provides credential-package
loading, read-only online browsing, Local/LocalCrypt copies and explicit Push/Pull.
Desktop uses the rclone CLI; mobile uses an embedded Go bridge. Shared services own
credential admissions, access grants and transfer approval.

- [Credential loading and lifetime](credentials.md)
- [Transfer planning, review and execution](transfers.md)
- [LocalCrypt resources and verified saves](localcrypt.md)
- [Read-only remote browsing](remote-browsing.md)

For controls and setup, see the [user guide](../user/user.md). Shared APIs belong
in commonUtils' own documentation; see the repository's
[integration boundary](../../../development/commonutils-integration.md).

## Owner map

| Change | Start under `Python/features/rclone/` |
| --- | --- |
| Shared credential prepare/publish/revoke | `service.py`, `credential_loading.py` |
| Desktop credential adapter and composition | `desktop_credentials.py`, `desktop_service.py` |
| Remembered desktop ZIP paths and remote names | `desktop_catalog.py` |
| Native credential adapter and composition | `mobile/credentials.py`, `mobile/service.py` |
| Native credential load sequencing and host port | `mobile/credential_workflow.py` |
| Native credential controls, prompts and navigation | `mobile/credentials_ui.py` |
| Retained ZIPs, encrypted vault and package metadata | `mobile/credential_packages.py`, `mobile/credential_vault.py`, `mobile/credential_retention.py` |
| Remote sessions and cancellation/access policy | `remote_access.py`, `access.py`, `remote_resources.py`, `mobile/remote_resources.py` |
| Native browser listing workflow and UI adapter | `mobile/browser_workflow.py`, `mobile/cloud_ui.py` |
| Shared transfer approval and execution handoff | `transfers/service.py`, `transfers/review.py` |
| Desktop transfer planning and launch | `transfers/desktop.py`, `transfers/workflow.py`, `transfers/sync.py`, `transfers/launch.py` |
| Native copy records, proposal planning and execution | `transfers/mobile/records.py`, `planning.py`, `jobs.py`, `transport.py` |
| Desktop ciphertext provider/cache/command transport | `localcrypt/backend.py`, `localcrypt/read_cache.py`, `localcrypt/transport.py` |
| Native ciphertext resources and verified publication | `localcrypt/mobile/resources.py`, `localcrypt/mobile/content.py` |

The Go bridge source lives in `mobile_build/rclone_bridge/`. It is application
source, not a generated build output. Update `mobile_sources.json` when adding or
moving a portable/native Python module.

## Terms and lifetimes

| Term | Meaning |
| --- | --- |
| Credential package | The original ZIP containing remote configuration TXT entries |
| Saved credentials | Desktop `.conf` or native device-protected credential material |
| Session-only credentials | Loaded for the process without saving decoded configuration |
| Retained ZIP | The original protected package kept for a later password unlock |
| Grant / generation | Access to one unlocked generation; another unlock cannot revive an old grant |
| Resource session | Browser/reader access with independent leases, cancellation and closure |
| Connection identity | Configuration/account binding used to associate a copy with its remote |
| Cipher identity | Crypt-settings binding used to interpret encoded paths |
| Copy mapping | Local destination plus remote scope and identities, captured before approval |
| Review | Read-only comparison; approval remains separate from execution preflight |

Credential lifetime, resource-session lifetime and copy persistence are separate.
Locking revokes old readers but preserves ciphertext and ordinary local files.
Closing a browser releases its lease; independently open documents retain theirs.
Transfer cancellation does not roll back changes already written.

## Follow credential loading

The desktop/mobile UI captures a load request and consumes its password.
`CredentialService.prepare_load` stages validation without publishing; `unlock`
consumes one service-owned admission. Publication rejects cancelled/stale work and
retires pending loads. The native workflow checks the host/client/navigation and
published generation again after metadata preparation before updating the UI.

The platform adapter owns storage and publication. Retaining an original ZIP is a
separate operation from saving decoded credentials. See
[credential contracts](credentials.md) for cancellation, forgetting and retained data.

## Review session and execution handoff

Interactive commands capture a platform request, call `TransferService.review`,
present the shared `ReviewSession`, and consume approval once through `execute`.
Full approval rechecks the completed comparison; explicit incomplete approval waits
for comparison retirement. Desktop incomplete approval also skips full LocalCrypt
integrity scanning and generated-file cleanup, retaining structural/access checks.
Normal approval and mobile incomplete approval retain full transfer preflight.

`TransferPlan.valid` includes the reviewed record binding; `active` tracks access
through execution so the transfer's own record writes remain valid. The
[transfer guide](transfers.md) traces each stage and its tests.

## Follow an encrypted read or save

Open a resource through `RcloneService.localcrypt` or `.remotes`, then pass that
provider to generic browser/document hosts. Providers own virtual/physical path
validation and credential checks; documents retain their own access leases.

A LocalCrypt save stages ciphertext, verifies it, revalidates the original file
and grant, publishes, then removes staging. Neither a cache nor a transport may
authorize publication. See [LocalCrypt](localcrypt.md) and
[remote browsing](remote-browsing.md) for platform details.

## Mobile ownership

`CloudController` and `TransferController` retain application compatibility
accessors. Workflow code should consume small presentation protocols rather than
add more host forwarding. Existing examples are `RemoteBrowserPresentation`,
`CredentialPresentation`, `ReviewPresentation` and `TransferPresentation`.
Adapters translate those effects into controls and navigation; workflow owners keep
state, cancellation and stale-result rejection.

Mobile Pull and downloads keep open provider documents and their unsaved drafts alive through
both review and execution readiness. Destination files can be replaced by the
reviewed transfer; saving an older draft still checks its original revision and
retains the draft on conflict. Push retains its existing save-or-close preflight.
`test_mirror_ui.py` covers pulling over the same file held by an open editor and
refusing a subsequent stale save without overwriting the pulled bytes.

## Validation

```sh
python3 dev.py test-owner rclone --mode fast
python3 dev.py lint
python3 dev.py test desktop test_portable_imports.py --mode fast
```

Use the focused commands in the [transfer guide](transfers.md#checks-for-a-change)
for a smaller change. Credential freshness tests reject results superseded during
metadata refresh; credential-service tests cover one-use admissions and revocation.
Real CLI tests require the pinned executable. Go bridge tests, native-library
integration tests and physical-device checks are separate validation scopes.
Historical passing results do not validate a new change.

## Selected remote-item downloads on mobile

`mobile/remote_downloads.py` captures a selected remote path and kind, then uses
`mobile.editor_picker` for an ordinary app-owned or unlocked LocalCrypt destination.
The captured connection generation and identities are checked before native I/O
and publication. It uses the existing transfer execution/progress/cancellation owner.
`mirror_sync` requests with `download=true` select `download_sync.go`: folder Pull
uses rclone Sync, while file Pull copies only that named object. Native staging
must be empty and independent. LocalCrypt wraps that staging folder with the
selected destination cipher, so no decrypted staging files are written.

The Python owner exclusively renames the completed staged item into its requested
name; it rejects collisions and never removes the source. Failure/cancellation
cleans only the operation's staging folder. No persistent mirror mapping is added.
`test_remote_downloads.py` covers selection, picker roots, confirmation, collision,
credential change, cancellation and owned cleanup. Native `TestDownload*` fixtures
cover the wire request, single-item scope, crypt sources/encrypted destinations and
rejection of changed identities or nonempty staging. Portable checks do not replace
physical-device interaction with an actual network share.

## Adjacent integrations

The [Dropbox feature](../../dropbox/development/development.md) discovers desktop
Dropbox-client folders and reviews local conflicting copies. Rclone remotes use
their own credential and transfer workflow; loading one does not configure that
Dropbox-client integration.

[FUSE](../../fuse/development/development.md) contributes an optional desktop
mount action for saved credential contexts. Its detached mount lifetime and
platform drivers are separate from integrated transfer jobs and resource leases.
Mobile uses the embedded bridge and offers no FUSE mounts.

The November 4 documentation audit reviewed source and existing tests only.
No CLI, bridge, Qt or native-device validation was rerun during the release hold;
current acceptance remains limited to the separately recorded test scopes.
