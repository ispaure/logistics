# Video Player development

Open a local video through **File Browser** on desktop or **Open Document**
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
| Provider admission, read-ahead or errors | `playback.py`, `transport.py`, `buffering.py` |
| Chapters and folder queue | `chapters.py` reads Matroska ChapterAtoms and MP4 chpl data. `session.py` orders the queue. |
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

The iOS-only `native_video_airplay` mobile preference defaults off. On open,
`IOSAirPlayVideo` admits ordinary local MP4, MOV and M4V sources with an
external-playback grant and a guarded physical file path. The retained source
still owns revision checks and the shared resume checkpoint. AVPlayer reads the
file URL directly and AVPlayerViewController supplies the route picker and
system remote controls. Revocation detaches the current item and disables
external playback. Protected, encrypted, provider-decoded and cloud content
use the existing VLC path. Selecting the player on each open lets the user
switch back after a format or receiver failure.

An iPad simulator smoke test verified local H.264/AAC and HEVC/AAC playback
from a saved seek position, pause and teardown, with external playback enabled.
On physical Apple TV, test H.264/AAC and HEVC/AAC separately. Confirm the
receiver shows the movie with Screen Mirroring disconnected, exercise Siri
Remote Play/Pause and seeking, and check the output refresh rate with a 24 fps
fixture and Match Frame Rate enabled. Check saved position when switching back
to VLC and verify TV output stops when the app enters session-only protection.
Local playback and SDK compilation cannot establish receiver compatibility.

#### MKV stream copy

The host validation driver exercises H.264/AAC and HEVC/AAC MKVs with 24 fps
video, B-frames and closed GOPs. It stream-copies both tracks into fragmented
MP4 HLS and checks that the compressed stream hashes match. It decodes each
fragment with only its initialization segment and verifies decode timestamp
continuity. A separate input-seek check starts near 12.5 seconds and compares
the resulting video packets with the third HLS fragment. The host stream-copy
driver rejects Opus because it exercises the copy path only.

```sh
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.video_airplay_remux --output test-results/mkv-remux.json
```

The driver uses host FFmpeg and ffprobe with synthetic media. Only the JSON
report survives the build manager's scratch lease.

On iOS, the same preference enables indexed local MKV with H.264 or HEVC
and one AAC, AC-3 or E-AC-3 track. If none are present, the adapter can
convert mono, stereo or 5.1 Opus to AAC-LC. Each fragment starts a fresh
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
Closing the player stops the server and releases its file descriptor.
Admission failure selects VLC. **Use VLC** reopens the current file at the
shared checkpoint without changing the preference.

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

Use `video_probe_tools` with a current video-enabled package for native
fullscreen, rotation and remote/crypt matrices. Its synthetic HTTPS/WebDAV
fixture retains TLS and disposable trust. `video_chrome_tools` checks iOS menus,
fade and geometry. `video_fold_probe.py` checks retained playback and hinge
exclusion. `video_remote_resume_tools` checks a delayed MKV range at a saved
seek. `video_privacy_tools` checks app switching, concealment, callback
retirement and paused resume. Record real codec/clock observations and the
exact payload. Use [hardware acceptance](hardware-acceptance.md) for physical
touch, audible sync, route changes, Split View and receivers.

## Further reading

- [Video storage and playback contracts](video-player.md)
- [iOS HDR pause and resume](hdr-play-pause.md)
- [Hardware acceptance](hardware-acceptance.md)
- [Desktop controls](../user/user.md)
- [Mobile controls](../user_mobile/user_mobile.md)
