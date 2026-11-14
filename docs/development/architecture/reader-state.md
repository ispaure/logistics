# Document progress and private history clearing

`services/documents/{progress,progress_identity}.py` own observations and
admitted document identity. Local identity is root-relative when managed;
protected identity includes credential authority and namespace. Load state before
initial layout, observe only displayed locations, and flush through lifecycle
workers. Checkpoints bind compatible revisions and clear generations. Positions
and bookmarks publish independently. Interrupted writes preserve old bytes.

Ordinary files use bounded atomic JSON, including read-only local documents.
Protected providers persist through `credential_state.py` only with approved
credential ZIP password authority. Saved mobile connection metadata, a clear
ZIP and an inner archive password do not supply this key. Otherwise report
session memory. Encrypted lookup keys and opaque filenames live separately for
positions and bookmarks. Preserve unreadable originals and recheck grants.

`ReaderKeys/positions` and `ReaderKeys/bookmarks` encrypt the random lookup keys
with the ZIP password. Repacking or changing the password preserves source
identity and checkpoint names. Imported copy revisions bind binary digests
through SHA-256. Preserve pending observations for retry and use continuous
publication because mobile termination can skip final callbacks.

## Password changes and clearing

Unlock the new ZIP, then supply the old password through Reader history.
`state_migration.py` validates the source, re-encrypts in RAM and verifies before
publication. Preserve unmatched or corrupt ciphertext. The old password is
transient.

Clear positions without keys using the generation fence. Old readers cannot
republish; reopened readers can. Keep bookmarks, documents and Recent. Unloaded
external LocalCrypt sidecars become invalid and are retired on later access.
Clear Recent separately across credential caches and windows. Legacy unloaded
reopen records may also retire; active readers and saved positions remain.

`DocumentCatalog` retains favourites independently of desktop `DocumentRecent`
(ten entries). Private rows require unlocked credential access. iOS resolves
existing relocated Documents paths before deduplication and keeps the newest row.

Run `python3 dev.py test desktop test_unified_progress_core.py` for publication,
encryption and clear fences. Mobile adapter and native disposable probes cover
restoration after relaunch. Supported locators include page/zoom, scroll, UTF-16
line anchors and playback position, subject to revision compatibility.
