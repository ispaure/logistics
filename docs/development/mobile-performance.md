# Mobile performance implementation and verification

The 2026-10-19 audit approved the following ordered changes. Complete and verify
one point, then commit it before starting the next. Preserve unrelated work.
Session-only content, credentials and decrypted bytes must never enter persistent
summaries, recovery records, telemetry or benchmark output. Synthetic QA uses an
isolated storage root; reports contain fixed workload names and numeric metrics.

## Verification baseline

`Mobile/native_tests/tests/logisticsmobile/performance_probe.py` retains its
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
checks. `Mobile/tests/test_performance_workloads.py` verifies detection of blocked
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
19. Background EPUB text indexes — pending.
20. Cached EPUB DOM text indexes — pending.
21. Present pages before progress persistence — pending.
22. Batched EPUB position updates — pending.
23. Event-driven reader layout — pending.
24. Sampled comic decoding and reusable spreads — pending.
25. Coordinated Python/native memory budgets — pending.
26. Native loading-panel draw readiness — pending.
