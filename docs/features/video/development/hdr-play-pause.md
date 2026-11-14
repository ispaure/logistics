# iOS HDR pause and resume

## Pause presentation

`PausePresentation.m` keeps the native sample-buffer layer visible while VLC
pauses. The player retains its clock, explicit pause intent, audio suppression
and privacy checks. A few queued frames can complete before acknowledgement.
Other renderer fallbacks use a volatile snapshot. System-managed HDR is the
iOS 26+ default; Maximum remains available.

## Rendering and version boundary

1. `playback.py` retains ProviderContent and bounded memory ranges. Remote rclone
   crypt and native LocalCrypt provide decoded **file bytes**, not decoded video
   pixels. `transport.py` exposes authorized loopback HTTP ranges. There is no
   color conversion in this transport. VLC owns container demuxing; MKV requests
   `mkv_trusted,mkv` for indexed seeking. Local and remote sources converge here.
2. `mobile/ios.py` passes the transport URL, settings, authorization and position
   through Rubicon to `LGVideoController`. `playbackMedia` sets caching, language,
   audio time stretching and complete-frame decoding preferences. No HDR filter,
   gamma adjustment or forced software decoder is configured.
3. `VideoPlayer.m` requests `samplebufferdisplay,any`. Actual decoder selection
   belongs to VLC. A sample-buffer layer proves that presentation surface exists;
   it does not prove VideoToolbox hardware decoding or HDR-preserving fallback.
4. The drawable installs VLC's view into `movie`; recursive configuration targets
   `AVSampleBufferDisplayLayer` only. iOS 26+ requests automatic/high; iOS 17–25
   requests extended range. Picture sizing affects geometry; subtitles and controls
   are separate. There is no app-owned pixel conversion or enqueue callback.
5. Native Pause/Resume does not deliberately recreate, flush, retag or change the
   dynamic range of that layer. Privacy concealment/retirement can hide it;
   restoration is subject to the existing access gates. Previously, ordinary
   Pause alone added the separate snapshot overlay.

The project pins VLCKit commit `2e0868f5ed40fe59cd92f377645fdcc260c6e759`.
Its [package manifest](https://github.com/videolan/vlckit/blob/2e0868f5ed40fe59cd92f377645fdcc260c6e759/Package.swift)
selects `VLCKit-4.0-20260929-1631.zip`, checksum
`f37c8dbdd4427d1a3f5d75dc4b8bd1ae863cef4426f9a405a2fd1c5c9012f1fb`.
The inspected cached iPhoneOS framework contains
`4.0.0-dev-39228-g48b12f61c8`; its Info.plist's generic `1.0` is not a useful
libVLC version. The package's compile script instead names `005e69e67`.
The exact binary revision could not be retrieved from the GitHub mirror;
VideoLAN's raw source endpoint returned a bot challenge. Do not equate these
revisions or substitute latest upstream as evidence about the bundled binary.

As a **qualified reference only**, the package-script revision's
[VLCSampleBufferDisplay.m](https://github.com/videolan/vlc/blob/005e69e67/modules/video_output/apple/VLCSampleBufferDisplay.m)
uses CVPixelBuffers, creates a CMVideoFormatDescription from each image buffer,
creates a timed sample buffer and enqueues it. Non-CVPX inputs use a BGRA
converter, so that fallback must not be assumed HDR-capable. Rotation is another
conversion boundary. Its VideoToolbox decoder selects 10-bit video-range buffers
for applicable inputs and maps primaries, transfer and matrix into the format
extensions. These observations are not a binary-level verification of all HDR
metadata, Dolby Vision profiles, or hardware decoder selection.

## Transition diagnostics

Set environment variable `LOGISTICS_VIDEO_HDR_DIAGNOSTICS=1`, or the development
app's Boolean Info.plist key `LGVideoHDRDiagnostics`. `[VideoHDR]` logs occur on
Play/Pause requests, asynchronous player state notifications and mode changes.
Each includes monotonic uptime, media clock, layer identity, overlay presence,
requested/effective dynamic-range preference, selected codec/profile/level,
libVLC version/changeset, screen
EDR headroom and renderer readiness. On iOS 17.4+, a temporary copy of the
**displayed** pixel buffer supplies its FourCC and allowlisted attachments:
primaries, transfer, YCbCr matrix, mastering display, content-light and ambient
viewing metadata. No image bytes, media URLs or per-frame samples are logged.
Copies are released immediately; diagnostics are off by default.

Interpret `x420` as 10-bit bi-planar video range, `xf20` as 10-bit full range,
`420v` as 8-bit video range and `420f` as 8-bit full range. PQ/BT.2020 is consistent
with HDR10, HLG with HLG output; neither proves preservation of Dolby Vision
RPU metadata. Missing attachments mean absent from this displayed-buffer copy,
not necessarily absent from the compressed stream or original CMSampleBuffer.
Presence does not prove the compositor used an attachment. EDR headroom greater
than one alone does not prove accurate HDR or decoder hardware acceleration.

VLCKit does not expose the enqueued CMSampleBuffer or VTDecompressionSession to
this owner. Source bit depth, hardware use, sample-buffer extensions and DV
handling need source/decoder evidence: inspect a consented local source using
`ffprobe -show_streams`, correlate with these transitions, and use a separately
instrumented build of the **binary-matching** VLC renderer/decoder if needed.
Log module selection, VT hardware-use status and color-only format extensions at
first frame and state changes, never source URLs or per-frame image contents.
Compare source metadata with buffer metadata before declaring loss; if metadata
is stable but luminance changes, investigate compositor behavior using a fixed
HDR test pattern and physical display measurement. Do not infer missing metadata
is the cause merely because its attachment is absent.

## Reproduction and regression checks

The existing `video_chrome_tools --hdr --pause-transitions --framework FRAMEWORK --output OUTPUT`
compiles current production code against an existing simulator framework, runs
on a manager-owned disposable simulator and removes it and scratch builds.
Use a fresh ignored `test-results/` output. Without `--hdr` it supplies SDR H.264.
The shared fixture now calls the production Pause action, tests automatic and
maximum modes, and records playing/paused/resumed metadata. It requires Pause
acknowledgement, advancing time on resume, stable layer identity/format/attachments
and no snapshot overlay. It also requires the requested mode to actually reach
the layer and PQ fixtures to retain BT.2020 primaries, PQ transfer and BT.2020
matrix attachments. Missing metadata cannot pass merely by staying absent. Automatic is accepted as an HDR preference; actual HDR output remains
a separate observation. The physical `video_hdr_device_tools` shares these
checks, but replaces/restores the supplied app and should only be used with the
appropriate device/app deployment authorization. Simulator output cannot certify
screen luminance or physical VideoToolbox use. Physical reports additionally
require 10-bit video-range output and EDR headroom above one in every transition;
the runner fails on unsuccessful, incomplete or non-HDR reports after saving the
evidence. This operational HDR check still does not establish color accuracy.

On an iPhone with the newly built controller:

| Content/action | Acceptance |
| --- | --- |
| HDR10 dark static ramp, Play → Pause → Play | Stable shadows and gradations; no overlay; metadata stable |
| HDR10 bright pattern and dark scene with highlights | Retain genuine HDR highlights; no compensating brightness lift |
| HLG | Correct HLG tags/output if supported, stable transitions |
| Dolby Vision, recording each profile/base-layer type | No regression; verify supported profiles individually, including dynamic metadata |
| SDR H.264 and HEVC | No color or pause regression |
| Same source local and through rclone crypt ranges | Same output metadata and visual result; no buffering regression |
| Automatic and Maximum, fullscreen and windowed | Stable transitions within each mode; mode differences may be legitimate |
| Seek while paused, resume, subtitles, starvation, privacy lock | Existing clock, controls, access and buffering behavior retained |
| Hardware-capable HEVC source | Confirm active hardware decoder; no performance/battery regression |

Keep brightness, ambient light, display settings and thermal state stable; record
OS, device, source metadata, mode, layer identity and transition uptime. Repeat
with controls shown/hidden. Compare both images against a known HDR reference or
measurement, not the assumption that the brighter picture is correct. If the
shift remains without a snapshot, retain the native presentation and use the
metadata comparison to isolate VLC versus Apple; do not add arbitrary gamma.

No public bridge API, framework dependency, minimum OS, SDK pin or rendering
engine changed. Buffer diagnostics require iOS 17.4 and are availability guarded.

## Validation limits

The transition probe checks layer identity, pixel format, color attachments,
dynamic range, resumed clock and absence of a snapshot over the sample-buffer
layer. Simulator results with unit headroom establish transition contracts.
Measure luminance and verify hardware HEVC and full-range display behavior on
a supported device. The physical probe attempts normal-app restoration even
if QA cleanup fails, and reports cleanup and restoration independently.
