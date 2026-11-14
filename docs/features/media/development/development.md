# Develop Media Tools

Media Tools renames Matroska Audio (`.mka`) chapter files using titles in a CSV.
Playback is owned by the [Video Player feature](../../video/development/development.md).
See the [Media Tools user guide](../user/user.md) for the desktop workflow.

## Try a chapter filename change

On desktop, enable **Media Tools** in **Settings → Features**. In a disposable
folder, create an empty `Chapter_01.mka` and a `names.csv` containing
`1,Introduction` on its first line. Open **Debug → Rename MKA from CSV…**, select
the folder and click **Review names**. Expect `1 - Introduction.mka` in the
destination column. The tool works with an empty fixture because it only reads
filenames and CSV rows.

For a small experiment, use an underscore separator so the review shows
`1_Introduction.mka`. Change the destination format in `_build_rename_plan`
in `Python/features/media/mka.py`, then relaunch and review again. Apply the
reviewed names to check the result. In the test file below, adjust the expected
destination names, failure-injection target and progress text together so the
rollback case still exercises failure on the second move. Run from the
repository root with the desktop environment installed.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_mka_renames.py
```

Expect the new names and unchanged file bytes on success. The failure case
should restore both source names and bytes. This check uses placeholder files and exercises renaming without
opening an audio decoder. The dialog tests check progress,
fresh review after a failed apply, cancellation and unresolved recovery paths.

## MKA Chapter Rename

`Python/features/media/ui_contributions.py` registers the Debug action and
lazily opens `ui/dialogs.py` (`RenameMkaDialog`). **Review names** calls
`mka.plan_from_csv()`; the planner scans only the target folder's top level.
It requires exactly one CSV and names with a `Chapter_` prefix and positive
chapter number. Chapter N uses CSV row N, starting at one with no header.
Column A must agree with the file's chapter number. The planner removes
double quotes and trims the title in column B and requires a nonempty result.

The shared `commonUtils.filesystem.rename` engine validates the complete batch
through `plan_named_renames()`. Destinations must be portable, stay in their
source folder and be unique across case and Unicode equivalents. An occupied
destination prevents the batch from starting.

The dialog consumes the approved plan when applying it. `apply_renames()`
rechecks source stamps and destinations, stages the batch, then publishes the
renames. Cancellation is checked between atomic moves. Publication failure or
cancellation triggers a rollback attempt and requires a fresh review. If
rollback cannot restore a file, keep the staged file and use the reported
staged and original paths to recover it.

## Platform boundary and validation

The MKA workflow runs in desktop Qt. See the
[mobile boundary](../user_mobile/user_mobile.md) for supported mobile workflows.
The [Video Player compatibility link](video-player.md) points to the playback owner's
requirements.
