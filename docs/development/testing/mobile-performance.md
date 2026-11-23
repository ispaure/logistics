# Mobile performance and profiling

Find the [mobile owner](../architecture/mobile-runtime.md#owners). Time usable Home
separately from vault restore, provider listing separately from native drawing,
and document preparation separately from the first visible frame and checkpoint.
For Chat, separate parsing, DOM updates and loop delay. For LocalCrypt page turns,
separate archive reads, decode and rendering.

## Run focused probes

Use `mobile_build.validation.document_storage_tools` with `--probe filename-search`
for matched native Local and LocalCrypt fixtures on a disposable device. The
probe records first actionable match, completion, cancellation, rename and
credential-lock behavior. Timing starts at the native query event. The receipt
also records time from synthetic value assignment, which can include initial UIKit
keyboard work before the query event. Run `Python/tests/platform/benchmark_folder_open.py`
with a Manager scratch path and a separate evidence output path for desktop
folder opening, navigation and rename.

Run `mobile_build.validation.file_drag_ios` with `--output` under
`tmp/test-results/` to exercise real hold-and-drag gestures on an owned iPhone
simulator. The probe verifies folder entry and checks that the file and folder
contents survived the move in List and Tiles.

Use `performance_probe.py` for Android first draw and navigation,
`performance_workloads.py` for loop delay and Python allocations, and
`BenchmarkCryptArchivePage` in `mobile_build/rclone_bridge/archive_blocks_test.go`
for bridge reads. Use `test_footer_lifetime.py` for layout callback coalescing
and retirement. See [native suite timings](platform-checks.md#native-suite-timings).

Use [disposable synthetic fixtures](validation-artifacts.md) and record revision,
device, rendering and instrumentation. Measure native RSS and physical E Ink
latency on the relevant device.
