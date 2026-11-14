# Audio playback and capture privacy

Mobile video and all existing mobile read-aloud paths (EPUB, Markdown and plain
text, including provider readers) share one output-consent owner. There is no
standalone music player in the current app. This policy does not add one.

## Behavior at a glance

| Event | Ordinary content | Any session-only credentials loaded |
| --- | --- | --- |
| Start audio on an identifiable built-in/wired output | Ordinary player controls | Explicit Play plus the existing credential authorization |
| Start audio on unapproved Bluetooth | Bypass approval list; ordinary playback | Block; offer approval plus credential authorization |
| Approve Bluetooth | Not required; no playback dependency on the list | Save approval; remain paused until a separate Play |
| Selected audio output changes, including to an approved device | No consent-related pause or extra Play | Pause; separate Play required |
| Decline/cancel, unknown identity, or remove approval | No approval-list restriction | Remain paused; no fallback to speakers |
| OS-reported iOS capture/mirroring/remote control | Ordinary document browsing remains available | Black app shield; pause app audio; conceal video |
| Android capture or nonsecure display | Ordinary document browsing remains available | Secure-window protection; video external modes refused |
| Call/interruption or headphone/Bluetooth output loss | Pause; never automatically resume | Same; resume authorization still applies |

Bluetooth consent and the separate Play requirement on output changes apply only
while session-only protection is in effect: at least one loaded session-only
credential, or retained protection that would also forbid screencasting. The
scope covers the process and retained protected readers/players, not just the
currently displayed file. Ordinary playback never reads the approval list or
requires an identifiable Bluetooth output. Native output-removal/loss and call/interruption
safeguards remain independent and still pause ordinary playback; reconnection or
interruption end does not automatically resume it.

A Bluetooth approval grants an output, not access to a credential session. Existing
trusted-Wi-Fi behavior only waives eligible repeat password prompts. It does not
waive Bluetooth approval or capture restrictions. Approvals are device-local app
preferences, separate from system pairing. Manage them in **Settings → Privacy &
Security → Protected audio outputs**. Only selected outputs are candidates for approval; nearby and paired
but unused devices are not treated as active outputs. Device names are labels,
not authorization identities. Saved identifiers hash the platform port UID/address
and profile; profile/identity changes may require a new approval. This is not
cryptographic hardware attestation.

## Ownership

`services/audio_output.py` is toolkit-free consent state and preference validation.
`mobile/audio_output.py` owns the route generation, explicit Play latch, native
lifetime, coalesced approval prompts and cross-scene revocation. It consumes the
explicit process protection scope; it does not discover privacy through UI
observers or player internals. See [access and privacy](access-privacy.md) for
registration, challenge provenance and effect ordering. A route, lifecycle,
credential or Settings change invalidates a pending approval. Approval leaves
the Play latch closed. Passive checks compare the current native route with the
admitted route to catch changes before callback delivery. Native monitors and
explicit commands update the observed route and own pause and dialog effects.

`mobile/audio_output_native.py` and the Android `AudioOutputs.java` class query
outputs and report transitions. On iOS, the approval alert is presented above
the visible native controller, including full-screen video. If iOS dismisses
that controller and its alert, Play or Settings can offer approval again.
The mobile host injects the consent owner into read-aloud presentation. Video
mutes during its explicit pause callback, and mobile read-aloud stops the
current native utterance and retains the reading position. Video checks
permission before starting and during playback. Read-aloud checks before
submitting each utterance. Host replacement or exit unregisters the native
monitors and cancels pending prompts.

`mobile/screen_privacy.py` remains the app-wide screen owner. Capture restrictions
use the process credential store, including sessions loaded in another window,
not just the active document. iOS observes both screen capture and scene capture
traits, covers the app window above native modals, and suspends sensitive video.
Audio is denied across scenes while a sensitive scene reports capture. Ordinary
speech metadata becomes generic whenever any session protects the app.

## OS boundaries and residual concerns

- Apple's supported [scene capture API](https://developer.apple.com/documentation/swiftui/protecting-sensitive-content-when-screen-sharing)
  covers OS-reported capture, mirroring and remote control. Actual **iPhone
  Mirroring** transitions still require hardware acceptance; a Mac being authorized
  by the OS does not authorize a Logistics session. A cast flag alone is insufficient.
  iOS has no supported general still-screenshot prevention API. External cameras
  and a compromised OS remain outside app guarantees.
- iOS queries the active [audio session ports](https://developer.apple.com/documentation/avfaudio/avaudiosessionportdescription).
  Android 13+ queries anticipated media outputs with
  [getAudioDevicesForAttributes](https://developer.android.com/reference/android/media/AudioManager#getAudioDevicesForAttributes(android.media.AudioAttributes)).
  If the selected-route query is unavailable, Android accepts a single enumerated
  output or an internal-only speaker and receiver combination. Multiple outputs
  with an external device remain ambiguous. Unreadable or redacted Bluetooth
  identities also fail closed only for protected playback. Ordinary playback bypasses these consent checks. The app does not silently trust a display name.
- Android device callbacks plus a 100 ms route recheck catch selection changes
  without connection events. Both operating systems can reroute an active
  stream before the app observes the change. Receiver buffers can also retain
  audio already sent to them. Verify brief audible output during a transition
  on physical hardware. Android output-removal callbacks pause even when the
  removed output was idle.
- Saved progress, subtitles, thumbnails, stream tokens, native decoder buffers and
  credential revocation retain the video feature's existing lifetime rules. No
  whole-file plaintext staging or audio transcript/cache is added by consent.
- Desktop capture protection remains best effort and has separate platform limits.
  The new approved-output list is implemented in the mobile host; desktop Qt
  playback does not yet have equivalent selected-Bluetooth identification/consent.

## Validation and deferred acceptance

The portable output tests cover reconnect before callback delivery, duplicate
route events, read-aloud pause and retry after a declined video approval, and
Settings approval with a device selected at launch. The iOS bridge fixtures cover
raw notification arguments and alert presentation over full-screen video. The
existing tests cover ordinary playback, unknown identities, cross-scene revocation
and interruption and capture latches.
`mobile_build.validation.video_native` compiles the changed iOS video gate and all
three Android audio/video adapters against native SDKs. Compilation and dummy-host
checks do not establish real iOS/Android route behavior.

The reusable `audio_hardware_probe.py:main` opens **Settings → Privacy & Security**
with native read-aloud controls and transition logging. The
existing `video_hardware_probe.py:main` includes ordinary/session-only audio phases
and an enabled-but-unavailable Wi-Fi password phase. Rebuild native adapters and
Python from current source before using either entry point. Physical
Bluetooth acceptance requires an authorized device session.
Follow the [video hardware guide](../../features/video/development/hardware-acceptance.md)
for isolated app/device authorization, source freshness, evidence and cleanup.

## Disposable read-aloud playback acceptance

Before a fresh probe build, follow the [pinned wheel setup](../build-release/mobile-device-deployment.md)
and export `PIP_FIND_LINKS` in the same shell so Briefcase's
child installers can find it. Then run from the repository root with the prepared
mobile interpreter.

```sh
mobile_build/.venv/bin/python -m mobile_build.validation.document_storage_tools ios \
  --probe speech-playback --output test-results/speech-playback
```

`--ios-runtime` accepts an installed CoreSimulator
runtime identifier; combine it with a supported `--family` when comparing OS versions.
Selecting `--family all` also requires network access for the runner's pinned,
hash-checked Duo helper, or an existing reviewed helper passed with
`--duoctl /absolute/path/to/duoctl`.
The lease records the exact selected runtime and model. Existing devices are only
read to select a compatible model; the runner creates and removes its own simulator.

The fixture opens Read aloud Settings, uses the production `NativeSpeech` adapter
and read-aloud panel, restores a missing saved voice to the system default and
requires native playback-start, word-progress and completion callbacks. An unavailable
engine fails this strict probe. Its initialization trace records the production
function's executed source lines, which distinguishes voice enumeration/default
lookup stalls from synthesizer construction. Callback completion verifies native
playback, not acoustic volume or physical speaker/Bluetooth behavior; physical
acceptance remains with the release coordinator.

Cleanup still removes the lease-owned simulator after app-termination/uninstall
timeouts or evidence-copy failures. Ownership is checked before app cleanup actions.
