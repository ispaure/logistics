# iOS HDR pause and resume

`PausePresentation.m` keeps the VLC sample-buffer layer visible through Pause.
Queued frames can finish before acknowledgement. Other renderers can use a
volatile snapshot. iOS 26+ defaults to system-managed range and offers Maximum.

## Renderer boundary

`VideoPlayer.m` requests `samplebufferdisplay,any`. VLC owns demuxing and
decoder selection. The app configures `AVSampleBufferDisplayLayer` for
automatic/high on iOS 26+ and extended range on iOS 17–25. Transport serves
encoded file bytes. The renderer can convert non-CVPX input to BGRA.

Compare the packaged VLCKit changeset with renderer source before attributing
behavior. The pinned package's advertised build source and the inspected
binary's changeset differ.
[VLCKit package](https://github.com/videolan/vlckit/blob/2e0868f5ed40fe59cd92f377645fdcc260c6e759/Package.swift) ·
[Renderer reference](https://github.com/videolan/vlc/blob/005e69e67/modules/video_output/apple/VLCSampleBufferDisplay.m)

## Diagnose a transition

Set `LOGISTICS_VIDEO_HDR_DIAGNOSTICS=1` or Boolean `LGVideoHDRDiagnostics`.
Compare the Play/Pause/Resume `[VideoHDR]` records for layer identity, overlay,
clock, range request and EDR headroom. On iOS 17.4+ they include displayed-buffer
FourCC and color attachments without image bytes or source URLs. `x420` and
`xf20` are 10-bit video/full range. `420v` and `420f` are 8-bit. PQ and BT.2020
support an HDR10 observation. Dolby Vision metadata, hardware decoding and
measured luminance need separate evidence.

Run from the repository root with the mobile host environment:

```sh
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.video_chrome_tools \
  --hdr --pause-transitions --framework FRAMEWORK --output test-results/video-hdr
```

Expect Pause acknowledgement, a stable layer, format and PQ attachments,
applied range preference, no overlay and resumed clock advance. Repeat with
SDR by omitting `--hdr`. For physical acceptance use `video_hdr_device_tools`
with an authorized current QA deployment. It requires 10-bit video-range
output and EDR headroom above one, and reports cleanup and app restoration.
Check a fixed HDR test pattern, black detail, real highlights, HLG, supported
Dolby Vision profiles, local/crypt playback, and fullscreen in both modes.
