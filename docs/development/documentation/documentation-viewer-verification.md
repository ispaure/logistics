# Documentation viewer checks

Start with the [documentation hierarchy](documentation-hierarchy.md#validation)
for page structure and link checks. When changing viewer entry points or layouts,
exercise the production desktop and mobile hosts as well.

## Desktop and mobile host tests

Run from the repository root:

```sh
python3 dev.py test desktop test_documentation_layout.py
python3 dev.py test desktop test_documentation_viewer.py --profile full
python3 dev.py test mobile 'test_documentation_*.py'
python3 dev.py test mobile test_packaged_startup.py --profile full
```

Desktop tests use real Qt widgets to check feature Settings, Help and File
Browser entry points. They check the selected article, the visible catalog and
history across scopes. Mobile host tests check the Settings entry, folder links,
page history, search, speech lifetime and compact/wide layouts. The full desktop viewer profile includes the extended feature and folder sweeps.
The full packaged-startup profile checks the staged payload and offline Help
history in an isolated process.

## Native layout

Mobile Help keeps Back/Forward and speech in the article command row. Android
also puts Actions there. Apple keeps Browse and Actions beside the title. The
command row follows the article when the tree moves between overlay and pinned
layouts.

Use `document_storage_tools ios --probe documentation-header` and the
corresponding `android` command for native Help. The iOS `--family all` option
covers iPhone, iPad and Duo poses. On Android, add `--android-tablet` for wide
layout. The probe opens Settings → Help, rotates the app, measures titles and
tree labels, and captures the article and browser. Review native layout and
interaction separately from host checks. See [local validation artifacts](../testing/validation-artifacts.md)
for disposable workspaces and evidence.
