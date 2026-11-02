# Video Player

See [playback tools](controls.md) for speed, picture size, queues, seek undo, preferences and encrypted cloud resume.

Enable **Video Player**, then open an MP4, MKV, AVI, MOV, M4V, WebM, MPEG, TS/M2TS, WMV or OGV video from the file browser, or choose
**Video Player** in Documents. The picker includes Local and unlocked LocalCrypt
locations. Open remote/crypt cloud videos directly from the Cloud browser.

Windows and macOS offer a checksum-verified LibVLC runtime download on first use;
an installed VLC application is not required. Linux uses the distribution's
LibVLC 3 libraries and codec/subtitle plugins. On Ubuntu, install `libvlc5`,
`vlc-plugin-base` and `vlc-plugin-video-output`; Fedora needs `vlc-libs`,
`vlc-plugins-base`, `vlc-plugin-ffmpeg` and `vlc-plugins-extra`, plus
`libavcodec-freeworld` from RPM Fusion Free for the complete codec set. Follow
[Fedora's codec guidance](https://fedoraproject.org/wiki/Hardware_Video_Acceleration)
when enabling that repository.

Opening a video starts playback automatically. Use the Play/Pause, back/forward ten-second buttons, seek bar, mute button and
volume slider over the video. Controls hide after three seconds of active
playback; move the pointer or click the picture to reveal them. Pausing, loading,
menus and keyboard focus keep them available. The movie stays centered when
controls appear or hide. Buttons have tooltips and keyboard focus.
The audio/subtitle selectors and secondary actions stack in narrow windows,
including floating playback. Space toggles playback; Left/Right skip ten seconds;
**M** toggles mute. **Full screen** or **F** toggles fullscreen;
Escape returns to the normal window. The audio selector chooses an embedded
audio track. The subtitle selector chooses an embedded track or turns subtitles
off. **Load subtitles…** accepts UTF-8 SRT, WebVTT, ASS and SSA without a plaintext
temporary file. Matching sidecars are discovered after playback starts, with at
most 32 matching files and an 8 MiB limit per file. The picker also browses other
folders in the current provider.
Private subtitles must belong to the video's storage, so their credentials cannot
silently outlive the player. Ordinary subtitles can also accompany private video.

**Chapters…** lists chapters exposed by the decoder, with names and start times.
Selecting one seeks without changing Play/Pause. Files without chapters say so.

Double-click the left/right thirds of the picture to skip ten seconds, or its
center to toggle Play/Pause. **Playback → Lock controls** prevents accidental
touch and keyboard actions; the visible Unlock button or Escape restores them.
**Show in folder** opens the provider browser, selects the video and closes playback.

**Floating window** detaches an ordinary local video and keeps its window on top.
Use **Return to document size** to restore the previous window geometry.
**Cast…** discovers VLC-compatible receivers and offers a return-to-window action.
Discovery can take a few seconds; reopen the menu to refresh it. Session-only
credentials disable casting and floating, including while another session-only
credential package is loaded. Desktop LocalCrypt currently uses
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

Hidden/minimized inline playback pauses; visible ordinary playback may continue
when another desktop application receives focus. Explicit casting can continue
with the main window hidden. Sleep/lock notifications and default audio-output
loss pause playback without automatically resuming. Display-awake requests apply
only to requested, visible playback, including buffering. Native notifications and
receiver behavior still require acceptance on each target OS.

The player saves position approximately every five seconds, when paused and on
close. Local records stay in the app cache. Session-only LocalCrypt and remote records use the owning credential ZIP password through the shared reader-state store. Other LocalCrypt records remain encrypted through their provider. Private positions are not written to ordinary history or recovery. Replacing a movie invalidates its old
position. Reaching the end resets resume to the start. Storage write failures are
shown in the player; read-only LocalCrypt locations cannot retain durable encrypted progress through that provider.

The desktop LibVLC decoder has been checked on macOS with all eight
MP4/MKV × H.264/H.265 × AAC/Opus combinations, including decoded video frames,
audio samples and seek admission. This does not establish hardware output quality
or native Windows/Linux playback. See [mobile controls](../user_mobile/user_mobile.md)
for the separate native validation status.

Caption playback uses software decoding where required for VLC's subtitle
composition; movies without captions retain automatic hardware decoding.
ASS styling can constrain font overrides. Desktop HDR is outside the current scope.

## Cloud playback

Remote and crypt cloud sources stream through rclone without saving a decrypted
movie on disk. Startup or seeking can be slow, buffer, or fail depending on the
provider, network and quotas. Close and reopen to retry, or manually make a Local
or LocalCrypt copy for more reliable playback. Cloud resume is encrypted and survives reopening when its credentials and revision still match. Session-only credentials retain the same external-playback
restrictions, and locking or replacing credentials stops further reads.


Remote playback retains up to 128 MiB in memory per open video so recent backward
seeks can reuse downloaded data. This is roughly one minute at 18 Mbit/s; higher
bitrates or long jumps may need more buffering. Closing the player clears this
cache. It does not create a decrypted file on disk.
