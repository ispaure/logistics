# Developing the rclone feature

## Try a change to credential import

On desktop, follow **Settings → rclone → Credential packages → Import credential ZIP…**. Revise the same-name collision message in `Python/features/rclone/credentials.py:import_credential_package`, called by `ui/page.py:RclonePage`. Run from the checkout root. Expect first import to select without unlocking, identical reimport to reuse the ZIP, and collision to preserve saved bytes.

```sh
python3 dev.py test desktop --exact-file Python/tests/resources/test_credential_import_ui.py
```

## Find the owner

| Change | Guide |
| --- | --- |
| Import, unlock, lock, forget | [Credential loading and lifetime](credentials.md) |
| Compare, approve, execute | [Transfers](transfers.md) |
| Offline encrypted mappings and saves | [LocalCrypt](localcrypt.md) |
| Online listings and readers | [Remote browsing](remote-browsing.md) |

Desktop `ui_contributions.py` registers sources, actions and settings over the CLI. Android/iOS use `mobile_sources.json` and the embedded Go bridge.

## Mobile ownership

`mobile/service.py` composes services. Controllers adapt workflows to controls; workflows own cancellation and stale-result rejection. Reopen after credential lock/replacement to obtain a fresh grant.

## Selected remote-item downloads on mobile

`mobile/remote_downloads.py` captures path, kind and generation. Go `download_sync.go` stages file Copy or folder Sync in independent storage, encrypted for LocalCrypt. Python publishes without clobber and retires staging on cancel/failure. Selected downloads leave mirror records unchanged. Check `test_remote_downloads.py` and native `TestDownload*`.

Related desktop owners are [Dropbox](../../dropbox/development/development.md) and [FUSE](../../fuse/development/development.md).
