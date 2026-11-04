# Documentation viewer verification

Validated October 16, 2026 against the local working tree. This is a documentation
navigation check; it does not certify other application workflows.

## Desktop

`Python/tests/tooling/test_documentation_viewer.py` uses real Qt widgets and windows.
All four integration tests pass with both offscreen Qt and the native macOS Cocoa
backend. They exercise all 25 installed feature User Guide buttons, including
when disabled; every Help / Guides menu entry; File Browser help; and Bulk Rename
help. Each check verifies both the selected article and the complete scoped
catalog, rather than only the requested filename.

Every documentation folder in the 27 application/feature/Bulk Rename scopes is
selected through its actual tree item. Its same-named landing opens, Up opens the
parent landing, and Back restores the article. Cross-scope links and history
switch the tree between Logistics and Git and preserve selection. Desktop window
captures were visually reviewed for Git and systemic Logistics help.

Run from the repository root:

```sh
PYTHONPATH=Python:. QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest \
  tests.tooling.test_documentation_layout tests.application.test_settings_page \
  tests.tooling.test_documentation_viewer \
  commonUtils.tests.markdown.test_wiki_catalog commonUtils.tests.markdown.test_markdown_wiki -q
```

Use `QT_QPA_PLATFORM=cocoa` to exercise the four viewer integration tests on macOS.
The layout checks include H1s, parent-child mentions, compatibility links, local
assets, heading targets and separate repository boundaries.

## Mobile host and packaged payload

The 14 documentation, packaged-startup and shared native-Markdown tests pass on
the dummy mobile backend. They cover the actual Settings documentation handler,
phone/tablet presentation, title widths, folder rows, heading navigation, search,
cross-wiki history and the staged payload without checkout packages on its import
path. Packaged feature links resolve within the bundled documentation mirror.

```sh
PYTHONPATH=Python:. TOGA_BACKEND=toga_dummy \
  mobile_build/.venv/bin/python -m unittest mobile_build.tests.documents.test_documentation_ui \
  mobile_build.tests.tooling.test_packaged_startup \
  commonUtils.tests.native.test_native_markdown -q
```

## Native simulator evidence and limits

`mobile_build/native_tests/tests/logisticsmobile/documentation_probe.py` provides a
full-app probe and an independent native documentation host. Run `main()` in an
isolated simulator test bundle for the full application, or `standalone_main()`
to isolate the documentation viewer from unrelated startup failures. Each uses
a separate app identity and disposable storage. Results and screenshots are
written to the test app's cache under `documentation-evidence/`.

The independent host passed five cases on both an iPhone simulator (402 logical
units, browse/article switching) and an iPad simulator (834 logical units, pinned
tree and article): opening the mobile guide, rendering the expected H1 in the
native WebView, selecting Workspaces's folder landing and Up, clicking an actual
rendered link into the Chat wiki, and restoring scopes through Back/Forward.
The linked article is revealed in its expanded tree. Native screenshots were
visually reviewed. This host calls the production `show_documentation` entry
but supplies a minimal launch button; the real Settings screen is covered by
the mobile host test above.

The first iPhone screenshot exposed excessive title truncation: hidden scroll
content retained its minimum width. The shared viewer now binds tree content to
the allocated browse/sidebar width. Native title-button frames measured 330
logical units on iPhone and 212 on iPad after the fix. Selecting an article also
expands its ancestors so the current page remains visible after links/history.

The full-app native run was blocked before Settings by a `CodeInput` style
initialization failure in the ongoing mobile-editor work. That failure was
reported to its owning chat. A native end-to-end Settings check remains pending;
the independent viewer success must not be interpreted as a full-app startup pass.
Android device/emulator and physical iOS device behavior were not validated in
this pass.

The October 16 full-app limitation above retains its original snapshot scope.
Later full-app simulator and portable-catalog evidence is recorded in the
[maintenance assessment](maintenance/history/architecture-audit.md#current-assessment-after-the-october-23-maintenance-pass).

## November 3 title and command rows

The Logistics Help host keeps page Back/Forward and speech in a content command
row. Android places its actions menu there as well, leaving native Close/Browse
and the title above it. Apple uses the existing document-title row with Browse
and Actions at its edges; history and speech stay below. Both rows follow the
article pane when the documentation tree becomes pinned, including after a
resize back to a phone layout. Desktop retains its existing wiki layout.

The focused Help host suite covers Settings entry, page history, folder links,
search, speech lifetime, and allocations from 320 through 1400 logical units.
`documentation_header_probe.py`, selected with
`document_storage_tools --probe documentation-header`, opens Settings → Help on
an isolated native QA app, rotates between portrait and landscape, measures title
and tree-label widths, and saves article/tree screenshots before owned cleanup.
The `--family all` option covers iPhone, iPad and closed/open/partial iPhone Duo;
Android phone and `--android-tablet` runs use disposable emulators.

The November 3 native Help matrix passed three orientation samples each on
an iPhone, iPad, and closed/open/partial iPhone Duo. App-window article and tree
captures were visually reviewed. The title measured 246/322 points in iPhone
portrait/landscape, 604/668 on iPad, 226/438 on closed Duo and 513/439 on
open/partial Duo. The partial Duo's final whole-display capture was black;
its app-window captures and native geometry checks succeeded. These are
simulator layout checks, not physical-device or full-app release certification.

The November 4 Android native matrix passed three orientation samples each on
Android 15 disposable phone and tablet emulators (360-dp and 800-dp portrait
viewports). The full app opened Settings → Help and rendered its article before
capturing the article/tree layouts. Native Help titles measured 232/672 dp on the
phone and 640/969.5 dp on the tablet in portrait/landscape; tree labels retained
at least 164 dp. Screenshots were visually reviewed, including pinned tablet
browsing. This completes the earlier Android startup/visual acceptance gap.

`document_storage_tools android --probe android-header` also checks Notes toolbar
order, actual title gutters, history/edit/menu taps, unabridged breadcrumb labels,
and native swipes/taps back to the library root and ancestor landing pages. Add
`--android-tablet` for the tablet allocation. Notes titles measured 184/624 dp on
the phone and 592/921.5 dp on the tablet. All six orientation samples passed;
the tablet pinned Files in landscape and returned to compact Files in portrait.
The native checks exposed Android button insets clipping breadcrumb labels;
those insets and the measured/drawn typeface now agree. The runners removed their
QA packages and disposable devices, and the owned scratch build was deleted.

Notes toolbar/breadcrumb checks, the desktop folder-navigation/scroll check,
17 Help host tests and 16 shared/native-bar host tests pass. A broader 33-case
Notes host run has two failures in video embed/media retirement, outside this
layout change, and one skipped test. It is not a passing full Notes suite.
