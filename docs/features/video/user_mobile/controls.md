# Mobile playback tools

Tap to reveal controls. Double-tap the left or right side to skip ten seconds, or the center to play/pause. **Lock controls** guards against accidental input. Use **Unlock controls** or Escape to unlock. Undo seek is desktop-only.

Open **Playback** on iOS or **More playback options → Playback…** on Android for **Go to time**, **Start over**, speed, folder order and autoplay. **Show in folder** closes playback and selects the source. Reopening resumes at the saved position. See the [shared control guide](../user/controls.md).

Keyboard shortcuts include Space, Left/Right, M, F, G, P/N and Escape. **Subtitles and audio** browses the current provider for SRT, VTT, ASS and SSA up to 8 MiB. Set preferred languages, subtitle size and delay, or audio sync offset. Positive delay means later. Android font/language changes can briefly rebuffer. **Cache ≈** maps remote cached bytes to time approximately.

On iOS 17.4 or later, turn on **Playback → Subtitle PiP (reopen video)** and reopen to enable subtitle composition. Turn it off and reopen for classic PiP. See the [iOS pause presentation and physical checks](../development/hdr-play-pause.md).

## Watching on a TV with iPhone or iPad

1. Enable **Settings → Video → Native AirPlay video** and open a local MP4, MOV, M4V or compatible MKV.
2. Tap **AirPlay** beside **Forward 10 seconds** and select the TV. Use the phone or tablet's normal timeline, play/pause and skip controls.
3. Select **iPhone** in the route picker to continue on device, including after a connection or seek failure.

Compatible MKV streams use H.264/HEVC and compatible AAC, AC-3, E-AC-3 or Opus audio. Opus converts to AAC. Choose supported tracks in **Audio tracks** and **Subtitles**. SRT and WebVTT can display on TV, with PGS available for local playback. The TV controls subtitle appearance and HDR. Session-only protection blocks AirPlay.
