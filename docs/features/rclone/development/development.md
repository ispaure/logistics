# Developing the rclone feature

rclone supplies the remote storage used by Cloud browsing, transfers and
LocalCrypt copies. Desktop calls the rclone CLI. Android and iOS use the
embedded Go bridge. Credential loading is the entry point for remote access
and sets the lifetime of grants used by browsers, transfer jobs and readers.

## Follow credential import and unlock

**Settings → rclone → Credential packages → Import credential ZIP…** calls
`credentials.import_credential_package` through `ui/page.py:RclonePage`.
Import validates and copies the encrypted ZIP and selects the imported
package. Unlock is a separate action that loads credentials for use. The
desktop tests exercise import without unlocking, identical reimport, and
preservation of existing bytes when a different package has the same name.

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

Desktop `ui_contributions.py` registers sources, actions and settings.
Update `mobile_sources.json` when adding imports needed in the mobile build.

## Mobile ownership

`mobile/service.py` composes services. Controllers adapt workflows to controls; workflows own cancellation and stale-result rejection. Reopen after credential lock/replacement to obtain a fresh grant.

Related desktop owners are [Dropbox](../../dropbox/development/development.md) and [FUSE](../../fuse/development/development.md).
