# LM mobile workflows

## Mobile development builds

Mobile Chat supports text conversations with an existing OpenAI-compatible
server, or a supported on-device provider: Apple Intelligence on iOS and Gemini
Nano on Android. Start with [Chat on mobile](conversations.md) for provider setup,
model readiness, generation limits and platform-specific controls.

For server chat, connect explicitly to discover models, select one and save the
settings. Use the computer's LAN address when hosting the server on a computer.
For on-device chat, check availability or explicitly prepare the model in settings
before saving. On-device inference does not fall back to a cloud server.
Apple and server replies stream; Nano currently presents a completed reply.

Start **New chat**, write a message and use **Send**. During generation, **Stop**
keeps received text. You can write the next draft while a reply arrives. Return
to the conversation drawer to reopen saved threads. **Export conversation…**
writes a Markdown copy through the platform picker; export a valid in-memory
copy before reopening a record with a save conflict.

## Desktop and mobile boundaries

| Workflow | Desktop | Mobile |
| --- | --- | --- |
| Existing OpenAI-compatible server | Supported | Supported |
| Apple Intelligence / Gemini Nano | No provider UI | Supported on eligible iOS / Android devices respectively |
| Saved text conversations and drafts | Supported | Supported in app-private storage |
| Export | JSON and Markdown | Markdown through export-copy picker |
| Screenshot input and text-file attachment picker | Supported | Unavailable |
| IDE Code mode, project tools and guarded Undo | Supported | Unavailable |
| Nested conversation folders, pinning and forks | Supported | No corresponding mobile UI |
| Separate reasoning display and answer read-aloud | Supported | No corresponding mobile UI |

The shared conversation schema does not provide automatic desktop/mobile sync.
Mobile has no desktop conversation import UI and accepts only its bounded
text-only Chat records. Desktop screenshots, project changes and folder workflows
are described in the [desktop guide](../user/user.md).

See the [general mobile guide](../../../user_mobile/user_mobile.md) for application
setup and navigation. Provider availability depends on the installed native build
and system model readiness; implementation and fixture coverage do not establish
acceptance on every physical device.
