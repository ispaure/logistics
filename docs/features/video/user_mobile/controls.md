# Mobile playback tools

Tap to reveal controls. Double-tap the left or right side to skip ten seconds, or the center to play/pause. **Lock controls** guards against accidental input. Use **Unlock controls** or Escape to unlock. Undo seek is desktop-only.

Timeline ticks mark embedded chapter starts. Open **Chapters** to choose a named position or use **Previous chapter** and **Next chapter**. Within the first second of a chapter, **Previous chapter** jumps to the preceding chapter if there is one. After that it restarts the current chapter. **Next chapter** is unavailable in the final chapter. Jumps keep the current Play/Pause state. Videos without chapters have no chapter ticks or skip actions.

Open **Playback** on iOS or **More playback options → Playback…** on Android for **Go to time**, **Start over**, speed, folder order and autoplay. **Show in folder** closes playback and selects the source. Reopening resumes at the saved position. See the [shared control guide](../user/controls.md).

Keyboard shortcuts include Space, Left/Right, M, F, G, P/N and Escape. **Subtitles and audio** browses the current provider for SRT, VTT, ASS and SSA up to 8 MiB. Set preferred languages, subtitle size and delay, or audio sync offset. Positive delay means later. Android font/language changes can briefly rebuffer. **Cache ≈** maps remote cached bytes to time approximately.

On iOS 17.4 or later, turn on **Playback → Subtitle PiP (reopen video)** and reopen to enable subtitle composition. Turn it off and reopen for classic PiP. See the [iOS pause presentation and physical checks](../development/hdr-play-pause.md).

With Subtitle PiP enabled, choose **Subtitles and audio → Subtitle brightness
in PiP**. Choosing a level opens Picture in Picture to preview the current cue. **Dim** lowers
the caption brightness and **Default** keeps the normal level. **Bright**
raises caption brightness for HDR video when the output has headroom.
Inline iOS playback, classic PiP, Android, Cast, AirPlay and connected displays
keep their native subtitle appearance.

## Watching on a TV with iPhone or iPad

1. Enable **Settings → Video → Native AirPlay video** and open a local MP4, MOV, M4V or compatible MKV.
2. Tap **AirPlay** beside **Forward 10 seconds** and select the TV. Use the phone or tablet's normal timeline, play/pause and skip controls.
3. Select **iPhone** in the route picker to continue on device, including after a connection or seek failure.

With native AirPlay, use **Chapters** on the iPhone or iPad to jump to a named position or skip between chapters. Availability of chapters on the TV itself depends on the media and receiver.

Compatible MP4/MKV streams use H.264/HEVC and compatible AAC, AC-3, E-AC-3 or Opus audio. Opus converts to AAC. Embedded MP4 timed text and MKV SRT, WebVTT and ASS/SSA text are offered as TV subtitle tracks, together with discovered SRT/WebVTT sidecars. ASS styling and drawings are omitted; the TV controls subtitle appearance. Image subtitles such as PGS remain local-only. Session-only protection blocks AirPlay.

Once native AirPlay is playing on the TV, switching apps or locking the iPhone
keeps that session available, including pause/resume. Start a new AirPlay session
while the phone is unlocked. Playback still stops if source access is revoked or
the file becomes unreadable; session-only protection continues to block AirPlay.
If AirPlay stalls, Logistics can retry once from the last confirmed position
when the phone is active. If playback stops, select the TV again in **AirPlay**.
To continue on the phone, choose **iPhone** in the picker if the TV is still
selected, then press **Play**.

On Apple TV, reveal the playback controls with the remote and open **Subtitles** to choose a track or **Off**, alongside the audio selector. Only compatible subtitle tracks appear. The phone's **Audio tracks** and **Subtitles** menus control the same selection and reflect TV changes when reopened. MP4/MOV files outside the stream-copy profile use native playback, where available embedded Apple-compatible tracks remain selectable but sidecars are unavailable.

Closing the video player stops its AirPlay video, releases the playback item and closes its streaming server. iOS may keep Apple TV selected as the system audio route. To return that route to the phone, choose **iPhone** in the AirPlay picker or Control Center; you do not need to disable AirPlay in Settings. Apple does not provide a reliable app API to disconnect that audio route. See [Apple's explanation](https://developer.apple.com/forums/thread/810035).

iOS controls automatic AirPlay suggestions. To stop those suggestions while
keeping manual selection available, choose **Settings → General → AirPlay &
Continuity → Automatically AirPlay → Never** in the system Settings app.
See [Apple's AirPlay settings](https://support.apple.com/en-ca/102661).
Logistics does not request automatic route selection when opening the app or
session-only video, and protected video never creates a native AirPlay item.
