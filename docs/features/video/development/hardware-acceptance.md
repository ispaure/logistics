# Session video hardware acceptance

## Resume this test later

When the user says they are ready to test video privacy, resume from this page and
read the current implementation before preparing anything. Physical acceptance
was deferred at the user's request; a previously installed QA app was removed.
**Keep the test sources and instructions, not a saved app build.** Rebuild from the
current checkout, including the current native adapters. Replacing only Python
inside an older binary does not test native changes.

The reusable in-app entry point is
`mobile_build/native_tests/tests/logisticsmobile/video_hardware_probe.py:main`.
A native QA launcher runs:

```python
from tests.logisticsmobile.video_hardware_probe import main
main().main_loop()
```

The automated companion is
`mobile_build/validation/video_privacy_tools.py`. It accepts `--context remote`,
`--context crypt` or `--context localcrypt` to keep simulator batches small.
Read its current command-line help and use a freshly built matching native app.
Its injected network/route events supplement physical tests; they do not replace
them. The portable contracts are in
`mobile_build/tests/native/test_video_player.py`,
`mobile_build/tests/workspace/test_screen_privacy.py` and
`Python/tests/readers/test_desktop_video_privacy.py`.

## Prepare from current source

Use the project's normal build-manager/native-build owners and a leased scratch
workspace. Select only an explicitly authorized physical device. The earlier
session authorized the user's iPhone 15 Pro Max; confirm current availability and
scope from the new conversation before installing. Do not select another paired
phone or tablet just because it is available.

Build a separate QA bundle, with no main-app group access and app-private synthetic
storage. Preserve the installed Logistics app and its data. Stage the current
probe and synthetic video fixtures with the current native decoder adapters.
Generate a sufficiently long video through the existing `video_fixtures` helpers
and FFmpeg rather than retaining a movie or app build between sessions. The probe
expects `video-fixtures/hardware.mp4` and the existing synthetic LocalCrypt fixture.

Keep framework-copy phases when removing app-extension embedding from an isolated
QA target. Verify the device Python and VLC frameworks are present and every
embedded Python wrapper/framework has a valid device signature before installing.
Verify the app reaches the video screen before asking the user for hardware
interactions. Use only existing authorized signing material; do not change account
or device-security settings to get a test to pass.

Real trusted-network recognition needs the appropriate Wi-Fi-information
entitlement and foreground permissions. The wildcard profile used during initial
preparation lacked that entitlement. If this is still true, report real trusted
Wi-Fi acceptance as pending and test the enabled-but-unavailable fail-closed path;
do not label a synthetic SSID as physical trusted-network acceptance.

## Physical matrix

Test ordinary local video, session-only LocalCrypt, and available remote/crypt
sources. Use synthetic test sources and no personal cloud credentials. Test normal
and session-only policies separately, and test permitted PiP/casting modes only
for the normal policy when a receiver is available.

| Action | Required observation |
| --- | --- |
| Switch apps and return; lock/sleep and wake | Session video, subtitles and audio stay concealed until required authentication succeeds. No flash in the app switcher or during resume. |
| Cancel or enter a wrong password | Video remains hidden and audio silent. Correct authentication restores controls without autoplay. |
| Trusted Wi-Fi disabled | Password required on session resume. |
| Trusted Wi-Fi enabled, trusted association | Stay hidden/silent while a fresh association check is pending. After authorization, restore controls and remain paused. |
| Untrusted, disconnected, unavailable or failed Wi-Fi lookup | Keep the password challenge. |
| Rebackground during Wi-Fi/password verification | Reject stale success; remain concealed until the latest transition is authorized. |
| Incoming call: ringing, decline, answer and end | Pause all video policies, including compact banners and iPad relayed calls where available. Never resume automatically. |
| System pause before an app interruption callback; duplicate callbacks | Stay paused. No toggle, new seek, audible burst or second disruptive transition. |
| Unplug wired headphones; disconnect Bluetooth audio | Pause, without speaker fallback audio. Reconnection stays paused until explicit Play. |
| Session-only casting/PiP/pop-out and system external routes | Controls and native actions refuse external playback. Screen capture/output protections remain enforced. |
| Explicit lock, Forget, credential replacement; mix saved and session accounts | Retire affected decoder/transport access. An ordinary player must not bypass a session gate or retain external playback permission. |

On the hardware probe, **Done** advances from ordinary video to session-only video.
Use the synthetic resume password defined by the current probe; do not substitute
or retain a personal password. Its Wi-Fi phase must reflect the current code and
available signing capabilities. Adapt the probe alongside future implementation
changes rather than replaying old instructions against a different build.

## Evidence and cleanup

Collect the QA app's `Library/Caches/video-hardware-result.json` and the user's
observations about flashes and audible output. Native player-state sampling alone
cannot prove that physical speakers emitted no brief sound. Keep raw records,
recordings and concise results under ignored `test-results/`, not in the wiki.
Distinguish actual calls/route changes from injected notifications and physical
sleep from simulator display-power commands.

After evidence collection, uninstall only the temporary QA bundle and verify it is
gone. Remove the task's temporary native apps, APKs and build copies; retain the
reusable probe, this guide and concise validation evidence. Do not keep a build
for the next test session: prepare a new one from the then-current code.
