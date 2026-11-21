# Mobile file storage and sharing

Use [mobile file storage settings](../../user_mobile/settings/settings.md#file-storage)
for paths users see. This page covers collection locations, iOS storage
migration and native file sharing. For opening and saving documents through
those locations, see [Document storage sessions](document-storage.md).

## Android collection drive selection

`services/documents/locations.py` binds a selected volume to its `Logistics/.logistics-storage` marker. Copies, encrypted copies and ordinary Files move together; credentials and mappings stay private. An absent drive stalls access and intake. `storage_ui.py` opens system All files access for user approval. The migration checkpoints text, blocks active transfers/provider readers, stages and hashes files, rejects links and conflicting trees, then writes the pointer last. Original trees remain for recovery. Restart after success.

**Use these files** runs `recover_location`. It validates the retained root
and existing collection folders, creates missing companion folders and activates
the location without walking the files. Empty setup requires empty destinations.
Android API 24–29 uses mounted app-owned directories. API 30+ uses mounted
volumes and All files access.

See [document publication](document-storage.md#publication-and-compatibility)
for the SD/FUSE move fallback. Run
`python3 dev.py test mobile test_storage_location.py` for location checks.
Verify SD-card writes and removal on hardware.

## Incoming files and Inbox

`mobile/incoming_files.py` publishes into **On My Phone / On My Tablet**. iOS uses public Documents; Android uses collection Files. The layout journal copies legacy Inbox contents and moves Received Files entries with numbered conflict suffixes. Apple's system Inbox remains outside the ordinary provider. Android `ReceiveActivity.java` streams ACTION_SEND/MULTIPLE content URIs. UIKit `IncomingFiles.m` handles cold/warm file URLs. `ShareViewController.m` writes into the App Group for the main app to consume on open.

`incoming_build.py` embeds `io.github.ispaure.logisticsmobile.inbox`. Enable `group.io.github.ispaure.logisticsmobile` on both identifiers, keep the existing team and refresh both profiles. Use [matching TestFlight profiles](../build-release/mobile-testflight.md#app-and-inbox-profiles-must-match).

Receivers stream private partial batches and atomically mark them ready. Bounds are 100 attachments, 1 GiB/file, 4 GiB queued and 2 GiB/Android batch. Incomplete forced exits expire after 24 hours. The consumer validates and hashes bytes, publishes with exclusive destination rename and receipts the result before retiring the handoff. Cancellation leaves unadmitted work queued; admitted work settles under the mutation lock. Retired hosts receive no UI updates.

Run `python3 dev.py test mobile test_incoming_files.py` for retry and retirement contracts. The manager's `android.incoming` and `ios.incoming` suites build owned sender/receiver apps and exercise real Sharesheets or Files **Open With**. Check bytes, names, reopen after restart and ownership cleanup. iOS profiles distinguish Share extension receipt from main-app Open In; iPad additionally verifies scene routing with existing windows preserved. Physical App Group provisioning remains a device check.

## Outgoing file shares

File menus capture the row’s provider, logical path and available revision.
`mobile/file_items.py` uses those references for favourites and handing off
files. `mobile/outbound_share.py` checks the source before and after streaming
saved bytes into an app-private cache. Protected providers use the document
export confirmation. The source is checked again before the share sheet opens.

UIKit receives a file URL and the cache copy is removed on completion or
cancellation. Android hands off a read-only content URI scoped to one share.
The Android provider rejects new opens after 15 minutes. The share flow
cleans cancelled or expired staging, and startup prunes stale copies.

Run `python3 dev.py test mobile test_document_menus.py` for item ownership and
protected staging. Run `python -m mobile_build.validation.outbound_android
--output tmp/test-results/<run-id>` in the mobile tooling environment for
the Android share sheet, generated receiver, exact bytes and expiration.

## iOS shared Local storage

`services/documents/migrations/ios_storage.py` relocates old Toga Documents data to `Library/Application Support/Logistics` before services start. Exclusive moves and private journals preserve original identities and stop on conflicts. Public Documents retains ordinary files and `Rclone Copies`; encrypted copies stay private. The plist exposes Documents through Files as **Logisticks**. Open upgrades once before file sharing, since the plist capability takes effect at installation.

Every launch requires Documents' backup exclusion before migration or registration. Run `python3 dev.py test mobile test_ios_storage.py` for migration, missing sources, conflicts and backup failures. Verify actual Finder/Files visibility separately.
