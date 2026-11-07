# Mobile performance and profiling

Start with the [mobile runtime owner map](mobile-runtime.md#owners) to find
the code that prepares or publishes the work you want to measure.

| Workload | What to trace |
| --- | --- |
| Home startup and connection unlock | Time to the first usable Home separately from native vault restore, folder discovery and credential publication. Home retains controls when visible content is unchanged. |
| Workspaces entry and scrolling | Distinguish provider listing, row construction, native drawing and touch-to-scroll behavior. Retained roots and row recycling affect different parts of the workload. |
| Document opening and editing | Separate load-panel draw readiness, document preparation, first visible content and checkpoint publication. Recovery writes can coalesce, with explicit flushes at lifecycle boundaries. |
| Chat streaming | Separate background Markdown parsing, DOM updates and rendering from loop delay and response latency. |
| LocalCrypt comic page turns | Track archive reads separately from image decode and native rendering. The bridge reuses authenticated blocks within the archive request and does not create plaintext staging files. |
| Idle reader layout | Reader footers coalesce edge-width refreshes. Hidden and detached controls skip scheduling. Permanent retirement cancels the pending callback and removes the layout subscription. |

## Run focused probes

`mobile_build/native_tests/tests/logisticsmobile/performance_probe.py` measures
Android navigation, first native draw and workflow spans. The synthetic
`performance_workloads.py` helper measures typing, folder listing, document
opening, comic page turns and streaming Markdown. It records elapsed time,
maximum loop delay and Python allocations. Use native memory instrumentation
when the question concerns RSS. `test_performance_workloads.py` checks blocked
callback detection and ensures operation return values stay out of reports.

`BenchmarkCryptArchivePage` in `mobile_build/rclone_bridge/archive_blocks_test.go`
measures bridge archive-read work. `test_footer_lifetime.py` checks callback
coalescing, hidden controls and retirement. For suite-level orientation and
layout costs, see [native suite timings](platform-checks.md#native-suite-timings).

Use synthetic content and a [disposable workspace and app](validation-artifacts.md).
Record the source revision, device or emulator, rendering configuration, workload
and instrumentation. Compare like-for-like runs and keep raw timings outside the
wiki. Nested spans overlap, and Python or emulator measurements do not establish
native RSS, physical E Ink latency or device battery use.
