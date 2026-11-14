# Read-only remote browsing

Select a configured account and remote in **Workspaces → Cloud** on desktop or
mobile. On desktop, **File Browser → File → Open Remote…** reaches the same
provider browser. Change listing, preview or reader behavior here. Use
[Transfers](transfers.md) for explicit Push/Pull and [LocalCrypt](localcrypt.md)
for encrypted offline copies.

## Desktop browser and unlock

Desktop hosts `RemoteBrowserView` in the existing File Browser workspace. Its
`RemoteLocation` carries config identity, remote name and relative directory;
cloning a tab retains all three. Workspaces selection and the browser's
Open Remote command share this route. Local and LocalCrypt routing is preserved.

In desktop Workspaces, selecting a locked session-backed remote or LocalCrypt
copy shows `ui/workspace_unlock.py:WorkspaceUnlockView` inside Files. The
form reads the credential ZIP on an OperationProgress worker and publishes the
session only after successful completion while still active. Invalid passwords
remain inline; cancelling, changing folder/source or closing the page discards
late results. Unlock resumes the selected location and updates all affected lock icons.
Standalone File Browser windows retain their existing unlock dialog.

Desktop Workspaces uses `services.folders.workspaces.workspace_remote_sources`
to expose declared loaded credential sources. `CopyContext` associations and
unassociated local folders remain available locally but do not create Cloud
placeholders. Credential-package discovery uses saved configs, live sessions and the persisted
nonsecret session catalog. Catalog entries restore locked Cloud destinations
with the matching credential ZIP path after a restart.
A successful unlock refreshes lock icons and actions even if opening the browser
then fails. Action detection captures the credential generation and discards or
restarts results if credentials lock or are replaced while its worker runs.
Actions detection waits for required credentials; ordinary decrypted files can be
browsed while their remote actions use a separate inline unlock view. Closing or
replacing that view cancels its worker and discards late password results.

The rclone feature owns remote credentials, CLI/native adapters, direct-open
policy and previews. The commonUtils provider browser and range-reader contracts
are reused without modification. No remote path is passed to the ordinary local
filesystem browser, index, local mutation actions or external document launchers.

Desktop remote commands retain at most 64 KiB of rclone stderr in memory on a
failed request. The adapter translates recognized authorization, missing backing
remote, invalid crypt password setting, folder access, rate limit and network errors to fixed recovery messages;
unknown failures report the exit status. Raw provider text, tokens and paths are
never included in the presented exception. Credential revocation takes precedence
over command failure when a session is locked during a request.

Desktop snapshots an explicit account's configuration into an isolated in-memory
child session, with process-private aliases and a null rclone config. Parent
session revocation invalidates the child. Saved configs are checked for revision
changes before/after I/O; credential-manager replacement/removal immediately
revokes their browser snapshots. Readers retain provider leases beyond the tab lifetime;
private-view guards retire their windows when the credential session is revoked.
Commands use bounded output, connection/read timeouts and per-worker cancellation.
Range reads compare metadata before/after fetching; this detects observed changes,
not an atomic remote snapshot. CLI process startup and stat calls add latency.

## Mobile listings and connection admission

Mobile Workspaces keeps each loaded account's Cloud destination independently of
its local sync mappings. A matching mapping replaces only its own account's
browse target with the mapped folder scope. If the saved connection identity no
longer matches, the loaded Cloud destination stays available and unlocked;
Pull/Push retain their existing identity checks and do not retarget the local
copy. `test_folder_discovery.py` covers stale mappings, credential filtering and
multiple packages declaring the same remote name.

Mobile Workspaces projects loaded remotes and retained ZIP metadata into Cloud
rows. Retained package names and connection identities allow password unlock
before a session is loaded; local folder names and transfer mappings alone do
not create Cloud destinations. Files and Home unlocks always load for the session
without a retention chooser. The chooser remains in Settings credential-package
unlock/import flows. Desktop workspace unlock already loads a session directly.

Mobile listing requests use `mobile.browser_workflow.RemoteBrowserWorkflow` and
`RemoteBrowserState`. The workflow receives captured connection/location inputs
and a presentation port for list publication, status, busy controls and route
recording; it never reads application attributes or widgets. `CloudBrowserPresentation`
adapts that port to existing controls. Controller/app compatibility fields forward
to the browser state. Failed requests restore the prior listing only while the
same live host, client and credential generation remain valid; stale results clear
the listing. Focused workflow and remote-reader tests cover both paths.

Mobile remote listings deliberately have no thumbnail callback, including tile
mode: enumerating a folder must not enqueue archive-cover reads on the serial
native connection. `CloudUI.remote_activity` delegates to `mobile.activity.RemoteActivity`,
which owns one UI-loop timer per controller and marshals worker step notifications
back to that loop. The newest active request owns status; nested or overlapping
requests can retire in either order. Its presentation port projects messages into
the browser/folder status controls. The timer and indeterminate bar are retired on
success, error and cancellation; late or already-queued worker callbacks are
ignored after their request retires.

`mobile/cloud_ui.py:CloudUI.show_cloud` admits the prepared client and manages
startup and busy presentation. `_build_cloud_controls` builds the controls and
`_build_cloud_views` assembles the browser and connection routes. The listing
workflow owns request validity and cancellation.

Workspaces derives online crypt-folder icons from published `crypt_identities`
as well as the loaded crypt-name list and retained package metadata; a local copy
is not required. Credential loading backfills missing retained `crypt_remotes`
metadata for the exact matching document-cache identity. Alias translation keeps
the retained index's remote names, so another loaded account with the same names
cannot change a regular folder's classification. Locked rendering reads this
metadata without decrypting the credential ZIP or calling the native bridge.

Mobile connection admission resolves remote aliases and checks the published
`identities` of every loaded package before probing the bridge. This keeps saved
and session-only Workspaces usable together when a redundant identity probe
would fail. Online document history reopens the named remote using its current
loaded credentials, including when the saved history fingerprint is stale after
a ZIP reimport. Name-only alias resolution assumes that shared names across
packages denote the same remote. Locked remotes still use the retained-ZIP
unlock/import flow; encrypted local copies retain their identity checks. Host tests
in `test_multi_credentials.py` cover mixed modes, a shared Dropbox name, opening
a uniquely named Workspaces remote, alias resolution and identity mismatch.

Workspaces checks online busy state before native credential lookups. A pending
online folder does not suppress a different local tap; completion respects the
newer navigation. LocalCrypt can share transfers and credential-stable remote
reads. Credential writes retain their guard. Busy action pages expose Cancel.
`folder_choices` performs no native discovery. Credential loading and explicit
Refresh populate `hub_crypt_locations` through a worker; discovery failure keeps
the existing UI usable. Refresh and credential/path checks compare navigation and
credential generations before publishing or navigating. Hub entry, credential
filter changes and action-page rendering reuse this snapshot. Mapped remote
identity checks and crypt path decoding run in workers with a visible status,
including the transfer-review entry path. They must never wait on native locks
on the UI thread. The native remote probe checks comic → Hub → other remote's
actions and rejects native requests made from the UI thread during that return.

## Mobile reader opening and cache

For mobile document opens, `mobile/remote_readers.py:RemoteReaders` owns format
handoff over an independently reopened grant. `mobile/remote_source.py:RemoteSource`
owns the generation-bound transport, seekable ranges and native RAM archive token;
`remote_readers.RemoteSource` remains available as an import for existing callers.
Decoded header/member lifetime is shared through
`services/documents/archive_access.py:NativeArchiveAccess`. Follow the
[source-to-reader trace](../../../development/architecture/document-storage.md#trace-a-mobile-provider-reader)
for publication, retry and terminal-close ownership.

Mobile remote reads use the existing serialized native network-operation scope.
Every stat/range/archive request binds a connection fingerprint; content requests
also bind a metadata revision. A credential-generation check rejects cached content
after replacement. Archive members and range blocks stay in bounded RAM buffers.
Mobile EPUB and CBZ/ZIP sources use `remote_cache_open` to read one continuous logical
remote stream into native RAM, validating the metadata revision before and after
the fetch. Opaque per-reader tokens bind the connection, path and revision.
`remote_cache_archive` uses that immutable snapshot and the existing native
plain/ZipCrypto/AES archive parser; page reads do not stat or contact the remote.
The native pool reserves bytes before allocation (128 MiB per file, 256 MiB per
process across scenes), releases failed/cancelled/closed reads, and clears on
credential retirement. This pool is separate from the 32 MiB Python draft budget.
Progress and release requests bypass the network lock; cached member reads use
the independent credential read scope. A short-lived Python polling worker
reports byte progress to the existing UI-loop status callback and always retires.
These calls do not create temporary plaintext files or change the transfer engine.
Network reads can wait for an active serialized network operation; LocalCrypt's
independent offline read scope remains separate.

Remote readers are read-only, including text and metadata. The internal Markdown
editor entry point also rejects read-only readers. Plaintext history eligibility
requires the current connection fingerprint to match a saved credential record;
a reused remote name alone cannot authorize it. Mobile location headers reuse
their native storage indicators while storage and lock state remain unchanged.
Document connection badges use published credential fingerprints without native
I/O on the UI thread, including while a network operation holds the bridge lock.
Unsupported formats and
reader limits produce a manual-copy dialog; there is no automatic download/open
fallback. Desktop and mobile filter the listed folder without invoking recursive
resource search. Ordinary and crypt remote previews stay in memory.

Mobile browser rows open files and folders directly, without per-row action
buttons. Inner ZIP password errors route to an item-specific password form that
retains the item and credential generation; retry clears the field before opening.
Credential retirement clears the item page and password. The browser reports
opening progress, setup exceptions and unsuccessful session presentation instead
of leaving only a selection message. Workspaces retains name-based groups but
does not promote the current remote listing's subfolders into its entry tree.
Explicit Workspaces locations preserve their folder when switching remotes.

Desktop browser actions preview remote items. Mobile also offers explicit
[selected-item Pull](development.md#selected-remote-item-downloads-on-mobile).
Existing offline-copy records retain read, edit and export compatibility.

## Mobile document history

Open documents and Recent use cloud/device and connection lock badges. The mobile
host's `document_sources` keeps saved-credential
references in ordinary app-private history. Session-only credential paths and
filenames use `mobile.document_lists.CredentialDocumentLists` instead. The host
injects its reference validator, history limit and reopen callback; the feature
does not import the mobile application package. Native
`document_lists_seal/open` writes/reads an AES-256 ZIP containing one generic
`entries.json` member, under hashes of the credential package and window. The
credential ZIP's original password is held only in native session memory and is
cleared with credential lock/replacement. Only authenticated, password-protected
credential ZIPs enable this cache. No cache contains file contents or unsaved edits.

Native startup initializes the cloud controller and awaits its saved-vault restore
in the workspace preparation phase, before building Home. Remote and LocalCrypt
document reopening also await an existing restore before resolving identities or
checking credential generations. Navigation away during that wait cancels the
open intent. Credential publication queues Home and Documents badge refreshes
even for saved packages, which have no session-only encrypted-list state.

After credential unlock, validated open/recent entries restore in RAM; restored
open entries are transient placeholders until selected. Restore never fetches
remote file content. Explicit close updates the encrypted open list; credential
lock preserves it. The **Clear** action beside
**Recent** clears ordinary history and the recent lists of currently unlocked
credential caches while preserving open references and saved files. Forgetting
retained credentials deletes list caches across windows and serializes with
cache writes. Malformed/authentication-failed
archives are preserved; there is no plaintext cache fallback. Native tests cover
AES strength, credential-password compatibility, authentication, tampering,
replacement, isolation and bounded input; host tests cover restoration, migration,
list limits, explicit close and forget actions. Live readers remain transient.

## Native connection and archive errors

`mobile_build/rclone_bridge/main.go` owns cached backend contexts in `clients`.
Each operation temporarily connects its cancellation to those retained contexts.
Normal completion detaches all cancellation hooks before ending the request, so
cached OAuth work is not left attached to an already-completed request. Explicit
cancellation retires the connected lifetimes; a later access rebuilds them.
Rooted online mirror/download connections use the same `remoteRootFs` owner.
Crypt backing lookups validate the cached filesystem identity and full remote-path
join, including colon-containing roots; a foreign cached lifetime is cleared and
retried rather than adopted. `backend_lifetime_test.go` and
`operation_scope_test.go` cover these boundaries with synthetic host backends.

`crypt_stream.go:archiveContents()` keeps member-read cancellation and deadline
errors distinct from an inner ZIP password error. For an unencrypted member,
payload I/O/size failures have a generic wire message while preserving their
underlying cause internally. Encrypted AES/ZipCrypto members retain the existing
password fallback for other failures. `file_archive_test.go` covers these bounded
member paths; manifest, metadata and thumbnail paths are outside this correction.
These host checks do not establish OS/device acceptance.

## Remote reader validation

From the repository root, run the desktop or mobile host checks for the code
you changed:

```sh
python3 dev.py test desktop --exact-file Python/tests/resources/test_remote_browser.py
python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_remote_readers.py
```

The desktop fixture uses synthetic local, alias and crypt CLI backends for
account isolation, read-only opens, tab cloning, filtering and revocation.
Its CLI cases require the pinned rclone executable. The mobile fixture uses
stub clients to check read-only presentation, bounded caches, listing recovery
and generation revocation. Native `remote_document_test.go` exercises ranges,
archive members, identity, revision checks and cancellation with synthetic
remotes. `test_remote_bridge_native.py` can use a rebuilt host library through
`LOGISTICS_REMOTE_BRIDGE=/absolute/path/to/library`. Live-service performance and
touch interaction require separate checks.

## Offline folder snapshots

Ordinary mobile collection listings validate the selected drive at snapshot
boundaries, scan entries once, and retain per-child link, hard-link, regular-file
and protected-root checks. LocalCrypt decodes names through `crypt_paths` in
batches of at most 256; each batch validates the cipher identity and runs in the
local-read credential scope. Names remain in memory. Listings still validate
parents, cancellation and the final collection location before publication.

The host uses cancellable local reads without rebuilding cloud controls or
rescanning downloads on folder taps. A superseded host, folder request or private
credential generation cannot publish late rows. Native pages contain at most 40
entries, are assembled offscreen, and load thumbnails asynchronously.

## Home credential unlock

Home checks retained package metadata and file presence without restoring or
decrypting credentials. `home_unlock_candidates` excludes loaded package names
and credentials hidden by the Legacy visibility policy. The generic Home action
opens `show_retained_unlock` with a credential selector in the Home route; the
existing session-only import, private-reader edit guard and password clearing
apply. Successful unlock returns to Home. No remote list or document contents
are added to the Home heading.
