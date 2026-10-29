# Mobile Video Player

Android and iPad builds and focused emulator/simulator playback checks have
passed for all eight supported codec/container combinations and LocalCrypt.
Physical-device acceptance remains pending for casting, picture in picture,
audio/video quality and lock timing during those modes.

Enable **Video Player** in Features, then open an MP4 or MKV in Local, unlocked
LocalCrypt or the remote/crypt Cloud browser. The native player opens
in its own screen with Play/Pause, a seek bar, elapsed/total time, ten-second skips,
audio/subtitle selection and a close button. Playback and utility buttons have
screen-reader labels and at least 48-point/dp targets. They use two rows in narrow
views and one row in wide views. On iOS, controls follow the current window's safe
area and avoid an active Duo fold; short windows can scroll the controls.
Choose **Fullscreen** to hide the controls and system bars. Tap the video to
bring the controls back; tap again to hide them. While playing, revealed controls
hide again after three seconds. Pausing, finishing or encountering an error shows
the controls. Choose **Exit fullscreen** to keep them visible. The movie fills
the player area behind the controls, preserving the video's aspect ratio.
Automatic hiding is disabled with VoiceOver or Android touch exploration.

While video plays visibly on the device, the player keeps the display awake.
Pausing, finishing, closing or hiding playback releases that request so normal
screen timeout can resume. Casting and picture-in-picture do not keep the main
display awake. The three-second controls timer only hides controls.
On iOS, the Video accessibility element also offers **Show video controls**.
Use device volume buttons. The audio/subtitles button lists embedded audio and subtitles, a subtitles
off action, and matching external sidecars. Put UTF-8 SRT files beside the movie,
using the same stem, for example `Movie.mkv`, `Movie.srt` and `Movie.en.srt`.
The VLC adapters also admit matching ASS/SSA and WebVTT sidecars. At most 32
sidecars are admitted, each limited to 8 MiB. Subtitles stay in provider streams.

For ordinary Local files and mobile LocalCrypt with saved credentials, the
**More playback options** menu offers **Picture in picture** and **Cast…**. Casting uses VLC's discovered
receivers (Chromecast); AirPlay video routing is not implemented. Receiver discovery
may take a few seconds: reopen Cast to refresh the list. Both actions recheck
credential policy. They are unavailable with session-only credentials.

Inline playback pauses on backgrounding. Android screen-off notifications pause
playback even in picture in picture or when casting. The iPad adapter pauses on
protected-data loss and pauses inline playback when the app resigns active;
lock timing during background PiP/casting still needs physical-device validation.
Session-only content is hidden behind the existing credential resume gate.
This also protects an ordinary video while any session-only credential is loaded.
A newly loaded session retires a player that was previously allowed external
playback. Casting and picture in picture remain unavailable while that protection
is in use. Restoring the surface never starts playback automatically.

Returning to session-only video requires its credential password unless the
existing optional trusted Wi-Fi setting authorizes resume. Video, subtitles and
audio remain concealed while the fresh Wi-Fi decision is pending. An unavailable
or failed lookup keeps the password challenge. A later background transition
invalidates an earlier authorization attempt.

Incoming calls and audio-session/focus interruptions pause every video, including
ordinary playback. Removing wired headphones or losing a Bluetooth audio output
also pauses it. Ending a call, regaining audio focus or reconnecting a headset
does not resume playback: press Play again. Duplicate system and application
pause notifications do not toggle playback. The paused decoder remains muted
until explicit Play; a stopped decoder has no active audio output. Resume records use
the same encrypted LocalCrypt sidecar as desktop; unlocking the source remains
necessary before reading its saved position.

Cloud playback is best effort: startup and seeking may buffer or fail with slow
networks, provider quotas or limited range support. Close and reopen to retry,
or manually make a Local/LocalCrypt copy. Cloud positions stay in memory while
the player is open and are lost on close; no plaintext movie or cloud resume
sidecar is saved. Remote and crypt playback passed focused Android, iPad and iPhone
emulator/simulator checks using synthetic HTTPS remotes. Live-cloud throughput
and physical-device behavior still require separate acceptance. See the [implementation and remaining acceptance work](../development/development.md).
