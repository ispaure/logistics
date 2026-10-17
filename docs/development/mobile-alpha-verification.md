# Alpha verification — 2026-10-14

Three verification passes target alpha commit `6f954a19df2473866a1ea15e32c762033170ff87`,
with local audit fixes. Further commits, pushes and releases are paused by the user.
The concurrent “Improve mobile remote folders” work is excluded from the frozen
snapshot; these results do not validate that ongoing work or the entire shared
working tree. The snapshot is `/private/tmp/logistics-alpha-audit-snapshot`.

## Pass 1 — brief, ownership and restoration

Reviewed the navigation brief and traced its milestone/validation requirements
against the implementation and existing fixtures. Reproduced a cold-start library
reader selecting itself despite the disabled restore preference. The fix keeps
retained readers and progress available for explicit reopening without selecting
one automatically. This fix was committed before the user's commit hold as
`6f954a1` (Phase 6 Part 1). All 68 host tests and 39 core tests then passed.

## Pass 2 — asynchronous ownership and privacy

Added failing regressions for a delayed private open replacing a newly selected
ordinary editor or Settings, folder successes/errors publishing to a superseded
host, and a delayed comic password prompt focusing a hidden or superseded reader.
Local fixes reserve the session without selecting it, retain completed private
loads for explicit activation, reject disposed-host publication, and suppress
hidden password focus. Existing drafts remain available. All 71 host tests and
Go bridge race tests passed after these fixes.

## Pass 3 — native containers and platform verification

Extended existing native cases with held real ciphertext opens and encrypted comic
password detection. The iPad run exposed an overly strict container identity
check: UIKit can replace a wrapper without a user navigation action. The fix tracks
navigation intent and workspace selection instead, including accepted programmatic
and native Back. A host regression verifies an incidental container refresh still
allows the requested open. All 72 frozen host tests, 39 portable core tests and
lint checks pass. All 25 native cases pass on Android, iPad and iPhone simulators. The iPad
run also verifies independent system scenes. All three reports match the same
staged runtime fingerprint and explicitly record dirty local source.

## Brief coverage and limits

Existing tests exercise independent text drafts, duplicate identity and repeated
opens, recovery and save conflicts, route/back ownership, Files history,
Markdown preview restrictions, EPUB/comic progress and bookmarks, private lock and
credential boundaries, cancellation and late results, bounded archive handling,
adaptive containers and independent scene activation. The new regressions strengthen
stale completion, disposed views and password focus coverage.

Physical provider permissions/revocation, cancelled touch gestures, original iPad
window destruction, minimum OS versions, Duo/fold poses, screen readers, hardware
keyboard, large text, RTL and the full light/dark/device matrix remain unverified.
Simulator and programmatic tests do not establish these manual device claims.
Home-first is the brief's updated decision; user-authorized managed Push supersedes
its earlier read-only remote proposal.

The separately released main.07 remains the exact alpha.34 commit `8416b248`.
It was installed in place on the physical test iPhone and successfully launched
after unlock. Existing file listings/sizes were preserved; file bytes were not
copied or compared. This audit does not install local alpha fixes on that phone.

## Retained evidence

- [Android native cases](mobile-evidence/2026-10-14-alpha-audit-android-native-ui-local.json)
- [iPad native cases](mobile-evidence/2026-10-14-alpha-audit-ipad-native-ui-local.json)
- [iPhone native cases](mobile-evidence/2026-10-14-alpha-audit-iphone-native-ui-local.json)
- [Portable host core](mobile-evidence/2026-10-14-alpha-audit-host-core-local.json)

The frozen audit patch is retained locally at `Mobile/logs/alpha-audit-fixes.patch`;
host output is `/private/tmp/logistics-alpha-audit-host.log`. Native runtime
fingerprint: `2f48b0f7d3dc098a4320b4ab3de004630bfb8f5dd3a60008d578b6a05cdd0932`.
These are local development checks, not clean-release evidence. The shared
checkout retains the audit fixes alongside the other chat's unrelated work.

### Native gate lifecycle and concurrent-transfer probes

The disposable test app starts its exercise once per app instance even if Android
activity recreation repeats `on_running` before the queued task begins. Repeated
callbacks reuse the same task, including while its result is being flushed.

The LocalCrypt native concurrency probe pulls a real 256 MiB encrypted fixture
with the production 1 MiB/s bandwidth option. Files, Documents, the catalog
library shortcut and the Documents library shortcut each receive a fresh
transfer. Every route requires live progress before opening readers, verifies
the transfer remains pending with its original cancellation handle, then cancels
and retires it before the next route. Route timings are retained in native logs.
Only the probe's abandoned bytes are removed between routes; a reviewed native
push removes the synthetic remote object before later remote observations.
This avoids assuming one transfer outlasts all four cold layout sequences and
does not raise the native gate's 15-minute deadline.
The initial reviewed push that seeds this bulk fixture has a 120-second budget;
ordinary document reviews retain their 30-second budget.

Worker progress is coalesced per transfer: a lock protects the latest snapshot
and one pending event-loop callback. The callback releases the lock before
rendering, allowing at most one successor while native UI work is busy. Existing
epoch checks reject stale snapshots; completion and cancellation still publish
terminal UI state synchronously. Burst, concurrent-render and stale-epoch tests
cover these delivery guarantees.
Native reviewed-transfer timeouts retain the review status, visible comparison
and latest progress text, distinguishing a pending recheck from active I/O.
The iOS native gate also exercises Foundation backup exclusion and exclusive
moves against a disposable legacy-storage fixture, checking that ordinary files
become shared Local files while credentials remain under private support storage.

## Reader and editor validation scope

Simulator/emulator checks exercise zoom, fit, page direction, reading-mode restore,
appearance and session ownership. Physical pinch/Back gestures, screen-reader
interaction and large-text usability still require device evidence.
