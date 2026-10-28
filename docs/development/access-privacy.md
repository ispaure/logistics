# Access and privacy ownership

Logistics owns application privacy policy; commonUtils owns retained resource,
cancellation and speech mechanisms. A valid credential grant, an authenticated
resume challenge, and permission to play or transmit content are different facts.
Unlocking one does not grant the others.

## Behavior contract

Protection means loaded session-only credentials or a retained protected owner
that still requires external-sharing refusal. Encrypted storage alone does not
mean session-only credentials. Scope includes ordinary content in the protected
process, not just the active file. Closing a view does not unload credentials;
removing credentials does not make a retained private draft public.

| Situation | Required behavior | Existing regression owner |
| --- | --- | --- |
| No protection, Bluetooth selected/changed | No approval-list dependency or protection-specific pause/Play gate, including unknown identity and malformed approvals | `native/test_audio_output.py` |
| Protected audio, already-connected/new Bluetooth | Selected output approval; adding approval never starts audio; separate Play | `native/test_audio_output.py` |
| Output loss or call/interruption, either mode | Pause; no automatic resume | audio and native video tests |
| Protection starts/ends during playback | Reevaluate immediately; reject stale approval; no unsolicited resume | audio tests |
| Background/screen-off with protected content | Conceal; require eligible resume authentication; retain native immediate safeguards | `workspace/test_screen_privacy.py` |
| Trusted Wi-Fi resume | Waive only a lifecycle challenge for previously unlocked credentials; unknown/failed lookup challenges normally | `workspace/test_trusted_wifi.py` |
| Manual lock, initial setup, revoked/replaced grant | Wi-Fi cannot authorize it; authentication cannot revive an invalid grant | Wi-Fi, credential and screen tests |
| Cast, external display or PiP while protected | Refuse even after password/Wi-Fi authentication | external-display and video tests |
| Background speech opt-in | Continue admitted content only; retain output/call/capture/grant checks; do not authorize new file reads | speech/audio tests |
| Read-aloud sleep timer expires | End the listening budget; do not lock credentials or change protection scope | commonUtils speech tests |
| Progress/recovery/export | Preserve existing provider-owned encrypted publication and explicit plaintext-export consent | document and video-progress tests |

Paths in the table are relative to `mobile_build/tests/` unless noted. See
[audio playback](audio-playback.md) for platform limitations and hardware probes.
Device sleep is an environment/lifecycle event; the speech timer counts listening
time and is not a credential gate.

## Baseline and migration

The starting source is `2fa216af`, with commonUtils `b9c7f78a`. It includes the
corrected ordinary-playback Bluetooth bypass. Focused baseline audio (21 cases)
and Wi-Fi (18 cases) host checks passed on October 28, 2026; these are dummy/portable
checks, not physical Bluetooth or Mirroring acceptance.

The current migration removes provider-policy inference from video, explicit
feature inventories from screen protection, and authorization based on lock-form
widgets. Each bounded change must integrate its effects, disposal, tests and
documentation. Keep provider grant validation at I/O boundaries and native
immediate denial in platform adapters. Do not replace them with a UI-only check.

No new encrypted format, export policy, desktop Bluetooth feature or generalized
permission framework is required. Preserve stored settings and credential IDs.

## Provider declarations

`services.access_policy.session_only` composes explicit provider declarations
through document wrappers. Video no longer reads credential package dictionaries
or guesses retention from context filenames. Desktop LocalCrypt declares its
memory-only context; native LocalCrypt derives the declaration at its owning
credential boundary. Unknown private providers conservatively refuse external
playback. Document persistence and provider I/O grants remain separate.

## Explicit retained protection sources

The native credential store owns a lazy process `ProtectionScope`. Loaded
credential gates contribute directly, before any scene or player exists.
`mobile.protection.for_app` gives composition one window scope. Private-session
managers, EditorPicker, NotebookPanel and ComicBatchController register their
own gate suppliers; ScreenPrivacy asks the scope instead of inspecting feature
attributes. Suppliers are synchronous snapshots with no I/O. Notebook disposal
releases its registration; host disposal clears all window sources. A retained
draft keeps its gate after credential removal; duplicate contributions share one
challenge. Providers still validate the original grant independently.

## Resume challenges and asynchronous callbacks

`services.session_auth.ResumePassword` is platform-neutral. It records setup,
explicit and lifecycle challenge reasons separately from provider revocation.
A repeated lifecycle callback neither overwrites a manual lock nor restores a
failed Wi-Fi waiver. `authorize(revision)` accepts a verified result only for
that challenge; `waive_lifecycle(revision)` additionally requires a still-eligible
lifecycle lock. Wi-Fi holds only the pending request snapshot, not another global
lock-provenance dictionary. Network preference changes while a read is pending
reject its waiver. Multiple passwords remain separate challenges.

Credential publication snapshots observers under the credential lock and calls
them after releasing it. UI callbacks return to their scene loop. Native screen
shielding stays synchronous; asynchronous verification cannot reveal content
after rebackgrounding or credential replacement. These callbacks never revive a
revoked I/O grant.
