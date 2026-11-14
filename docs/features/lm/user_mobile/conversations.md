# Chat on mobile

Open **Conversations** to reopen saved chats or tap the compose icon to start one.
**Send** becomes **Stop** while generating and keeps text already received.
Use **••• → Export conversation…** to export Markdown. In Duo laptop posture,
the conversation stays above the hinge and **Back to draft** restores the
composer below it when there is room.

## On-device models

Open **Chat settings** (sliders icon) or **Settings → LM Chat → Server &
generation settings**, then choose a **Provider**.

- On supported iPhones and iPads with Apple Intelligence enabled and ready,
  choose **Apple Intelligence (on device)** and **Check on-device availability**.
  This requires iOS 26 or later and compatible hardware (iPhone 15 Pro/Pro Max
  or later compatible models). Apple replies stream.
- On supported Android devices, choose **Gemini Nano (on device)** and
  **Prepare Gemini Nano (may download)**. Nano uses AICore and displays a
  completed reply. Preparation can download system model assets.

When ready, **Save settings**. Inference stays on device. Context estimates cap
at 4,096 tokens for Apple and 3,072 for Nano, with 1,024 reply tokens. The system
model enforces its own availability and limits.

## LM server chat

1. In **Chat settings**, enter an OpenAI-compatible server address such as
   `http://192.168.1.10:1234` and an optional session API key. Use the host’s LAN
   address. A plain address adds `/v1`; explicit paths stay intact.
2. Choose **Connect & load models**, or **Enter model ID manually** if necessary.
3. Choose a model and **Save settings**. Use **Generation limits** to adjust
   context and reply limits. Older complete turns may be omitted.

HTTPS verifies certificates. HTTP sends prompts and credentials in plaintext.
Keys stay in memory and must be entered again after restart. If connecting
times out, check address, port, network and firewall. If generation stalls,
check the selected model and server.

Drafts and received text are saved privately. Interrupted records keep their
status and partial reply. If a record is invalid or changed externally, export
the current valid copy before reopening. Requests are text-only and capped at
1 MiB, replies at 256 KiB and conversations at 200 messages. Markdown export
uses the platform picker and is capped at 1 MiB. Change the transcript and
composer text size under **Settings → Markdown → Font size**.
