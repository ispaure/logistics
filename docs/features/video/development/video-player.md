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
