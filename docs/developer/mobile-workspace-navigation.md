# Mobile workspace drawers and paired documents

`workspace_navigation.py` owns feature-level layout inside the existing
commonUtils native tab and navigation stacks. The host retains native Back,
keyboard safe areas, immersive-reader chrome and independent window ownership.
It no longer installs the earlier Documents-only UISplitViewController. Settings
and Chat remain full-screen destinations; chat configuration is a full-screen
route in Chat.

`WorkspaceFrame` keeps each original editor/browser Box as its route view. Its
existing children move into a retained content Box, with a top-left hamburger
and a horizontal content area. Transfer banners retain their original registered
parent. Compact drawers replace only visible content, not session or folder
state. At 840 points/dp, the file browser and document each receive half the
actual content width. The same measured-window rule drives Chat's conversation
list and message area; it does not infer device type from a name.

The file drawer has independent browser state over the shared bounded browser
and ResourceSelection APIs. Its roots are local files and available LocalCrypt
copies. Remote connection/mapping operations stay in the existing folder hub.
Enumeration runs in a worker, rejects superseded folder/storage results, and
serializes scheduled refreshes. Opening files uses the existing provider-session
or library import path and preserves the destination where the user opened it.
It does not modify the Files tab's selected resource or reuse transfer cancellation
handles. Failed enumeration disables stale file opening.

In Documents, Split chooses another open editable text/Markdown session. The
current session becomes the left-hand pinned editor; the selected session is the
right-hand editor. Each widget has one native parent. Reparenting borrows the
existing owner rather than cloning its text, draft or callbacks. The hamburger
temporarily substitutes the file browser for the pinned editor. Narrowing keeps
the selected document and retains the other session. Closing a pinned session
clears its presentation; editor commands rebind to their actual owner and can
swap the active/pinned sides. Books and comics retain their existing reader
lifecycles and are not paired by this text-editor command.

Conversation selection uses stable conversation IDs, preserves unsent drafts,
and disables conversation switching during a request. Generation settings and
export commands remain available from Chat. No model request starts from
navigation. The conversation list represents the existing flat conversation
store; no new folder or branching persistence format is introduced.

Host coverage is in `Mobile/tests/test_workspace_navigation.py`, including
compact drawers, nested-file opening, independent drafts, two-document/browser
switches, collapse and close, and chat history/draft restoration. The native UI
review calls `workspace_checks.py` to exercise real phone/tablet content and
capture the file drawer, paired documents, conversation list, Chat and Settings.
Wide native checks assert that actual pane widths differ by at most two points.
Evidence must identify the staged source; a simulated width in a host test does
not establish native Duo fold-gesture support.
