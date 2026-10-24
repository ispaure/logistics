# Read-only remote browsing

Mobile `CloudUI.show_cloud` retains prepared-client admission, cached credential
publication, restore startup, busy-state projection and generation refresh checks.
`_build_cloud_controls` constructs the existing connection/browser/download controls;
`_build_cloud_views` assembles their connection/import/advanced routes and browser
directly in their final layout. Browser status and parent navigation belong to the
browser header; advanced actions never temporarily adopt those controls. Both
builders populate the retained CloudController fields;
they introduce no account, request or cancellation owner. Credential workflows and
the remote listing service remain independent from this construction boundary.

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
placeholders. Credential-package discovery uses saved configs and live sessions;
remembered names alone do not declare online sources.
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
The mobile browser is titled **Cloud File Browser** and starts with its compact
location header and the listing. Open documents and Recent use cloud/device and
connection lock badges. The mobile host's `document_sources` keeps saved-credential
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

After credential unlock, validated open/recent entries restore in RAM; restored
open entries are transient placeholders until selected. Restore never fetches
remote file content. Explicit close updates the encrypted open list; credential
lock preserves it. Documents has a blue **Clear** action beside **Recent**; it
clears ordinary history and the recent lists of currently unlocked credential
caches while preserving open references and saved files. Forgetting retained credentials deletes list caches across
windows, and cache writes serialize with deletion. Malformed/authentication-failed
archives are preserved; there is no plaintext cache fallback. Native tests cover
AES strength, credential-password compatibility, authentication, tampering,
replacement, isolation and bounded input; host tests cover restoration, migration,
list limits, explicit close and forget actions. Live readers remain transient.
`set_cloud_busy` attaches Cancel to the location header and a slim progress bar
below it only during requests, removing both on completion. It uses the header’s
current parent because adaptive presentation may wrap the browser contents.
Successful remote listings mark the location header unlocked. Encrypted locations
reuse Workspaces's combined folder/lock glyph and color beside the cloud icon;
local encrypted listings use the same unlocked glyph beside the device icon.
Remote provider opening holds the application's cloud-busy state, and Cancel
signals both pending private controllers and the native request. Workspaces
shows a status and spinner in its existing list before awaiting a folder,
rejecting duplicate taps while opening. Its menu uses the displayed snapshot
without rediscovery; credential grouping reuses the same discovery result instead
of scanning the folders again. Existing mapping actions retain a guarded online destination
before credentials load, preserving the job's identity and decoded folder scope.

Desktop snapshots an explicit account's configuration into an isolated in-memory
child session, with process-private aliases and a null rclone config. Parent
session revocation invalidates the child. Saved configs are checked for revision
changes before/after I/O; credential-manager replacement/removal immediately
revokes their browser snapshots. Readers retain provider leases beyond the tab lifetime;
private-view guards retire their windows when the credential session is revoked.
Commands use bounded output, connection/read timeouts and per-worker cancellation.
Range reads compare metadata before/after fetching; this detects observed changes,
not an atomic remote snapshot. CLI process startup and stat calls add latency.

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

The browser exposes no standalone download/copy actions for files or folders on
any platform. Retired Python copy/folder-download helpers and native `read`,
`crypt_read` and `crypt_fetch` endpoints are removed. Managed Pull/Push remains
the only remote-to-local transfer workflow. Existing offline-copy catalogs retain
read/edit/export compatibility; their tests seed pre-existing records directly.

Validation uses synthetic local/alias/crypt CLI backends, memory-backed native Go
remotes, and Toga dummy/Qt offscreen UI tests. No user accounts are accessed.
`test_remote_browser.py` covers account isolation, range/CBZ reads, nested encrypted navigation, preview-only actions, revocation, tab cloning and current-folder filtering.
Mobile `test_remote_readers.py` covers reader presentation, mutation guards,
manual-copy dialogs, cache revocation and absence of standalone downloads. Native
`remote_document_test.go` checks ordinary/crypt ranges, archive members, identity,
revisions, bounds and cancellation. Live-service performance and physical-device
behavior remain outside this local validation.

`test_remote_bridge_native.py` can also run against a rebuilt host C bridge using
`LOGISTICS_REMOTE_BRIDGE=/absolute/path/to/library`. It round-trips synthetic
ordinary/crypt remote text and comics through the real Python/native boundary,
without creating an offline copy.


## Native validation, 2026-10-15

The final browse-only payload passed 16 targeted checks on each of Android 15
arm64 (emulator), iPhone iOS 26.5 and iPad iOS 27.0 (simulators). The probe uses a
separate app identifier and synthetic ordinary/crypt memory remotes. It checks
navigation/current-folder filtering, direct text/image/EPUB/comic rendering,
manual-copy dialogs, absence of standalone downloads, no persisted document
plaintext, unchanged remote contents and credential-lock retirement. Credentials
are session-only. This is not physical-device or live-cloud-service validation.

Native macOS Qt passed seven remote-browser tests. The mobile host suite passed
243 tests; affected catalog/UI tests passed again after the final deletion of
unused record writers. Go tests and race tests passed, as did rebuilt host-bridge
remote-reader and existing LocalCrypt text/metadata/large-archive compatibility
checks. Ruff and whitespace checks passed.

The validation manifest (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-validation.json`)
records source fingerprints and scope. Per-target reports:
Android (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-android.json`),
iPhone (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-iphone.json`),
iPad (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-ipad.json`).
Screenshots: desktop (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-desktop-browser.png`),
Android (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-android-browser.png`),
iPhone (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-iphone-browser.png`),
iPad (local artifact `test-results/mobile-evidence/2026-10-15-remote-preview-only-ipad-browser.png`).


### Final code and UI review

A follow-up audit found disabled Save controls and a Save As/Metadata overflow
label inherited by mobile remote readers. Remote views now omit these controls
entirely, including the discard-edits action and editable-file help text. Local
and LocalCrypt readers retain their editing controls. Regression checks inspect
both the main reader and overflow tools for text, images and comics; the native
probe repeats the check for EPUB too on all three mobile targets.

The audit found no standalone remote file/folder download or copy entry points.
The remaining offline catalogs only read existing records; their creation/fetch
helpers and the retired native endpoints are absent. Managed Pull/Push, local
file operations and existing offline-file export remain intentional. Current
reports and the validation manifest above reflect the reviewed source snapshot.


A second audit also found disabled desktop EPUB/comic metadata actions. These
are now hidden for remote providers, including the EPUB metadata button, and
restored when the reader returns to a local file. Seven native macOS reader UX
tests passed, including a regression covering both transitions. No mobile code
changed during this second audit; the native mobile evidence above still applies.
Credential retirement clears the mobile browser's listing, thumbnails, selection
and navigation history through its existing stop contract.


### Expanded end-to-end pass

The final source passed 31 native scenarios each on Android, iPhone and iPad,
eight desktop remote-browser tests, seven desktop reader UX tests, all 252 mobile
host tests, the host Python/native remote-reader integration and Go race tests.
The native bridge source fingerprint still matches the rebuilt libraries.

Added scenarios invoke reader tools and Appearance and return through Back,
exercise Markdown preview/text switching, corrupt PNG/CBZ/EPUB, missing files,
oversized text, failed navigation, and credential lock/replacement. Error-dialog
requests and messages are asserted by intercepting presentation; reader widgets,
real document decoding, menus and navigation run through native backends.
These local fixtures do not model live-provider outages or physical touch gestures.

This pass fixed selection-placeholder restoration after failed mobile navigation,
prevented stale-listing restoration after credentials change, added the manual-copy
explanation to desktop direct-read failures, restricted remote reader menus to
commands available for each format, and replaced Markdown's misleading Edit label
with Text for read-only remote documents. Existing managed transfers/offline-copy
compatibility remains preserved. The reports above now contain the 31-scenario
runs and final staged-source fingerprint.

Android's implemented appearance controls and E Ink limitations are described in
the [mobile user guide](../../../user_mobile/settings/settings.md#appearance-and-e-ink-status).

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
