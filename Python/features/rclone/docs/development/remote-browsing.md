# Read-only remote browsing

Desktop hosts `RemoteBrowserView` in the existing File Browser workspace. Its
`RemoteLocation` carries config identity, remote name and relative directory;
cloning a tab retains all three. Folder Hub's Browse action and the browser's
Open Remote command share this route. Local and LocalCrypt routing is preserved.

The rclone feature owns remote credentials, CLI/native adapters, direct-open
policy and previews. The commonUtils provider browser and range-reader contracts
are reused without modification. No remote path is passed to the ordinary local
filesystem browser, index, local mutation actions or external document launchers.

Mobile remote listings deliberately have no thumbnail callback, including tile
mode: enumerating a folder must not enqueue archive-cover reads on the serial
native connection. `CloudUI.remote_activity` runs a UI-loop timer and marshals
worker step notifications back to that loop. Its timer and indeterminate bar are
retired on success, error and cancellation; late worker callbacks are ignored.
Remote provider opening holds the application's cloud-busy state, and Cancel
signals both pending private controllers and the native request. Folder Hub
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

Folder Hub checks online busy state before native credential lookups. A pending
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

Remote readers are read-only, including text and metadata. Unsupported formats and
reader limits produce a manual-copy dialog; there is no automatic download/open
fallback. Desktop and mobile filter the listed folder without invoking recursive
resource search. Ordinary and crypt remote previews stay in memory.

Mobile row menus retain the selected item and credential generation, and open an
item-specific page rather than remote configuration. Inner ZIP password errors
route to that item's password form; retry clears the field before opening.
Credential retirement clears the item page and password. The browser reports
opening progress, setup exceptions and unsuccessful session presentation instead
of leaving only a selection message. Folder Hub retains name-based groups but
does not promote the current remote listing's subfolders into its entry tree.
Explicit Folder Hub locations preserve their folder when switching remotes.

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

The [validation manifest](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-validation.json)
records source fingerprints and scope. Per-target reports:
[Android](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-android.json),
[iPhone](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-iphone.json),
[iPad](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-ipad.json).
Screenshots: [desktop](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-desktop-browser.png),
[Android](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-android-browser.png),
[iPhone](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-iphone-browser.png),
[iPad](../../../../../docs/development/mobile-evidence/2026-10-15-remote-preview-only-ipad-browser.png).


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
the [mobile user guide](../../../../../docs/user_mobile/settings/settings.md#android-appearance-and-e-ink-status).

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
