# Video Player development

| Change | Owner | Focused checks |
| --- | --- | --- |
| Provider admission and subtitles | `Python/features/video/playback.py`, `subtitles.py` | `test_video_player.py`, `test_cloud_video.py` |
| Range transport and resume | `transport.py`, `services/documents/video_progress.py` | `test_video_player.py`, `test_cloud_video.py` |
| Desktop controls and decoding | `ui/player.py` | `test_video_decode.py` |
| Mobile adapters and payload | `mobile/`, `mobile_sources.json` | mobile `test_video_player.py`, packaging checks |

Video is independently registered as `video` on desktop and mobile. Media Tools
retains MKA renaming. The previous mobile `media` disabled preference migrates to
`video`; native Java/Objective-C class identities stay unchanged. Decoder imports
remain lazy. See [feature conventions](../../../development/features.md).

## Video player

The [brief](video-player.md) is the acceptance contract. `playback.py` admits
Local, LocalCrypt and remote/crypt MP4/MKV sources through retained `ProviderContent` grants.
Mobile LocalCrypt uses the native decoded range source rather than its ciphertext
transfer stream. `transport.py` serves bounded HTTP byte ranges on loopback under
per-session random capability URLs. It exposes no directories and sends no-store
headers. Suspension, revision changes and credential revocation stop further reads.
VLC owns any receiver transport; the provider server never binds a LAN interface.

The host's `services/documents/video_progress.py` binds positions to provider identity and the video's revision.
Ordinary records use app-private state; private records use the encrypted
provider's hidden `.logistics-video` directory, including native decoded reads
when restoring. No video or subtitle is staged in a plaintext file. Resume
metadata deliberately does not enter the workspace/recent-document projection.

`ui/player.py` integrates Qt Multimedia/FFmpeg into desktop document hosting.
It provides seeking, volume, embedded audio/subtitle selection, bounded UTF-8 SRT
captions, fullscreen and policy-checked floating playback. LocalCrypt browser
activation dispatches directly to the retained provider-backed player.

`mobile/player.py` owns native presentation, periodic checkpoints, credential
revocation and shutdown. Mobile storage dispatch and feature admission occur
before attempting a text/document import. The host's existing screen privacy,
Back and shutdown owners retire or conceal the player. Native controls perform
their own policy checks before play, cast and picture-in-picture requests.

Android uses `org.videolan.android:libvlc-all:3.7.5`; its feature-owned Java surface
is installed through the existing Gradle source owner. iOS uses the official
VLCKit Swift package at the immutable revision in
`mobile_build/build_support/video_build.py`. That package currently distributes a
4.0 prerelease SDK, required for its PiP protocol. The existing iOS build helper
links the package and installs the feature-owned Objective-C controller.
These native SDKs and their upstream notices must be retained in packaged builds.

Mobile fullscreen is owned entirely by the native adapters. Controls overlay the
video surface; Fullscreen hides them and the Android system bars or iOS status
bar/home indicator. A surface tap reveals controls and a three-second timer hides
them again during playback. Pause, completion and errors reveal controls. Timers
defer during seeking, menus and screen-reader use. Android saves and restores the
host's bar visibility and behavior across concealment/disposal; iOS uses controller
appearance overrides and invalidates its timer on retirement/disappearance.
This presentation state does not grant playback or bypass credential gates.

### Validation and remaining release gates

Focused commands (use the documented desktop/mobile host environments):

```sh
python3 dev.py test desktop 'test_video*.py'
python3 dev.py test mobile test_video_player.py
PYTHONPATH=Python:. .venv/bin/python -m mobile_build.validation.video_native android
PYTHONPATH=Python:. .venv/bin/python -m mobile_build.validation.video_native ios
```

The native API compiler checks download pinned upstream interfaces into
`logistics_build.build_retention.scratch()`, compile and remove the scratch tree. They
do not install apps or prove native playback. Desktop fixtures generate all
eight required codec/container combinations and observe decoded frames and audio
samples. Provider regressions exercise actual rclone ciphertext with an 11 MiB
seekable source, encrypted position creation/replacement, and credential revocation.
Host tests cover range forms, invalid ranges, suspension, private resume decoding,
subtitle boundaries, mobile conceal/reveal, shutdown and native project refresh.

The focused non-cloud native probe uses twelve-second fixtures and checks the
Fullscreen button, actual system-bar visibility, surface tap reveal, timed hiding,
paused controls and fullscreen exit restoration. iOS additionally checks movie
geometry against its full controller bounds. Run this probe against newly rebuilt
native binaries after fullscreen changes; restaging Python into older binaries
cannot validate the new native UI. API compilation and host tests alone do not
establish immersive behavior, rotation or picture-in-picture transitions on devices.

Both native adapters passed API compilation on October 28, 2026. Full managed
Android debug APK and iOS simulator builds also passed using captured uncommitted
Logistics and commonUtils source. Focused probes restaged Python test code into
those native binaries and ran all eight codec/container cases on owned Android
and iPad test devices. Android captured decoded test-pattern frames; iPad checked
advancing playback, video output and audio-track discovery. Both exercised
LocalCrypt streaming, encrypted resume records, external-playback denial and the
password gate without autoplay. The disposable emulator/simulator were removed.
These checks do not establish audible output, A/V sync or physical lock behavior.
No commit, push, physical-device installation or release was performed.

The reusable focused driver uses retention-owned scratch and existing device
lifecycle helpers; its reports identify the base native binary and the restaged
Python probe. Pass an existing managed APK or simulator app, and a fresh ignored
evidence directory:

```sh
PYTHONPATH=Python:. .venv/bin/python -m mobile_build.validation.video_probe_tools --apk /absolute/path/app-debug.apk --output test-results/video/android-video
PYTHONPATH=Python:. .venv/bin/python -m mobile_build.validation.video_probe_tools --ios-app '/absolute/path/Logistics Mobile.app' --output test-results/video/ipad-video
```

Before release, validate audible output and audio/video sync across the full matrix,
embedded tracks, external subtitles, long seeks, completion/reopen, ciphertext
resume records and revocation on each target. Validate Android and iPad PiP,
receiver playback, rotation and exact lock/unlock behavior on hardware. In
particular, iPad protected-data notifications do not yet establish immediate
pause on every lock during background PiP/casting. AirPlay video output remains
unimplemented. Native adapters therefore remain pending acceptance; do not treat
host tests as a completed mobile release gate. Cloud emulator/simulator acceptance is recorded below; live-provider and physical-device acceptance remain separate.

## Cloud range playback

Remote browsers dispatch MP4/MKV directly to this feature on desktop and mobile.
The rclone providers already expose seekable, bounded ranges: desktop uses
`rclone cat --offset/--count`; mobile uses the native `remote_range` bridge.
Crypt remotes decode through the provider, including logical plaintext offsets.
No decrypted movie is staged and the decoder sees only an unguessable loopback
URL. Each request uses bounded reads and validates credential grants and source
revisions. Unknown sizes and nonseekable resources are rejected. Streams have a
small memory block cache, rather than a whole-file cache. Close, lock, credential
changes and revision changes stop subsequent reads. In-flight provider requests
can take time to return; the transport rechecks access before sending their bytes.

Cloud playback is best effort. Startup and seeks may issue multiple metadata and
range requests; latency, quotas and backend range support can cause stalls or
failure. Retry by closing and reopening the file, or manually make a Local or
LocalCrypt copy. There is no automatic plaintext download fallback. Optional
mobile sidecar I/O failures do not prevent opening the movie. A revision or grant
failure still stops playback. Remote progress remains in RAM for the current
player only; neither cloud plaintext sidecars nor ordinary app-cache records are
written, including for encrypted cloud sources. Closing loses that position.

Portable cloud checks exercise actual rclone with disposable local/crypt backends,
HTTP prefix/tail/cross-block seeks, decoded desktop video frames and audio from
plain and crypt rclone streams, native bridge resource contracts, revision and
credential invalidation, and memory-only resume. These do not establish real-cloud
throughput or native cloud codec/casting/PiP acceptance.

## Further reading

- [Video playback brief](video-player.md)
- [Desktop controls](../user/user.md)
- [Mobile controls](../user_mobile/user_mobile.md)

## Native remote/crypt acceptance — October 28, 2026

Android API 36 (Pixel 9 emulator), an iPad simulator and an iPhone simulator each
passed 19 focused cases. Each target played and sought through all eight
MP4/MKV × H.264/H.265 × AAC/Opus combinations on both ordinary remote and crypt
sources. Additional cases covered an eight-second seek, password lock/unlock
without autoplay, and Cloud-browser activation followed by credential revocation.
Matching remote subtitles were read through retained provider content. Remote
resume stayed in memory and no decrypted movie appeared in the private workspace.
Session-only external playback was denied.

These probes use a read-only synthetic HTTPS/WebDAV server, actual native rclone
range requests and actual crypt ciphertext. TLS verification remains enabled.
The ephemeral fixture CA is installed only in the owned Android emulator's
disposable certificate-store mount or the owned simulator's keychain. Android
checks rendered SurfaceView test-pattern pixels. Each iOS target produced 36
native VLC frame snapshots whose decoded color content was checked on the host.
Audio-track discovery is checked; audible output and A/V sync require separate
acceptance. This does not measure live cloud throughput, quotas or provider errors,
physical lock timing, casting or picture in picture.

The existing managed binaries supplied unchanged native player adapters; current
Python modules and probes were restaged and source manifests retained with the
local evidence. This is not evidence of a fresh full application build. An APK
without the native Video Player is rejected before a probe can run. App extensions
are omitted only from the scratch simulator test copy. Every owned emulator,
simulator, synthetic trust store and scratch build was removed after the runs.

Validation exposed an iOS presentation race after closing/unlocking/reopening:
a new controller could be presented through an older controller still transitioning.
The iOS adapter now loads its native view, waits for a stable presenter and cancels
pending presentation on disposal. The host waits for visible native readiness and
rechecks navigation before reporting success. Cloud status is set after native
controls exist. Portable regressions cover that readiness/navigation contract and
replacement of stale APK Python bytecode.

Run with Logistics' mobile test interpreter, an existing managed video-enabled
APK or simulator app, and a fresh ignored evidence directory:

```sh
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.video_probe_tools --cloud --apk /absolute/path/video-enabled.apk --output test-results/video-cloud-native/android
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.video_probe_tools --cloud --ios-app '/absolute/path/Logistics Mobile.app' --ios-model iPad --output test-results/video-cloud-native/ipad
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.video_probe_tools --cloud --ios-app '/absolute/path/Logistics Mobile.app' --ios-model iPhone --output test-results/video-cloud-native/iphone
```

The host needs FFmpeg, the pinned rclone, cryptography/Pillow in that interpreter,
and the existing Android/Xcode tools. Reports retain native-binary provenance,
restaged source manifests, range counters, completed cases and iOS frame evidence.


## Session resume and interruption validation

`features/video/mobile/player.py` combines the video's credential policy with
active host resume gates. Native controls cannot resume a transport while a
password or fresh Wi-Fi authorization is pending. Loading session-only credentials
retires a previously unrestricted native player; explicit locking conceals even
a movie from another provider. iOS presentation retries are cancelled and
reauthorized after concealment, and capture-change notifications cannot reveal
a locked movie surface.

The native iOS adapter observes AVAudioSession interruption/route changes and
CallKit calls (including calls that do not background the scene). Android owns
media audio focus, noisy-audio broadcasts and audio-device removals. Both adapters
coalesce pause requests, retain a manual-resume latch and suppress decoder audio
until explicit Play. Focus gain, interruption end and reconnection never autoplay.
The CallKit framework is linked explicitly during managed project refresh.

`mobile_build/validation/video_privacy_tools.py` runs synthetic local, LocalCrypt,
remote and crypt tests on manager-owned disposable devices. The associated
`video_privacy_probe.py` checks real app switching, Android screen-off/resume and
emulator ringing/answered calls, native decoder state, pause ordering, and
password/trusted/untrusted/unavailable/delayed/failed/stale Wi-Fi decisions.
Audio-route and iOS interruption notifications are injected; they do not establish
physical headset, Bluetooth or Continuity-call behavior. An iOS display-power
command was found not to produce lock lifecycle events on the current toolchain;
it is not counted as sleep acceptance. iOS protected-data handler injection plus
app switching is labelled separately from physical sleep.

Run the privacy probe against a managed video-enabled artifact with the mobile
test interpreter. Frozen source snapshots do not contain downloaded host tools;
`--rclone` supplies the pinned host binary for synthetic fixture encryption. Its
checksum is retained in the run's fixture provenance. It does not replace the
application's native rclone service.

```sh
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.video_privacy_tools android --binary /absolute/path/app-debug.apk --rclone /absolute/path/pinned/rclone --output test-results/video-privacy/android
```

Use `iPhone` or `iPad` with a simulator `.app` for iOS. Failures retain the last
permission, audio-focus, transport and decoder states without private paths or
capability URLs. Startup checks issue one Play action; they do not retry Play to
hide a lost permission or unsolicited pause.

`video_hardware_probe.py` is an interactive isolated-app probe for explicitly
authorized iOS hardware. It uses synthetic local/LocalCrypt content, records
lifecycle/player state and reports any content or unmuted playback observed before
authorization. It does not establish audible output or real incoming-call behavior
without the corresponding user-operated actions. A provisioning profile without
Wi-Fi-information capability cannot validate real trusted-network recognition.
Keep its raw records under ignored test-results and remove only its QA app after
evidence collection, preserving the main app and data.

Desktop `features/video/ui/privacy.py` clears the decoder source on application
deactivation and restores controls only after asynchronous, revision-checked
password verification. Encrypted ZIP identity is pinned to the opening package;
passwordless packages require an in-memory temporary gate. Portable Qt tests cover
concealment, wrong/correct passwords, stale results and revocation. These do not
establish native desktop sleep timing or external-display capture guarantees.


Resume deferred physical testing from [session video hardware acceptance](hardware-acceptance.md).
This preserves the current-code test entry point and matrix, not an app build.
