# Archives development

## Try an extraction menu change

In desktop File Browser, right-click a disposable ZIP containing `notes.txt` and extract to a new folder in the library. Rename **Extract archive…** to **Extract entire archive…** in `Python/features/archives/__init__.py:register`. Keep the action ID and callback. Update the ZIP and CBZ menu assertions and run from the repo root after [desktop setup](../../../development/setup/getting-started.md).

```sh
python3 dev.py test desktop --exact-file Python/tests/archives/test_archive_browser.py
```

Expect the new label and TAR extraction with original bytes, one output refresh and one parent refresh. Failure or cancellation leaves sources and refresh state intact.

## Routing and lifecycle

Under `Python/features/archives/`, `ui/browser.py` owns scoped refresh and `ui/window.py` reuses documents by current admitted path. A failed open preserves that path. Browser closure and feature disablement leave retained documents usable. Comics owns CBZ double-clicks. Passive Archive Contents remains available with Archives disabled. ZIP/CBZ permit verified edits. TAR is read-only in the workspace.

`ui/session.py` serializes workers and queued credential retries. Close clears retries, requests cancellation and waits for idle. Suppress refresh after close begins. Use scoped fixtures that retire workers even on assertion failure. See [commonUtils archive operations](https://github.com/ispaure/commonUtils/blob/main/docs/development/reference/archives/archives.md) for shared staging and publication.

## Password policy and the two creation flows

`services.documents.zip_passwords` walks `remoteConfig.ini` to the nearest explicit `[LogisticsZIP]`. Missing or blank `archive_password` there stops inheritance. Defaults and interpolation are disabled. Verified interactive passwords stay in memory, including across replacement identities.

The source basket (`ui/create.py`) asks for a new confirmed AES password. **Create encrypted ZIP…** (`ui/create_zip.py`) resolves every source's configured password, refuses conflicts, and requires a confirmed fallback to match any configured password. Its dialog waits for worker cancellation. A published ZIP survives late cancellation.

See [desktop formats and controls](../user/user.md). Mobile reader password input serves Books and Comics. Test those adapters with their owners.
