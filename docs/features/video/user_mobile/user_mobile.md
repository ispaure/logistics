# Mobile Video Player

See [playback tools](controls.md) for speed, picture size, queues, seek undo, preferences and encrypted cloud resume.

Android and iPad builds and focused emulator/simulator playback checks have
passed for all eight supported codec/container combinations and LocalCrypt.
Physical-device acceptance remains pending for casting, picture in picture,
audio/video quality and lock timing during those modes.

Enable **Video Player** in Features, then open an MP4, MKV, AVI, MOV, M4V, WebM, MPEG, TS/M2TS, WMV or OGV video in Local, unlocked
LocalCrypt or the remote/crypt Cloud browser. The native player opens
in its own screen with Play/Pause, a seek bar, elapsed/total time, ten-second skips,
audio/subtitle selection and a close button. Opened videos also appear in Home
and Documents **Recent** lists. Opening a video, including from Recent, starts playback automatically when audio is permitted.
Local and saved-credential sources use ordinary recent references; session-only
sources use the existing credential-password encrypted recent list and appear
only while those credentials are loaded. Videos are not restored as open documents
or started automatically at app launch. Playback and utility buttons have
screen-reader labels. On iOS these are native navigation bar items: UIKit chooses
the side or horizontal bar for the current window, including Duo's exterior and
interior displays. The timeline overlays the bottom of the screen within the safe area and avoids an active Duo fold.
The iOS filename occupies the native title area alongside playback controls,
with centered storage details beneath it and a glass background on iOS 26 or newer.
The green cached-range strip follows the seek track's endpoints directly beneath it.
The movie stays centered in the full player surface when controls appear or hide. Android retains its responsive
48-dp playback buttons.
On a partially folded Duo with a horizontal hinge, the player uses the upper
panel for the movie and keeps a control deck on the lower panel. Large round
ten-second skip buttons flank a larger Play/Pause button; the timeline and
Audio, Subtitles, Chapters and Done controls stay accessible below the hinge.
Unfolding restores the full video surface. The split follows the system's hinge
state and reserved division; physical-pose acceptance is separate from layout tests.

**Chapters** lists embedded chapter names and start times when the file provides
them. Selecting a chapter seeks without resuming a paused movie. AVI files often
have no embedded chapters; the player does not manufacture chapter boundaries.

Choose **Fullscreen** for immersive playback. Controls remain visible initially on iOS, then hide during playback. Tap the video to
bring the controls back; tap again to hide them. While playing, revealed controls
hide again after three seconds. Pausing, finishing or encountering an error shows
the controls. Choose **Exit fullscreen** to keep them visible. The movie fills
the available player area, preserving the video's aspect ratio.
Automatic hiding is disabled with VoiceOver or Android touch exploration.

When a cloud read exhausts playable data, playback holds its last rendered
position while more data is fetched. Slow background prefetch alone does not
pause the video.
It resumes when data is ready unless you pressed Pause, left the app, or lost
audio/credential permission.

While playback is requested visibly on the device, including during buffering,
the player keeps the display awake.
Pausing, finishing, closing or hiding playback releases that request so normal
screen timeout can resume. Casting and picture-in-picture do not keep the main
display awake. The three-second controls timer only hides controls.
On iOS, the Video accessibility element also offers **Show video controls**.
Use device volume buttons. Separate **Audio tracks** and **Subtitles** buttons list embedded tracks and matching external sidecars. Track names and languages appear when provided by the file; subtitles can be switched off. Put UTF-8 SRT files beside the movie,
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

Buffering shows a quiet spinning indicator after both playback time and frame counters stop progressing for three seconds. Batched frame statistics alone do not trigger it while time advances. During a network wait, six seconds without rendered-frame progress also detects a frozen picture whose clock is still advancing. Background prefetch and decoder percentages do not show a waiting message while video is playing. Play/Pause reflects your requested state immediately. Startup and seeking use a three-second VLC network cache; sustained playback still requires sufficient throughput.

AVI is a container: its video and audio codecs determine whether it can play. The existing VLC engines retain hardware decoding where supported and software fallback for other codecs. Codec availability and energy use depend on the platform and file.

Cloud playback is best effort: startup and seeking may buffer or fail with slow
networks, provider quotas or limited range support. A connection or decoder failure
shows a retry message instead of an endless spinner; press Play to retry from the
held position. A changed video must be closed and reopened. For persistent issues,
or manually make a Local/LocalCrypt copy. Cloud checkpoints are encrypted and can survive closing; no plaintext movie or cloud resume sidecar is saved. Remote and crypt playback passed focused Android, iPad and iPhone
emulator/simulator checks using synthetic HTTPS remotes. Live-cloud throughput
and physical-device behavior still require separate acceptance. See the [implementation and remaining acceptance work](../development/development.md).


Remote playback retains up to 128 MiB in memory per open video so recent backward
seeks can reuse downloaded data. This is roughly one minute at 18 Mbit/s; higher
bitrates or long jumps may need more buffering. Closing the player clears this
cache. It does not create a decrypted file on disk.
