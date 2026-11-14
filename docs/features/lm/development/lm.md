# LM Chat integration

## Organization and controls

Desktop `storage.py:Store` derives folders from physical placement, keeping legacy flat version-one files readable. Preserve malformed, oversized and duplicate records for recovery. Conversation IDs own edit leases across moves. Publish moves without clobber, check both revisions, then remove the source. On removal failure, roll back only while both verified copies survive unchanged. Profiles have independent locks; keys stay in memory. Failed checkpoints retain exportable state. [Shared generation](development.md#shared-desktop-and-mobile-generation)

Chat/Code tabs preserve independent selections; absent legacy `mode` means Chat. Requests budget recent completed turns and save effective settings, endpoint, chosen message IDs and usage. [Code mode](development.md#code-mode-and-optional-direct-edits)

## Mobile server setup

`mobile/ui.py` and `mobile/transport.py` connect and list models without a model ID. Preserve the current listed model, allow manual IDs and defer initial history selection until connection controls are idle. `mobile_api_url` adds `/v1` only for an empty path. Discovery times out after 15 seconds; chat has a 120-second socket idle timeout and a ten-minute deadline checked between events. Diagnostics exclude keys and bodies. `Python/tests/test_mobile_chat.py`, `test_chat_ui.py` and `test_chat_inventory.py` cover transport and draft/selection ordering. Use `chat-settings`, `chat-laptop` and the keyboard probe for native layout and retained drafts.

## Pasted screenshots

Bounded PNGs live in additive `draft_images` and message `images` fields. Save/rollback treats text and images together. Prefer local raster file URLs over Finder icon MIME previews. Clipboard and drop use the same decoder. Vision requests use `image_url` data URLs and a separate token reserve; text-only request shape is preserved.

## Mobile on-device providers

`mobile/on_device.py` selects server (legacy default), `apple` or `nano`. Check availability at model listing and inference. Apple Foundation Models uses the iOS 26 Swift bridge and streams snapshot suffixes; Android ML Kit Prompt requires API 26 and returns a complete response. Android preparation is explicit and may download AICore assets. Unavailable models report failure without HTTP fallback. Workers close native tasks on retirement.

`mobile_build/build_support/lm_build.py` weak-links the iOS bridge in the main app and retains Android API 24 host minimum. `test_on_device.py` checks provider isolation/cancellation; `test_lm_build.py` checks integration. Native bridge compilation has been verified. Inference requires an eligible physical device.

## Mobile persistence and validation boundaries

`mobile/storage.py:ChatStore` stores text Chat and separate profiles, bounded to 200 messages, 65,536 draft characters and 2 MiB per conversation. Serialize revision-checked writes and prevent queued drafts from overtaking explicit saves. Preserve malformed records and drafts typed during discovery. `test_chat_inventory.py`, `test_deferred_chat.py` and `test_lm_storage_adapters.py` exercise these cases.
