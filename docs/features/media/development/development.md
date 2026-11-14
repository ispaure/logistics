# Develop Media Tools

## Try a chapter filename change

In desktop **Debug → Rename MKA from CSV…**, review a disposable folder with empty `Chapter_01.mka` and one CSV row, `1,Introduction`. Change `Python/features/media/mka.py:_build_rename_plan` to propose `1_Introduction.mka`. Update expected names, progress and the second-move failure target. Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_mka_renames.py
```

Expect unchanged bytes under the new name on success and original names and bytes after rollback.

`ui/dialogs.py:RenameMkaDialog` consumes the approved plan. `mka.plan_from_csv()` reads one top-level CSV, with chapter N at row N and a matching number in column A. The commonUtils rename engine enforces portable, unique and vacant destinations, rechecks sources, and rolls back failed or cancelled batches. Review again after failure. Keep any unresolved staged file and report both recovery paths.

See [desktop usage](../user/user.md), [mobile availability](../user_mobile/user_mobile.md) and the [Video Player compatibility link](video-player.md).
