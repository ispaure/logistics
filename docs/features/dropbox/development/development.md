# Developing Dropbox folder tools

## Try a change to conflict cleanup

On desktop, open **Workspaces → Local → Source → Dropbox → Conflicting Copies…** for a managed folder. In `Python/features/dropbox/conflicts.py:_require_reviewed_identity`, include the changed path in the stale-review error. Run from the checkout root. Expect replaced or edited pairs to survive and unchanged identical copies to be removable.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_dropbox.py
```

`detection.py` discovers account roots from desktop Dropbox's `info.json`; `ui_contributions.py` supplies contained folder actions. Review skips links and compares SHA-256. Apply rechecks both identities and deletes directly without Trash or Undo. A writer can still race the final check. Re-review failures before retrying; Dropbox owns recovery. [Desktop setup](../user/user.md)
