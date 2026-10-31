# iOS Shortcut value widgets

## Ownership and process boundary

`Python/mobile/ios/widgets/` owns Logistics' widget identity, app group,
Set Widget Value App Intent, widget configuration and refresh policy.
`mobile_build/build_support/widget_build.py` embeds two native Swift targets:

- `LogisticsWidget.appex` is a WidgetKit extension under `PlugIns/`.
- `LogisticsWidgetActions.appex` is an ExtensionKit App Intents extension under
  `Extensions/`, registered through `EXAppExtensionAttributes`.

Neither target links Python, Toga, rclone, video engines or application bootstrap
code. Set Widget Value is compiled only into the App Intents extension. Its
`openAppWhenRun` is false and it accepts locked execution for explicitly supplied
display values. App Intent metadata is extracted by Xcode; no Python startup or
runtime registration is needed to advertise the action.

commonUtils owns the native `WidgetValueStore` and `WidgetValueView` components.
Their contracts are documented in its native UI guide. Logistics injects the
existing `group.io.github.ispaure.logisticsmobile` container, leaves the saved
Shortcuts counter authoritative, and publishes a separate widget snapshot.
There is no automatic access to Shortcuts' global values.
The action and configuration default to `DuoFoldCount`. The previous default,
`folds`, is a host-owned alias for that name; the widget falls back to its old
display record until a new value is published. Custom names remain independent.

## Bounded work and refresh policy

The action accepts name/value/title, atomically replaces one local named snapshot,
then requests `WidgetCenter.reloadTimelines(ofKind:)` only when content changed.
It performs no increments, server requests or directory scans. It also persists
a bounded display snapshot for the Watch and notifies a running phone app.
Watch Connectivity is compiled out of this extension with
`LOGISTICS_WIDGET_ACTIONS`; the separate **Sync Widget Values to Watch** intent
runs only in the containing app and waits at most three seconds per session
activation attempt. A failed Watch transfer does not fail the phone widget
publication. The phone widget reload remains conditional on content changes.
The widget reads its selected snapshot and returns a single-entry `.never`
timeline. iOS owns reload timing; there is no timer to overcome throttling.

Storage protection permits reads after the first unlock, including later locked
automation runs. The widget is marked privacy-sensitive. This is a non-sensitive
display channel, not a general credential or private-document interface.
Concurrent publications are last-writer-wins. Deleting or resetting the Shortcuts
counter does not change the widget until the shortcut publishes again.

The widget declares no custom URL, document route, session-restoration activity or
foreground App Intent. A tap uses the normal containing-app launch/resume path;
the existing application/scene privacy notifications and credential gates remain
authoritative, including configured trusted-Wi-Fi resume. The extension's locked
execution policy applies only to publishing explicit display content, never to
application session authentication. Widget code accesses only `WidgetValues/`;
it does not load credential services, LocalCrypt providers or session state.

## Build and signing

Normal device and TestFlight builds currently omit Watch targets, pending Apple
signing setup. The source and isolated native fixture remain available:
`widget_build.configure_ios(project, include_watch=True)` explicitly invokes
`watch_build.py` to embed a native SwiftUI
`LogisticsWatch.app` under the iPhone app's `Watch/`, with
`LogisticsWatchWidget.appex` under its `PlugIns/`. Both require watchOS 10 and
use the same App Group identifier on the Watch. Watch storage is separate from
the phone's container. Neither Watch target includes the Python runtime.

The persistence portion of `WatchValuePublisher` runs in the App Intents extension
and the containing app; its Watch Connectivity portion runs only in the app.
It stores a display-only `watch.json` envelope alongside the named widget records,
using an interprocess lock for publications. The envelope retains at most 16
names and is limited to 60,000 encoded bytes. Older custom names are evicted for
either limit, retaining the fold count and current publication. `folds` remains
an alias for `DuoFoldCount`. Existing fold records
are imported when the containing app launches; other existing names are added
when their publishing action next runs. An identical publication retries sending.

The app publisher uses latest-state application context plus a coalesced user-info
transfer for opportunistic background delivery. Reachable Watch apps also receive
an immediate message. A Darwin notification lets a running containing app retry;
it does not wake a terminated app. The native lifecycle bridge starts the phone's
session and retries when the app becomes active, and the Watch's Refresh button requests that persisted snapshot from the
phone. Watch-originated messages can launch the phone app in the background,
which follows the containing app's normal startup path. **Sync Widget Values to
Watch**, compiled only into the app target, also follows that startup path in the
background and may start Python. On iOS 27 it explicitly declares `.main` execution.
Place it after **Set Widget Value** in the existing Shortcut for automatic delivery
when the app is closed. Set Widget Value itself remains in the native extension.

The Watch receiver validates each envelope, ignores older snapshots, saves the
newest one atomically, then requests complication reloads. It completes system
Watch Connectivity background tasks after pending content is delivered. Background
activation does not request a refresh from the phone; opening the app or using
Refresh does, including a request made before session activation completes. It does
not count folds, poll, connect to application servers or read credentials.
The complication supports inline, circular and rectangular accessory families,
and uses a configurable value name with the existing fold-count default.

The normal cloud-build project preparation invokes `widget_build.configure_ios`
after the existing Inbox/app-group setup. Repeated preparation uses stable target
identities and does not duplicate phases, source references or capabilities.
The main app retains its existing bundle identity and entitlements. Extension
identifiers append `.widgets` and `.widget-actions`; iOS 17 is their minimum.
Watch identifiers append `.watchkitapp` and `.watchkitapp.widgets`.

Physical-device signing admits only the containing app and five known companion/extension
identities, using the existing pinned team. Automatic signing can provision the
new extension identifiers. The owning device-build helper reuses the configured
App Store Connect API-key reference when Xcode has no signed-in account; credentials
are not copied into source or the build workspace. A valid API key does not prove
that Xcode can provision a new app-group extension: if Apple rejects that request,
sign in with the existing developer account in Xcode and retry. Do not substitute
wildcard profiles, remove the shared-container entitlement or change the app ID.
The device helper's `--xcode-account` option explicitly selects that signed-in
account instead of passing the configured API key to Xcode.
Manual TestFlight signing needs the exact App Store
profiles for all products: `--inbox-profile`, `--widget-profile`,
`--widget-actions-profile`, `--watch-profile` and `--watch-widget-profile`, alongside
`--profile`. Both Watch profile arguments explicitly enable the companion and
complication targets in the production archive builder. Neither argument keeps
phone-only builds available; supplying only one fails before creating an archive.
Each profile must authorize the same app group. Build/version updates apply to
all embedded extensions.

Swift sources are explicit members of the mobile manifests and payload hashes.
commonUtils' mobile staging includes native Swift sources and rejects uncommitted
native files for release staging. No Python imports of these Swift sources occur.

## Validation

`mobile_build/tests/tooling/test_widget_build.py` checks deterministic embedding,
native-only extension inputs, app-group preservation, extension registration,
safe entitlement paths, team selection and manual export profiles. Existing
Inbox, device-deployment, TestFlight and shared-staging tests remain relevant.

`mobile_build/validation/widget_native.py` compiles and runs commonUtils' native
storage and Watch-envelope checks and builds a small native host with the real
phone extensions, Watch app and complication through
the owned scratch lifecycle. It verifies embedded action metadata and absence of
Python dependencies, and saves concise evidence before deleting scratch outputs.
This validates compilation, envelope round-trips and packaging, not system widget refresh
latency, paired-device delivery or Shortcuts invocation on a physical phone. Use the normal manager's
iOS device workflow for the complete signed app; preserve the installed app/data.

Pass `--device-build` to additionally compile unsigned Release products for the
iPhone and Watch hardware SDKs, using the targets' native architecture selection.
The envelope checks cover large Unicode values overflowing the aggregate payload
budget, retention of the fold count/current value, stale arrivals and explicit resets.
