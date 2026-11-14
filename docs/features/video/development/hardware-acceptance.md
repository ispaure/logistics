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

Use a local MKV with two distinct supported audio tracks, ordinary text subtitles,
forced subtitles and an SDH track. Enable **Native AirPlay video**, keep Screen
Mirroring disconnected and select Apple TV in the player's AirPlay picker.

| Do this | Expect this |
| --- | --- |
| Open the TV's audio and subtitle menus with the Siri Remote | Compatible languages and text tracks appear with distinct names; PGS is absent. |
| Select a different audio track or subtitle on the TV, then reopen the Duo's track menu | The TV plays the selected track and the Duo marks the current Apple player selection. |
| Change a track or turn subtitles off on the Duo | The receiver changes its output without reopening the video or resetting the timeline. |
| Pause with the Siri Remote, then change speed or mute on the Duo | Playback remains paused. Play resumes at the chosen supported speed and mute state. |
| Seek from either device and change fit/fill | The shared timeline follows the seek and the TV picture uses the chosen sizing. |
| Choose iPhone in the same AirPlay picker while playing, paused and muted | VLC receives the current position and intent after the audio route returns; muted playback stays muted. |

Check forced subtitle and accessibility preferences on the receiver separately
from manual selection. SDK and host playlist tests do not establish these
receiver behaviors.

## Evidence and cleanup

Save `Library/Caches/video-hardware-result.json` and actual visible/audible
observations under ignored test results. Record app identity, OS, receiver or
headset, and real versus injected events. Listen for brief audio during route
transitions. Uninstall the owned QA app after collecting evidence and confirm
removal. Preserve the main app and its data. The [developer guide](development.md)
covers AirPlay receiver and HDR checks.
