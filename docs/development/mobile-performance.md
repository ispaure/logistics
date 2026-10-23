# Mobile performance implementation and verification

## BOOX background publication and retained Home controls — 2026-10-20

A separate diagnostic run isolates work outside the native vault request: Home
reconstruction takes 193.5 ms (182.9 ms building its controls), connection model
preparation 39.1 ms, protected-key unlock 28.2 ms, crypt metadata/discovery 64.4 ms,
and package-association updates 14.6 ms. These spans are diagnostic samples and
can nest or overlap; they do not account for all native/async scheduling latency.
A separate function profile confirms 33 widget constructions during Home refresh.

Home now compares its visible summaries, source references, open states, notices
and unlock-action availability. If these match, it retains its root, actions and
recent rows and updates only changed credential glyphs/accessibility descriptions.
Changed content still rebuilds Home; active detail routes retain their existing
guards. The optimized diagnostic records no Home construction and a 14.3 ms Home
refresh. Package associations skip unchanged preferences, reducing that observed
step to 2.2 ms. Crypt names and local-directory fingerprints use published records,
removing the extra crypt-remotes query and 16 crypt-path requests in this workload.
Alternate adapters keep native-query fallback, and actual opening/decrypting still
passes native credential checks. Metadata/discovery wall time did not improve in
the single diagnostic pair (76.9 ms after), so request removal alone is not claimed
as a measured wall-time improvement.

Matched minimally instrumented build `202610249` uses identical native code for
three baseline and five optimized cold-process launches. The baseline probe only
disables these three Python performance changes in generated files. Medians are:

| Measurement | Baseline | Optimized |
| --- | ---: | ---: |
| Background setup outside vault request | 559.8 ms | 312.8 ms |
| Whole background connection setup | 813.5 ms | 601.4 ms |
| Python entry to all connection preparation complete | 3617.6 ms | 3325.0 ms |

Outside-vault latency falls 44.1%; total background setup falls 26.1%. Every run
passes all 35 unlocked-badge checks, without constructing remote UI or unopened
Documents. All samples remain in the evidence, including one optimized 1215.6 ms
outlier; its vault request also rises to 591.8 ms. The other four optimized runs
span 579.9–627.1 ms. Other user-authorized Android chats were using the shared
workspace/device, so these are noisy shared-device measurements. Timings exclude
native/interpreter boot and physical E Ink refresh.

Go checks, 99 focused host checks, correctness Ruff and whitespace checks pass.
Host coverage includes retained button identity across unlock/relock, changed
history/notices/unlock action, metadata-only discovery, and unchanged preference
writes. A Java cast correction also resolves the current rail source's build error.
The shared signed release `202610250` supersedes the measured release; APK inspection
confirms identical native Go code and bytecode for the three performance owners,
with no startup probes. Its navigation rendering differs, and its latency is not
separately timed. Device data is retained. Numeric evidence (local artifact `test-results/mobile-evidence/2026-10-20-boox-background-publication.json`)
contains every trial and diagnostic method span; real-device captures remain in
ignored logs.

## BOOX native vault stages — 2026-10-20

Temporary Go stage timers on the physical BOOX Note Air5 C isolate the remaining
vault restore cost. Across three baseline cold-process launches (probe build
`202610245`), eight distinct cipher creations take 505–522 ms. Their median is
506.6 ms, versus 511.0 ms for all of `openVault`. Median read, AES-GCM decrypt,
JSON decode and remote parsing spans are 0.19, 0.56, 1.23 and 0.67 ms respectively;
installation and metadata take 0.33 and 0.88 ms. Parsing and cipher creation are
nested within validation/open and must not be added again. The primary work is
rclone cipher creation, whose expensive operation is scrypt key derivation.

Missing distinct configurations now derive with up to four workers, sharing the
existing private candidate cache only after every worker succeeds. The scrypt
parameters and saved credential format are unchanged, and automatic loading still
prepares every cipher before credential publication. Simultaneous scrypt scratch
memory is bounded to approximately 64 MiB. No derived key cache is persisted.

Three optimized launches (probe build `202610246`) produce these medians:

| Measurement | Sequential | Bounded parallel |
| --- | ---: | ---: |
| Native validation wall time | 508.8 ms | 265.1 ms |
| Whole bridge vault restore | 517.9 ms | 284.7 ms |
| Background connection preparation | 946.2 ms | 767.8 ms |
| Python entry to connection preparation complete | 3805.3 ms | 3562.8 ms |

Vault request latency falls 45.0%, and background preparation falls 18.9%. Home
remains independent of restoration (about 2.8 seconds from Python entry). These
clocks exclude native/interpreter boot and physical E Ink refresh. Parallel
per-cipher elapsed spans overlap and their sum is not preparation wall time or
CPU time. Worker scheduling and memory contention limit the improvement.

All 35 credential badge checks remain unlocked in every trial. Native inspection
also confirms populated Cloud sources with unlocked icons, without opening a
remote. Full Go tests, targeted race checks, and 41 focused mobile host tests pass.
Tests cover encryption equivalence, reuse and failed-batch atomicity. Signed
release `202610247` removes all probes and is installed over existing device data.
Numeric evidence (local artifact `test-results/mobile-evidence/2026-10-20-boox-vault-stages.json`) records each
stage and trial; real-device captures remain in ignored local logs.

## BOOX connection setup without hidden UI — 2026-10-20

Build `202610243` separates automatic credential preparation from remote-browser
and connection-settings construction. The diagnostic background function profile
found 229 widget constructions, five busy-state updates and five hidden retained
package-list rebuilds. Credential publication also built an unopened Documents
hub and triggered additional document-list refreshes. These cumulative profile
timings include profiling overhead and are not additive.

`prepare_cloud` and `start_cloud_restore` now load credentials independently of
the screens. Cloud source navigation shares the same task and displays names and
lock states without constructing a browser. `show_cloud` builds controls when
needed and adopts the current names/busy state, including when opened mid-restore.
Package settings cards wait for their first visit. Credential publication updates
Home and existing Documents hubs without constructing unopened Documents. LocalCrypt
discovery shares collection-base validation across the scan.

Using the previous release's minimal timing probes on the same BOOX Note Air5 C,
three optimized cold-process runs measured 978.61, 983.58 and 984.20 ms of background
setup, versus the previous 2,267.17 ms median: a 56.6% reduction. Median Python entry
to complete connection preparation fell from 5,092.69 to 3,809.57 ms. Home readiness
remained about 2.8 seconds. These clocks exclude native/interpreter boot and physical
E Ink refresh. Vault restoration still takes about 524 ms; a separate detailed
timing run measured about 167 ms refreshing Home and 70 ms preparing crypt metadata.

All 35 loaded-credential badge checks were unlocked in every run, and neither the
remote UI nor Documents was constructed. Native inspection confirmed the Cloud
folder icons and first-visit connection settings; visiting settings did not repeat
vault restoration. Focused cloud, credential, startup, navigation, discovery, reader,
storage and transfer checks pass, as does the Go bridge suite during the release
build. The final deployment restores the signed release without probes and retains
device data. Per-run evidence (local artifact `test-results/mobile-evidence/2026-10-20-boox-connection-setup.json`)
contains only numeric metrics and fixed workload names; actual UI captures remain
in ignored local logs.

## BOOX credential cipher reuse — 2026-10-20

Build `202610242` keeps automatic saved-credential loading and the existing
connection identities and unlocked icons. Native validation now reuses ciphers
for equivalent encryption settings, then transfers prepared ciphers into the
admitted credential session. Different backing paths retain distinct connection
identities while sharing an equivalent cipher. Lock clears the cache; credential
replacement prunes settings no longer referenced by loaded packages. The cache
remains in memory. See the [LocalCrypt contract](../features/rclone/development/localcrypt.md#shared-mobile-browsing-and-streaming).

On the same physical BOOX Note Air5 C and existing storage, four previous runs
versus three optimized runs measured these medians:

| Work | Previous | Optimized |
| --- | ---: | ---: |
| Vault restoration | 2,117 ms | 535 ms |
| Sixteen encrypted-folder identity calls, combined | 991 ms | 11 ms |
| Background connection preparation after Home | 5,324 ms | 2,267 ms |
| Python entry to all connection preparation complete | 8,171 ms | 5,093 ms |

Home remains available in 2.7–3.0 seconds from Python entry. The clock excludes
native/interpreter boot and physical E Ink refresh. All 35 loaded-credential badge
checks were unlocked in each trial. Native inspection confirmed a populated Cloud
tab with unlocked folder icons; the recorded bridge actions were local
`vault_open`, `crypt_remotes` and `crypt_path`, without opening a remote or starting
a transfer. Full Go tests, targeted cipher-lifecycle race checks and eleven Python
credential checks pass. The final deployment restores the release without probes
and retains device data. Numeric evidence (local artifact `test-results/mobile-evidence/2026-10-20-boox-cipher-reuse.json`)
records each run. Screenshots and UI dumps remain in ignored local logs.

## BOOX Home startup — 2026-10-20

Home no longer awaits connection-control construction, credential restoration or
LocalCrypt folder discovery. Initial restore starts after the native workspace
cover is removed and does not clear an ordinary local browser or reader opened
during loading. Saved-connection publication updates the document hubs without
replacing a retained detail route. Home's Open file action, local browsing and
ordinary local text reads do not wait for restoration. Cloud-backed reopens still
await matching credentials; the editor-specific Open/Save As picker retains its
shared credential-loading guard.

On the physical BOOX Note Air5 C, two before runs measured 8.887 and 8.906 seconds
from Python entry to native workspace reveal. Four after runs measured
2.986, 2.745, 2.801 and 2.761 seconds: a 68.7% median reduction. Connection work
continued for another 4.7–5.5 seconds. These clocks exclude interpreter/native
boot and physical E Ink refresh. A native tap of Home's Open file button while
restoration was pending opened the local browser, which remained visible after
completion. The final device installation is release build `202610241`, without
the temporary timing probes; existing data was retained.

The numeric evidence (local artifact `test-results/mobile-evidence/2026-10-20-boox-home-startup.json`) records
the measurement scope and checks. Fifty-two focused startup, credential,
document-navigation, reader/loading and packaged-startup tests pass. Broader
navigation/workflow suites retain nine existing failures reproduced with the
affected local-action changes reverted. Actual screenshots and UI dumps remain
in ignored local logs because they contain real device metadata.

## Earlier performance work

The 2026-10-19 audit approved the following ordered changes. Complete and verify
one point, then commit it before starting the next. Preserve unrelated work.
Session-only content, credentials and decrypted bytes must never enter persistent
summaries, recovery records, telemetry or benchmark output. Synthetic QA uses an
isolated storage root; reports contain fixed workload names and numeric metrics.

## Verification baseline

`mobile_build/native_tests/tests/logisticsmobile/performance_probe.py` retains its
Android tab/first-draw measurements and adds `performance_workloads.py` scenarios
for typing, a 1,000-file folder, opening text, a comic page turn and streaming
Markdown. The helper measures elapsed time, maximum loop delay and Python peak
allocations. It does not measure native RSS. Run native scenarios on a disposable
QA host; never point the probe at real app storage or loaded credentials.

Host dummy-backend baseline, with allocation tracing enabled (2026-10-19):

| Workload | Elapsed ms | Maximum loop delay ms |
| --- | ---: | ---: |
| Typing 20 edits | 159.8 | 149.7 |
| Folder with 1,000 entries | 632.2 | 137.8 |
| Open text | 36.2 | 14.9 |
| Comic next page | 3.8 | 2.1 |
| Streaming 20 updates | 3592.1 | 237.0 |

These are host measurements with instrumentation overhead, not device latency
claims. Native draw, native memory and visual correctness remain separate device
checks. `mobile_build/tests/test_performance_workloads.py` verifies detection of blocked
callbacks and omission of operation return values from reports.

## Ordered work

1. Performance baseline — implemented; host workloads and two helper tests pass;
   native device measurements pending.
2. Coalesce document recovery saves — implemented: idle batching (250 ms, maximum
   1 second), worker publication, and explicit flushes on navigation, focus loss
   and host replacement. Session-only buffers never queue; privatize/delete/save
   serialize with workers and retire pending snapshots. Fifty edits produce one
   worker write. Thirty-five recovery/private tests pass. Instrumented typing
   elapsed 140.4 ms versus 159.8 ms baseline. The workspace preview-mode test
   fails identically when restoring synchronous checkpoint behavior; it is a
   pre-existing navigation failure, not attributed to batching.
3. Coalesce chat draft saves — implemented: 250 ms idle batching, one-second
   maximum delay, serialized workers and explicit navigation/focus/exit saves.
   Explicit saves invalidate older workers; out-of-order workers and external
   revisions cannot overwrite newer records. Four storage tests and eleven UI
   tests include a session API-key sentinel. Twenty draft changes on a synthetic
   large-history record: 62.4 ms synchronous versus 0.18 ms queued callbacks.
4. Background streaming Markdown parsing — implemented: immutable text-only
   snapshots, a single renderer, 80 ms burst coalescing and conversation/generation
   checks before native publication. Eighteen UI/presentation checks pass,
   including switching conversations during a blocked worker. With tracing,
   synthetic large-reply loop delay fell from 840.5 ms to 17.1 ms (elapsed parsing
   850.4 versus 832.3 ms). No content is logged or cached on disk.
5. Incremental streaming DOM updates — implemented: reconcile sanitized top-level
   blocks while retaining unchanged nodes, the message container and Copy button.
   Seven presentation/browser checks pass in headless Chrome with all network
   requests blocked. Stable paragraph selection survives partial/final code-fence
   updates, final markup matches the complete renderer, and at most three blocks
   are removed across the two updates. Native WebView/device timing remains open.
6. Lightweight asynchronous document inventory — implemented: in-memory name/ID
   summaries keyed by recovery-file revision; live refreshes coalesce background
   scans and publish cached metadata immediately. Full open still validates
   original bytes and conflicts. Five inventory tests and 24 document/navigation
   checks pass. For 100 synthetic 50 KB documents, full reads took 160.1 ms,
   warm summaries 1.74 ms, cached UI reads 0.009 ms. Startup's synchronous initial
   scan is addressed by point 10. The old Home loading test expects an embedded
   banner and fails with both inventory implementations; point 26 will align it
   with the already implemented separate loading panel.
7. Cached asynchronous library inventory — implemented: background live scans,
   immediate copied metadata snapshots and an 8 MiB serialized-record cache keyed
   by filesystem revision. Journal recovery still precedes authoritative reads;
   corruption/deletion invalidate cached entries. Twenty-two inventory/catalog/
   reader/navigation checks pass. For 1,000 records, cached UI reads took 3.08 ms;
   warm worker scans 41.5 ms versus the audit's uncached 65.2 ms. Native device
   timing remains pending. No cache file or decrypted reader payload is added.
8. Coalesced library discovery — implemented: one discovery worker per catalog,
   two-second reuse for identical credential/job snapshots, explicit refresh and
   credential-generation invalidation. Twenty simultaneous requests invoke one
   scan. Twelve inventory/catalog/reader checks pass. Reuse is memory-only and
   never substitutes for credential checks when opening a folder.
9. Background Workspaces discovery — implemented: native tabs immediately reuse
   memory snapshots while filesystem discovery runs in one coalesced worker.
   Native selector reads are captured on the UI loop. Credential changes discard
   old results; catalog locking clears cached names and retires in-flight work
   before bridge locking completes. Sixty-four folder/private checks pass.
   A warmed 300-folder refresh measured 25.1 ms/18.9 ms loop delay before versus
   23.8 ms/13.7 ms after (host tracing enabled). No persistent discovery index.
10. Lazy startup screens and document loading — implemented for phased primary
    startup: durable model preparation/pruning and recent display metadata run in
    a worker. Home is constructed first; inactive Documents/Workspaces pages and
    restored editor content wait until requested. Only metadata is retained from
    preparation; full recovery text is revalidated on actual open. Fifteen startup/
    inventory checks pass, including deferred view construction, exact recovered
    draft restoration and worker-thread execution. Native startup timing remains
    unmeasured; synchronous scene/test construction retains its existing contract.
11. Queued encrypted document history — implemented: normal remember/close writes
    coalesce for 50 ms and seal/publish in a serialized worker. Credential identity,
    generation and publication tokens are rechecked before disk publication.
    Forget retires tokens under the deletion lock; memory clear serializes with
    writers. Focus/host replacement flush valid writes. Legacy migration retains
    synchronous ciphertext-before-plaintext-removal ordering. Twenty rapid updates
    invoke one seal. Twenty-seven credential-list/private checks pass, including
    plaintext sentinels and cancellation on forget/replacement. Crypto primitives
    are unchanged; these lifecycle tests use the existing opaque bridge fixture.
12. Conversation summary inventory — implemented: memory-only ID/title/updated
    summaries, revision-aware worker scans and cached UI publication. Cold first
    visits wait for inventory before selecting an existing conversation; explicit
    user selection cancels automatic initial selection. Twenty-five chat/storage/
    UI checks pass. For 500 synthetic conversations, full reads took 50.8 ms,
    warm scans 7.36 ms and cached UI reads 0.092 ms. Summaries contain no drafts,
    message bodies or API keys and add no persistent index.
13. Recycled conversation rows — implemented through the host presentation
    contract using existing UITableView/ListView recycling. Rows use conversation
    IDs, one shared icon, proper accessibility labels and no nested scrolling
    container. Busy state disables interaction and callbacks retain their guard.
    Eighteen chat/inventory/browser checks pass, including 1,000 rows without any
    per-row Button construction. Host update: 147.2 ms/8.27 MB peak allocations
    before versus 14.5 ms/1.29 MB after. Native compilation/device checks remain
    pending (no Android platform SDK is installed in this host environment).
14. Recycled library-folder rows — implemented: one native list with lightweight
    compatibility action models, provider/generation checks and scrubbed private
    rows on lock. Twenty-eight inventory/catalog/session/reader checks pass,
    including 1,001 rows without per-row controls and retired private callbacks.
    For 1,000 folders, host rendering fell from 569.8 ms/24.3 MB peak allocations
    to 28.3 ms/1.12 MB. A refresh barrier waits for inventory-triggered metadata
    work; integration tests use it before retiring fixtures. Read-only inventory
    no longer creates edit-journal directories. Native visual checks pending.
15. Visible-only browser thumbnail decoding — implemented: lightweight source rows
    defer cached image decoding until visible, reuse a 64-entry decoded cache and
    clear it on folder replacement/stop. iOS updates only the still-current visible
    cell instead of reloading the table for thumbnail changes. Sixteen browser
    checks pass. A 500-cached-image render performs zero decodes; viewing one row
    decodes once and revisiting it reuses that image. Retired rows cannot update
    native cells. Native device frame timing remains pending.
16. Bounded tile rendering — implemented: a maximum of 80 live cards, reused
    overlapping rows and fixed-height spacers retain the full scroll extent.
    Offscreen thumbnail work is cancelled and evicted callbacks are rejected.
    Twenty-four browser/keyboard checks pass, including 10,005 entries and exact
    last-file activation. Stop clears retained names/images and entry snapshots.
    Native scrolling and frame timing remain pending.
17. Formatted Markdown changed-block bridge — implemented: cumulative changed
    blocks replace whole-source URL messages; unchanged blocks retain exact
    original spelling. Byte counts are cached per block. Monotonic revisions and
    per-load nonces reject stale updates; cumulative payloads tolerate coalesced
    navigation. Twelve Markdown checks pass, including Unicode/CRLF preservation,
    undo, invalid indexes, out-of-order messages and disposal. Source stays in RAM.
18. Background provider Markdown previews — implemented: delayed edits and
    preview toggles render Markdown/sibling images in workers. Per-render tokens,
    exact text, reader identity and credential generation gate publication; clearing
    previews retires tokens and tasks. Twenty-six Markdown/private-session checks
    pass, including proof that conversion runs off the UI thread. No disk cache.
19. Background EPUB text indexes — implemented: imported and provider workers
    prepare inert chapter HTML and UTF-16 indexes together. Private rich/text
    surfaces consume the prepared index; fragment lookup reuses it. Thirty-two
    reader/session checks pass, including worker-thread indexing and no repeat
    indexing during native text-surface construction. No persistent chapter cache.
20. Cached EPUB DOM text indexes — implemented: one text-node/prefix-offset
    index per inert chapter, binary-search seeks and cached selection starts.
    Disposal clears node references. Ten browser/reader lifecycle checks pass.
    A synthetic 2,000-paragraph browser chapter performs one TreeWalker build
    across 100 Unicode selections and visible-position queries. Browser fixture
    notifications are intercepted to model the native navigation bridge.
21. Present pages before progress persistence — implemented: mount the page,
    controls and navigation state before awaiting the progress writer. Writes
    retain the original compare-and-swap record and reader/epoch guards. Twenty
    EPUB/reader checks pass, including a failed writer that observes the mounted
    page and leaves it readable with an error message. Provider positions remain
    memory-only. Native paint latency remains unmeasured.
22. Batched EPUB position updates — implemented: a fixed 150 ms window writes
    the latest event once, with event-driven busy waits. Focus/checkpoint, chapter
    navigation, bookmark actions and close attempts request an immediate flush;
    close retains its existing wait-until-saved guard. Twenty-one EPUB/reader
    checks pass, including twenty events producing one latest-position write.
    Private provider locations continue to live only in the session dictionary.
23. Event-driven reader layout — implemented: weak event subscriptions replace
    both 300 ms timer loops. Initial mounting, native window/fold resize, reader
    idle transitions and fit actions coalesce wakeups. Zoomed spreads defer reload
    until an eligible layout/fit notification. Twenty-two reader/layout checks
    pass; idle waits stay asleep, 100 notifications coalesce, and retired listeners
    are collected. Native fold/gesture geometry checks remain pending.
24. Sampled comic decoding and reusable spreads — implemented: Android uses
    BitmapFactory sampling and iOS ImageIO thumbnails bounded to draw resolution.
    Composition decodes one page at a time, releases Android scratch bitmaps and
    drains per-page Apple autorelease pools. Compatible spreads reuse the canvas
    after successful composition; failures preserve previous pixels. Twenty-eight
    reader/private checks pass for sampling, canvas identity, failure retention,
    manga order, alpha and gutter. Native decoder execution remains pending;
    Apple signatures were checked against installed SDK/backend sources.
25. Coordinated Python/native memory budgets — implemented: the native archive
    pool admits 128 MiB total while preserving the 128 MiB individual archive
    limit. Python private admission counts shared bytes once plus member caches
    and edit strings within 32 MiB; memory pressure clears decoded thumbnail
    caches. Named bitmap/decode/bridge reserves document a 384 MiB managed-reader
    envelope, excluding interpreter/WebKit/OS memory (not an RSS ceiling). Thirty
    Python accounting/private/remote checks pass. Native Go tests verify budget
    accounting without content disclosure, release, offline access and revocation.
    Real-device peak RSS remains unmeasured.
26. Native loading-panel draw readiness — implemented: Android acknowledges a
    draw traversal through a removable one-shot listener; iOS uses a transparent
    UIView draw probe. A 500 ms bound supports detached/hidden views; fallback
    yields are explicitly not native draw acknowledgements. Open work rechecks
    the destination/route afterward. Cancellation removes listeners and late
    callbacks cannot publish; panel retirement scrubs filename/image. Fifty
    opening/history/session checks pass, including Home, Documents and Workspaces
    waiting before I/O and rejecting completion after navigation. Native visual/
    first-draw timing remains pending; Android platform SDK is unavailable.


## Settings navigation work reduction (2026-10-20)

Settings constructs categories on demand and reads installed build identity
only when About opens. Initial profiling of the tab callback on the dummy backend identified
text fitting and layout as the main Settings-specific cold-open work; this is not
a measurement of native device latency.

The category menu now fits before it becomes scroll content, avoiding per-row
scroll layout while heights change. Category pages retain their last fitted width;
revisiting at the same width skips the recursive fitting pass. `SettingsLabel`
continues to fit changed status/voice text immediately, and resizing refits the
visible page. Text fitting caches source, width and font style before native font
reads, and wrapping measures whole words before falling back to character splits.
Menu selection also avoids duplicate surface painting and initializes unselected
buttons during construction.

The same disposable host profile at 390-point width reduced the first App-category
visit from 12 recursive `fit_section` calls and 16 `fit_text` calls to 6 and 8;
repeat visits reduced both counts to zero. A 900-point cold Settings open reduced
layout invocations from 12 to 10. Thirty-three Settings/navigation/appearance
checks pass, including retained-page reuse, changed status text, resizing and
avoiding native font reads on an unchanged label. These counts establish less
synchronous work, not a measured low-end iOS/Android speedup.

### Strict page deferral and native menu construction

No category is constructed on initial entry, including in the wide layout. The
right pane remains empty until a category is selected. Opened categories retain
their controls and fitted widths across navigation and resizing. About identity,
voice controls and feature settings are constructed only on actual access.

`show_settings` batches surface changes during construction and initial fitting,
painting final roles before mounting. Each menu button receives its native list
styling once rather than repeating it during text fitting. iOS composite icon
images use a bounded 64-entry cache keyed by icon names and display scale; these
are immutable template pixels, with independent button tint and interaction
state. Renderer geometry, symbol weight, padding and group styling are retained.

A paired run on a dedicated iPhone 17 simulator (iOS 27.0), using an isolated empty
workspace and the same profiler, produced:

| Measurement | Before | After |
| --- | ---: | ---: |
| First Settings callback, including tab activation | 142.9 ms | 74.5 ms |
| Next native draw after selection | 164.9 ms | 95.7 ms |
| Menu construction | 118.7 ms | 50.6 ms |
| Icon installation | 49.6 ms | 21.8 ms |
| Surface styling | 33.1 ms | 8.4 ms |

The component spans overlap; they must not be added. This is a single paired
simulator run, not a physical low-end device benchmark. Menu screenshot content
matched pixel-for-pixel outside the native tab selection animation; the App-page
options/comments also matched outside its native Back control. All 38 focused
Settings/navigation/checkpoint/appearance checks pass, including zero initial
subpages on wide screens, one final paint per menu row, saved values, narrow text
wrapping, resizing and native Back. The Android implementation shares batching
and lazy construction; this change has not received native Android timing or
visual verification.

## Final host verification (2026-10-20)

The combined regression selection covers 193 checks. Two localhost HTTP fixture
checks initially hit the sandbox's listener restriction; all thirteen chat UI
checks pass when rerun with the required local-network permission. Thirteen
additional build/checkpoint/keyboard checks pass. Both offline browser fixtures
pass (stable transcript DOM/selection and one EPUB text-index walk). A separate
synthetic formatted-editor browser check sends one small changed-block payload
for a 1,001-paragraph document and restores exact original source on undo. Native
Go archive accounting/offline/revocation checks pass. Ruff and diff checks pass
for this implementation. Unrelated working-tree changes remain unstaged.

Final review found that Toga's Image/backend reference cycle could retain sampled
Apple scratch images past the autorelease pool. Explicitly clearing their native
reference now retires those pixels after drawing, including draw failures. Four
composition checks pass after that correction; actual Apple decoding is still
awaiting native execution.

Fresh disposable dummy-backend run, with the same allocation instrumentation:

| Workload | Elapsed ms | Maximum loop delay ms |
| --- | ---: | ---: |
| Typing 20 edits | 142.7 | 132.2 |
| Folder with 1,000 entries | 639.7 | 139.3 |
| Open text | 38.7 | 17.6 |
| Comic next page | 3.9 | 2.1 |
| Streaming 20 updates | 3622.2 | 259.0 |

Typing improves modestly in this aggregate fixture; the other aggregate numbers
show no demonstrated improvement. The streaming fixture calls the parser directly
and does not exercise the worker/coalescing UI path. Targeted results above prove
bounded allocations, fewer publications and removal of specific UI-thread work;
they do not establish a device-wide speedup. Real iOS/Android visual checks,
first-draw timings, scrolling frame times and native peak RSS remain pending.
