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
