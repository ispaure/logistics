# Develop Media Tools

Media Tools turns CSV chapter labels into proposed names for MKA audio
files. The dialog previews each rename before asking the shared rename
engine to apply the reviewed batch.

## Follow a chapter rename

**Debug → Rename MKA from CSV…** reaches
`Python/features/media/mka.py:_build_rename_plan` before the dialog permits
application. Use the synthetic chapter fixtures to verify successful byte
preservation and restoration of original names after a failed batch:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_mka_renames.py
```

`ui/dialogs.py:RenameMkaDialog` consumes the approved plan. `mka.plan_from_csv()` reads one top-level CSV, with chapter N at row N and a matching number in column A. The commonUtils rename engine enforces portable, unique and vacant destinations, rechecks sources, and rolls back failed or cancelled batches. Review again after failure. Keep any unresolved staged file and report both recovery paths.

See [desktop usage](../user/user.md), [mobile availability](../user_mobile/user_mobile.md) and the [Video Player compatibility link](video-player.md).
