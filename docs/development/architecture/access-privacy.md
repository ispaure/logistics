# Access and privacy ownership

Treat I/O grants, resume authentication and permission to play or transmit as
separate checks. A process is protected while it has loaded session-only
credentials or a retained protected owner. Ordinary content in that process
also inherits protection. Retained private drafts keep it after credential removal.

| Event | Rule |
| --- | --- |
| Bluetooth on an ordinary process | Bypass approval records, including malformed records or unknown identity. |
| Protected Bluetooth | Require an approved selected output and separate Play. Pause on route changes or protection transitions. |
| Output loss or call interruption | Pause in either mode. Resume only on explicit Play. |
| Protected background, screen-off or iOS inactivity | Shield before conceal/lock effects. Authenticate the current challenge on return. |
| Protected cast, external display or PiP | Refuse even after successful authentication. |
| Background read-aloud opt-in | Continue admitted content subject to grant, route, call and capture checks. The sleep timer ends listening only. |
| Private export | Obtain explicit plaintext consent. [Storage and export](document-storage.md#privacy-and-lifetime) |

## Explicit retained protection sources

`mobile.protection` owns the process scope for a credential runtime. Register
window owners with `app.protection.register(owner, owner.privacy_gates)` and keep
the release handle. Use synchronous gate snapshots without I/O. Publish before
mounting sensitive content and call `app.protection.changed()`. Use the optional
`protected` supplier for playback restrictions without a password challenge.
Duplicate gates share a challenge.

Consume explicit provider `session_only` declarations through wrappers. Unknown
private providers conservatively refuse external playback. Keep grant validation
at the I/O boundary. Storage rows label session-only content beneath the title.

## Clipboard commands

The opt-in **Restrict clipboard in protected sessions** preference gates
clipboard commands at execution. It makes no clipboard writes on activation,
lock, preference changes or final release. A blocked Cut leaves the selection
and document intact, and blocked Paste inserts nothing. File Browser clipboard
transfers and the notebook canvas's internal ink and image operations have their
own scope.

| Surface | Enforcement and limits |
| --- | --- |
| Qt desktop | Standard focused shortcuts and Qt context actions for text widgets and embedded WebEngine. Logistics Edit actions and chat and Git clipboard writes consult the same decision. Linux primary-selection publication, direct accessibility text access, and OS clipboard history and sync are separate. |
| Android | Toga EditText covers text menu commands through the native edit handler. WebView intercepts standard shortcuts, Chromium selection actions routed through Android ActionMode, and DOM clipboard events on WebView versions with document-start scripts. Keyboard providers can still insert content as typed text. |
| iPhone and iPad | UIKit fields, text views and WebKit standard clipboard responder actions check the current process scope. WebKit link and image preview menus and system keyboard services are separate. |
| Mobile Chat | The transcript requests Copy through its host. The host rechecks the scope before writing rendered text to the platform clipboard. |

The desktop protection scope queries the existing session credential registry
and retains desktop private-view guards. A hidden view whose plaintext has
yet to retire counts until its window is destroyed. Mobile uses the existing
credential runtime and retained-owner protection scope shared by its scenes.
The mobile preference is stored with the primary host so it has one effective
value across scenes. Android publishes the current decision to native controls
at protection and preference changes. UIKit queries it in the responder.

The Qt regression runs on the offscreen clipboard. The mobile probe uses
generated strings and Manager-owned disposable devices. It checks native text
context handlers and focused shortcuts, embedded text editing, Chat Copy,
credential lock and final owner release. A second scope models process-wide
retention. On supported iPads the probe also opens a real second scene and
checks that protection held by the primary scene applies to its editor.

## Resume challenges and asynchronous callbacks

`services.session_auth.ResumePassword` separates setup, manual and lifecycle
challenges. Trusted Wi-Fi can waive only a current, eligible lifecycle challenge
for previously unlocked credentials. Unknown networks, lookup failures and
changed preferences retain the challenge. Recheck the challenge revision after
asynchronous work. Credential replacement revokes old I/O grants independently.
Use `resume_locked` for authorization state. `saved_content` belongs to the form.

Publish credential changes under the credential lock, then notify outside it.
Protection runs before ordinary UI observers. Native shielding is synchronous.
Queued callbacks must recheck owner lifetime and lifecycle revision before reveal.

## Effect order and failure boundaries

`ScreenPrivacy.prepare_native_protection` covers iOS or secures the Android
window before callbacks. Keep the shield if a required callback fails. Deny Play
before queuing pause. Pause and release fanout attempts all owners, retaining
failed releases for retry. Invalidate fixed native casting controls by retiring
the player when its restriction changes.

Conceal pixels, clear private labels and retire buffers before releasing protection.
On iOS, stop and release VLC on its serial worker, then return to the UI loop to
close the provider. Reopen awaits the same cleanup. Failed disposal retains
protection and denies new commands.

### Protected video and speech

Video captures its source policy with its retained grant. Removing credentials
cannot relax a player's own restriction. Audio Play uses the current selected
route and invalidates pending approval across lifecycle, route or settings
changes. If a submission check sees a route change before the monitor does,
it revokes consent immediately and queues the player pause on the UI loop.
A late callback must preserve a newer, currently authorized Play.

For speech, retain the accepted document and reading position if output consent
is lost. Recheck before submitting each utterance. Apply capture/call/output
safeguards in native adapters and keep the listening timer in commonUtils.

Credential setup and removal exercise the same retirement rules as window close.
Unwind subscriptions after failed construction, mark listeners inactive before
release and retain failed handles. Process scope snapshots evaluate suppliers
outside the snapshot lock, then check revisions before publishing. This avoids
credential/scope lock inversion and prevents older results replacing newer ones.

## Validation scope

Check `native/test_audio_output.py`, `workspace/test_screen_privacy.py`,
`workspace/test_trusted_wifi.py` and `test_protection_scope.py` under
`mobile_build/tests/` for stale callbacks, consent, multiple gates and failure
retry. Host doubles cover policy. Native acceptance covers shielding, observers
and real decoders. Physical Bluetooth, Mirroring and acoustic leakage require
separate checks. [Audio validation](audio-playback.md)

## Mobile resume form layout

The card caps at 560 × 520 logical pixels and scrolls inside its inset viewport.
Refit on safe-area or keyboard changes, using Android's native visible frame.
Retire its layout listener on unlock or disposal. The lockscreen probe checks
rotation with the keyboard open, wrong passwords, scrolling, Unlock and restored
navigation. Run from root with the mobile build environment:

Use a fresh run identifier for `RUN_ID`.

```sh
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.lockscreen_tools ios --output tmp/test-results/RUN_ID/lockscreen-ios
PYTHONPATH=Python:. mobile_build/.venv/bin/python -m mobile_build.validation.lockscreen_tools android --android-image 'system-images;android-35;google_apis;arm64-v8a' --output tmp/test-results/RUN_ID/lockscreen-android
```
