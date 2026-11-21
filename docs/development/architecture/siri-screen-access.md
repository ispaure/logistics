# Siri access to onscreen content

Logistics cannot promise to exclude a visible session from Siri or Apple
Intelligence. The public SDK and Apple documentation review on November 21,
2026 found no supported credential-driven app, scene or view control for
Siri's acquisition of arbitrary on-screen content. The review covered
Logistics `5ff3790c2`, the iOS and iPadOS 27.0 and 27.1 SDKs and the macOS
27.0 SDK (Xcode 27.0 and 27.1).

## iPhone and iPad

| Mode | Feasibility |
| --- | --- |
| Siri AI questions about the live screen, including images and text | Dynamic exclusion unavailable in the public APIs reviewed. Siri AI onscreen awareness is documented for supported hardware on OS 27 and later. Callback delivery, ordering and results in Logistics are untested on hardware. [iPhone](https://support.apple.com/guide/iphone/siri-ai-ask-siri-about-whats-on-your-screen-iphmk4p88mkuky/27/ios/27), [iPad](https://support.apple.com/guide/ipad/iphmk4p88mkuky/ipados) |
| Visual Intelligence on a user screenshot, or Siri's ChatGPT handoff | Dynamic pixel exclusion unavailable. A system screenshot can feed Visual Intelligence, and Apple documents a Siri handoff that offers a screenshot or a separate app-provided representation. Confirmation controls sending photos and files to ChatGPT. Acquisition, previews and responses in Logistics are untested on hardware. [Visual Intelligence](https://support.apple.com/en-gb/guide/iphone/iph12eb1545e/ios), [Apple's handoff demo](https://developer.apple.com/videos/play/wwdc2025/275/?time=700), [ChatGPT confirmation](https://support.apple.com/en-ie/guide/iphone/iph00fd3c8c2/26/ios/26) |
| Structured app context, Spotlight and intent donations | Apps control the entities, associations, indexed items and donations they supply. The Logistics source audit found no document or credential entities, Siri domain schemas, intent donations, Core Spotlight publishing or searchable activity registrations. Widget intents and workspace restoration have the limited roles described below. System interpretation of visible text and user-selected Files content remains a separate path. [Contextual cues](https://developer.apple.com/documentation/appintents/providing-contextual-cues-to-apple-intelligence-and-siri), [Spotlight integration](https://developer.apple.com/documentation/appintents/spotlight) |
| User-managed exclusion | OS 27 Siri settings document **Excluded Apps** for app access, Search and suggestions where available. Its effect on live visual questions and screenshots is untested. Screen Time also offers a system-wide Siri restriction, and the ChatGPT extension has its own switch. These settings are independent of the Logistics session. [iPhone settings](https://support.apple.com/en-euro/guide/iphone/iphc28624b81abc/27/ios/27), [iPad settings](https://support.apple.com/guide/ipad/change-siri-settings-ipade5045bb1abc/ipados), [Screen Time](https://support.apple.com/guide/ipad/block-features-or-content-with-screen-time-ipad12c0a656/27/ipados/27) |

`UIScreen.isCaptured` (iOS 11) and `UITraitCollection.sceneCaptureState`
(iOS 17) observe active recording, mirroring or remote-control capture.
Apple's contract gives no Siri-specific signal or ordering before acquisition.
`sceneWillResignActive` and the corresponding application notifications
describe lifecycle transitions. Whether Siri fires either callback before
acquisition, including when it is already open, remains unmeasured.
The screenshot notification arrives after a screenshot, and
`UIScreenshotService` supplies an optional PDF representation.
[Capture guidance](https://developer.apple.com/documentation/swiftui/protecting-sensitive-content-when-screen-sharing)
· [Scene lifecycle](https://developer.apple.com/documentation/uikit/uiscenedelegate/scenewillresignactive(_:))
· [Screenshot notification](https://developer.apple.com/documentation/uikit/uiapplication/userdidtakescreenshotnotification)
· [Screenshot service](https://developer.apple.com/documentation/uikit/uiscreenshotservice)

SwiftUI `privacySensitive` marks views for privacy redaction. The scene's
`systemProtectionManager` (iOS 18) reports system authentication protection.
ScreenCaptureKit filters the stream the capturing app requests. Secure text
entry and Writing Tools controls apply to text input. FairPlay and
`AVSampleBufferDisplayLayer.preventsCapture` apply to media output. Apple's
App-Protected Content entitlement is for visionOS. These contracts provide no
Siri exclusion for the Logistics UIKit/WebKit window tree.
[SwiftUI privacy](https://developer.apple.com/documentation/swiftui/view/privacysensitive(_:))
· [System protection](https://developer.apple.com/documentation/uikit/uiscene/systemprotectionmanager-swift.class)
· [ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit)
· [Media capture protection](https://developer.apple.com/documentation/avfoundation/avsamplebufferdisplaylayer/preventscapture)
· [App-Protected Content](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.protected-content)

## Logistics protection boundary

`NativeCredentialState` creates a `ResumePassword` gate for session-only
imports and SMB additions. The native reply's package list and epoch govern
replacement and removal. Publication releases the credential lock before
notifying protection, UI and document observers in that order. The shared
`ProtectionScope` is protected while any credential gate or retained protected
owner exists. Each window has its own retained owners and consumes shared
credentials. Locking or authenticating a gate changes access while its
protection contribution persists. Removing the last package can leave
protection active through retained content.

`ScreenPrivacy` joins the process during window startup, reads state on its
initial refresh and observes native capture and lifecycle changes. Existing
windows apply native effects immediately for a UI-thread protection
notification and schedule a refresh on the UI loop. Off-thread notifications
schedule that refresh. The opaque iOS shield depends on capture, interruption,
or inactivity and also covers lock transitions while the app switches roots.
An active, unlocked protected window remains visible during ordinary use.
The iPad workspace delegate assigns the scene before `makeKeyAndVisible`
and reports activation transitions. This sequence describes the existing
lifecycle behavior. It supplies no pre-acquisition fence for Siri.

The `io.github.ispaure.logistics.workspace` activity carries a workspace ID
for scene activation and restoration. It declares no entity association or
search eligibility. `SetWidgetValue` accepts explicit widget values, and
`SyncWidgetValuesToWatch` sends widget snapshots. Widget configurations
select named values. These actions expose no document or credential query.
The directory index serves in-app browsing and search. Now Playing is a
separate playback surface that uses a generic title for protected speech.
[Playback and output policy](audio-playback.md)

## macOS

The Qt desktop host can query loaded session-only contexts through
`features.rclone.session.paths()`. `services.desktop_video_access.session_contexts()`
uses that registry for output policy. It does not subscribe the desktop window
tree to the mobile protection scope. A future supported Siri integration would
need desktop publication and window-lifetime wiring, including retained content.
Apple documents live onscreen questions, window or region selection, and user
app exclusion on macOS 27. The SDK review found no credential-driven Siri
exclusion contract for these modes. Apple explicitly advises against using
`NSWindow.SharingType.none` to prevent capture. Native macOS behavior is untested.
[Mac onscreen awareness](https://support.apple.com/guide/mac-help/siri-ai-mac-screen-iphmk4p88mkuky/mac)
· [Mac Siri settings](https://support.apple.com/guide/mac-help/mchl31570551/mac)
· [Window sharing](https://developer.apple.com/documentation/appkit/nswindow/sharingtype-swift.enum/none)

## Verification and next gate

The focused protection-scope, screen-privacy and trusted-Wi-Fi host suite
passed 66 tests with synthetic credentials and native doubles. It verifies
publication order, scope across windows, retained protection, and reactions
to modeled lifecycle and capture signals. The simulated signals establish no
Siri behavior.

On a disposable iPhone 18 Pro simulator running iOS 27.0, the native resume
form passed keyboard and rotation checks, rejected a wrong password, accepted
Unlock through the native button and restored navigation. On a disposable
13-inch iPad Pro (M5) simulator running iPadOS 27.0, the form and keyboard
appeared in portrait. The probe stopped on the first rotation because the
keyboard disappeared, so iPad resume after rotation remains unverified.
Both runs used the reviewed Python revision and an existing Manager shell
with the native source checks enforced by the probe. The Manager removed both
simulators without reporting app cleanup errors.

Before making a Siri exclusion claim, ask Apple through Feedback Assistant
for a public exclusion contract that can take effect before visual acquisition
and be updated across all windows at a session transition. If Logistics later
adds structured context, control its publication separately at the shared
protection boundary, including any app-owned stale associations and index items.
On coordinated, Siri AI-capable iPhone and iPad hardware, record the device,
OS build, feature settings and app revision. Establish a positive unprotected
control for each mode, then use fresh synthetic text and image markers for
activation, protected use and deactivation. Inspect actual replies, attachment
previews and the order of publication, scene events and acquisition where
observable. An absent answer alone is inconclusive.

Include Siri already open when credentials activate, first import, second
package, replacement, single removal, final removal with retained content and
release, lock/unlock and background/resume. Exercise ordinary lists, text and
WebView readers, images/PDFs and full-screen media in iPad windows created
before and after activation. Check VoiceOver, ordinary capture, app-switcher
snapshots and external displays separately. Test the user-managed Excluded
Apps setting with the same positive controls before relying on its visual
coverage. No physical device has been used for this investigation.
