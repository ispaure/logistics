# Video Player

Enable **Video Player**, then open an MP4 or MKV from the file browser, or choose
**Video Player** in Documents. The picker includes Local and unlocked LocalCrypt
locations. Open remote/crypt cloud videos directly from the Cloud browser.

Use the Play/Pause, back/forward ten-second buttons, seek bar, mute button and
volume slider below the video. Buttons have tooltips and keyboard focus.
The audio/subtitle selectors and secondary actions stack in narrow windows,
including floating playback. Space toggles playback; Left/Right skip ten seconds;
**M** toggles mute. **Full screen** or **F** toggles fullscreen;
Escape returns to the normal window. The audio selector chooses an embedded
audio track. The subtitle selector chooses an embedded track or turns subtitles
off. **Load SRT…** loads a UTF-8 external SRT without a plaintext temporary file.
Private subtitles must belong to the video's storage, so their credentials cannot
silently outlive the player. Ordinary subtitles can also accompany private video.

**Floating window** detaches an ordinary local video and keeps its window on top.
Session-only credentials disable this action. Desktop LocalCrypt currently uses
a session credential context, so its floating action remains unavailable even if
a separate cloud connection has saved credentials.

Leaving the desktop app conceals a session-only video and retires its buffered
frames. Enter the owning credential ZIP password in the video lock panel before
its controls return, then press Play. If the package has no encrypted password
(or no recoverable package association), set a temporary video-session password
before the first frame. Its verifier remains in memory and is not saved.
Changing the credential ZIP or revoking credentials keeps the video locked;
reopen it after unlocking the source. The trusted Wi-Fi exception belongs to the
mobile credential-resume setting. Native desktop sleep/lock timing remains a
separate acceptance check from the portable application-state tests.

The player saves position approximately every five seconds, when paused and on
close. Local records stay in the app cache. LocalCrypt records live in the hidden
`.logistics-video` folder through the encrypted provider; their contents are not
written to ordinary history or recovery. Replacing a movie invalidates its old
position. Reaching the end resets resume to the start. Storage write failures are
shown in the player; read-only locations cannot retain durable encrypted progress.

The desktop Qt/FFmpeg decoder has been checked on macOS with all eight
MP4/MKV × H.264/H.265 × AAC/Opus combinations, including decoded video frames,
audio samples and seek admission. This does not establish hardware output quality
or native Windows/Linux playback. See [mobile controls](../user_mobile/user_mobile.md)
for the separate native validation status.

## Cloud playback

Remote and crypt cloud sources stream through rclone without saving a decrypted
movie on disk. Startup or seeking can be slow, buffer, or fail depending on the
provider, network and quotas. Close and reopen to retry, or manually make a Local
or LocalCrypt copy for more reliable playback. Cloud resume lasts only while the
player remains open. Session-only credentials retain the same external-playback
restrictions, and locking or replacing credentials stops further reads.
