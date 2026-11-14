# Rename a batch of files

Open **Bulk Rename** from the navigation rail or a File Browser selection. Rules
carry over when you open another selection.

## Using the window

1. Choose a folder and filename wildcard or Python regex. Use **Scope…** for
   folders, hidden entries and subfolders, then **Apply filter**. Depth 0 scans
   all levels without following directory symlinks.
2. Select the rows to rename. They start selected. Numbering follows natural
   path order (`page2` before `page10`).
3. Set rules and review **Preview**. **Rule presets…** saves or loads JSON.
   **Rules** hides the controls while keeping them active.

Rules run in this order: regex, stem, replace, case, remove, move/copy characters,
add text, date, parent folder, numbering, extension. Regex replacements accept
`\1` or `\g<name>`. Positions are zero-based Unicode character offsets. The
final extension is protected until the Extension step unless regex includes it.
Creation dates require filesystem support. Date rules affect the name.

## Applying, cancelling and undo

Fix preview errors before **Rename selected**. Select either a folder or its
descendants in a batch. Names must be portable, and duplicate, occupied, or
case/Unicode-equivalent destinations can block the batch. Logistics rechecks
sources and stages renames beside their originals to support swaps and case
changes without overwriting files.

Cancellation or failure rolls back the batch. If rollback is blocked or the
app crashes, keep any `.bulk-rename-*` entries and use the reported staged
and original paths for manual recovery when available. Cancellation checks
between items and can wait for a regex match.

**Undo last rename** uses the receipt in this window, until it closes. Undo
refuses when renamed items changed or an original name is occupied. Preview
again before the next batch.

[Application guide](../../../user/user.md)

## Platform availability

See [mobile availability](../user_mobile/user_mobile.md) for Android and iOS.
