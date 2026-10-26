# Logistics on mobile

Open **Settings → Help → Mobile documentation** for offline guides with
folder navigation and built-in file/title or page-text search. A hamburger toggles browsing
in narrow windows; wider windows show the tree and article together.

- [Getting started](getting_started/getting_started.md)
- [reMarkable notebooks](../features/notebooks/user_mobile/user_mobile.md)
- [Documents and readers](documents/documents.md)
- [Remote and offline files](documents/remote.md)
- [Using documentation](documentation/documentation.md)

Mobile action buttons use the file browser’s filled surfaces: near-white in light
mode and the same raised dark surface in dark mode. Ordinary actions have no
outline. Contents and documentation share indented rows, disclosure chevrons and
a highlighted current item.

Password and token fields start hidden. Use the eye button beside a field to
show or hide its value. Clearing the field hides it again.

## Installing Android test builds

Invited Android testers can accept a Firebase App Distribution invitation using
their Google account, download the APK and permit installation from that source
when Android asks. New build notifications lead to updates that you approve on
the device. Keep the existing beta installation to retain its data. A separately
debug-signed developer build has a different signing identity and cannot be
replaced by the beta in place. See the
[distribution launcher guide](../development/mobile-launchers.md#double-click-android-firebase-distribution).

## Direct remote reading

Open a remote from Workspaces or Remote files. Tap a supported file to open a
read-only, memory-only reader: small text/Markdown/INI, PNG/JPEG/WebP, EPUB and
CBZ/ZIP comics. Search filters the current folder only. Unsupported files and
content beyond the reader limits show a dialog asking you to manually make a
local copy; opening a file never automatically creates one.

Remote browsers have no standalone file or folder download actions, including
encrypted downloads. Use Workspaces's managed Pull workflows for offline Local
or LocalCrypt folders. Existing offline copies remain readable and exportable.
Direct readers show no Save, Save As or metadata-edit controls. Locking or replacing credentials
retires their contents, including readers opened with session-only credentials.
See the [rclone guide](../features/rclone/user/user.md#browse-remote-files-directly)
for limits and desktop behavior.

## Android appearance and E Ink status

See [Mobile settings](settings/settings.md#appearance-and-e-ink-status).

## Settings and build information

See [Mobile settings](settings/settings.md#settings-and-build-information).

## Current feature support

Android and iOS have the same prototype scope. “Implemented” describes code in
the native app; real-device interaction testing is still required.

| Logistics capability | Mobile status |
| --- | --- |
| Plain-text editing | Implemented: create in a chosen writable folder, reopen, edit and save; existing legacy saved documents remain available |
| reMarkable notebooks | Implemented: create/open `.rmdoc`, draw, manage pages/layers, Save/Save As and export in Local or unlocked LocalCrypt; cloud previews remain read-only |
| Workspaces and navigation | Native Home, Workspaces, Documents, Chat and Settings destinations; retained screen per destination |
| Markdown | Text editing and offline preview: tables, headings, nested lists, quotes, emphasis and code |
| Document import | Native picker adapters implemented; actual provider permissions still need device testing |
| Draft recovery | Implemented: checkpoints, restored drafts and conflict-safe save-a-copy |
| Encoding and line endings | Implemented for UTF-8 and recognized Unicode BOMs, with a 1 MiB text limit |
| EPUB and comics | Private library, EPUB chapter navigation and PNG/JPEG/WebP CBZ/ZIP pages, saved progress and bookmarks |
| Preferences / INI settings | Private INI with font size and last-document restore controls; no desktop preference migration |
| Export | Export a copy through the platform destination picker |
| Receive files from other apps | iOS share extension and Android share target copy attachments into Received Files |
| Save back to another app's original attachment | Not implemented; folder-backed files opened within Logistics save to their selected file |
| File browser | Shared native list/tile views, thumbnails and file information for app-managed Local/LocalCrypt files and remote browsing |
| Bulk rename, IDE and Git/Perforce UI | Not ported |
| LM chat | Native text conversations, configured server/model, streaming/cancel, private history and Markdown export |
| rclone remote files | Credential ZIP import, direct remote previews, existing offline copies/export, LocalCrypt encrypted offline reading/editing, local folder management and Save As; encrypted saved or session-only credentials |
| Media/image tools, archives and other desktop integrations | Not ported |

## Preferences and storage

See [Mobile settings](settings/settings.md#preferences-and-storage).

## Home and document search

See [Mobile navigation](navigation/navigation.md#home-and-document-search).

## File and conversation drawers

See [Mobile navigation](navigation/navigation.md#file-and-conversation-drawers).

## Document workflow

See [Document workflows](documents/workflows.md#document-workflow).

## Books and comics

See [Books and comics on mobile](../features/books/user_mobile/library.md#books-and-comics).

## LM chat

See [Chat on mobile](../features/lm/user_mobile/conversations.md#lm-chat).

## Remote files and credential ZIPs

See [Remote connections on mobile](../features/rclone/user_mobile/connections.md#remote-files-and-credential-zips).

## LocalCrypt encrypted offline reading

See [LocalCrypt on mobile](../features/rclone/user_mobile/localcrypt.md#localcrypt-encrypted-offline-reading).

## File browser locations and actions

See [Workspaces on mobile](folder_hub/folder_hub.md#file-browser-locations-and-actions).

## Reading and editing

See [Reading and editing on mobile](documents/reading-and-editing.md#reading-and-editing).

## Using iPad windows

See [iPad windows](navigation/windows.md#using-ipad-windows).

## Workspaces and Local / LocalCrypt sync

See [Workspaces on mobile](folder_hub/folder_hub.md#workspaces-and-local--localcrypt-sync).

## Using the mobile panels

See [Mobile panels](navigation/panels.md#using-the-mobile-panels).

## Panel layout

See [Mobile panels](navigation/panels.md#panel-layout).

## Credential groups, open documents and privacy

See [Mobile panels](navigation/panels.md#credential-groups-open-documents-and-privacy).

## Focused browsing and setup

See [Mobile panels](navigation/panels.md#focused-browsing-and-setup).

## Further reading

- [Workspaces on mobile](folder_hub/folder_hub.md)
- [Mobile navigation](navigation/navigation.md)
- [Mobile settings](settings/settings.md)
