# Reader history and saved positions

Open **Settings → Reader history** on desktop, or **Settings → App** on mobile.
Two separate actions apply across readers and sources, including credentials that
are currently locked or unloaded:

- **Clear all saved positions** resets saved reading/video locations. Documents,
  bookmarks and Recent are kept. Reopen an already-open reader before it saves new
  positions; closing it cannot put its erased old position back.
- **Clear all recent files** removes recent-file lists. Saved positions and files
  are kept. Old encrypted caches also contain private reopen references, so unloaded
  reopen references are removed as part of clearing those caches. Open documents
  stay open.

Session-only remotes, whether crypt or ordinary, and session-only LocalCrypt save
private positions and bookmarks under the owning credential ZIP password. Titles
and paths in session-only Recent use that password too. Passwordless sessions keep
reader state only in memory.

After changing a credential ZIP password, unlock the updated ZIP and choose
**Migrate protected reader history…**. Enter the previous password. Matching saved
positions, bookmarks and Recent can then be encrypted under the updated password.
Reopen readers afterward to restore them. Wrong passwords or unmatched accounts
leave the old encrypted files intact; they are not silently replaced with empty
history. Without the previous password, use the separate clear actions to discard
unavailable history.

Older LocalCrypt video positions are migrated or retired when that source is next
unlocked. Clearing positions while it is locked prevents those old positions from
returning; cleanup of the old encrypted sidecar happens on next access. These
controls clear application history, not filesystem backups or external snapshots.
