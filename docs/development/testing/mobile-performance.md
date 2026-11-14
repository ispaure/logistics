# Mobile performance and profiling

Find the [mobile owner](../architecture/mobile-runtime.md#owners). Time usable Home
separately from vault restore, provider listing separately from native drawing,
and document preparation separately from the first visible frame and checkpoint.
For Chat, separate parsing, DOM updates and loop delay. For LocalCrypt page turns,
separate archive reads, decode and rendering.

## Run focused probes

Use `performance_probe.py` for Android first draw and navigation,
`performance_workloads.py` for loop delay and Python allocations, and
`BenchmarkCryptArchivePage` in `mobile_build/rclone_bridge/archive_blocks_test.go`
for bridge reads. Use `test_footer_lifetime.py` for layout callback coalescing
and retirement. See [native suite timings](platform-checks.md#native-suite-timings).

Use [disposable synthetic fixtures](validation-artifacts.md) and record revision,
device, rendering and instrumentation. Measure native RSS and physical E Ink
latency on the relevant device.
