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
preferences, not the system pairing list, and can be removed in **Settings → Audio
playback**. Only selected outputs are candidates for approval; nearby and paired
but unused devices are not treated as active outputs. Device names are labels,
not authorization identities. Saved identifiers hash the platform port UID/address
and profile; profile/identity changes may require a new approval. This is not
cryptographic hardware attestation.

## Ownership

`services/audio_output.py` is toolkit-free consent state and preference validation.
`mobile/audio_output.py` owns the route generation, explicit Play latch, native
lifetime, coalesced approval prompts and cross-scene revocation. A pending dialog
cannot approve a route after a route, lifecycle, credential or Settings change.
Approval never clears the Play latch. Native callbacks and passive permission
checks never grant playback.

`mobile/audio_output_native.py` and the Android `AudioOutputs.java` class query
outputs and report transitions; they do not decide consent. The mobile host injects
the owner into read-aloud presentation. Video and speech register explicit,
idempotent pause callbacks. Native video admits deliberate Play separately from
its periodic permission checks; native speech resume also checks permission before
resuming an already-synthesized utterance. Host replacement/exit unregisters the
native monitors and cancels pending prompts.

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
  Older Android cannot reliably distinguish selected from connected outputs when
  several exist; protected playback then fails closed. Unreadable/redacted Bluetooth
  identities also fail closed only for protected playback. Ordinary playback bypasses these consent checks. The app does not silently trust a display name.
- Android device callbacks plus a 100 ms route recheck catch selection changes
  without connection events. OS routing can precede notification or polling;
  this is not a guarantee of zero audio at a new physical output. Android output-removal callbacks retain the existing conservative pause, even if the removed output was not selected. Real car,
  multipoint/BLE/headset, speaker leakage and receiver-buffer behavior need hardware
  checks. An external receiver may retain audio already sent to it.
- Saved progress, subtitles, thumbnails, stream tokens, native decoder buffers and
  credential revocation retain the video feature's existing lifetime rules. No
  whole-file plaintext staging or audio transcript/cache is added by consent.
- Desktop capture protection remains best effort and has separate platform limits.
  The new approved-output list is implemented in the mobile host; desktop Qt
  playback does not yet have equivalent selected-Bluetooth identification/consent.

## Validation and deferred acceptance

The portable output tests cover ordinary playback bypass, ordinary route-loss/interruption safety, retained protection, protection removal during approval, before-start protected approval, protected output transitions,
unknown/same-name identities, separate Play, decline/cancel, Settings removal and
persistence, cross-scene revocation, stale decisions and interruption/capture
latches. Existing video, speech, Settings and privacy regressions accompany them.
`mobile_build.validation.video_native` compiles the changed iOS video gate and all
three Android audio/video adapters against native SDKs. Compilation and dummy-host
checks do not establish real iOS/Android route behavior.

The reusable `audio_hardware_probe.py:main` opens the real **Settings → Audio
playback** category with native read-aloud controls and transition logging. The
existing `video_hardware_probe.py:main` includes ordinary/session-only audio phases
and an enabled-but-unavailable Wi-Fi password phase. Rebuild native adapters and
Python from current source before using either entry point; old binaries cannot
exercise new native interfaces. Physical tests are deferred at the user's request.
Follow the [video hardware guide](../features/video/development/hardware-acceptance.md)
for isolated app/device authorization, source freshness, evidence and cleanup.
