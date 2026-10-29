# Developing the rclone feature

Start here to find the owner of a change. The feature provides credential-package
loading, read-only online browsing, Local/LocalCrypt copies and explicit Push/Pull.
Desktop uses the rclone CLI; mobile uses an embedded Go bridge. Shared services own
credential admissions, access grants and transfer approval.

- [Credential loading and lifetime](credentials.md)
- [Transfer planning, review and execution](transfers.md)
- [LocalCrypt resources and verified saves](localcrypt.md)
- [Read-only remote browsing](remote-browsing.md)
- [Platform parity and migration reference](rclone-parity.md)
- [Historical implementation records](history/history.md)

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
for comparison retirement. Both paths retain mandatory transfer preflight.

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
