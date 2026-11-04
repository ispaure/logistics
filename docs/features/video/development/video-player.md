# Logistics Video Player brief

## Requested outcome

One in-app video player on desktop, Android and iPad, opening Local, LocalCrypt, remote and crypt cloud resources. The minimum acceptance matrix crosses MP4 and
Matroska (MKV) with H.264/AVC and H.265/HEVC video, and AAC and Opus audio.
Container recognition alone is not proof of codec support. Validate decoded
frames, audible output, seeking and audio/video synchronisation on each target.

Playback controls include play/pause, seeking, elapsed/total time, volume,
audio-track selection, embedded subtitle selection/off, external SRT subtitles,
and a readily accessible fullscreen toggle. Remember position per source and
revision; do not apply an old position to replaced content. Completion resets
resume to the start. Errors must leave a usable close/retry path.

## Storage and privacy contract

Use retained resource providers and seekable, bounded reads. Never materialise
a decrypted LocalCrypt movie or subtitle in a temporary file, export it to an
external player. URLs, credentials and private playback positions stay out of
ordinary workspace/history storage. Session-only reopen references and titles use
the existing credential-password encrypted recent list; ordinary recent references
require a matching explicitly saved connection. Revalidate credential grants and source revisions
while streaming. Closing or revoking access retires the decoder and transport.

Ordinary local resume records may use app-private storage. LocalCrypt resume
records must pass through the encrypted provider; ciphertext is durable while
decryption still requires its credentials. Read-only storage may retain progress
only for the current process and must report that persistence is unavailable.

Session-only credentials prohibit casting, external displays, picture in picture
and desktop floating windows. Enforce this in actions and transport admission,
including after credential changes, rather than only hiding controls. A mobile
lock pauses every movie, including floating/cast playback. Session-only resume
requires the existing credential password gate. Unlocking must not autoplay.
Backgrounding an ordinary movie may continue only through an explicitly selected
supported floating/cast mode; ordinary inline playback pauses.

## Scope and delivery

Local playback and rclone network ranges share the retained-provider transport.
Both crypt and non-crypt cloud playback are best effort and must not expose
remote credentials to a decoder or receiver. Historical cloud checks used memory-only resume for
the current player because remote sources are read-only.

Native mobile packaging, codec decoding, subtitle rendering, lock/unlock,
picture in picture and receiver playback require native acceptance. Host tests
alone cannot establish those capabilities. Keep the implemented status and
remaining acceptance work in the [development guide](development.md).

Session-only persisted state now follows the shared [credential-password and clearing policy](../../../development/reader-state.md).

## iOS framing and selection menus

Framing changes refresh the drawable layout immediately. The native
`AVSampleBufferDisplayLayer` uses aspect-fill gravity for Fill and aspect-fit
otherwise; VLC crop/scale settings still serve the decoder output. New rendering
layers and layout changes reapply the native gravity. The Picture icon owns the
framing selector in both the normal navigation toolbar and folded control deck,
without a duplicate Playback menu entry.

Selection menus use backdrop dismissal, including compact scrollable alerts on
Duo. The backdrop gesture excludes touches inside the menu; text-entry prompts
retain Apply/Cancel. The native chrome probe checks Fit/Fill geometry and gravity,
menu presentation without Cancel actions, inside/outside gesture filtering, and
backdrop dismissal. Landscape coverage also checks that the filename stays
visible above the timeline when the navigation bar has limited room.

## Per-video resume preferences

`VideoSettingsStore` writes validated `PlaybackSettings` into `VideoProgress`,
sharing its lock, history generation and encryption boundary. Completed playback
stores position zero while retaining settings. Legacy global preferences seed
videos without a saved record; new choices do not write that global file.
Local identity uses at most three 64 KiB decoded reads plus size; remote identity
remains resource/revision based. Existing path records are read as a migration
fallback before the first fingerprint checkpoint. Embedded track selections are
backend track IDs on Android and ordered track indices on iOS/desktop.

Regression coverage checks local moves across provider roots, completion,
replacement invalidation, encrypted LocalCrypt settings, and mobile lifetimes.
SDK compile checks validate adapter interfaces, not native playback acceptance.

## Mobile PiP controls and captions

Mobile never creates an Undo seek button or menu item. Android registers
package-local immutable PendingIntents for ten-second back/forward and Play/Pause,
updates their state only when it changes, and unregisters its receiver on disposal.
VLC's subtitle surface stays attached through the PiP transition.

iOS PiP delegate seeks use the bounded 64-bit on-screen seek path, including its
paused-position bookkeeping. Every system request completes, including a no-op at
a boundary, and seeking eligibility respects the control lock and access policy.
The native `video_chrome_tools --pip-controls` probe checks forward/backward,
start-boundary completion and control locking with real UIKit/VLC. It does not
establish system PiP-window rendering or physical-device button interaction.

On iOS 17.4 and later, `CaptionPictureInPicture.m` supplies AVKit with a
composited sample containing the decoded video and VLC's rendered subtitle
planes. It descends through VLC's shared drawable wrapper to exclude video
without excluding captions. A drawable-only adapter prevents VLC's automatic
PiP controller from replacing this captioned stream when the app backgrounds.
Caption parsing, track selection, styling and timing continue to belong to VLC.

The compositor uses volatile pixel buffers, at most 30 frames per second and
720 pixels on the longest side, with a three-buffer allocation limit. HDR input
uses a tagged 10-bit output and converts the subtitle plane into that color
space; SDR output is tagged for its actual sRGB conversion. Stop, lock and
retirement discard the timer, layer contents and pixel pool. Earlier iOS
versions retain VLC's original video-only PiP path because displayed-buffer
readback requires iOS 17.4.

`video_chrome_tools --pip-subtitles` tests actual active PiP with external SRT
captions, background frame/clock progress, subtitles off/on, paused forward seek,
backward cue restoration and retirement. `--embedded-subtitles --hdr` selects a
muxed subtitle track and checks the enqueued 10-bit format and PQ attachment.
The disposable iPad simulator supports system PiP; iPhone Simulator reports it
unsupported. Simulator rendering does not establish physical HDR headroom or
physical-device button interaction. The upstream
[Apple sample-buffer output](https://github.com/videolan/vlc/blob/master/modules/video_output/apple/VLCSampleBufferDisplay.m)
explains why its separate subtitle plane needs composition.

## Desktop plugin lifetime

The video runtime retains one idle LibVLC core until process exit. Each player
and subtitle-scale replacement still gets its own configured instance; the core
holds no media, providers or credentials. This prevents LibVLC from unloading its
plugin bank after each player closes and scanning every plugin on the next open.
Decoder/player disposal still releases streams and native player resources.

A full 13-codec run exposed repeated plugin discovery during instance creation,
rather than a decoder deadlock. Retaining the idle core reduced that matrix from
about 292 seconds to 8–19 seconds on the validation Mac, without raising the
runner's 300-second file limit. The complete parity file passed in 197 seconds.
Speed checks wait for the post-seek decoded clock to settle before sampling;
their rate tolerance is unchanged. Absolute timings depend on host load.
