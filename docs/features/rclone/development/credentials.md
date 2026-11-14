# Credential loading and lifetime

`service.py:CredentialService` owns admission. `desktop_credentials.py:DesktopCredentials` and `mobile/credentials.py` own publication.

## Desktop credential import and unlock presentation

`credentials.import_credential_package` copies a validated ZIP (1 MiB cap) without extraction, reuses identical bytes and rejects same-name replacements atomically. Discovery/import prefer the configured Dropbox credential root when present, otherwise the local root. `ui/page.py:RclonePage` uses cancellable refresh and preserves rows and selection on failure. `ui/credential_unlock.py` offers session or persistent unlock; existing saved config survives session-only unlock. [Import UI check](development.md#try-a-change-to-credential-import)

## Prepare and publish credentials

`prepare_load` validates in memory and returns a service-owned one-use admission. `unlock` publishes it; `load` combines both. Pass passwords separately; keep them out of requests, results and logs. Desktop requires protected credential TXT members and captures ZIP revision/digest plus validated crypt settings. Persistent writes atomically publish per-package `.conf`; session-only uses virtual `.session` paths without plaintext extraction. Desktop publishes sessions on the GUI thread. Revocation, competing publication and cancellation invalidate pending work before commit. Committed credentials survive post-commit cancellation.

Native `mobile/credential_loading.py` adapts ZIP, vault and SMB admission. Active network/local-reader scopes return `credentials_busy`; retry when idle. Import performs no online I/O. Go `credential_sets.go` copies alias maps while live token updates keep origin-generation checks. Retention stores the original protected ZIP via `NativeCredentialRetention`, validates package identity and captured generation, and reports storage failure independently of successful load. Diagnostics exclude exception text, payload and credential values. [Backend lifetime](remote-browsing.md#native-connection-and-archive-errors)

## Forget and lock

Lock retires access and keeps saved credentials and ZIPs. Native lock covers all loaded packages. Forget serializes with publication. Desktop selected-package Forget removes both saved and live credentials; Clear All removes directly contained saved configs, including legacy `rclone.conf`, while preserving session-only packages. Preserve source ZIPs and offline copies. Native Forget erases live credentials, vault, retained ZIPs and encrypted lists across scenes. Continue independent cleanup after failures, enumerate owned blobs even with a damaged index, keep the index for retry if cleanup fails, and report partial erasure. Navigation waits for worker retirement.

```sh
python3 dev.py test desktop --exact-file Python/tests/resources/test_credential_service.py
```

## Remembered desktop session destinations

`desktop_catalog` stores schema, ZIP path and remote names in `<account>.session.json`. Lock retains it; Forget removes it. Saved configs suppress duplicate inactive placeholders. Legacy visibility still applies. `WorkspaceUnlockView` resumes the selected route. Check `test_credential_catalog_desktop.py` and `test_folder_sources_ui.py`.

## Mobile credential import

`mobile/credential_panels.py` builds the buttons; `cloud_ui.py` presents connection, picker and password routes. `credentials_ui.py:CredentialWorkflow` opens the system picker first. Protected ZIPs take the password route; plain ZIPs go directly to Session-Only/Persistent. Retries reuse the admitted ZIP and choice. Route retirement advances the import epoch and clears pending ZIP, choice and password. Guard callbacks by epoch, client, route and generation through native submission. A stale view skips presentation, metadata and retention after commit. Compatibility callers can import without widgets. A mismatched unlocked package cannot resume a transfer.

```sh
python3 dev.py test mobile test_cloud_import_ui.py
python3 dev.py test mobile test_background_credential_refresh.py
python3 dev.py test mobile test_workflow_ownership.py
```

Expect protected/plain import, retry, stale-result rejection and compatibility forwarding. Use synthetic ZIPs in the disposable native runner to verify actual picker cancellation, password clearing, restore and Forget.
