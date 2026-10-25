# Testing and packaging plans

`python dev.py test-map` prints the project-owned suite inventory, owners,
platforms, entry points and recursively discovered test files. Functional tests
stay with their feature owners. `Scripts/validation_plans.py` owns the platform
composition used by `Python/tests/run_platform_checks.py` and the local manager;
the reusable execution machinery must not own these Logistics policies.

| Plan | Ordered work | Evidence and cost |
| --- | --- | --- |
| Static/contracts | Correctness lint, import/ownership/toolchain checks and focused runner contracts | Fast host checks; JSON per-test timings from the isolated runner |
| Desktop macOS, Ubuntu, Fedora, Windows | Windows native startup where applicable, shared regressions, application regressions, full historical compression parity | `summary.json`, per-phase logs and regression timing reports; phase budgets 60/600/900/600 seconds |
| Native iOS | One test-app build, then required iPhone, Duo and iPad suites | Hosted devices run in parallel; local selected devices run sequentially; each has isolated source-verified reports |
| Native Android | Curated payload, native bridge/application build, emulator readiness, functional flows and rotation, report verification | Full profiled x86-64 software-rendered CI app run: 32.7 minutes; all 260 pose audits retained |
| Runtime testbeds | Pinned CPython build, curated portable payload, actual Android/iOS smoke suite, exact source/report verification | Separate required runtime gates; host mocks and app builds do not replace them |
| Bridge | `go test ./...` in `mobile_build/rclone_bridge` | Native bridge's owning tests; separate from application UI |
| Release/package | Release-tooling regressions, source/submodule archive, gated publication | Failed, cancelled or required skipped prerequisites block packaging/publication |
| Optional investigation | Explicitly selected driver in `mobile_build/validation/` | Focused evidence only; not a substitute for native acceptance |

The native profiling run identified 23.0 minutes in the rotation matrix: 19.3
minutes waiting for orientation/layout acknowledgement and 2.6 minutes in the
existing fixed settling delay. Geometry audits took 0.272 seconds in total;
46 screenshots across the suite took 13.34 seconds. These are measurements from
one instrumented Android CI run, not guaranteed timings for other runners.
Repeated full matrices are not required for unchanged code merely to reassure
the operator. Reuse must identify the exact source, recursive submodules,
toolchain and suite configuration and remain explicitly labelled reused evidence.
Changing a revision invalidates a claim of fresh validation for the new revision.

The rotation panel/pose/cycle count and the LocalCrypt fixture above the former
32 MiB limit preserve specific regressions. Shorter waits require native readiness
proof; reducing those cases requires a concrete coverage rationale and agreement.
No coverage reduction is part of this test-organization change. Native section
timing and report commands are described in
[mobile alpha verification](mobile-alpha-verification.md#native-suite-section-timings).

Use synthetic data and disposable storage. Keep raw reports, snapshots and
runtime/build caches under ignored `test-results/` or `mobile_build/logs/`.
Personal profiles, credentials and signing inputs are not test inputs or artifacts.
