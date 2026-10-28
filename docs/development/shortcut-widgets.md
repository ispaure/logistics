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
It performs no increments, network requests, background tasks, or directory scans.
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

The normal cloud-build project preparation invokes `widget_build.configure_ios`
after the existing Inbox/app-group setup. Repeated preparation uses stable target
identities and does not duplicate phases, source references or capabilities.
The main app retains its existing bundle identity and entitlements. Extension
identifiers append `.widgets` and `.widget-actions`; iOS 17 is their minimum.

Physical-device signing admits only the containing app and three known extension
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
profiles for all extensions: `--inbox-profile`, `--widget-profile`, and
`--widget-actions-profile`, alongside `--profile`. Each must authorize the same
app group. Build/version updates apply to all embedded extensions.

Swift sources are explicit members of the mobile manifests and payload hashes.
commonUtils' mobile staging includes native Swift sources and rejects uncommitted
native files for release staging. No Python imports of these Swift sources occur.

## Validation

`mobile_build/tests/tooling/test_widget_build.py` checks deterministic embedding,
native-only extension inputs, app-group preservation, extension registration,
safe entitlement paths, team selection and manual export profiles. Existing
Inbox, device-deployment, TestFlight and shared-staging tests remain relevant.

`mobile_build/validation/widget_native.py` compiles and runs commonUtils' native
storage checks and builds a small native host with both real extensions through
the owned scratch lifecycle. It verifies embedded action metadata and absence of
Python dependencies, and saves concise evidence before deleting scratch outputs.
This validates extension compilation and packaging, not system widget refresh
latency or Shortcuts invocation on a physical phone. Use the normal manager's
iOS device workflow for the complete signed app; preserve the installed app/data.
