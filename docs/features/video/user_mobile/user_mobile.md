# Mobile Video Player

Enable **Video Player**, then open a video from Local, unlocked LocalCrypt or Cloud. MP4, MKV, AVI, MOV, M4V, WebM, MPEG, TS/M2TS, WMV and OGV are accepted containers. Playback depends on the codecs in the file. Videos open directly and can be reopened from Recent. When access and audio allow, opening starts playback.

Tap for controls. Use Play/Pause, ten-second skips and the timeline. **Chapters** jumps to an embedded chapter without resuming a paused video. **Audio tracks** and **Subtitles** choose embedded tracks or matching sidecars. Use matching stems, such as `Movie.mkv`, `Movie.srt` and `Movie.en.srt`. Up to 32 sidecars of 8 MiB each are supported. See [playback tools](controls.md) for exact time, speed, sizing and touch controls.

On iOS, the fullscreen deck fades after three seconds while playing. On Android, choose **Fullscreen** or **Exit fullscreen**. With an active horizontal Duo fold, the picture sits above the hinge and controls below it. Tap **Fill view** to crop or **Fit view** to restore the whole picture.

**More playback options → Picture in picture** or **Cast…** is available for ordinary Local and saved-credential LocalCrypt when policy allows. Use [Native AirPlay video](controls.md#watching-on-a-tv-with-iphone-or-ipad) for compatible local files on iPhone or iPad. Session-only credentials block external playback and can conceal even ordinary video. Unlock with the credential password or an authorized trusted Wi-Fi resume, then press Play.

Backgrounding pauses inline playback. Audio interruptions and loss of an audio output pause playback. Press Play after returning. Visible playback keeps the display awake, including while buffering. Pause or close to release it.

Cloud startup and seeking may buffer or fail. Press Play to retry from the held position. Reopen a changed file or make a Local/LocalCrypt copy for persistent problems. Remote cache is limited to 128 MiB in memory per movie. Cloud resume is encrypted and there is no plaintext movie cache.

Emulator and simulator playback checks passed for the covered codec combinations and LocalCrypt. Physical casting, PiP, audio/video quality, fold behavior and lock timing remain under validation. See [implementation and acceptance](../development/development.md).
