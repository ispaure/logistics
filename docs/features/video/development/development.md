# Video Player development

See the [desktop/mobile playback audit](playback-audit.md) for functionality
differences, remaining oversights and the adjustable memory-buffer policy.

| Change | Owner | Focused checks |
| --- | --- | --- |
| Provider admission and subtitles | `Python/features/video/playback.py`, `subtitles.py` | `test_video_player.py`, `test_cloud_video.py` |
| Range transport and resume | `transport.py`, `services/documents/video_progress.py`, `video_state.py` | `test_video_player.py`, `test_cloud_video.py` |
| Desktop controls and decoding | `ui/player.py` | `test_video_decode.py` |
| Mobile adapters and payload | `mobile/`, `mobile_sources.json` | mobile `test_video_player.py`, packaging checks |

Video is independently registered as `video` on desktop and mobile. Media Tools
retains MKA renaming. The previous mobile `media` disabled preference migrates to
`video`; native Java/Objective-C class identities stay unchanged. Decoder imports
remain lazy. See [feature conventions](../../../development/features.md).

## Video player

The [brief](video-player.md) is the acceptance contract. `playback.py` admits
Local, LocalCrypt and remote/crypt video sources admitted by `formats.py` through retained `ProviderContent` grants.
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
Reopen references are separate: successful mobile presentation publishes a
`file-reference` of kind `video` through `RecentDocuments` or the existing
credential-password encrypted document-list owner. The latter records recent
history only, without adding video to restored open documents. Recent entry
activation resolves current credentials again and dispatches to the native player,
including offline encrypted copies whose stored keys have no filename extension.

`ui/player.py` integrates Qt Multimedia/FFmpeg into desktop document hosting.
It provides seeking, volume, embedded audio/subtitle selection, bounded UTF-8 SRT
captions, fullscreen and policy-checked floating playback. LocalCrypt browser
activation dispatches directly to the retained provider-backed player.

`mobile/player.py` owns native presentation, periodic checkpoints, credential
revocation and shutdown. Mobile storage dispatch and feature admission occur
before attempting a text/document import. The host's existing screen privacy,
Back and shutdown owners retire or conceal the player. Native controls perform
their own policy checks before play, cast and picture-in-picture requests.

`retire()` immediately denies commands and starts native disposal. `close()` waits
for that shared completion barrier, then saves the captured checkpoint and closes
transport/provider resources before releasing protection. iOS releases VLC on a
serial worker so decoder-to-UIKit callbacks cannot deadlock the UI thread.
An independent process resource scope survives host-window disposal until this
cleanup completes; navigation cancellation cannot release it early.

Android uses `org.videolan.android:libvlc-all:3.7.5`; its feature-owned Java surface
is installed through the existing Gradle source owner. iOS uses the official
VLCKit Swift package at the immutable revision in
`mobile_build/build_support/video_build.py`. That package currently distributes a
4.0 prerelease SDK, required for its PiP protocol. The existing iOS build helper
links the package and installs the feature-owned Objective-C controller.
These native SDKs and their upstream notices must be retained in packaged builds.

Mobile fullscreen is owned entirely by the native adapters. Fullscreen auto-hide
conceals controls and the Android system bars or iOS status
bar/home indicator. A surface tap reveals controls and a three-second timer hides
them again during playback. Pause, completion and errors reveal controls. Timers
defer during seeking, menus and screen-reader use. Android saves and restores the
host's bar visibility and behavior across concealment/disposal; iOS uses controller
appearance overrides and invalidates its timer on retirement/disappearance.
This presentation state does not grant playback or bypass credential gates.

Visible local playback holds the display awake independently of the control-hide
timer. iOS uses a counted idle-timer request across scene players, restoring the
previous app setting when the last player releases it. Android requests screen-on
only on the attached video root. Pause, stop, completion, errors, interruptions,
concealment and retirement release the request. Casting and picture-in-picture
do not hold the main display awake. The native fullscreen probe observes the
actual idle request during Play and after Pause; API compiler checks alone do not
establish device timeout behavior.

Desktop transport buttons expose play/pause, ten-second skips and mute, with
accessible labels, tooltips and keyboard equivalents. Track selectors retain
visible labels and the controls stack below 520 pixels. Fullscreen uses the shared
reader state owner so its button and native window state agree and maximization
is restored. Android uses 48-dp targets and responsive playback/utility groups.
iOS presents `LGVideoController` inside `LGVideoNavigationController`, with real
`UIBarButtonItem` groups for Close, transport and utilities. UIKit owns their
axis, edge, shared glass and overflow; no custom-view button stack substitutes
for a native side bar. The container forwards immersive status/home-indicator
preferences to the player. Its timeline follows safe areas and active UIKit
division regions, updating for hinge and window changes. The timeline overlays the full movie surface. Showing or hiding controls
does not change its bounds or vertical center.
The iOS ten-second buttons and slider use bounded absolute times. Paused seeks
retain their requested position in the existing deferred-resume state, including
zero, and explicit Play reapplies it after authorization. This keeps controls and
checkpoints consistent when VLC has not yet updated its paused decoder clock.

### Validation and remaining release gates

The focused iOS `video_ui_probe.py` inspects rendered native item frames and
hit testing, exercises selectors and fullscreen, and sweeps closed, partial and
open Duo poses in portrait and both landscape directions. Upside-down portrait
is also requested; a UIKit scene error 101 is recorded separately as unsupported,
not counted as a passed orientation. The companion can inject a simulator touch
to verify immersive control reveal. Notebook page-selection checks run in the
same owned QA app's WKWebView; synthetic contacts do not certify physical palm
rejection or Pencil latency.

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

The optional `video_probe_tools --ui --ios-app ... --ios-model 'iPhone Duo'`
checks actual button frames/hit testing and dispatch through portrait and both
landscape directions. With an explicitly reviewed `--duoctl PATH`, `--pose open`,
`partial` or `closed` applies a simulator pose before launch. `--appearance` and
`--content-size` apply to that owned simulator only. Keep the helper and its cache
inside retention-managed scratch; retain its source identity with ignored evidence.
`--pose-sweep` additionally folds and unfolds the retained player, then checks
portrait and both landscape directions on the outer, partial and reopened inner
display without reopening the video.
The probe checks fold exclusion, scroll reachability, playback/skip/track actions,
fullscreen reveal and restoration, and saves screenshots. Simulated poses do not
establish physical touch/VoiceOver or genuine left/right system Split View.

### October 28 responsive controls validation

Fresh managed Android and iOS 27.1 simulator builds passed with these native
controls. The Android probe passed eleven cases: four rotation layouts with
reachable 48-dp buttons, fullscreen/tap/timer/bar restoration, all eight required
codec/container combinations with decoded test-pattern frames, and LocalCrypt
encrypted resume/password/external-playback denial. The Duo probe passed thirteen
states across inner, outer, partially folded and reopened displays, with portrait
and both landscape directions. The same retained player survived folding; active
division regions stayed clear of control hit targets. Playback, pause, ten-second
buttons, Tracks, fullscreen and tap reveal dispatched correctly in the inner
rotation sweep. Its paused-seek check observed the actual VLC clock advance past
the requested target after explicit Play, rather than accepting the deferred UI
position alone. Native screenshots were visually reviewed.

Desktop button dispatch, mute/floating/fullscreen state and 360/560/1000-pixel
layouts passed with the decoder regressions. Mobile host video/probe regressions,
desktop privacy regressions, documentation layout and lint passed. The native
runners saved their evidence before removing every owned test device and scratch
tree; no personal app or data was replaced. Physical touch, audible quality/A-V
synchronization, genuine system Split View and the complete accessibility matrix
remain separate acceptance work.

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

## Streaming latency and viewer controls

HTTP range admission checks the retained revision; remote providers validate each
new decoded range before and after retrieval. Loopback chunks recheck local
credential/gate access without issuing cloud stat requests twice per 256 KiB.
Local files retain per-chunk revision checks. Streams remain seekable, so the
demuxer can request metadata, audio and video at different byte offsets; the
transport does not assume interleaved tracks or stage the complete movie.

Both mobile engines use a 3000 ms network cache. Render progress drives a quiet
stall indicator; background prefetch percentages are ignored because they can
arrive while buffered video is still playing. No synthetic percentage is shown. Codec support comes from
the existing pinned VLC SDKs, preserving automatic hardware decoding and software
fallback, rather than a new codec dependency. `formats.py` centralizes desktop,
mobile, import and remote activation. Representative fixtures cover MPEG-4/MP3
and MJPEG/PCM AVI and AC-3, E-AC-3 and FLAC MKV in addition to H.264/HEVC/AAC/Opus.
A container extension alone does not certify every codec variant.

iOS mounts a center transport group, a right utility rail, and a bottom timeline
inside current safe areas. Active fold geometry repositions controls into an
available region. VLC rendering subviews do not participate in touch hit testing;
a root tap remains available after auto-hide. Audio and subtitles have separate
selectors; iOS labels combine track name, localized language, description and
codec where present. Standalone images, comics and PDFs start with immersive
content; tapping restores their existing controls.

The viewer regression pass validated the managed iOS simulator build with 13
codec fixtures, closed/partial/open Duo control geometry, two audio tracks and
embedded subtitles, and synthetic WebDAV/crypt playback, seeking, authentication
and revocation. Desktop playback covers the same codec matrix. Simulator results
do not establish physical device touch or energy behavior. The original physical
Duo stall session could not be recovered after its device connection dropped;
its particular throughput, interleaving and decoder cause remain unverified.


## Initial playback, surface geometry and remote read-ahead

Opening a video starts playback after native presentation and navigation/access
checks. Both native adapters use the same audio-consent and interruption checks
as Play. Returning from background, authentication or an interruption remains
paused. Desktop starts through its existing guarded playback action.

iOS extends the video surface behind native bars and overlays the timeline at
the physical window's safe bottom. Controller top/side guards remain in place;
an adaptive side rail's inherited bottom inset does not reserve another gap.
Fold regions still constrain the available control panel. Controls never change the movie constraints. VLCDrawable
rendering subviews receive the movie bounds on insertion and layout, including
rotation/fold updates. Android keeps its full-surface video and puts its timeline
below the button rows, with no extra bottom inset beyond the system safe area.

The native `remote_range` bridge admits reads up to 4 MiB, with identity and
revision checks before and after the read. Native Go boundary tests and the
Python integration test against the rebuilt host bridge cover the exact limit
and oversized rejection for plain and encrypted remotes.

Remote video streams use a shared, bounded 128 MiB memory LRU across HTTP
streams, with 4 MiB provider ranges and a four-chunk, 4 MiB read-ahead queue
per response. `buffering.py` centralizes these adjustable limits. Rewinding into
retained ranges reuses their bytes instead of starting another download. The producer overlaps cloud
fetches with decoder consumption; queued chunks recheck access before delivery.
Cancellation stops and joins the producer before the provider stream closes.
There is no decrypted disk cache. Network throughput can still cause buffering;
these limits do not guarantee uninterrupted playback or repair damaged codecs.


### Network starvation holds

Mobile loopback readers report a readiness hint after half a second without a
queued chunk. A hint alone never pauses playable data. Native controllers watch
both rendered-frame counters and playback time, and
show a quiet spinner after three seconds without either kind of progress.
A separate six-second rendered-frame watchdog during network waits catches VLC
clocks that free-run through a frozen picture; recovery retains the last frame
checkpoint rather than the later audio clock. VLC statistics arrive
in batches, so this threshold allows for their reporting interval. A real stall
with a network hint retains the last rendered position and queues Pause while
the producer keeps fetching. iOS recovery resumes the retained decoder without
an automatic seek, preserving reference pictures and buffered AVI demuxer data.
Explicit user seeks still apply. Android recovery seeks to the held position. Both resume only
if playback is still requested and audio/access checks pass. Manual Pause wins
over readiness, and the button reflects requested state immediately rather than
VLC's delayed asynchronous state. Returning from a credential lock synchronizes
readiness without restarting playback.

iOS disables libavcodec hurry-up decoding and output of frames marked corrupt.
This favors complete pictures over partial catch-up after starvation. It does
not repair damaged source frames or guarantee that all corruption is detected.
The physical Duo screenshot on October 29 confirmed block corruption and excess
timeline spacing before these changes; the exact source/decoder cause and the
fixes' effect on that movie still require physical playback acceptance.

The reusable native `video_buffer_probe.py` checks playable-prefetch behavior,
manual Pause and rotation for MP4 and AVI. `video_stall_probe.py` accepts a
read-only host fixture and a controllable slow-read endpoint to check actual
render starvation, held checkpoints, recovery and immediate command feedback.
These probes do not establish physical receiver behavior or cloud throughput.


### Chapters and Duo laptop controls

Native chapter menus use VLC's chapter descriptions and seek through the same
access-checked, paused-state-preserving path as the timeline. Desktop Qt has no
chapter API: `chapters.py` reads Matroska ChapterAtoms and MP4 `chpl` metadata from
seekable provider streams with a 2 MiB logical metadata budget and bounded element
counts/depth. It skips media payloads, uses SeekHead entries when available, and
does not spawn a decoder or stage plaintext. Unsupported chapter tracks, ordered Matroska editions and unindexed chapters
after media clusters are omitted; chapter lookup never walks all cloud clusters. Desktop loading runs off the UI thread; closing
cancels and joins that reader before releasing the content.

On iOS 27.1, a partial hinge state plus a horizontal reserved division activates
the Duo deck. The movie's lower constraint stops above the crease, the spinner is
centered within that movie region, and persistent transport/utility controls sit
below it. No split is inferred from an arbitrary screen aspect ratio. The native
`video_fold_probe.py` and `validation/fixtures/video_fold_geometry.m` exercise the
real controller with a QA-only reserved region; they do not certify physical hinge
orientation or receiver behavior.

Transport admission keeps four active reads and queues replacements for up to ten
seconds instead of rejecting ordinary AVI seek bursts immediately. Failures emit
only access/changed/read/busy categories. Native unexpected stop/error hides the
spinner, preserves a retry position and requires explicit guarded Play. Readiness
and failure hints never pause video that is still progressing.

### Playback tool ownership

`session.py` owns time validation, natural folder queues and preference values.
The host service `services/documents/video_settings.py` persists nonsecret settings.
`services/documents/video_progress.py` owns progress policy, `video_migration.py`
retires legacy records, and `video_state.py` owns device/remote encryption adapters.
Session-only positions use the credential ZIP password through the shared document-state owner. Non-session-only remote records retain their authenticated host encryption.
Encrypted records have opaque hashed names and bind source identity/revision.
There is no plaintext fallback. LocalCrypt progress continues through its provider.

`ui/controls.py` owns the Qt tools and approximate cache strip. `mobile/controls.py`
routes native commands, retains subtitle streams and waits for outstanding
provider work before releasing resources. Native `PlaybackControls.m/.java`
implement options, keyboard/touch input and sizing. `PausePresentation.m/.java`
retain volatile paused frames; they do not write screenshots. Android uses a
TextureView so its frame can be held without waiting for asynchronous decoder
pause. The iOS build helper stages these imported implementation files, and the
SDK validator fingerprints every native helper.

The [desktop tools](../user/controls.md) and [mobile tools](../user_mobile/controls.md)
document current behavior. Host contracts cover durable authenticated resume,
revocation/revision checks, queue ordering, preference bounds, time parsing and
cached-range eviction. Actual Qt playback verifies the responsive controls.
SDK compilation checks native interfaces; new touch/keyboard/pause/fold behavior
has not yet received physical-device acceptance. These additions are separate
from the baseline build/install requested before implementation.

### iOS control fade and playback menu regression

`mobile_build/validation/video_chrome_tools.py` compiles the current native controller against
an explicitly supplied, existing VLCKit simulator framework and runs the UIKit
fixture `mobile_build/validation/fixtures/video_chrome_checks.m` on a manager-owned disposable
simulator. Supply `--framework`, a fresh `--output` under `test-results/`, and
`--model` (`iPhone Duo`, `iPhone`, or `iPad`). `--orientation landscape` requests
a real scene rotation; the result retains the resulting orientation and bounds.
The runner selects the newest installed runtime compatible with the model. Compiler output lives in a leased
scratch workspace; the simulator is removed even on failure.

The probe starts a synthetic local movie, observes the initial auto-hide and
intermediate presentation-layer opacity, checks that status-bar visibility and
header position remain stable during the fade, then opens Playback and its
related option sheets. The shared menu factory owns their single Cancel action. Phone option lists use
scrollable alerts to avoid overflowing a compact Duo popover; iPad keeps anchored
action sheets.
The auto-hide timer retains its deadline across decoder notifications; explicit
control interactions reset it. Status/navigation removal commits only after the
control fade. These checks establish simulator behavior, not physical Duo touch.

The iOS video identity uses the navigation item's title view, with a centered
filename and storage caption inside a glass effect (dark material on older iOS).
Side-bar layouts move that title to the physical top safe area, matching document
viewers. Compact horizontal bars that omit UIKit's title view retain the identity
in the top-row gap between Done and the transport controls. Cached ranges are a noninteractive slider subview measured from
`trackRectForBounds:`, with 60% of the previous vertical gap and no additional
stack row beneath the seek control. The chrome probe checks endpoint alignment
and spacing and saves a synthetic-video screenshot before its menu checks.
