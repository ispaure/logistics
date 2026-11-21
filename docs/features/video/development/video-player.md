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
output. Unlock restores controls without autoplay. On iOS, ordinary retained local files
can continue their existing audio during background or device lock; foregrounding
restores the picture without issuing Play. Remote, private and session-only
sources retain their stricter policy. External playback retains its own route
and access checks. Remote
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

## Audio track changes

VLC audio selection starts a decoder at the demuxer's read-ahead position.
The desktop and mobile adapters seek back to the current playback position
after selecting a different track, so VLC flushes and prerolls audio and video
together. The controls show **Switching audio…** during the transition. Choosing
a track while paused does not request playback. Nonseekable active inputs keep
the current selection and explain that switching is unavailable.

Selection acknowledgement and 100% buffering alone are not output readiness:
VLC reports buffer completion before waiting for decoders. Local playback also
requires fresh audio output statistics after the seek's buffering cycle. Cast
uses sender decoder/clock progress because receiver audio statistics are not
available; physical receiver sound still needs hardware acceptance. Native
AirPlay retains its separate AVPlayer selection and playback lifecycle.
Replacement selections, user seeks, pauses, failures and retirement invalidate
or restart the pending operation. A readiness deadline pauses playback and
reports a retryable error instead of claiming success.
On Android, the selected track's preroll owns recovery until the switch
finishes or fails. The unequal-stream fallback waits because pictures can
arrive while the audio and playback clock are still recovering from the seek.

`video_chrome_tools --audio-switch` builds a two-language AAC fixture and checks
the production iOS controller on an owned disposable simulator: visible wait,
native audio output, paused selection/resume, rapid replacement and stale
callbacks, nonseekable refusal, timeout and retirement. The receipt records the
selection timestamp alongside audio buffers, presented pictures and clock
samples. These counters measure native delivery. Check speaker audibility on
hardware.

## Unequal stream lengths and declared media bounds

A file's video, audio and subtitles can end at different times. A subtitle cue
must not extend the playable timeline. The bounded metadata reader in
`features.video.chapters` exposes per-track declared bounds separately from
unknown values; it never scans the whole media file to invent an endpoint.
MP4 track headers and supported edit lists use their proper timescales.
Matroska duration tags retain muxer provenance and a bounded first-block start
witness when the tag is a span. The overall cap is available only when every
A/V track has a known declared endpoint. Native track IDs and container IDs
are separate namespaces; bindings must not equate them.

VLC can reopen a continuing audio tail with video decoding disabled when its
exhausted picture track prevents seeking or clock progress. Captions resume
when a seek restores the original video input. A video-only tail keeps the
native picture and subtitle renderer; choosing an already-ended language
records the selection for playback after a backward seek without waiting for
nonexistent audio output. Playback intent and declared A/V bounds survive
these transitions.

The iOS adapter reads libVLC's actual clock for seek acknowledgment, since the
VLCKit time property can retain an optimistic target during preroll. Statistics
come from a retained native media descriptor with an initialized C struct and
a checked success result; unavailable counters never become output evidence.
Local audio-only VLC inputs use a 250 ms cache so short tails can advance
before demux reaches EOF. During VLC teardown, the controller retains the last
position if the native clock resets to zero before the Stopped notification.
`video_chrome_tools --audio-tail --resume 8500` checks the saved position
in a synthetic 10-second file, tracks audio through EOF and requires fresh
picture and audio after Replay. Run the same probe without `--resume` to cover
the 6-second entry, Pause, backward seek and natural transition.

## AirPlay unequal-stream remuxing

The stream-copy adapter retains its byte, read and deadline limits while
allowing a longer final audio tail after the final video keyframe. It extends
the last *presented* picture, which can differ from the last decoded B-frame.
The bounded final-fragment timing repair preserves every presentation
timestamp, compressed sample and sync flag; decode durations and signed
composition offsets account for the held picture. It does not replay a GOP.

A shorter audio rendition advertises its actual final sample interval,
followed by explicit HLS gaps. Split a partially populated final interval at
the declared audio endpoint: advertising absent audio as present misaligns
AVPlayer's later gap seeks. Opus conversion uses that same per-track endpoint
instead of padding the absent remainder of a video interval. Text renditions share the A/V timeline and clip
cues at its endpoint.

`video_chrome_tools --airplay-controls` exercises the production remuxer and
playlists with native AVPlayer: HEVC B-frames and EAC3, both unequal-stream
directions, natural transitions, legible tail captions, pause, backward and
near-end seeks, and actual end notifications with later subtitle cues. It
uses AVPlayer's ordinary buffering policy. Receiver hardware, physical TV
routing and speaker audibility remain separate acceptance checks.
