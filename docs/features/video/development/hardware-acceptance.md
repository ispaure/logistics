# Video hardware acceptance

Use a current, separately signed QA app with synthetic media and no main-app
group access. The probe entry is
`mobile_build/native_tests/tests/logisticsmobile/video_hardware_probe.py:main`.
Supply `video-fixtures/hardware.mp4` and the synthetic LocalCrypt fixture.
Verify device Python and VLC frameworks, signatures and a working video screen
before testing. Use the owning Build Manager and a leased scratch workspace.

`mobile_build.validation.video_privacy_tools` supports `--context remote`,
`crypt` or `localcrypt` for injected checks. Physical accepted-route and Wi-Fi
checks require working native signals and the required Wi-Fi entitlement.
If identity is unavailable, verify the password challenge and record that scope.

## Physical matrix

Use test videos with audible tracks. Exercise ordinary local, session-only
LocalCrypt and synthetic remote/crypt sources. Use **Done** to advance the
hardware probe from ordinary to session-only playback.

| Do this | Expect this |
| --- | --- |
| Switch apps; lock/sleep; wake; cancel or enter a wrong password | Session video, captions and audio stay concealed. Successful authentication restores paused controls. |
| Change trusted Wi-Fi, then rebackground during lookup | Fresh trusted association can restore paused controls. Unknown, stale, offline or untrusted results retain the challenge. |
| Ring, decline, answer and end calls; repeat after system Pause | Video stays paused without an audible burst or surprise seek. |
| Unplug headphones or disconnect Bluetooth | Pause before speaker fallback. Reconnection requires Play. |
| Request Cast, PiP, external display or pop-out with session-only access | The guarded action refuses external playback. |
| Lock, Forget or replace credentials during playback | Affected output and provider access retire. Saved accounts cannot bypass another session's restriction. |

## Bluetooth and mirroring

Use `tests.logisticsmobile.audio_hardware_probe:main` on iPhone and Android
for video and speech. Reconnect an unapproved headset during protected
speaker playback and listen on both outputs. Decline, retry and approve from
**Settings → Privacy & Security → Protected audio outputs**. Protected route
changes pause. Approval requires a separate Play. Verify the approval persists
after restart and removing it during playback takes effect. In ordinary
playback, unapproved outputs need no approval. Calls and actual output loss
still pause.

Start iPhone Mirroring before and after loading a session. Repeat in an
ordinary document while the session stays loaded, with multiple windows,
and while a password or Wi-Fi decision is pending. The restriction is
app-wide. Supported capture signals conceal native video and pause audio.
Check ordinary browsing again after the last session clears.
[Audio policy](../../../development/architecture/audio-playback.md)

## Apple TV playback controls

Use local MP4 and MKV files with two distinct supported audio tracks, ordinary text subtitles,
forced subtitles and an SDH track. Include MP4 timed text, MKV SubRip/ASS and an
SRT sidecar. Enable **Native AirPlay video**, keep Screen
Mirroring disconnected and select Apple TV in the player's AirPlay picker.

| Do this | Expect this |
| --- | --- |
| Open the TV's audio and subtitle menus with the Siri Remote | Compatible languages and text tracks appear with distinct names; PGS is absent. |
| Select a different audio track or subtitle on the TV, then reopen the Duo's track menu | The TV plays the selected track and the Duo marks the current Apple player selection. |
| Change a track or turn subtitles off on the Duo | The receiver changes its output without reopening the video or resetting the timeline. |
| Pause with the Siri Remote, then change speed or mute on the Duo | Playback remains paused. Play resumes at the chosen supported speed and mute state. |
| Cast the same generated H.264/AAC MP4 and compatible MKV for at least five minutes each with Duo awake, then repeat while locked on the same Apple TV and route. Use media at least ten minutes long and continue to EOF where possible. | Compare real TV picture, audio, and media position around three and five minutes, then wake and check position, audio and transport controls. Source revocation and session protection still stop output. |
| Briefly interrupt buffering, then break the video route with the audio route still selected. Wake Duo if locked and cast again after a timeout or teardown. | Brief buffering keeps the existing playback item. A stalled session gets one recovery attempt on an available route while Duo is active. Retry or play locally at the confirmed position. Listen for overlapping audio. |
| If an established cast freezes during lock, leave the AirPlay route selected, wait for the player error, then unlock Duo and return to Logistics without pressing Play. | The player retries once at the last confirmed timestamp. Confirm that both the Apple TV picture and audio resume there. If the retry fails, check that the timestamp remains available for a manual retry. |
| Switch apps repeatedly, return to Logistics, and press Siri Remote Play/Pause during and after a phone seek | Each Pause holds, including when an outstanding seek completes. Repeat after several minutes. Record whether the clickpad and Back still work if transport controls fail. |
| Seek from either device and change fit/fill | The shared timeline follows the seek and the TV picture uses the chosen sizing. |
| Start a large MKV midway through, then press Back 10 seconds repeatedly on the Siri Remote past the starting position; repeat after a phone timeline seek | Earlier fragments load and playback continues without ending AirPlay. Repeat rapidly while video is loading, and record the movie timestamp and player/server errors if it disconnects. |
| Skip forward repeatedly into uncached video, reverse direction, and seek near the end; repeat with the phone timeline and on-device playback | Both directions remain responsive without ending the session. Repeated skips follow the latest requested position, stop at file boundaries, and respect an explicit Pause. |
| Choose iPhone in the same AirPlay picker while playing, paused and muted | VLC receives the current position and intent after the audio route returns; muted playback stays muted. |
| Close the player while streaming, paused, loading, and after a connection/seek timeout | TV video stops, the item and HLS server are released, and reopening requires an explicit playback action. The system audio route may still show Apple TV; choosing iPhone in Control Center returns it without changing Settings. |
| Open a movie and pause/resume before its audio output is ready; return from TV to iPhone and press Play | Sound resumes without a manual seek, route toggle or app restart unless deliberately muted. |
| Resume a 4K HDR MKV at a saved position, then scrub while the TV loads | The handoff starts, the requested target remains visible, and playback reaches that target. A stalled load or seek reports failure and preserves the last confirmed position for local playback. |
| Open a generated MP4 with named chapters, then a remuxed MKV with the same chapter starts. Use the phone's **Chapters** panel during native AirPlay, with playback running and after pausing from the Siri Remote. | The receiver seeks to the named starts and preserves the receiver's play or pause state. Check the first and final chapter boundaries and return to local playback. Record separately whether the particular receiver shows an embedded chapter list for a direct file. |

Check forced subtitle and accessibility preferences on the receiver separately
from manual selection. SDK and host playlist tests do not establish these
receiver behaviors.

For a transport-control failure, capture `[VideoAirPlay] rate-change` entries
around the button press, together with app/OS versions and the movie timestamp.
The log contains playback state and the system rate-change reason, without source
names or stream URLs. Compare Siri Remote input with phone and Watch input;
successful navigation alone does not establish that a Pause reached AVPlayer.
For a lock failure, record which transition occurs first among HLS requests or
fragment reads, playhead movement, and loss of the video route. Native MP4
does not use the HLS server, so compare the AVPlayer and route observations for
that file separately. Save only state and timing fields.

## Evidence and cleanup

Save `Library/Caches/video-hardware-result.json` and actual visible/audible
observations under ignored test results. Record app identity, OS, receiver or
headset, and real versus injected events. Listen for brief audio during route
transitions. Uninstall the owned QA app after collecting evidence and confirm
removal. Preserve the main app and its data. The [developer guide](development.md)
covers AirPlay receiver and HDR checks.
