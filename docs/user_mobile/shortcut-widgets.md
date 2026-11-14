# Show Shortcut values on your phone and Apple Watch

On iOS 17 or later, Logistics' **Shortcut Value** widget shows a number or
short text published by **Set Widget Value** in Apple Shortcuts. Match the name
in the action and widget when you want to publish other values.

## Connect an existing fold counter

Add **Set Widget Value** after the counter's final **Store Content** action.
Keep **Name** as `DuoFoldCount` and **Title** as `Folds`. For **Value**, select
the **Calculation Result** variable from **Stored Content + 1**. The action
publishes the result after the counter saves it. Keep the
phone's **Closed** trigger and **Allow Running When Locked** enabled.

To initialize without counting another fold, add **Set Widget Value** to
**Show Fold Count** after **Get Stored Content**. Pass **Stored Content** to
both **Set Widget Value** and **Show Content**, then run the shortcut.

## Add the widget

Hold the Home Screen and tap **Edit → Add Widget**. Find Logistics (it may
appear as **Logisticks**) and add a small or medium **Shortcut Value** widget.
Match the shortcut's case-sensitive name. The old `folds` name still works.
An em dash means you need to publish a value. If storage is unavailable,
unlock the phone and publish again.

## Apple Watch

On watchOS 10 or later, install the companion through the iPhone Watch app and
open it once. Signed builds need both Watch provisioning profiles
(`signing.watch_profile` and `signing.watch_widget_profile`). Add **Sync
Widget Values to Watch** immediately after **Set Widget Value**. Run **Show Fold
Count** with both actions to send the current count.

Choose Logistics' **Shortcut Value** complication in an inline, circular, or
rectangular slot. Match the widget name. If it lags, use **Refresh from iPhone**.
If a value is missing, unlock the phone after restart, open Logistics, and
run the publishing shortcut again.

## Battery, refresh timing and privacy

iOS schedules refreshes. Use non-sensitive values because the widget can
appear when the device is locked. The widget stores explicitly published
values locally and on the paired Watch. Publish an empty value under the same
name to clear it.
