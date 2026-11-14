# LM Chat integration

Use this reference when changing conversation files, request settings,
screenshot input or mobile provider admission. For the desktop worked example,
shared generation lifecycle and Code tools, see
[LM feature implementation](development.md).

## Organization and controls

Desktop `storage.py:Store` keeps records under `LM/conversations`. The tree
mirrors real directories. Version-one records can include `folder`; reads
derive the value from physical placement, so old flat and manually relocated
files still load. Malformed, duplicate-ID and oversized files remain available
for recovery. The inventory warns about them and excludes them from editing
baselines. Reads are bounded to 32 MiB plus one byte.

The stable conversation ID owns the edit lease, regardless of folder. A short
publication lock serializes revision checks and writes. Moves first publish a
new copy without clobbering a destination, verify both revisions, then retire
the original. If removal fails, rollback removes the new copy only while both
copies still match the verified revisions. Preserve a changed copy or the sole
surviving copy and report the conflict for recovery. Profiles have independent
locking and expected-value checks. Desktop profile records publish ID, name
and base URL. API keys stay in memory.

Draft publication debounces at 700 ms and active replies checkpoint at one
second. A failed publication cancels generation and keeps an exportable copy in
memory. Closing waits on persistence and cooperative request retirement before
releasing the edit lease. Close can proceed after explicit discard.
See [shared generation](development.md#shared-desktop-and-mobile-generation).
Use `test_lm.py`, `test_lm_session.py` and the widget/loopback fixtures in
`test_lm_ui.py` for storage and lifecycle coverage.

## Mode-specific conversation navigation

Desktop Chat/Code tabs filter by saved conversation mode with separate
selections. Switching filter leaves each record's mode intact. Missing `mode`
in legacy version-one files means Chat. The request estimates context with
whole completed turns, newest first, and uses the latest completed answer per
turn. Effective settings, endpoint, chosen message IDs and any returned
completion/usage details are saved with the response. The model/server
tokenizer remains authoritative. See [Code mode](development.md#code-mode-and-optional-direct-edits)
for project settings and write recovery.

## Mobile native action placement

On iOS, New Conversation and the action menu are screen-level controls.
The conversations drawer occupies the leading navigation group. UIKit
places it according to the window and orientation. Composer and Send/Stop
stay in the message pane. Android uses its native header layout. The
managed `chat-settings` and `chat-laptop` probes exercise rotation, native
control placement and retained drafts with synthetic inputs.

## Mobile server setup

Android and iOS share `mobile/ui.py` and `mobile/transport.py`. Setup labels the
server address, optional session key and model separately. **Connect & load
models** needs no model ID; it retains the current model when listed, otherwise
selects the first result, and persists the selection. Manual IDs remain available
for servers without model discovery. Invalid saves stay in setup with feedback.
Selection-list replacement suppresses change callbacks until the intended model
is restored, so refreshing does not silently replace it with the first model.
Initial conversation discovery can complete while a connection request owns the
controls. Keep the initial selection pending during that request and refresh it
when the controls become idle, so an existing draft is restored or an initial
conversation is created before sending. `mobile_build/tests/chat/test_chat_inventory.py`
checks both an existing conversation and an empty library under this ordering.

`mobile_api_url` adds `/v1` only to addresses with no API path; profile validation
and the HTTP client use the same normalization. Explicit paths remain unchanged.
Connections/model discovery retain a 15-second timeout. After connecting, chat
requests use a 120-second socket idle timeout, including waiting for response
headers, to accommodate model loading. Diagnostics distinguish connection,
first-response and stream idle timeouts without exposing credentials or server
response bodies. Cancellation still interrupts the socket and worker queue.
The ten-minute generation deadline is checked between event reads; a pending
read remains bounded by the socket idle timeout.

Focused verification: `Python/tests/test_mobile_chat.py` checks URL normalization,
request paths, timeout stages and cancellation; `mobile_build/tests/chat/test_chat_ui.py`
checks discovery without a model, selection persistence and validation feedback
through Toga's dummy backend. Native device layout and real-server behavior need
separate Android/iOS verification.

Android keyboard layout uses the shared navigation adapter's removal of
Material's automatic IME padding from bottom navigation. The scrolling transcript
has a zero minimum height, and the composer caps growth at one quarter of the
native container height (52–120 logical units), so the keyboard-reduced viewport
does not clip Send or overlap navigation. `chat_keyboard_probe.py` in the native
test owner exercises an isolated app with no server, long header/model labels,
multiline drafts and repeated keyboard opening/closing. It checks actual native
rectangles, keyboard visibility, bar height and retained draft text.

## Pasted screenshots

Composer accepts clipboard image MIME data, converts it to bounded PNG records,
and shows removable native previews. Optional `draft_images` and message `images`
fields are additive to version-one JSON; legacy text conversations still load.
Images are embedded, so revision-checked publication, moves, forks and exports
retain them without external paths. Draft clearing and save-failure rollback
operate on text and images together. User bubbles render separate native image
widgets; Markdown's resource-loading restrictions remain in force.

OpenAI-compatible requests use image_url data URLs in user content arrays. Recent
complete turns retain their images, while omitted/failed turns follow existing
context policy. Budgeting uses a documented image-token reserve rather than
base64 length, including Code-mode continuations. Vision support must be supplied
by the configured model/server; text-only payloads retain their original shape.

Local file URLs take precedence over clipboard imageData: macOS Finder can offer
a generic file icon as imageData for a copied screenshot. The file loader uses
bounded bytes and QImageReader format/dimension checks, accepts raster formats
only, and reports unreadable files without falling back to their icon preview.
Direct screenshot pixels still use the original image MIME path.

Composer and LMPage explicitly accept image/file-URL drag events and route drops
through the same bounded clipboard decoder. They do not insert file:// text for
image files. Ordinary text drops retain the editor’s native behavior.

## Mobile on-device providers

`mobile/on_device.py` dispatches explicitly between the existing HTTP adapter,
Apple Foundation Models and Android ML Kit Prompt API (`genai-prompt:1.0.0-beta4`).
Native imports are lazy. Legacy profiles default to the server; an optional
`provider` field selects `apple` or `nano`. The provider control appears for the
current platform; runtime availability is checked before listing its model and
again before inference. No cloud fallback or automatic inference occurs.
Explicit Android preparation may download system model assets through AICore.

`mobile/ios/FoundationChat.swift` exposes an Objective-C bridge for Rubicon, with
an iOS 26 availability guard. Each request reconstructs a typed Foundation Models
transcript with separate instruction/user/assistant entries. Swift streams
cumulative snapshots; the Python worker publishes only new suffixes. Android
uses Chaquopy and `GenerativeModelFutures`, supplies the selected role-tagged
history as JSON in a single prompt, and publishes the completed response.
On-device settings cap approximate context at 4096/3072 tokens (Apple/Nano) and
maximum replies at 1024. Native context checks remain authoritative.

Both clients use the shared generation coordinator and mobile execution adapter,
including durable pending-turn publication, partial replies, Stop and retirement.
Each worker owns and closes its native model/task; cancellation is observed
between short polls. Preparation/status waits are bounded. Generation metadata
identifies the local provider with an `on-device://` endpoint, never a server
fallback. Server addresses can remain in the profile for switching back.

`mobile_build/build_support/lm_build.py` adds the Swift source only to the main
application, weak-links Foundation Models and embeds Swift runtime libraries
without raising the app's deployment target. The feature payload manifest includes
the bridge. Android dependencies are synchronized into reused Gradle projects by
the existing build owner. The two optional GenAI libraries declare API 26;
the manifest override preserves the host API 24 minimum, while the native adapter
checks API 26 before loading either library. Neither library declares startup
components in its manifest.

Host checks in `test_on_device.py` cover availability, explicit preparation,
no HTTP fallback, profile compatibility, incremental publication, cancellation,
error preservation and a saved UI conversation without an address or key.
`test_lm_build.py` checks repeatable main-target integration and preservation of
the Android host minimum. Disposable native host builds verified the Swift bridge
and Android dependency/API compilation plus manifest merging. Native bridge
compilation is separate from successful inference on eligible physical devices.

## Mobile persistence and validation boundaries

`mobile/storage.py:ChatStore` keeps a flat private directory and separate
`profile.json`. It accepts text Chat only, with at most 200 messages, 65,536
draft characters and 2 MiB per record. Profile fields are schema, URL, model,
generation settings and provider. Session keys stay in memory.

Mobile draft saves debounce at 250 ms with a one-second maximum while
typing. Sequence and generation guards keep queued writes from overtaking
explicit saves. The write lock serializes publication, and prior bytes
are rechecked before replacement. Missing previously saved records and wrong
revisions are conflicts. Preserve malformed records for recovery. Catalog
summaries cache ID, title and update time using file identity and timestamps.
Discovery preserves a draft typed while inventory loads.
`test_chat_inventory.py`, `test_chat_ui.py`, `test_deferred_chat.py` and
`test_lm_storage_adapters.py` cover these boundaries.
