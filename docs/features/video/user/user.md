# Video Player

Enable **Video Player**, then open a video in Documents or from Local, unlocked LocalCrypt or the Cloud browser. Supported containers include MP4, MKV, AVI, MOV, M4V, WebM, MPEG, TS/M2TS, WMV and OGV. Playback starts automatically when access and audio allow.

On first use, macOS prepares a verified libmpv runtime. Compatibility playback uses LibVLC. Linux requires distribution packages.

- Ubuntu — `libvlc5`, `vlc-plugin-base`, `vlc-plugin-video-output`
- Fedora — `vlc-libs`, `vlc-plugins-base`, `vlc-plugin-ffmpeg`, `vlc-plugins-extra` and `libavcodec-freeworld` for additional codecs. [Fedora codec guidance](https://fedoraproject.org/wiki/Hardware_Video_Acceleration)

Use **Space** to play/pause, **Left/Right** to skip ten seconds, **M** to mute and **F** for fullscreen. Move the pointer to restore fullscreen controls. **Escape** closes settings, unlocks controls or exits fullscreen. Use **Chapters** to jump without changing Play/Pause. **Show in folder** closes playback and selects the source file. See [playback tools](controls.md) for track settings, seek undo and queues.

On macOS, **Picture → Output** uses available HDR headroom or tone maps to SDR. Choose **SDR** to force it. **Picture → Renderer → Compatibility (VLC)** selects the SDR fallback. Windows and Linux use VLC SDR. Physical HDR output remains under validation.

**Cast…** switches to VLC compatibility playback and retains the held position. **Refresh receivers** retries discovery. Casting is unavailable while session-only credentials are loaded. Leaving the app conceals session-only video. Unlock with the credential ZIP password, then press Play. If necessary, set a temporary password before first playback. Revoked credentials require reopening after unlocking the source.

Sleep, lock or loss of audio output pauses playback. Press Play after returning. Resume saves periodically, on pause and on close. Private resume is encrypted, and replacing the file invalidates its checkpoint. See [mobile controls](../user_mobile/user_mobile.md) for mobile behavior.

## Cloud playback

Remote and crypt videos stream through rclone, with up to 128 MiB of memory cache per open movie and no decrypted file on disk. Startup and seeks depend on provider and network support. Reopen to retry or make a Local or LocalCrypt copy. Cloud resume requires the matching credentials and revision.
