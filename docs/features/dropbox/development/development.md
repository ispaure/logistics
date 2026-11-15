# Developing Dropbox folder tools

Dropbox integration discovers folders managed by the desktop Dropbox client.
In a folder review, Logistics identifies conflict copies with identical
contents. It checks that the reviewed pair still matches before deleting
the copy.

## Follow a cleanup review

The **Conflicting Copies…** action in Workspaces reaches
`Python/features/dropbox/conflicts.py`. `_require_reviewed_identity` checks that
apply still refers to the reviewed pair. The synthetic fixtures verify that
replaced or edited files survive while unchanged identical copies are eligible:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_dropbox.py
```

`detection.py` discovers account roots from desktop Dropbox's `info.json`; `ui_contributions.py` supplies contained folder actions. Review skips links and compares SHA-256. Apply rechecks both identities and deletes directly without Trash or Undo. A writer can still race the final check. Re-review failures before retrying; Dropbox owns recovery. [Desktop setup](../user/user.md)
