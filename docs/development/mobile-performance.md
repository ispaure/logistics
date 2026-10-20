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
3. Coalesce chat draft saves — pending.
4. Background streaming Markdown parsing — pending.
5. Incremental streaming DOM updates — pending.
6. Lightweight asynchronous document inventory — pending.
7. Cached asynchronous library inventory — pending.
8. Coalesced library discovery — pending.
9. Background Workspaces discovery — pending.
10. Lazy startup screens and document loading — pending.
11. Queued encrypted document history — pending.
12. Conversation summary inventory — pending.
13. Recycled conversation rows — pending.
14. Recycled library-folder rows — pending.
15. Visible-only browser thumbnail decoding — pending.
16. Bounded tile rendering — pending.
17. Formatted Markdown changed-block bridge — pending.
18. Background provider Markdown previews — pending.
19. Background EPUB text indexes — pending.
20. Cached EPUB DOM text indexes — pending.
21. Present pages before progress persistence — pending.
22. Batched EPUB position updates — pending.
23. Event-driven reader layout — pending.
24. Sampled comic decoding and reusable spreads — pending.
25. Coordinated Python/native memory budgets — pending.
26. Native loading-panel draw readiness — pending.
