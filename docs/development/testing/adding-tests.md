# Add and diagnose a Logistics test

Run from the checkout root with [host setup](testing.md#run-everyday-checks). Use `py`
for `python3` on Windows.

## Choose an observable behavior

Reproduce with synthetic input. Assert a visible state, saved/reopened content or
lifecycle outcome. Pair the failing input with a nearby success. Use
`python3 dev.py owners` and `python3 dev.py test-owner images --dry-run` to locate
a fixture and suite. Check selected cases with `dev.py test desktop --inventory`
or `dev.py test mobile --inventory`.

## Worked example: WebP header acceptance

Create `Python/tests/images/test_image_header_contributor.py` to check static WebP
dimensions and reject PNG at the Images validation boundary.

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

Expect two passes. Temporarily expect `(99, 3)` to verify the dimensions case
fails, then restore `(2, 3)`. Remove practice-only tests and extend existing
coverage where available.

For GUI cleanup use [QtTestCase](testing.md#correctness-checks-and-test-ownership).
Synchronous Toga tests use `mobile_build/tests/support/app.py`'s `mobile_app()`
context or `create_app(self)`. Keep storage alive until window and loop cleanup.
Use the context inside a temporary-directory context so the app retires first.
For explicit loop ownership, use `commonUtils.testing.event_loop.close_loop()`
to drain executor work before removing files. Failed fixture cleanup retains
its root under `test-results/mobile-fixtures/`. Reuse the support folder's
document/backend fixtures. Wait for bounded observable
milestones and preserve cancellation, dismissal and retirement assertions.

## Decide which files to update

| Change | Owner and check |
| --- | --- |
| Test in an existing root | Declare its stage and run it. Add a side-effect-free `__init__.py` for new recursive unittest packages. |
| Classified root or pattern | `test-structure.json` and runner discovery. Run structure plus execution. |
| Owner selection | `Scripts/ownership.json`. Preview with `dev.py test-owner OWNER --dry-run`. |
| Suite or prerequisite | `build-tests.json` and owning workflow plan. Inspect phase commands and gates. |
| Manager-selectable suite | `build-project.json` → `test_suites` and `logistics_build/manager_suites.py`. Verify applicable routing. |
| Environment policy | `test-environments.json`. Check the affected environment and acceptance. |
| Mobile source | Owning `mobile_sources.json`. Run `dev.py test desktop test_mobile_packaging.py`. |

## Extend native coverage deliberately

Update the owning native scenario and, for a new top-level case, the package's
`CASES` and ordered reporting in `__main__.py`. For rotation, add a stable ID,
setup and route to the [rotation inventory](testing.md#shared-native-rotation-inventory).
For embedded runtime smoke, update `EXPECTED_TESTS` in `Python/mobile/smoke.py`.
Manager checks both report contracts in `logistics_build/manager_suites.py`.
Run the affected [native journey](../build-release/mobile-handbook.md). Record device
and source identity and save evidence before cleanup. On Boox, remove temporary
Logistics apps, verify only `io.github.ispaure.logisticsmobile` remains, preserve
its data and report any leftovers.

## Diagnose a missing or failing test

| Symptom | Check |
| --- | --- |
| Missing file | Suite, quoted glob or [exact path](testing.md#run-everyday-checks), then owner patterns |
| Missing cases | Stage and unittest discovery. Read the structure diagnostic for invalid declarations. |
| Missing Manager suite or cases | Platform/applicability and declared JUnit artifact, respectively |
| Group-only failure | Windows, tasks, patches and fixture retirement before storage deletion |
| Device behavior in question | Affected native scenario and report |

Report the behavior covered, checks and platform scope. Keep raw reports in
[ignored storage](validation-artifacts.md).
