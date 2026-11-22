# Video Player development

Open a local video through **File Browser** on desktop or **Workspaces**
on Android/iOS. The same feature owns decoder selection, subtitles and resume.
For visual controls, start in `ui/` on desktop or `mobile/` on the phone or tablet.
For file behavior, start with the portable modules.

## Change how a subtitle is found

Open a disposable local MP4 in File Browser. Load an SRT through the player's
Subtitles panel and close the video. Move the containing folder and reopen the
video. A saved subtitle choice can follow the file when the relative directory
changes and the subtitle basename still matches.

To change that fallback, edit
`Python/features/video/sidecars.py:discover_sidecars`. Desktop
`ui/player.py` and mobile `mobile/player.py` call it. Use a synthetic
movie name and short caption fixture to exercise the old saved path and the new
location. Run the portable contracts from the repository root:

```sh
python3 dev.py test desktop --exact-file Python/tests/readers/test_video_player.py
```

Expect the moved-folder check to admit `captions.srt`, and the range, revision,
authorization and subtitle-parser contracts to pass. The desktop host suite
opens loopback sockets and its LocalCrypt case needs the local rclone tool.
Check actual caption rendering with the existing native parity fixture when
changing a renderer.

## Find the owner

| Change | Start here |
| --- | --- |
| Enable, open or activate a video | `__init__.py` declares Video Player and `formats.py` owns recognized types. The legacy mobile Media disable preference migrates to Video. |
| Desktop surface or controls | `ui/backend.py`, `ui/player.py`, `ui/chrome.py`, `ui/panels.py`, `ui/presentation.py` |
| Mobile playback or controls | `mobile/player.py`, `mobile/controls.py`, `mobile/ios.py`, `mobile/android.py`; native `PlaybackControls`, `PausePresentation` and iOS `DuoDeck.m` |
| Android video view hierarchy and native events | In Android `VideoPlayer.java`, the view setup builds the overlay and controls, `applyControlInsets()` fits the controls to the safe area, `show()` attaches VLC to the mounted view, and `onPlayerEvent()` handles VLC events. |
| iOS video view hierarchy and layout | The `VideoChrome` category in `mobile/ios/VideoPlayer.m` builds the inline surface and controls, resolves the fold and safe-area geometry, and sizes the inline picture and control deck. |
| Provider admission, read-ahead or errors | `playback.py`, `transport.py`, `buffering.py` |
| Chapters and folder queue | `chapters.py` reads Matroska ChapterAtoms and MP4 chpl data. The desktop and native timelines use the existing seek paths for chapter jumps. `session.py` orders the queue. |
| Resume or privacy | [Playback tool ownership](#playback-tool-ownership) and [storage policy](video-player.md) |

## Desktop playback

macOS prefers libmpv for color output. Windows/Linux use VLC. The VLC runtime
owner verifies the pinned archives and payloads on macOS/Windows. Linux uses
distribution LibVLC 3. `ui/surface.py` paints bounded SDR memory frames with
aspect, padding and rotation correction. Captions can require software decoding
when VLC cannot blend on an opaque hardware surface. Font changes replace the
instance at its held position.

Header, picture and footer have separate allocations. Settings sit beside
a wide picture and below a narrow one. Short windows use a compact category
selector. Fullscreen restores its original document slot on exit. Decoder
and provider leases remain active through control reparenting and close in
ownership order. External receiver admission rechecks source permission.

## macOS HDR and tone mapping

`ui/mpv_binding.py` serializes libmpv commands and `ui/mpv_surface.py` uses a
16-bit float Cocoa framebuffer. The renderer maps to BT.709/PQ at
203 × screen EDR headroom with BT.2390 and converts to extended sRGB in
`ui/extended_srgb.glsl`. SDR caps at 203 nits. Reevaluate headroom on display
changes and explicitly repaint paused output. Free the render context while
its GL context is current, then stop the worker. Renderer handoff carries
position, Pause and fullscreen with a fresh provider lease.

`services/mpv_runtime.py` verifies the checksum-pinned IINA 1.5.0 universal
runtime and dependency hashes. Packaged Mach-O dependencies load before libmpv.
The source notice inventory records IINA dependencies and GPL references.
[IINA build recipes](https://github.com/iina/deps-buildscripts) ·
[mpv 0.41 rendering API](https://github.com/mpv-player/mpv/blob/v0.41.0/include/mpv/render.h)

Run `test_video_colour.py` for options and runtime receipts. The extended
`test_video_colour_native.py` needs Cocoa and `LOGISTICS_TEST_MPV_LIBRARY`
set to the verified runtime. It checks real PQ/HLG frames, paused repaint,
rendering transitions, captions and clocks. Forced headroom on SDR covers
the float pipeline. Physical luminance, Dolby Vision and HDR10+ require
separate evidence. Windows/Linux HDR is unavailable.

## Mobile playback and display

Mobile mounts the native controller only while the route and authorization
remain current. A replaced or concealed view rejects delayed presentation.
Fullscreen, fold changes and compact menus retain the active session and
clear the actual system reservations. iOS applies rates after Pause
acknowledgement and seeks to the held position before resuming. Mobile
preference writes serialize. See [iOS HDR pause and resume](hdr-play-pause.md)
and [PiP and captions](video-player.md#mobile-pip-controls-and-captions).

### Inline subtitle clearance

The inline controllers compare the painted bounds of a supported text cue with
the laid-out control deck in window coordinates. A cue moves up just far enough
to clear an intersection and returns after the deck fades. A separate deck
leaves the cue at its original position. Video sizing, text styling, and the
decoder clock continue through the same rendering path.

iOS uses the transparent subpicture view of the pinned sample-buffer renderer.
Android uses the separate LibVLC subtitle surface when its pixels can be read.
A sidecar whose codec is missing from Android's track metadata can qualify when
an explicit SRT attachment identifies one new track.
A renderer that blends captions into the video, a secure Android window,
unidentified tracks, positioned ASS, and bitmap tracks retain native placement.
If the full cue will not fit above the deck inside the picture, it retains
native placement there too. PiP and external playback use their own geometry.

Use `video_chrome_tools --inline-subtitles --orientation landscape` to check
an embedded multiline cue through playback, Pause, automatic hide and synthetic
external drawable handoff. Use
`--inline-subtitles --fold` in portrait with the Duo SDK to verify separate panes.

### Dedicated iOS display output

`mobile.external_display` and the VLC controller reparent the live picture
and subtitles into the external scene using its bounds and display aspect.
Controls and audio remain with the device. Explicit Cast takes over and active
PiP delays the handoff. Revocation hides the picture, mutes/pauses and returns
it inline before asking for explicit playback. Ordinary output can continue
on a replacement route. Protected and Bluetooth route loss still pause.

Use `video_chrome_tools --external-display` for a synthetic viewport. On a
physical TV, capture `LOGISTICS_EXTERNAL_DISPLAY` with
`LOGISTICS_DISPLAY_DIAGNOSTICS=1`. Compare reported scene, mode and video
bounds to the visible picture in two aspect ratios. Exercise pause/seek,
rotation, captions, audio, connection before/during playback, exit and
revocation. Save logs under ignored test results.

### Native AirPlay video

The iOS-only `native_video_airplay` preference defaults off. Ordinary local
MP4, MOV, M4V and MKV files with a guarded path and an external-playback grant
have one native **AirPlay** picker in the VLC controller. The selected AirPlay
audio route starts preparation. The controller confirms external video with
AVPlayer and keeps the same deck and timeline. On route loss or playback
failure, the picker stays available. VLC waits for the audio route to return
before resuming. Revocation disables external playback and detaches the item.
A window reuses its empty AVPlayer for successive requests, disabling external
playback when the video controller retires. Startup does not opt into long-form
automatic route suggestions; iOS's Automatically AirPlay preference owns those
system notifications, including ones shown while browsing protected media.
The controller retains the reusable route player separately from its active item:
retirement disables external playback even after a timeout has already detached
the item. It does not attempt to force the system audio route back to the phone.
That selection belongs to iOS's route picker/Control Center.

Device lock preserves an established, authorized ordinary AirPlay session.
`hasEstablishedAirPlay` requires a retained player that has reached external
playback; `allowsAirPlay` still checks the current source grant and session
restriction. New handoffs and local playback remain denied while protected data
is unavailable. File protection is unchanged: an inaccessible source still fails
its access/read checks. Closing, revocation and session protection detach as before.

AVKit receiver controls can pause AVPlayer without calling the Logistics pause
method. Timeline polling accepts that state during seeks, and seek completion
rechecks the player before restarting; this prevents a stale `playRequested`
flag from undoing receiver Pause. Rate-change notifications log state and system
reason without filenames, titles or stream URLs. These logs help distinguish a
pause reaching AVPlayer from one that never reaches the sender; they do not prove
why a physical receiver stopped sending commands.

Playback starts the receiver handoff while a saved-position seek is pending;
output stays muted until the seek completes. Loading keeps the known-duration
timeline usable. Connection and seek deadlines prevent an unresponsive receiver
from retaining the player indefinitely. Local mute is user intent, separate
from VLC's transient output state; returning from AirPlay flushes queued audio
at the held position.

`video_chrome_tools --airplay-controls` checks the production controller with
real VLC audio state and simulated AVPlayer loading, interrupted and stale seek
completions, phone/receiver Pause and timeout recovery. It injects device-lock
availability and background notifications to check continued AirPlay, pause/resume,
denied new handoffs, source revocation, route loss and session protection.
Receiver Pause is checked during pending seeks, before polling and after repeated
background transitions. It also measures the system
route picker's alignment beside Forward and verifies HDR metadata with the
pinned iOS remuxer. This disposable simulator check does not establish physical
receiver compatibility.
It also exports real native MP4/MKV fragments, serves the production HLS
playlists over loopback and checks AVKit's legible options, selection, Off,
and emitted caption text after seeking across a subtitle boundary. Each native
media fragment is also decoded independently. The fixture includes MP4 timed text
and MKV SubRip/ASS, including style removal. Its simulator and scratch files are removed
after recording the result.

An iPad simulator smoke test verified local H.264/AAC and HEVC/AAC playback
from a saved seek position, pause and teardown, with external playback enabled.
On physical Apple TV, test H.264/AAC and HEVC/AAC separately. Confirm the
receiver shows the movie with Screen Mirroring disconnected, exercise Siri
Remote Play/Pause and seeking, and check the output refresh rate with a 24 fps
fixture and Match Frame Rate enabled. Check saved position when switching back
to VLC and verify TV output stops when the app enters session-only protection.
Local playback and SDK compilation cannot establish receiver compatibility.

#### MKV and MP4 stream copy

The host validation driver exercises H.264/AAC and HEVC/AAC MKVs with 24 fps
video, B-frames and closed GOPs. It stream-copies both tracks into fragmented
MP4 HLS and checks that the compressed stream hashes match. It decodes each
fragment with only its initialization segment and verifies decode timestamp
continuity. A separate input-seek check starts near 12.5 seconds and compares
the resulting video packets with the third HLS fragment. The host stream-copy
driver rejects Opus because it exercises the copy path only.

Use a fresh run identifier for `RUN_ID`.

```sh
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.video_airplay_remux --output tmp/test-results/RUN_ID/mkv-remux.json
```

The driver uses host FFmpeg and ffprobe with synthetic media. Only the JSON
report survives the build manager's scratch lease.

On iOS, the same preference enables indexed local MKV and MP4/MOV with H.264 or HEVC
and separate AAC, AC-3 or E-AC-3 audio renditions. Mono, stereo or 5.1 Opus
tracks convert to AAC-LC. A master playlist exposes audio renditions and
plain-text WebVTT derived from embedded SubRip, WebVTT, ASS/SSA or MP4 timed text and ordinary local
SRT or WebVTT sidecars. Audio and subtitle menus select the AVPlayer media
options while on TV and read the current selection when reopened, including
changes initiated by the receiver. The master declares the output codecs,
video dimensions, frame rate and HDR range, and retains language, forced subtitle,
SDH and audio-description roles for native receiver menus. Commentary remains
manually selectable. A bounded stream-info probe resolves cadence and color
from the bitstream when the container omits them. HDR variants include both VIDEO-RANGE and
FRAME-RATE; Apple rejects an incomplete or incorrect HDR declaration.
Host tests cover these declarations and bounded HTTP requests; actual Apple TV
menu presentation and selection need receiver acceptance.
The subtitle codec is declared as `wvtt`; each VOD subtitle playlist covers the
whole video, including empty segments. The timestamp map includes the remuxer's
video presentation offset. ASS overrides/drawings and MP4 timed-text style boxes
are removed; text and line breaks remain. PGS and other bitmap tracks are omitted.
MOV sample indexes use decode timestamps, so the adapter resolves presentation
timestamps at selected keyframe boundaries before creating HLS segments. Opening
and per-fragment I/O remain bounded. MP4 retains its sample decode times and
durations rather than reconstructing them from average frame cadence; audio and
subtitle clocks include the same offset used to avoid negative initial DTS.
Unsupported MP4/MOV profiles fall back to
AVFoundation's file playback after rechecking access; that path exposes native
embedded tracks without sidecars. MKV still requires the remux profile.
Each fragment starts a fresh
decoder and encoder, using audio preroll and a shared AAC sample grid so
fragments can be generated out of order. The HEVC bitstream and color signaling
stay with the video. `MKVRemux.m` uses FFmpeg 9.0 headers
against the symbols in pinned VLCKit. It reads Matroska cues, validates the
random-access sample at each requested boundary, and stream-copies that range
into fragmented MP4. It bounds input I/O, fragment size and request time and
rejects unsupported streams and codec configuration changes. The HLS server
binds the Wi-Fi interface for receiver access and serves only the current
unpredictable capability URL. It keeps fragments in memory and rechecks
the source revision and external playback policy during each response.
Up to four responses hold request slots. A seek that overlaps older responses
waits up to ten seconds for a slot, rechecking access while it waits. Host
regressions cover uncached forward/backward video and audio requests, revocation
during that wait and the busy deadline; they do not establish physical receiver
behavior. Native fixtures also cover rapid forward skips, direction changes and
end-of-file clamping while the receiver loads or has a pending seek.
Failure diagnostics record fragment indices and track IDs or native error
domains/codes, without logging source filenames or capability URLs.
Closing the player stops the server and releases its file descriptor.
In `mobile/player.py`, remux preparation recovers its worker result into a
provisional cleanup scope. Only an authorized, revision-checked native handoff moves
that stream into the player's retained `mkv_stream`. Rejected or cancelled
preparation drains provisional cleanup; detach drains retained-stream cleanup.
Retirement waits for native disposal, discovery and tracked control commands
before releasing streams, then finishes progress writes before closing content
and releasing protection. Host lifecycle tests cover cancellation during remux
and close, failed handoff/retry, and authorization checks on file fallback.
Selecting the phone in the same picker returns to
VLC within the same presentation. At open HEVC GOP boundaries, a fragment can
hold its final frame briefly across the gap left by dropping leading pictures
that depend on both sides of the boundary.

An iPhone simulator probe linked the pinned VLCKit binary, requested
fragments out of order and decoded each fragment independently. Compressed
stream hashes matched for AVC/AAC, HEVC/AAC, HEVC/AC-3 and HEVC/E-AC-3,
and AVPlayer loaded the generated HEVC/AAC stream over HTTP and resumed
from a saved 12.5-second seek. An HEVC Main 10 fixture retained its compressed
video, PQ transfer and BT.2020 primaries while its six-channel Opus audio
converted to six-channel AAC. AVPlayer resumed that stream at 12.5 seconds
and continued playing after a backward seek to 2.4 seconds.

Physical acceptance includes Dolby audio selection, HDR color and timing,
Apple TV retrieval of the playlist and segments, forward and backward remote
seeks, handoff to VLC and revocation during streaming. Test the fallback
when the receiver cannot access the phone over Wi-Fi. TrueHD/Atmos uses a
supported alternate track if available. Dolby Digital Plus Atmos and receiver
output have separate hardware acceptance.

## Cloud range playback

`playback.py` retains provider content and `transport.py` serves bounded
loopback byte ranges with revision and credential checks. LocalCrypt, remote
and crypt sources supply decoded file bytes. Remote reads use bounded
read-ahead and retry from the held position. A failed range should expose
retry/close while preserving intent. `buffering.py` owns thresholds. During
starvation, present a wait state, hold the clock, and resume only if the latest
intent allows it. Test slow headers, delayed body and recovery with
`test_video_stream_latency.py` and the native `video_stall_probe.py`.

Initial inline playback has a 20-second startup deadline while Play is
requested. Output can start before a duration is available. A provider read
failure takes precedence over a decoder error. VLC can report end of media
without decoding any tracks, so the desktop adapter classifies that as a
failed open. Desktop VLC can also report an AVI video track that yielded no
frames while its audio decoded. Generic decoder results can leave the exact
container, codec or corruption cause unknown. The focused desktop regressions
in `test_video_open.py` exercise the window, transport and decoder together.

## Playback tool ownership

`session.py` validates times and preferences. `services/documents/video_settings.py`
and `video_progress.py` persist settings/position. `video_migration.py` reads
legacy state and `video_state.py` binds encryption and credential lifetimes.
LocalCrypt writes through the encrypted provider. Session-only state uses the
credential ZIP password. Remote durable state requires its authenticated scope.
Identity and revision distinguish a moved movie from a replaced one.
Completion resets position; readable settings remain. See the
[storage and privacy contract](video-player.md#storage-and-privacy-contract).

## Verify playback changes

```sh
python3 dev.py test desktop 'test_video*.py'
python3 dev.py test mobile test_video_player.py
```

The desktop fixtures under `Python/tests/readers/fixtures/video/` cover
MP4/MKV × AVC/HEVC × AAC/Opus with decoded picture/audio, pause, seek and
captions. Custom encoder tests use FFmpeg. The mobile host covers credentials,
mount/retirement, settings and native-source staging. Compile native adapters
with `mobile_build.validation.video_native` for `android` or `ios` in the
project environment.

Run the generated chaptered and chapterless clips through the normal mobile open path on owned disposable devices:

```sh
python -m mobile_build.validation.document_storage_tools ios --probe video-chapters --output tmp/test-results/ios-chapters
python -m mobile_build.validation.document_storage_tools android --probe video-chapters --output tmp/test-results/android-chapters
```

Both probes check marker positions, accessible chapter labels, skips while paused and playing, and clearing markers when the stream changes.
Native AirPlay exposes source VLC chapters in the iOS player and tries the current AVAsset's timed metadata when VLC has no rows. Chapter skips use the active AVPlayer's seek and its completion handling. MKV and compatible MP4 served through the HLS remux use the source timeline on the phone. The sender's public AirPlay APIs have no contract for installing custom chapter markers or skip buttons on a receiver. Apple's navigation marker groups and custom transport menus belong to a tvOS app's player. Direct file metadata may be presented by a receiver. [AVAsset chapters](https://developer.apple.com/documentation/avfoundation/avasset/loadchaptermetadatagroups%28bestmatchingpreferredlanguages%3Acompletionhandler%3A%29?language=objc) · [AVPlayer seek](https://developer.apple.com/documentation/avfoundation/avplayer/seek%28to%3Atolerancebefore%3Atoleranceafter%3Acompletionhandler%3A%29?language=objc) · [tvOS navigation markers](https://developer.apple.com/documentation/avkit/presenting-navigation-markers)

Use `video_probe_tools` with a current video-enabled package for native
fullscreen, rotation and remote/crypt matrices. Its synthetic HTTPS/WebDAV
fixture retains TLS and disposable trust. `video_chrome_tools` checks iOS menus,
fade and geometry. `video_fold_probe.py` checks retained playback and hinge
exclusion. `video_remote_resume_tools` checks a delayed MKV range at a saved
seek. `video_privacy_tools` checks app switching, concealment, callback
retirement and paused resume. For ordinary local iOS playback,
`video_chrome_tools --background-audio` compares a foreground pause with three
paused switches to Settings and back. Each explicit resume must advance the
clock and deliver fresh pictures and audio beyond the first second.
`video_android_audio_tail --background-resume` checks the same transition on
Android. When Android destroys VLC's inline surface in the background, the
next explicit Play reopens the decoder at the held position and binds the
surface again. Retained surfaces resume their existing input.
`video_android_audio_tail --captions --startup-control` checks ordinary
startup before testing caption restoration and Replay. `--stereo-aac` changes
only the audio tracks and `--avc-aac` changes both encodings while keeping the
stream endpoints. Record real codec/clock observations and the
exact payload. Use [hardware acceptance](hardware-acceptance.md) for physical
touch, audible sync, route changes, Split View and receivers.

## Further reading

- [Video storage and playback contracts](video-player.md)
- [iOS HDR pause and resume](hdr-play-pause.md)
- [Hardware acceptance](hardware-acceptance.md)
- [Desktop controls](../user/user.md)
- [Mobile controls](../user_mobile/user_mobile.md)
