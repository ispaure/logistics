# Chat on mobile

## LM chat

Choose **Chat** in the bottom navigation. Open **••• → Server & model settings**, enter your
existing server's address (for example `http://192.168.1.10:1234`) and optional
session API key. A plain address automatically uses `/v1`; an explicit API path
is preserved. Tap **Connect & load models** to contact the server and fill the
model selector. The first model is selected and saved automatically, or your
current model is retained if still available. Choose another model if needed.
You do not need to type a model ID to connect. If your server does not list
models, enter its exact model ID in the labeled field instead.
Use the computer's LAN address/hostname when the
server is on a computer: `localhost` on a phone means the phone itself. HTTPS
protects requests and credentials; HTTP sends them unencrypted. TLS verification
is enforced for HTTPS, and redirects are refused. iOS declares the local-network
purpose; physical-device permission behavior still requires validation.

Generation defaults can usually be left as they are. To adjust them, choose
context tokens and maximum reply tokens, then tap **Save & return to chat**.
These settings, URL and model persist privately. API keys remain in memory for
this app session and are not written to configuration or conversation fields.
Re-enter a required key after restarting. Opening chat alone makes no request.

**New chat** at the bottom of the conversation drawer starts a private thread. Drafts are checkpointed while typing.
**Send** streams a text reply and preserves partial progress during generation.
The same button becomes **Stop** during generation; it stops the connection and
retains received text with cancelled status.
Reopening an interrupted streaming record identifies it as interrupted. Failures
retain the user message/partial reply; no automatic retry occurs. The top-left
conversation menu reopens saved conversations. Malformed, oversized or concurrently changed files
are preserved, and saving reports the problem. Export can preserve a current
valid in-memory copy before reopening a conflicting file.

The chat canvas follows the device’s light/dark theme: white in light mode and
black in dark mode, including the background while messages load. Messages fade
into that background at the top as you scroll. On iPad and unfolded Duo, the
composer stays centered and caps its width for comfortable reading; long header
titles truncate before reaching the action buttons.
The header shows the conversation title and configured model. Your messages use
right-aligned grey bubbles; assistant replies use the full reading width with offline
Markdown formatting (tables, headings, nested lists, quotes, emphasis and code). Raw HTML is
escaped and links/images do not load external resources. **Copy** copies a reply's
displayed text; if the platform declines copying, select the text and use its
system Copy command. Streaming follows the latest reply only while you are near
the bottom. **Latest message ↓** returns there after reading older messages.

The native message field grows as you type, up to a bounded height; longer drafts
scroll inside it. A circular up-arrow sends your message; it becomes a square Stop
control during generation, inside the same rounded composer. The header’s pencil
button starts a new conversation. On Android phones, the bottom navigation keeps
its normal height when the keyboard opens. The transcript shrinks and long drafts
scroll within a smaller message field, keeping the text and Send button above
the keyboard. Completed messages omit visible role headings;
interrupted and incomplete replies keep their status labels. Status appears only for ongoing
work, feedback or problems. Server/model settings and **Export conversation…**
are in the **•••** menu. Configuration is scrollable when the keyboard reduces
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
