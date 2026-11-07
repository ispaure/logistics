# Chat on mobile

Conversations, the compose icon and the Chat settings icon share the leading
action area. On iOS, these controls use the native navigation bar. Eligible
controls move to the side on iPhone Duo and extra actions join the system
overflow menu. Send and Stop stay beside the message field.

Open **Conversations** to browse chats grouped by the month they were last
updated. The newest month starts expanded. Tap a month to expand or collapse
its conversations, then tap a conversation to open it. On a narrow screen the
browser gives the list the full pane and returns to the transcript when you
choose a chat.

In Duo laptop posture, the conversation stays above the hinge. The lower screen
provides a larger draft area, Send/Stop and direct controls for Conversations,
New conversation and Chat settings. Conversations opens in that lower panel without
replacing the transcript; Back to draft restores the same draft. If the keyboard
leaves too little room below the hinge, chat uses a compact composer above the
keyboard and crease. Unfolding restores the normal layout without reloading the
conversation or clearing the draft.

## On-device models

Open **Chat → Chat settings** using the sliders icon, or
**Settings → LM Chat → Server & generation settings**. The page, Save and Back
stay in the tab where you opened it. Choose a **Provider**; only that provider's
controls appear. Opening the page does not contact a provider.
On iOS, choose **Apple Intelligence (on device)** and tap **Check on-device
availability**. This uses Apple's Foundation Models framework on iOS 26 or later
with Apple Intelligence enabled and its model ready. Supported iPhones start with
iPhone 15 Pro/Pro Max; regular iPhone 15/15 Plus are unsupported. Compatible iPads
can also use the model. Availability depends on the device, language and region.

On Android, choose **Gemini Nano (on device)** and tap **Prepare Gemini Nano
(may download)**. Supported devices use Android's AICore through ML Kit. If the
system reports downloadable model assets, this explicit action downloads them;
opening Chat or sending a message does not start a model download. Unsupported
or unready devices show a status message and cannot select the built-in model.

Once the model is ready, tap **Save settings**. Neither provider needs a
server address or API key. Inference stays on the device with no cloud fallback.
Apple replies stream; Gemini Nano currently displays the completed reply.
Both use the same private conversation history and Stop control as server chat.
On-device context estimates are capped at 4096 tokens for Apple and 3072 for Nano,
with replies capped at 1024 tokens. Older complete turns are omitted as needed;
the system model still enforces its actual context, language and usage limits.

## LM server chat

Open **Chat settings** in Chat, then enter your
existing server's address (for example `http://192.168.1.10:1234`) and optional
session API key. A plain address automatically uses `/v1`; an explicit API path
is preserved. Tap **Connect & load models** to contact the server and fill the
model selector. The first model is selected and saved automatically, or your
current model is retained if still available. Choose another model if needed.
You do not need to type a model ID to connect. If your server does not list
models, the manual model ID field opens automatically. You can also choose
**Enter model ID manually** at any time. Switching providers keeps your server
address, session key and model entry.
Use the computer's LAN address/hostname when the
server is on a computer: `localhost` on a phone means the phone itself. HTTPS
protects requests and credentials; HTTP sends them unencrypted. TLS verification
is enforced for HTTPS, and redirects are refused. iOS declares the local-network
purpose; physical-device permission behavior still requires validation.

Generation defaults can usually be left as they are. Open **Generation limits**
to adjust the separately labeled context and maximum reply token limits, then
tap **Save settings**.
These settings, URL and model persist privately. API keys remain in memory for
this app session and are not written to configuration or conversation fields.
Re-enter a required key after restarting. Opening chat alone makes no request.

The compose icon starts a private conversation.
Draft recovery writes are batched briefly while typing and flushed when leaving
the screen or backgrounding the app. Session API keys remain in memory.
**Send** streams a text reply and preserves partial progress during generation.
The same button becomes **Stop** during generation; it stops the connection and
retains received text with cancelled status.
Reopening an interrupted streaming record identifies it as interrupted. Failures
retain the user message/partial reply; no automatic retry occurs. The top-left
conversation menu reopens saved conversations. Malformed, oversized or concurrently changed files
are preserved, and saving reports the problem. Export can preserve a current
valid in-memory copy before reopening a conflicting file.

Chat uses the shared Logistics light and dark colors. The conversation pane
header shows the conversation title and configured provider or server model.
On iPad and unfolded Duo, the composer stays centered and caps its width. Your
messages use right-aligned bubbles. Assistant replies use the reading width with
offline Markdown formatting (tables, headings, nested lists, quotes, emphasis and code). Raw HTML is
escaped and links/images do not load external resources. **Copy** copies a reply's
displayed text; if the platform declines copying, select the text and use its
system Copy command. Streaming follows the latest reply only while you are near
the bottom. **Latest message ↓** returns there after reading older messages.

**Settings → Markdown → Font size** controls both conversation text and the
message field, using the same size as notes, Markdown files and documentation.
Pinching the conversation also updates this shared size.

The native message field grows as you type, up to a bounded height; longer drafts
scroll inside it. The up-arrow sends your message; it becomes a square Stop
control during generation, inside the same rounded composer. The header’s pencil
button starts a new conversation. On Android phones, the bottom navigation keeps
its normal height when the keyboard opens. The transcript shrinks and long drafts
scroll within a smaller message field, keeping the text and Send button above
the keyboard. On iOS, destination tabs and their reserved spacing disappear
while the keyboard is open, then return after dismissal. In short keyboard
layouts, Chat temporarily hides the conversation heading and status to give
the message field and Send more room. Completed messages omit visible role headings;
interrupted and incomplete replies keep their status labels. Status appears only for ongoing
work, feedback or problems. **Export conversation…** is in the **•••** menu. Configuration is scrollable when the keyboard reduces
the available space. Draft storage and text-only request limits are unchanged.

Requests reuse the desktop whole-turn context budget: older completed turns may
be omitted, with their count shown during generation. Server token limits remain
authoritative. Mobile limits are 200 text messages per conversation, a 64 KiB
character draft, 2 MiB per stored record, 256 KiB per reply, 64 KiB per server event
and 1 MiB per request. Connecting and model-list reads time out after 15 seconds;
generation waits up to 120 seconds without data to allow for model loading.
Timeout messages distinguish connecting, waiting for the first reply and a
stalled reply. Check the address, port, network and firewall for connection
timeouts, or the selected model/server status for reply timeouts. Generation
checks a ten-minute limit between event reads; an outstanding read can extend
that by its idle timeout. Model lists are bounded to 128 IDs / 512 KiB.

**Export conversation…** writes UTF-8 Markdown through the platform export-copy
picker, subject to its 1 MiB limit. Conversations use the desktop LM domain/schema,
but mobile currently supports text-only Chat mode: no screenshots, project Code
mode, model tools, folders, or desktop conversation import UI. Model tool calls
are rejected rather than executed.
