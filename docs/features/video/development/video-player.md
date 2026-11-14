# Video storage and playback contracts

## Storage and privacy contract

Keep video and subtitles under retained provider access with bounded ranges.
LocalCrypt stays encrypted at rest, including resume state. Ordinary local
resume can use app-private storage. Read-only sources report when state is
process-only. Check source revision and credential scope during streaming.
Revocation retires the decoder and transport. See the
[shared reader-state contract](../../../development/architecture/reader-state.md).

Session-only access denies external display, Cast, PiP and desktop pop-out.
Enforce the policy in native actions and admission. Lock pauses and conceals
output. Unlock restores controls without autoplay. Ordinary background
playback requires an explicitly selected supported external mode. Remote
credentials stay with the provider and never appear in decoder URLs.
[Resume ownership](development.md#playback-tool-ownership)

## Per-video settings

`VideoSettingsStore` writes validated settings with progress under one lock.
Local fingerprints use size and up to three 64 KiB reads. Remote keys bind
resource/revision. Older path records can seed a checkpoint. Completion zeros
position and retains settings. Android embedded tracks use backend IDs.
iOS/desktop use ordered track indices.

## Mobile PiP controls and captions

Android sends immutable package-local ten-second back/forward and play/pause
actions. Keep the subtitle surface attached and refresh the current seek when
reenabling a cue. Retire the receiver on disposal. iOS delegates bounded seeks
through the same lock/access policy as on-screen controls. On iOS 17.4+ the
captioned path composites VLC's video and subtitle planes at up to 30 fps,
720 pixels on the longest side and three volatile buffers. HDR uses tagged
10-bit samples. Lock or stop retires the timer and buffers. Earlier iOS uses
video-only VLC PiP. [Upstream Apple sample-buffer output](https://github.com/videolan/vlc/blob/master/modules/video_output/apple/VLCSampleBufferDisplay.m)

Run the module `mobile_build.validation.video_android_pip_tools --output PATH`
for real Android action dispatch and caption pixels on an owned emulator. Use
`video_chrome_tools --pip-controls` for iOS seek/lock checks and
`--pip-subtitles` for system PiP on a supported simulator. Add
`--embedded-subtitles --hdr` for 10-bit PQ checks. Physical display, sound and
touch remain separate.

## Desktop plugin lifetime

Keep one idle LibVLC core until process exit to avoid scanning the plugin bank
on each open. Configured players still release native resources, providers and
credentials at close.
