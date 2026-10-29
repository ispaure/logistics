# Add and diagnose a Logistics test

Use this walkthrough after [setting up a checkout](getting-started.md). Commands
run from the Logistics repository root. Use `py` instead of `python3` on Windows.
You can complete the host-test loop without credentials, SDKs or a device.

## Choose an observable behavior

Start with the owning user guide and reproduce the problem with synthetic data.
Write down the input, action and expected observable result. For a regression,
include the failing input and a neighboring successful case. Assert a returned
value, saved/reopened content, visible state or lifecycle outcome that matters to
the caller. An assertion that a mocked helper was called is useful only when that
call itself is the boundary being tested.

Use `python3 dev.py owners` and the [code map](code-map.md) to find the owner;
`python3 dev.py test-owner images --dry-run` shows its current test selection.
Read a nearby test for import and fixture conventions, then confirm those helpers
still match the behavior you need. Existing tests provide examples, not authority
to preserve a bug.

| Information needed | Where to get it |
| --- | --- |
| Expected user behavior | Owning feature's user guide and a disposable reproduction |
| Policy, callbacks and state owners | Feature developer guide, registration factory and implementation |
| Existing coverage and filenames | `dev.py test-owner OWNER --dry-run`, `Scripts/ownership.json`, nearby tests |
| Selected host cases and classifications | `dev.py test desktop --inventory` or `dev.py test mobile --inventory`; source-wide `dev.py test-structure --inventory` |
| Test failure and duration | Printed report path under ignored `test-results/test-timings/`; inspect outcomes and `exit_code`, not just `complete` |
| GUI lifetime and asynchronous readiness | Shared Qt fixture guide linked from [testing](testing.md#correctness-checks-and-test-ownership), or mobile fixtures below |
| Native appearance, gestures or OS lifecycle | Owning native scenario and [mobile validation helpers](mobile-launchers.md#native-navigation-foundation-checks) |

Invent minimal public input instead of copying personal documents, credential
files or a real account response. Reusable fixtures stay with the narrowest test
owner; one-off screenshots, logs and reports stay in ignored evidence storage.

## Worked example: WebP header acceptance

This example uses the committed `features.images.validation.webp_dimensions`
entry point. It returns dimensions from a static WebP header and rejects another
image format. This tests header acceptance, not successful decoding of pixels.
Pillow is included by the desktop setup and creates public fixtures in memory.
If these cases already exist, extend those tests rather than retaining duplicate
coverage. To try a new file, create
`Python/tests/images/test_image_header_contributor.py` with:

```python
"""The WebP entry point accepts WebP dimensions and rejects PNG input."""
from io import BytesIO
import unittest

from PIL import Image
from commonUtils.testing.stages import TestStage
from features.images.validation import webp_dimensions

TEST_STAGE = TestStage.REGRESSION


def image_bytes(format):
    with BytesIO() as output, Image.new('RGB', (2, 3)) as image:
        image.save(output, format=format)
        return output.getvalue()


class WebPHeaderTests(unittest.TestCase):
    def test_static_webp_keeps_width_and_height(self):
        self.assertEqual(webp_dimensions(image_bytes('WEBP')), (2, 3))

    def test_png_is_rejected_by_the_webp_entry_point(self):
        with self.assertRaises(ValueError):
            webp_dimensions(image_bytes('PNG'))
```

Run the test, validate classification, then check the affected owner and lint:

```sh
python3 dev.py test desktop test_image_header_contributor.py --dry-run
python3 dev.py test desktop test_image_header_contributor.py
python3 dev.py test-structure
python3 dev.py test-owner images --dry-run
python3 dev.py lint
```

The focused test should discover two passing cases and print its timing-report
path. As a learning check, temporarily change the expected dimensions to `(99, 3)`:
the same command must fail and identify that case. Restore `(2, 3)` and rerun.
This proves the assertion is reached. For a real bug fix, also establish that the new regression
test fails against the original behavior and passes with the fix.

Use an ordinary `unittest.TestCase` for portable behavior. Desktop GUI tests use
the shared `QtTestCase`, its `temporary_directory()` and condition-based
`wait_until()` so workers, windows and watchers retire before temporary storage.
Do not copy ad hoc application/loop teardown from older tests.

Mobile host tests belong under `mobile_build/tests/<owner>/` and run with
`dev.py test mobile FILENAME`. Synchronous app tests use
`mobile_build.tests.support.app.mobile_app()` as a context, or `create_app(self)`
for unittest cleanup ownership. Reuse `support/readers.py`, `pdf.py`, `mirror.py`
and `localcrypt.py` where applicable; inspect their arguments before use. These
fixtures run Toga dummy and do not certify native controls. Async tests need a
lifecycle appropriate to their running loop; the synchronous app fixture rejects
an already-running loop.

## Decide which files to update

A normal `test_*.py` file under an existing recursive root needs its stage
declaration and test code. It does not need a new manager suite for each file.
New nested unittest test folders need package initializers (`__init__.py`) for
recursive discovery; keep those initializers free of setup side effects.

| Change | Update when applicable | Check |
| --- | --- | --- |
| Test inside an existing root | Test source, narrow fixtures; owner selection if its patterns omit the new name | Focused run, inventory and `test-owner OWNER --dry-run` |
| New classified root or filename family | `test-structure.json`; the actual runner's discovery/routing too | `dev.py test-structure` and an actual focused run |
| Owner association | `Scripts/ownership.json` | `dev.py owners`, `dev.py test-owner OWNER --dry-run` |
| Execution suite or prerequisite | `build-tests.json`, plus owning adapter/plan integration | Inspect selected phase commands and dependency gates |
| Selectable manager suite | `build-project.json` → `test_suites`, routing in `logistics_build/manager_suites.py` and the adapter | Applicable selection works; unknown/inapplicable selection fails |
| New mobile application module | Owning `mobile_sources.json` | `dev.py test desktop test_mobile_packaging.py` |
| Native scenario | Owning driver, exact case inventory, fixtures and report verification | Native acceptance on the affected platform |
| Test environment/version policy | `test-environments.json`; dependency pins stay in their existing owners | Environment contracts and fresh affected acceptance |

Classification, execution selection and UI selection are separate contracts.
Passing `test-structure` checks labels; it does not establish that the selected
runner executed a file. Manager file previews come from `Phase.test_files`, actual
case results from declared JUnit artifacts, and live progress from the runner's
optional structured events. See [manager integration](build-manager.md#guided-manager-suites-and-tester-acceptance).

## Extend native coverage deliberately

For an app-native scenario, trace
`mobile_build/native_tests/tests/logisticsmobile/__main__.py` and the scenario it
calls. Add the action and meaningful assertions in the owning scenario module.
If adding a new top-level case, update `CASES` in that package's `__init__.py` and
the ordered successful-case reporting in `__main__.py` together. Whole journeys
retain their ordered state and classification; host profile selection does not
turn them into independent unit tests.

Runtime smoke cases have a separate contract: `Python/mobile/smoke.py` owns
`EXPECTED_TESTS` and checks discovered methods against it. Native UI and runtime
evidence are verified by `logistics_build/manager_suites.py`; an extra file or a
successful build alone does not add verified coverage. Use the owning payload
and validation helpers rather than editing generated build copies.

Select the affected native validation in the manager and inspect the prepared
source, platform, case inventory, reports and cleanup. For targeted investigations,
use the [build tooling map](build-tooling.md) and existing validation drivers.
Record device/runtime identity and retain screenshots/logs before owned cleanup.
A screenshot helps diagnose layout; assertions must also establish the intended
content, route or persistence outcome. Use
`logistics_build.build_retention.scratch()` for one-off probes and save needed
evidence outside its disposable workspace before it exits.

After testing on the user's Boox, remove temporary Logistics test/probe/QA apps
and verify that only `io.github.ispaure.logisticsmobile` remains among Logistics
packages. Preserve that main app and its data. Report any cleanup that could not
finish. See [storage lifecycle and native setup](mobile-handbook.md).

## Diagnose a missing or failing test

| Symptom | Next check |
| --- | --- |
| No matching files | Filename/glob, suite root and quoted shell wildcard; compare the inventory |
| Test exists but owner shortcut omits it | `Scripts/ownership.json` patterns and dry-run output |
| Classification preflight fails | File/line diagnostic, one valid default, overrides and declared root patterns |
| File is listed but no cases execute | `unittest` discovery, `TestCase` inheritance, method names and selected stage |
| Suite is absent from manager selection | Descriptor metadata, platform/operation applicability and adapter support |
| Phase runs but case details are absent | Declared JUnit artifact path/type and actual nonempty report, not console text |
| Test passes alone but fails in a group | Leaked windows, tasks, environment, patches or fixture state; preserve isolation |
| Native behavior remains unverified | Run the actual affected native scenario; a dummy/offscreen pass is narrower evidence |

Before handing over a change, state the behavior protected, selected checks and
results, report location and any unverified platform scope. Update the owning
guide, review the diff and exclude generated/private evidence. For a practice-only
file, remove it after the walkthrough; keep real regression coverage with its owner.

[Developer index](development.md) · [Testing reference](testing.md)
