# Desktop video playback parity brief

Prepared November 1, 2026 against the current working tree, including ongoing
iOS control changes. This is an implementation plan, not a claim of tested parity.
Use the [original acceptance contract](video-player.md) and
[playback audit](playback-audit.md) for the existing storage and playback rules.

## Current reading guide

The comparison and sequence below preserve the November 1 planning baseline;
“Desktop today” in that table describes the pre-implementation state. They are
not the current capability inventory. Current desktop playback uses macOS libmpv
colour output with a VLC compatibility path; Windows/Linux use VLC SDR output.
See the [current desktop guide](../user/user.md) and
[implementation owners](development.md#macos-hdr-and-tone-mapping).
Windows/Linux HDR implementation and verification remain pending, and physical
macOS HDR brightness remains unverified. Existing native/host results do not
establish those acceptance gates or real receiver and OS lock behavior.

## Outcome and scope

Bring desktop video to the mobile feature level with mouse, keyboard and optional
touch input. Preserve document docking, detached windows, volume controls and
Original size. Exclude HDR output work, HDR controls and HDR certification for now.
Use SDR fixtures for acceptance. No mobile redesign is required.

Parity means equivalent actions and playback guarantees, not copying UIKit or a
folded phone layout. Desktop split/docked windows need responsive controls; Duo's
hinge-specific deck remains mobile-only. OS media transport controls and thumbnail
scrubbing are absent from the current mobile baseline and are separate work.

## Pre-implementation differences verified in source

| Area | Mobile baseline | Desktop today / required change |
| --- | --- | --- |
| Engine | Native VLC adapters | Qt Multimedia/FFmpeg; establish a backend capable of missing subtitle, sync and receiver features. |
| Viewing surface | Controls overlay a stable movie surface; timed hiding; accessible reveal | Controls and external captions occupy layout rows. Add overlays without moving/resizing the movie when chrome changes. |
| Identity and navigation | Filename, source label and Show in folder | Window title only; add in-surface identity and provider-aware folder reveal. |
| Input | Keyboard, side double-tap skips, center double-tap Play/Pause, control lock | Core keyboard actions already exist, including G/P/N/Ctrl+Z. Add surface gestures and control lock with visible unlock/Escape. |
| Subtitles | Automatic matching sidecars and source browser; SRT/VTT/ASS/SSA; 32 discovered files, 8 MiB/file | Explicit SRT picker, plain-text application renderer, size/delay for external SRT only. Add discovery, formats and embedded adjustments. |
| Audio | Preferred language and audio sync offset | Language and tracks exist; audio delay is stored in shared settings but not applied by desktop. |
| Playback intent | Immediate requested-state feedback, held pause frame, starvation recovery that respects manual Pause | Button follows Qt decoder state; transport receives no waiting callback. Add explicit intent and measured frame/clock recovery. |
| Resume startup | Saved duration displayed before metadata; pending resume survives startup | Restores position after duration arrives; does not wire saved duration into its timeline/checkpoints. |
| Floating and receivers | Explicit PiP and VLC receiver discovery | Whole-window always-on-top mode, no Cast UI. Add compact playback and receiver workflow. |
| Lifecycle | Inline pauses on background; explicit external playback exceptions; interruption/route-loss pauses | Restricted video has application-deactivation concealment; ordinary playback can continue. Define desktop visibility, lock and audio-event policy. |

Already shared: Local/LocalCrypt/remote/crypt retained providers, revocable range
transport, bounded memory rewind cache, encrypted/revision-bound progress, speed,
Fit/Fill, track selection, chapters, folder queues, opt-in automatic next, exact
time and eight-second seek undo. Preserve these rather than implementing them again.
Desktop chapter parsing is bounded MP4/Matroska metadata, whereas mobile uses VLC;
chapter names/order and paused selection still need cross-backend acceptance.
iOS currently offers a direct Fit/Fill toggle; Android and desktop also support
Original size. Keep that desktop capability.

## Implementation sequence

1. **Prove the desktop backend before broad UI changes.** Introduce a small
   desktop playback adapter separating decoder operations/events from `VideoWindow`.
   Keep providers, transport, progress and settings outside it. First wrap Qt to
   preserve behavior, then evaluate a bundled LibVLC adapter as the leading
   candidate for subtitle formats, embedded subtitle delay/size, audio offset,
   chapter access and casting. Do not assume the mobile SDK can be reused as a
   desktop binary. Prove video embedding in docked/detached Qt windows, frame
   progress, hardware/software fallback, subtitle URL loading and clean teardown
   on macOS, Windows and Linux. Check distributable binaries, licensing, packaging
   and dependency loading through the existing build owners. Gate: packaged SDR
   playback and track-switch/close regressions pass without an installed VLC app.
   If the candidate fails, record the unsupported capabilities and resolve the
   backend choice before claiming full parity; do not expose ineffective settings.

2. **Make playback state authoritative.** Separate requested Play/Pause, decoder
   state, temporary network hold and authorization. Wire `VideoTransport.waiting`
   through the Qt thread boundary with overlapping-wait tokens. Detect starvation
   from actual presented frames/clock, never prefetch alone. Update the button and
   silence audio immediately on Pause; retain a volatile frame/checkpoint if the
   backend acknowledges asynchronously. Recovery requires outstanding Play intent,
   visibility/external-mode eligibility and current audio/access permission.
   Manual Pause, lock, errors, interruption and close cancel recovery. Ignore stale
   events after reload/retirement. Show saved position/duration before metadata,
   keep an unknown-duration seek bar visible but disabled, preserve pending seeks
   including zero, and save decoder duration through `VideoProgress.duration`.
   Gate: slow MP4/AVI and indexed MKV resume tests check frames, clock, original
   duration, requested-state feedback and manual-pause precedence.

3. **Add immersive desktop controls.** Use a stable black video surface with
   independent title/source, caption, transport and timeline overlays. Keep key
   actions accessible in small dock panes and compact floating mode. Match the
   mobile three-second active-playback hide policy; pointer movement/tap reveals,
   menus, focus in controls, seeking, pause, startup and errors retain controls.
   Respect accessibility and reduced motion; hiding chrome must not strand keyboard
   focus. Add ten-second side double-click/tap skips, center Play/Pause, control
   lock and provider-aware Show in folder. Keep F/Escape fullscreen and all current
   shortcuts; specify gesture precedence so a double-click triggers one action.
   Gate: movie bounds stay identical across show/hide, including subtitles,
   window resize, fullscreen, docking and display scaling.

4. **Complete subtitle and sync workflows.** Extract only portable sidecar
   discovery from the mobile owner into `features/video/`; keep host pickers and
   native UI separate. List matching sidecars asynchronously after playback starts,
   with the existing count/size limits and same-source private-access rules.
   Retain `SubtitleContent` and capability URLs until the decoder releases them.
   Support browsing other folders in the current provider, all four formats,
   embedded/external selection and Off, preferred languages, subtitle size/delay
   and audio offset. Reuse validated `PlaybackSettings`; positive delay means
   later. Preserve position, rate, mute and requested Pause across decoder reloads.
   ASS styling may constrain overrides, as on mobile. Gate: real rendered cues and
   measured audio offsets, plus revoked subtitle grants and close-during-discovery.

5. **Finish floating, casting and lifecycle parity.** Make existing floating mode
   a compact, always-on-top playback view with a clear return-to-document action;
   native OS PiP is optional if equivalent desktop behavior is reliable. Add Cast
   discovery, receiver choice, stop/return and safe failure feedback through the
   proven backend. Never hand a receiver a loopback URL and assume it can reach it:
   prove backend-owned receiver transport without rebinding the provider server to
   the LAN or exposing credentials. Enforce current process/session protection at
   admission and after policy changes, not just through disabled buttons. Conceal
   titles, captions and held frames and stop protected external output on lock or
   revocation. Minimize/hidden inline playback pauses; ordinary visible desktop
   playback may continue when focus moves to another window. Explicit floating/
   cast may continue while the main document is hidden, but not through lock or
   interruption. Device removal, sleep/lock and supported platform audio events
   pause without autoplay on return. Request display-awake only for visible,
   requested playback, including buffering. Gate: real receiver and native desktop
   lifecycle acceptance on each supported OS; unavailable APIs are recorded as gaps.

## Owners and validation

Start with `Python/features/video/ui/player.py`, `ui/controls.py` and `ui/privacy.py`;
put the backend boundary and overlay helpers alongside them. Shared policy stays
in `session.py`, `playback.py`, `transport.py`, `buffering.py` and
`Python/services/documents/video_*`. Mobile reference behavior lives in
`mobile/player.py`, `mobile/controls.py` and native `PlaybackControls`/
`PausePresentation` helpers. Keep the Qt native-audio ownership workaround in
`ui/audio_output.py` while the Qt backend remains supported; track switching has
a documented lock-inversion regression.

Extend existing `Python/tests/readers/test_video_decode.py`,
`test_video_audio_output.py`, `test_desktop_video_privacy.py`, `test_video_session.py`,
`test_video_buffering.py`, `test_video_stream_latency.py`, `test_video_chapters.py`
and `test_cloud_video.py` by behavior. Run focused selectors through
`python3 dev.py test desktop <filename>`; use existing managed build/deployment
owners for packaged checks. Use retention-owned scratch workspaces and save raw
evidence only under ignored `test-results/`.

Final acceptance crosses macOS/Windows/Linux with MP4/MKV, H.264/HEVC and AAC/Opus,
then representative AVI/other admitted formats, multiple tracks, chapters and
all subtitle formats. Exercise Local, LocalCrypt, remote and crypt; slow reads,
retry, revision replacement, credential revocation, encrypted resume, automatic
next, resize/fullscreen/floating and real casting. Host mocks do not certify
audible output, sync, physical sleep or receiver behavior. Keep the existing
128 MiB per-video cache bound; a global cache-pressure budget is separate work.

Mark each step complete only with focused regression results and its stated
native/package gate. Update desktop usage and the playback comparison as each
capability lands. Implementation now uses the LibVLC adapter and Qt-painted SDR
surface, with the Qt adapter retained for compatibility regressions. The macOS
native codec, caption/font, chapter, offset, overlay and provider-lifetime checks
have run. A throttled provider also verifies that prefetch waits do not pause
healthy playback, actual starvation holds the last rendered position, and recovery
respects manual Pause. Caption composition requires a software fallback for opaque hardware
pictures; the frame bridge copies pixels into host memory. Full cross-platform/
package, native sleep/lock and physical receiver acceptance
remain separate gates; source-level functionality alone does not satisfy them.
See the [implementation owners](development.md#desktop-parity-implementation).
