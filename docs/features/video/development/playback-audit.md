# Desktop and mobile video playback audit

Source audit and focused validation: October 29, 2026. This records implemented
behavior and remaining gaps; it is not blanket physical-device certification.

## Functionality comparison

| Capability | Desktop | Android | iOS / Duo |
| --- | --- | --- | --- |
| Decoder | Qt Multimedia / FFmpeg | LibVLC 3.7.5 | Pinned VLCKit package distributing a 4.0 prerelease |
| Opening a video | Starts through guarded Play | Starts after presentation and audio checks | Starts after presentation and audio checks |
| Local / LocalCrypt / cloud / crypt | Retained provider streams | Retained provider streams | Retained provider streams |
| Seek and ten-second skips | Slider, buttons, Left/Right | Slider and buttons | Slider and native bar buttons |
| Volume and mute | In-app slider and mute; M shortcut | Device volume; in-player mute and M shortcut | Device volume; in-player mute and M shortcut |
| Embedded audio/subtitles | Track selectors | Native menus | Native menus and compact-bar overflow |
| External subtitles | Explicit Load SRT picker; UTF-8 plain-text cues, 8 MiB limit | Matching SRT/VTT/ASS/SSA sidecars plus source browser; 8 MiB/file | Same sidecars plus current-source file browser |
| Fullscreen | Shared window fullscreen; controls remain laid out below video | Immersive system bars; timed control hiding | Native immersive controller; timed control hiding |
| Centering when controls change | Video centered in its layout allocation above controls | Full-surface video with overlaid controls | Full-surface video behind native bars and timeline |
| Chapters | Bounded Matroska ChapterAtoms / MP4 chpl reader; unsupported chapter tracks omitted | VLC chapter menu | VLC chapter menu, including fold deck |
| Duo laptop posture | Not applicable | No platform fold split implemented | Horizontal partial-fold split: upper movie, persistent lower deck |
| Keyboard controls | Space, F, Escape, Left/Right, M | Space, arrows, M/F/G/P/N, Escape; touch lock | Space, arrows, M/F/G/P/N, Escape; touch lock |
| Floating playback | Always-on-top application window | OS picture in picture | VLCKit picture in picture |
| Cast | No player receiver UI | VLC receiver discovery | VLC receiver discovery; no AirPlay video routing implementation |
| Network starvation hold | Qt handles decoder buffering; application does not wire the mobile network-hold coordinator | Renderer progress gates network holds; readiness alone never pauses buffered video | Same; exact-file slow-read probe covers iOS |
| Rewind cache | Shared memory ranges per open remote video | Same shared memory ranges | Same shared memory ranges |
| Resume position | Local durable state; private state via encrypted provider | Same storage policy | Same storage policy |
| Cloud resume | Session-only: credential ZIP password | Session-only: credential ZIP password | Session-only: credential ZIP password |
| Leaving the app | Session-only content locks; ordinary desktop playback may continue | Inline pauses; explicit PiP/cast may continue until lock/interruption policy intervenes | Inline pauses; explicit PiP/cast may continue until lock/interruption policy intervenes |
| Audio interruption protection | Desktop privacy/application-state owner; no native mobile-style call/headset/focus observer | Audio focus, noisy-route, device-loss and screen-off handling | Audio session, route-loss, call and protected-data handling |
| Session-only external playback | Floating denied | PiP/cast denied | PiP/cast denied |
| Error feedback and retry | Safe transport categories; guarded Play retry | Safe transport categories; guarded Play retry | Safe transport categories; guarded Play retry |
| Speed and aspect | 0.5–2×; Fit/Fill/Original | Same | Same |
| Folder queue and automatic next | Natural order; opt-in next | Same current-source queue | Same current-source queue |
| Exact time / undo | G; Ctrl+Z; eight-second seek undo | Menu and visible undo | Menu and visible undo |
| Subtitle size/delay, audio sync | External SRT size/delay only; no Qt embedded/audio offset API | VLC adjustments; font/language updates reopen decoder | VLC adjustments |
| Cached range display | Green byte-range strip, approximate time mapping | Cache ≈ strip | Cache ≈ strip |

Thumbnail scrub previews, desktop automatic sidecars, desktop embedded subtitle
styling/delay and audio sync offset, mobile system-media transport controls and a
process-wide cache pressure budget remain absent. The new tools have SDK/host
validation; physical interaction acceptance is still outstanding.

## Confirmed oversights and follow-up priorities

1. **Native range contract coverage was incomplete.** Python video requests grew
   to 4 MiB while native remote reads still rejected more than 1 MiB. This caused
   a generic playback failure despite credentials being available. The bridge now
   admits bounded 4 MiB reads. Go tests check the exact boundary and oversize
   rejection for plain and crypt remotes; a Python test uses the rebuilt native
   library and the actual VideoContent path. A permissive mock alone cannot
   validate this cross-language contract.
2. **Network waiting and manual Pause were conflated with decoder state.** Mobile
   now tracks temporary network holds separately. Readiness can resume only an
   outstanding playback request, with current audio/access approval. A manual or
   lifecycle pause cancels recovery. The exact-file AVI slow-read probe checks a stationary
   checkpoint and rendered frame count, recovery and manual Pause. Slow prefetch
   alone no longer pauses playable data or shows a waiting message. Requested
   Play/Pause state also survives delayed native command completion. Desktop still needs an equivalent slow
   source / actual-clock acceptance test before claiming identical recovery.
3. **Rewind data was owned by each HTTP stream.** A seek could discard useful
   decrypted ranges and fetch them again. Remote videos now retain a bounded
   shared LRU across streams, with concurrent duplicate-fetch coalescing. The
   default is 128 MiB per open video, configurable in `buffering.py`. This is about
   a minute at 18 Mbit/s, not a time guarantee for every bitrate. Several desktop
   video windows multiply that budget; there is no process-wide pressure budget.
4. **Android paused-seek accounting was corrected.** Slider, skips and chapter
   selection now share one guarded seek method. A deferred target, including zero,
   survives Pause and is consumed on Playing. SDK compilation verifies the API;
   physical Android timing still needs acceptance.
5. **Failure classification and retry were improved.** Transport failures use safe
   access/changed/read/busy categories. Native premature stop/error releases the
   spinner and exposes guarded Play retry from the retained position. Desktop
   likewise uses safe errors and reloads its source on explicit retry. Changed
   resources still require reopening. Actual codec/connection diagnostics remain
   deliberately separate from unverified claims that a source file is damaged.
6. **Subtitle workflows differ.** Mobile now has a current-source arbitrary subtitle browser as well as discovery. Desktop still lacks automatic sidecar discovery and supports external SRT only. ASS styling belongs to VLC; desktop external captions are plain text. Mobile offers audio/subtitle sync and sizing; desktop exposes external SRT size/delay only.
7. **Immersive and input behavior differ.** Desktop retains its controls in the
   layout instead of mobile-style overlays/auto-hide, and mobile now has explicit external-keyboard shortcuts, in-player mute, double-tap skips and touch locking. Native touch/keyboard acceptance remains separate from API compilation.
8. **Device acceptance remains narrower than codec admission.** Extension lists
   do not prove decoding, audio quality or A/V synchronization for every codec.
   PiP/cast routing, receiver playback, actual lock timing and Android starvation
   timing still need physical-device checks. Desktop Windows/Linux decoding and
   headset/call behavior need their own acceptance. The Duo simulator verifies
   view geometry and native clock behavior, not a particular cloud connection's
   sustained throughput.

9. **Cloud startup still has metadata latency.** Each new HTTP stream admits the
   source revision and opens the retained provider again; native range requests
   also check revision before/after fetching. Cached rewind avoids retransferring
   video bytes but cannot promise zero network operations. Measure actual crypt
   first-frame and seek latency before changing/coalescing these checks; keep
   grant revocation and replacement detection intact.

10. **Active buffering now retains the display-awake request.** Requested visible
    playback owns it until explicit Pause, completion, error, hiding, external
    playback or closing. Physical-device screen-timeout acceptance remains.
11. **AVI range bursts could be rejected prematurely.** Four active reads formerly
    caused an immediate HTTP 503 for a replacement range. Admission now waits up to
    ten seconds, while revocation/closing cancels that wait. A regression checks
    that a fifth request succeeds when a slot is released.
12. **Moving video could show a stale buffering spinner.** Native frame statistics
    arrive in batches. Progress in either the clock or frame counter now clears
    the indicator; a hold retains the last observed rendered-frame position.

## Buffer policy and ownership

`Python/features/video/buffering.py` owns `DEFAULT_BUFFERING` and
`BufferingPolicy`: `memory_bytes` (128 MiB), `range_bytes` (4 MiB),
`read_ahead_chunks` (4), `chunk_bytes` (1 MiB) and `stall_seconds` (0.5).
`range_bytes` must not exceed the Go bridge's 4 MiB limit. Cache allocation grows
only as data is read. Closing clears it; it is not a disk cache or an offline
copy. Credential checks still guard cache hits, and source revision checks guard
stream admission and new native range fetches. A seek into cached data avoids
refetching those bytes; metadata admission can still require a cloud round trip.

The implementation owners are [content and provider reads](../../../../Python/features/video/playback.py),
[buffer policy and cache](../../../../Python/features/video/buffering.py),
[HTTP transport](../../../../Python/features/video/transport.py),
[desktop player](../../../../Python/features/video/ui/player.py),
[mobile lifetime](../../../../Python/features/video/mobile/player.py),
[Android player](../../../../Python/features/video/mobile/android/io/github/ispaure/logistics/video/VideoPlayer.java),
[iOS player](../../../../Python/features/video/mobile/ios/VideoPlayer.m),
[resume storage](../../../../Python/services/documents/video_progress.py) and
[native remote reads](../../../../mobile_build/rclone_bridge/remote_document.go).

## Validation scope

Host checks cover provider ranges, revision/grant enforcement, cache eviction,
concurrent fetch coalescing, streaming teardown, queued-byte revocation, real
rclone plain/crypt decode, native bridge range limits and cross-stream rewind
reuse. Mobile lifetime tests cover overlapping waits and readiness while hidden.

The reusable [native video buffer probe](../../../../mobile_build/native_tests/tests/logisticsmobile/video_buffer_probe.py)
checks playable prefetch, manual-pause precedence and rotation for MP4 and AVI.
The [real-stall probe](../../../../mobile_build/native_tests/tests/logisticsmobile/video_stall_probe.py)
uses a host fixture with controllable slow reads to check rendered-frame
starvation, held checkpoints, recovery and immediate Play/Pause feedback.
Host mocks and simulator probes do not establish physical receiver behavior or
real cloud stall quality.

## Playback tools and immediate pause follow-up

Shared queue, time parsing and validated preferences live in `features/video/session.py`.
Encrypted remote progress lives in the host’s `services/documents/video_state.py` and `video_progress.py`; the old
service path is a compatibility import. Desktop controls are in `ui/controls.py`;
mobile routing is in `mobile/controls.py`, with native UI and transient frame holds
in separate Objective-C/Java helpers. The [control guide](../user/controls.md) and
[mobile guide](../user_mobile/controls.md) describe implemented behavior and limits.

Manual Pause retains a frame and checkpoint while the decoder acknowledges the
command. Audio suppression and the requested-state icon still happen immediately.
Resume seeks back to the held point if VLC continued decoding. Temporary snapshots
are discarded on privacy/retirement edges. This fixes the application's delayed
visual response path; it does not claim to make a blocked native input synchronous.
Renderer-startup snapshot failure, PiP/cast timing, actual Duo touch/fold behavior
and Android TextureView output require physical acceptance.

Session-only checkpoints now use the shared [password-bound reader-state owner](../../../development/reader-state.md), with independent clear actions and explicit previous-password migration. Device-key and credential-settings-only encryption are no longer used for session-only video progress.

## Desktop track-switch lock ordering

The desktop player constructs its audio output through the fixed native Qt
Multimedia declaration in `ui/audio_output.py`. The output and its declaration
engine belong to the video window and retire with it. Audio volume, mute, track
selection and subtitle decoding continue through the normal Qt APIs.

This avoids a captured PySide lock inversion: a track setter holds Python's
interpreter lock while waiting for Qt's connection mutex, while an FFmpeg audio
worker holds that mutex and enters `QAudioOutputWrapper::disconnectNotify`,
which needs the interpreter lock. Qt's native audio output has no Python virtual
callback on that worker. The decoder regression verifies native ownership,
repeated audio/subtitle changes, preserved volume/mute and output destruction;
the existing real codec, embedded-caption and external-SRT checks remain required.
`test_video_audio_output.py` also checks construction and retirement on desktops
without the optional FFmpeg fixture generator.
