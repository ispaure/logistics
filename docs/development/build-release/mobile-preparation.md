# Mobile document host and validation

The Toga entry point is `Python/mobile/app.py:main`. `mobile_build/pyproject.toml` declares the Briefcase app, platform dependencies and separate native test entry. For controller and adapter ownership, use the [mobile runtime map](../architecture/mobile-runtime.md), [workspace navigation](../architecture/mobile-workspace-navigation.md) and [feature catalog](../../features/features.md).

## Owner-declared source selection

Add a new dependency to the host, service or feature's schema 1 `mobile_sources.json`. `SOURCE_OWNERS` in `mobile_build/tools.py` selects the manifests. Preflight verifies the generated `mobile.app` entry and selected module imports, including existing child packages referenced by `from` imports. Type-only imports and uncalled registration factories stay outside the runtime closure. The digest includes selected HTML, CSS and JavaScript paths and bytes.

Staging adds portable commonUtils and declared package data. It rejects linked source paths and excludes private files, Git data and the external feature checkout. Clean staging requires tracked shared sources. Local builds may use `--allow-dirty`; their evidence must bind the exact staged fingerprint. Edit sources and manifests to change generated payloads. See [mobile feature selection](../architecture/mobile-runtime.md#mobile-feature-selection) for runtime boundaries.

## Validation gates

Run `python3 dev.py test desktop test_mobile_packaging.py` from the root for payload omissions and digests. Use [host commands](mobile-launchers.md#host-validation) for controller checks and [platform gates](../testing/platform-checks.md) for full native app and separate embedded CPython acceptance. The native job retains the normal APK/simulator build before the test-mode build. The native and runtime verifiers require exact source, platform and case inventories. Use real OS fixtures for pickers and independent iPad scenes. Use [Duo checks](mobile-handbook.md#duo-rotation-and-fold-verification) for measured fold geometry.

## Offline component notices

Staging copies `services/licenses/` and writes platform requirements to `mobile/open-source-dependencies.json`. The offline viewer combines installed Python metadata, rclone's native Go manifest and Android's resolved runtime/Chaquopy asset. Update native provenance with dependency pins and verify notices inside the final artifact. See [collectors and refresh commands](open-source-notices.md).

## Launcher artwork

`mobile_build/resources/icons` owns the iOS light, dark and tinted slots and Android adaptive/night/themed artwork. `cloud_build.py` invokes the standard-library installer after Briefcase create/update. Use Pillow only to regenerate from the source PNGs:

```sh
mobile_build/.venv/bin/python mobile_build/build_support/icon_build.py /path/to/light.png /path/to/dark.png /path/to/monochrome.png
python3 dev.py test mobile test_icon_build.py
```

Preserve the full source tile, opaque iOS variants and Android monochrome alpha mask. Compile the iOS catalog after slot changes and verify launcher appearance on devices.

## Native destination routes

`mobile/navigation.py` owns Home, Workspaces (route `files`), Documents, feature-gated Chat and Settings. Destinations retain independent route stacks. UIKit reports native pops through its retained delegate. Android's tracked `NavigationBack.java` connects lifecycle-scoped Back to AndroidX, enabled when a route can pop. Recreate the generated project after Gradle source selection changes. Back pops a screen; dirty Close uses the document command.

## Shared document workspace

`workspace.py` keeps a 64 KiB/32-item ordinary manifest of managed UUIDs and whitelisted state, including per-text Edit/Preview. It preserves malformed input. Transient providers stay in memory. Callbacks capture session owner and generation. Replacement hosts retire old callbacks and pending private work. [Workspace navigation](../architecture/mobile-workspace-navigation.md) owns adaptive panes. See [UIKit scenes](#independent-uikit-scenes) for window ownership.

| Contract | Owner |
| --- | --- |
| Private edit/save | `documents.py` bounds text to 1 MiB, preserves encoding/endings and checkpoints atomic UUID-based drafts. Stale/deleted originals require conflict handling. |
| Import copy | `access.py` and `pickers.py` stream scoped URI/URL grants, then release them. |
| Preferences | `preference_schema.py` validates values; `preferences.py` atomically publishes private INI with concurrency and malformed-file guards. |
| Preview | `preview.py` renders bounded offline Markdown with escaped raw input. |
| Readers and chat | Follow the [feature catalog](../../features/features.md) to Books, Comics and LM. Native tests use generated files and loopback-only chat. |

### Explicit text-session close

Close prompts on the captured dirty owner with Save, Keep draft, Discard or Cancel. Save/checkpoint failures retain the session. Discard reads and checkpoints current bounded source bytes without writing the original. Private sessions omit durable Keep. See [draft checkpointing](../architecture/mobile-runtime.md#startup-and-document-responsiveness). Unavailable restored entries can retry or remove the workspace entry while preserving saved data.

### Memory-only provider sessions

`PrivateSessions` admits four controllers and 32 MiB of whole-file input. Identity is opaque and ordinary manifests omit all provider entries. Clean decoder resources release on inactivity or memory pressure; dirty text and forms remain until saved or discarded. Credential reload/forget checks every dirty owner before invalidating generations. `native_private_workspace` covers two encrypted drafts, cancellation and callback retirement.

### Repeatable one-way folder pulls

`pull_jobs.PullJobs` binds jobs to opaque connection identities and file/directory hashes. It stages a complete incoming tree and preserves edited local targets alongside the new snapshot. For unchanged targets it journals the replacement and retains the old version. Retry reconciles hashes and surviving paths. Removing a job removes metadata. Decrypted remote paths and crypto jobs remain transient. `resource_imports.ResourceImports` maps ordinary opaque source identities to imported UUIDs.

## Embedded rclone contract

`mobile_build/rclone_bridge/` links pinned rclone and AES/ZipCrypto support. The ZIP chooser copies up to 1 MiB while its grant is held. Load clears the password, keeps input for retry after failure and releases the ZIP after success. Remote selection is explicit. For native bridge, credentials and named storage contracts see [Rclone development](../../features/rclone/development/development.md) and [LocalCrypt](../../features/rclone/development/localcrypt.md).

### Side-by-side credential contexts

`credential_sets.go` admits up to 32 packages. Aggregate aliases delegate to the original package, with collisions disambiguated by package identity. Crypt lookups stay inside that package. Stable connection hashes let existing copies resolve the same account. Saved contexts persist in the encrypted vault; session contexts remain memory-only. LGCV1 is readable and multi-package saves use LGCV2. `CloudClient` serializes publication and state epochs across scenes. Lock clears all contexts; generation checks reject late operations.

## Unified Files

The commonUtils browse model drives mobile list/tile views, while Logistics retains provider, folder action and lifecycle policy. Retained routes preserve history/search/selection. The bounded folder pin store records ordinary private-relative paths or opaque connection identities. Stale identities fail closed. Credential lock retires details and thumbnails. Stream large transfers independently of buffer limits on range reads and decoded media.

## Native reader presentation

`ComicCanvas` uses native Apple and Android zoom containers from the widget factory. `ReaderChrome` owns controls and immersive presentation. Fit-size gates page gestures; fullscreen enables the hold magnifier for imported/provider comics and spreads. Android fullscreen releases hidden rail width. The mobile Auto spread policy uses measured landscape geometry, manga direction and standalone landscape/DoublePage metadata. Use `comic_viewport_probe.py` and `comic_spread_probe.py` for focused QA, and verify native touch and fullscreen restoration.

## Independent UIKit scenes

`window_scenes.py` attaches a host and bounded `Windows/<id>` workspace to each scene. Ordinary storage is shared and `WindowOwners` grants exclusive writers. The original window retains connection, transfer and chat ownership; protected sessions require a single window. Disconnect cancels picker work, checkpoints drafts and retires callbacks and leases. `scene_build.py` configures the generated plist. Required iPad evidence creates actual scenes, rejects a duplicate writer and restores separate state.

## Managed mobile transfers

Mirror mappings bind source identity, destination and baseline. Pull stages a verified copy and journals replacement, preserving edited destinations and previous versions. Push checks local bytes and remote revisions, verifies remote backups and rechecks uploaded bytes. Per-file baselines record partial completion. Concurrent external puts can race a provider write. All Push routes confirm before review and again before writes. Credential changes invalidate reviews. See [transfers](../../features/rclone/development/transfers.md).

### Scoped ciphertext and transfer preflight

Schema 2 separates physical namespaces by connection while retaining cipher identity for decryption. Old trees and journals keep their original namespace. OAuth pins live in the authenticated vault and keep token refresh from changing identity. Authenticate all ciphertext, hash the stable staged source and check remote revisions before writes. Progress reports bounded stages without filenames or credentials. Ordinary archive I/O can proceed outside the credential lock.

## Android collection drive selection

`services/documents/locations.py` binds a selected volume to its `Logistics/.logistics-storage` marker. Copies, encrypted copies and ordinary Files move together; credentials and mappings stay private. An absent drive stalls access and intake. `storage_ui.py` opens system All files access for user approval. The migration checkpoints text, blocks active transfers/provider readers, stages and hashes files, rejects links and conflicting trees, then writes the pointer last. Original trees remain for recovery. Restart after success.

For regular files on SD/FUSE, exclusive source publication may fall back to exclusive-create, hash verification and source removal. The destination is visible during the copy; directories still need native exclusive rename. `test_storage_location.py` checks collisions and partial cleanup. Verify SD-card writes and removal on hardware.

### Incoming files and Inbox

`mobile/incoming_files.py` publishes into **On My Phone / On My Tablet**. iOS uses public Documents; Android uses collection Files. The layout journal copies legacy Inbox contents and moves Received Files entries with numbered conflict suffixes. Apple's system Inbox remains outside the ordinary provider. Android `ReceiveActivity.java` streams ACTION_SEND/MULTIPLE content URIs. UIKit `IncomingFiles.m` handles cold/warm file URLs. `ShareViewController.m` writes into the App Group for the main app to consume on open.

`incoming_build.py` embeds `io.github.ispaure.logisticsmobile.inbox`. Enable `group.io.github.ispaure.logisticsmobile` on both identifiers, keep the existing team and refresh both profiles. Use [matching TestFlight profiles](mobile-testflight.md#app-and-inbox-profiles-must-match).

Receivers stream private partial batches and atomically mark them ready. Bounds are 100 attachments, 1 GiB/file, 4 GiB queued and 2 GiB/Android batch. Incomplete forced exits expire after 24 hours. The consumer validates and hashes bytes, publishes with exclusive destination rename and receipts the result before retiring the handoff. Cancellation leaves unadmitted work queued; admitted work settles under the mutation lock. Retired hosts receive no UI updates.

Run `python3 dev.py test mobile test_incoming_files.py` for retry and retirement contracts. The manager's `android.incoming` and `ios.incoming` suites build owned sender/receiver apps and exercise real Sharesheets or Files **Open With**. Check bytes, names, reopen after restart and ownership cleanup. iOS profiles distinguish Share extension receipt from main-app Open In; iPad additionally verifies scene routing with existing windows preserved. Physical App Group provisioning remains a device check.

### iOS shared Local storage

`mobile/ios_storage.py` relocates old Toga Documents data to `Library/Application Support/Logistics` before services start. Exclusive moves and private journals preserve original identities and stop on conflicts. Public Documents retains ordinary files and `Rclone Copies`; encrypted copies stay private. The plist exposes Documents through Files as **Logisticks**. Open upgrades once before file sharing, since the plist capability takes effect at installation.

Every launch requires Documents' backup exclusion before migration or registration. Run `python3 dev.py test mobile test_ios_storage.py` for migration, missing sources, conflicts and backup failures. Verify actual Finder/Files visibility separately.
