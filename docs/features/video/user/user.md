# Video Player

See [playback tools](controls.md) for speed, picture size, queues, seek undo, preferences and encrypted cloud resume.

Enable **Video Player**, then open an MP4, MKV, AVI, MOV, M4V, WebM, MPEG, TS/M2TS, WMV or OGV video from the file browser, or choose
**Video Player** in Documents. The picker includes Local and unlocked LocalCrypt
locations. Open remote/crypt cloud videos directly from the Cloud browser.

macOS downloads a checksum-verified colour playback runtime on first use, using
libmpv from the IINA distribution. An installed IINA application is not required.
VLC compatibility playback on macOS and Windows also offers a verified download;
an installed VLC application is not required. Linux uses the distribution's
LibVLC 3 libraries and codec/subtitle plugins. On Ubuntu, install `libvlc5`,
`vlc-plugin-base` and `vlc-plugin-video-output`; Fedora needs `vlc-libs`,
`vlc-plugins-base`, `vlc-plugin-ffmpeg` and `vlc-plugins-extra`, plus
`libavcodec-freeworld` from RPM Fusion Free for the complete codec set. Follow
[Fedora's codec guidance](https://fedoraproject.org/wiki/Hardware_Video_Acceleration)
when enabling that repository.

Opening a video starts playback automatically. The window/tab title identifies
the video and the storage row identifies its source. The heart adds the file to
**Favourites**; the other header icons **Show in folder** and **Cast** when available.
The timeline and icon controls stay in a deck below the picture. Play/Pause,
ten-second skips, Previous/Next and Mute are directly available. The volume slider
moves into Audio settings in narrow windows.

**Speed**, **Picture**, **Audio**, **Subtitles**, **Chapters**, **Current folder**
and **Playback** open scrollable settings beside the picture, or below it in narrow
windows. In short narrow windows, an open settings pane provides a category
selector in place of the secondary icon row; closing it restores the icons.
Filename, track names and status messages expose their full text in tooltips
when space is limited. **Picture** offers Fit, Fill and Original size. Desktop
uses colour-managed playback on macOS. **Picture → Output** automatically uses
the screen’s available HDR brightness range, or tone maps to SDR when the screen
has no HDR headroom. Choose **SDR** to force SDR output. PQ/HDR10 and HLG sources
retain their colour metadata through the GPU conversion; the default BT.2390
tone curve preserves highlight detail. Mobius, Hable and Reinhard are also
available in **HDR tone mapping**. Output adapts when the window moves to another
screen or the available brightness changes.

**Picture → Renderer → Compatibility (VLC)** selects the earlier SDR renderer.
Automatic playback falls back to VLC if the colour runtime cannot be prepared.
Native colour output currently requires macOS; Windows and Linux retain VLC’s
8-bit SDR surface. Native HDR brightness has not yet been checked on a physical
HDR display. Host checks verify 16-bit float rendering and HDR-range pixels,
plus PQ/HLG tone mapping in windowed and fullscreen layouts.

The deck stays visible in a normal window. In fullscreen, it hides after three
seconds of active playback; moving the pointer or clicking reveals it. Pausing,
loading, settings and keyboard focus keep it available. Fullscreen isolates the
player from the workspace and overlays controls on the picture, which uses the
whole viewport without reserved header/footer space. Fit preserves the entire
picture with aspect-ratio bars; Fill crops it to the viewport. Leaving fullscreen
restores its original document pane. Buttons have tooltips, accessible names and keyboard focus.
Space toggles playback; Left/Right skip ten seconds; **M** toggles mute.
**Full screen** or **F** toggles fullscreen. Escape closes settings, unlocks
controls, or returns to the normal window. Audio and Subtitle settings choose
embedded tracks, matching sidecars or Subtitles off. **Choose subtitle file…**
accepts UTF-8 SRT, WebVTT, ASS and SSA without a plaintext temporary file.
Matching sidecars are discovered after playback starts, with at most 32 matching
files and an 8 MiB limit per file. The picker also browses other folders in the
current provider.
Private subtitles must belong to the video's storage, so their credentials cannot
silently outlive the player. Ordinary subtitles can also accompany private video.

**Chapters…** lists chapters exposed by the decoder, with names and start times.
Selecting one seeks without changing Play/Pause. Files without chapters say so.

Double-click the left/right thirds of the picture to skip ten seconds, or its
center to toggle Play/Pause. **Playback → Lock controls** prevents accidental
touch and keyboard actions; the visible Unlock button or Escape restores them.
**Show in folder** opens the provider browser, selects the video and closes playback.

Detach the video tab using the workspace controls to place it in another window.
**Cast…** switches colour playback to VLC compatibility playback while retaining
position and Play/Pause intent, then discovers VLC-compatible receivers and
offers a return-to-window action.
Discovery can take a few seconds; use **Refresh receivers** in the Cast pane. Session-only
credentials disable casting, including while another session-only
credential package is loaded. Desktop LocalCrypt uses a session credential context.

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
ASS styling can constrain font overrides.

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
