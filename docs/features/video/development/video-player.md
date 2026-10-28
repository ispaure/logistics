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
external player, or persist its URL, credentials, title or position in ordinary
workspace/history storage. Revalidate credential grants and source revisions
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
remote credentials to a decoder or receiver. Cloud resume stays in memory for
the current player because remote sources are read-only.

Native mobile packaging, codec decoding, subtitle rendering, lock/unlock,
picture in picture and receiver playback require native acceptance. Host tests
alone cannot establish those capabilities. Keep the implemented status and
remaining acceptance work in the [development guide](development.md).
