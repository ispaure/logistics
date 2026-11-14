# iOS Shortcut value widgets

`Python/mobile/ios/widgets/` owns app identity, configuration and Set Widget
Value. `widget_build.py` embeds native-only `LogisticsWidget.appex` in `PlugIns/`
and `LogisticsWidgetActions.appex` in `Extensions/`. Both use
`group.io.github.ispaure.logisticsmobile` through commonUtils widget components.

Set Widget Value atomically replaces one explicit display snapshot and reloads
on change. It can run locked after first unlock without opening Logistics.
Shortcuts owns the counter. `DuoFoldCount` is the default and `folds` is its
legacy alias. Widget taps follow normal app privacy gates. The extension sees
display values only. WidgetKit controls refresh timing.

Watch transfer uses a bounded latest-state snapshot (16 values, 60,000 bytes).
Place **Sync Widget Values to Watch** after Set Widget Value for delivery when
Logistics is closed. That intent runs in the containing app and may start Python.
Failed transfer preserves phone publication. Watch receivers reject stale
snapshots and request complication reload after saving.

Phone Watch Connectivity is compiled out of the App Intents extension.
The app persists `watch.json`, retaining the fold count and the current
publication when evicting older custom values. It retries latest-state transfer
on activation. A Darwin notification can notify a running app. The Watch's
Refresh action requests the saved phone snapshot. Watch storage is a separate
container and the complication has inline, circular and rectangular variants.

## Build and signing

Phone extensions require iOS 17. Watch targets require watchOS 10 and are opt-in
via `configure_ios(..., include_watch=True)` or both Watch TestFlight profiles.
Manual signing needs exact app, Inbox, Widget, Widget Actions and any Watch
profiles with the shared app group. If API-key provisioning fails, retry with
the signed-in Xcode account via `--xcode-account`. Keep native Swift in the
manifest and payload hashes.

Run `python3 dev.py test mobile test_widget_build.py` for embedding and signing.
`mobile_build.validation.widget_native` verifies native packaging and storage;
`--device-build` compiles hardware targets. Paired delivery and refresh timing
require device acceptance.
