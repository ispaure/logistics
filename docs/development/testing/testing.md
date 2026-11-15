# Testing Logistics

Start with the behavior you changed, run its focused checks, then widen the
scope when the change crosses an owner or platform boundary. A desktop or mobile
host test gives quick feedback in a local environment; native appearance,
gestures and OS lifecycle need device or simulator validation as well.

Run commands from the checkout root. On Windows use `py` instead of `python3`.

## Run everyday checks

Prepare the [desktop environment](../setup/setup.md) first. `python3 dev.py doctor`
reports missing dependencies without modifying environments. If your change
also needs mobile host tests, run `python3 dev.py setup mobile`; this prepares
its separate environment without requiring a mobile SDK.

For example, after changing feature enablement:

```sh
python3 dev.py test desktop test_feature_registry.py --dry-run
python3 dev.py test desktop test_feature_registry.py
```

The first command shows the interpreter and selection. The second runs the
selected test file in isolation. Read the reported failures and skips as well as
the exit status. A passing host check does not establish native device behavior.

Other common selections are:

```sh
python3 dev.py test desktop 'test_git_*.py'
python3 dev.py test mobile test_editor_picker.py
python3 dev.py test desktop --exact-file Python/tests/tooling/test_regression_runner.py
```

Quote globs. Use a repository-relative `--exact-file` path when filenames are
ambiguous; repeat it for multiple files. Omit the filename to select the whole
suite. See [selection and environments](runner-reference.md#selection-and-environments)
for overrides and selection rules.

## Find the tests for your change

Feature Development guides explain the behavior and focused checks owned by
that feature. Use [the feature catalog](../../features/features.md) to find one,
or list the project owner associations:

```sh
python3 dev.py owners
python3 dev.py test-owner images --dry-run
```

Replace `images` with your owner ID. Removing `--dry-run` runs its deduplicated
selections across the required environments. `Scripts/ownership.json` owns these
associations. For example, an image compression change can start with
`Python/tests/images/test_image_folder_tool.py`, then use the Images owner
selection to check related behavior.

| What changed | Additional check |
| --- | --- |
| A wiki page or link | [Documentation checks](../documentation/documentation-viewer-verification.md) |
| An owning `mobile_sources.json` | `python3 dev.py test desktop test_mobile_packaging.py` |
| Imports or owner boundaries | `python3 dev.py architecture` and the [portable import matrix](runner-reference.md#portable-import-matrix) |
| A test declaration or discovery root | `python3 dev.py test-structure` |
| Native controls, gestures or OS behavior | The owning feature's native journey and [mobile handbook](../build-release/mobile-handbook.md) |

When behavior lacks coverage, follow [Add and diagnose a test](adding-tests.md)
for a small worked example, fixture cleanup and ownership rules.

## Execution stages and failure policy

Profiles choose how much of the selected tests to run:

| Profile | Coverage |
| --- | --- |
| `smoke` | Deterministic startup and core contracts |
| `daily` | Smoke plus ordinary regression behavior |
| `full` (default) | Daily plus extended matrices, parity and soak checks |

```sh
python3 dev.py test desktop --profile smoke --mode fast
python3 dev.py test-owner document-services --profile daily
```

The default diagnostic mode continues independent checks after a failure. Fast
mode gates later stages on earlier results; `--fail-fast` also stops at the first
failure inside a file. A narrower profile is useful feedback, but it leaves the
unselected coverage untested. Use [the runner reference](runner-reference.md)
for stage declarations, process isolation, reports and parallel execution.

## Correctness checks and test ownership

Run `python3 dev.py lint` for correctness lint. Review unused-import suggestions
with the owner before removing re-exports, registrations or lifetime handles.
For Qt tests, use `QtTestCase`, `temporary_directory()` and bounded `wait_until()`
to retire workers and windows before deleting storage. The
[shared fixture guide](../../../Python/commonUtils/docs/development/reference/tests/tests.md)
owns commonUtils APIs; [adding tests](adding-tests.md) explains Logistics fixtures.

Keep credentials, environments and generated output local. Use
[validation artifacts](validation-artifacts.md) to locate reports and understand
cleanup. After staging specific paths, `python3 dev.py hygiene` checks the index
for ignored files and recognizable secrets.

## Broader validation

Choose these guides when your change needs evidence beyond a focused host test:

- [Test runner reference](runner-reference.md) — environments, shared suites,
  scheduling, reports and CI gates.
- [Platform checks](platform-checks.md) — cross-platform archive and desktop
  validation, including hosted diagnostics.
- [Mobile performance](mobile-performance.md) — profiling and performance work.
- [Validation artifacts](validation-artifacts.md) — owned storage, report
  locations and cleanup.
- [Build and release](../build-release/build-release.md) — managed platform
  plans, installable apps and release gates.
