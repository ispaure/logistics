# Archives development

Archives adds extraction and creation actions to File Browser and opens
archives in a retained inspection workspace. The feature owns the desktop
dialogs, refresh and credential prompts. The archive operations themselves
come from commonUtils.

## Trace an extraction

In File Browser, right-click a disposable ZIP containing `notes.txt` and extract
it into a new folder. `Python/features/archives/__init__.py:register` declares the
action and callback. The browser test follows that route through extraction and
checks preserved source bytes, successful refreshes, and failure/cancellation.
Run from the checkout root after [desktop setup](../../../development/setup/setup.md):

```sh
python3 dev.py test desktop --exact-file Python/tests/archives/test_archive_browser.py
```

## Routing and lifecycle

Under `Python/features/archives/`, `ui/browser.py` owns scoped refresh and `ui/window.py` reuses documents by current admitted path. A failed open preserves that path. Browser closure and feature disablement leave retained documents usable. Comics owns CBZ double-clicks. Passive Archive Contents remains available with Archives disabled. ZIP/CBZ permit verified edits. TAR is read-only in the workspace.

`ui/session.py` serializes workers and queued credential retries. Close clears retries, requests cancellation and waits for idle. Suppress refresh after close begins. Use scoped fixtures that retire workers even on assertion failure. See [commonUtils archive operations](https://github.com/ispaure/commonUtils/blob/main/docs/development/reference/archives/archives.md) for shared staging and publication.

## Password policy and the two creation flows

`services.documents.zip_passwords` walks `remoteConfig.ini` to the nearest explicit `[LogisticsZIP]`. Missing or blank `archive_password` there stops inheritance. Defaults and interpolation are disabled. Verified interactive passwords stay in memory, including across replacement identities.

The source basket (`ui/create.py`) asks for a new confirmed AES password. **Create encrypted ZIP…** (`ui/create_zip.py`) resolves every source's configured password, refuses conflicts, and requires a confirmed fallback to match any configured password. Its dialog waits for worker cancellation. A published ZIP survives late cancellation.

See [desktop formats and controls](../user/user.md). Mobile reader password input serves Books and Comics. Test those adapters with their owners.
