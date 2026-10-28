# Show a Shortcut value on your Home Screen

Logistics' **Shortcut Value** widget displays a number or short text supplied by
Apple Shortcuts on iOS 17 or later. Use a small or medium Home Screen widget.
Each widget selects a name; the **Set Widget Value** action publishes that name's
title and value. Different names can show different values.

## Connect an existing fold counter

Keep the shortcut that already counts your phone's closures. After its final
**Store Content** action, add **Set Widget Value** from Logistics' actions:

1. Search actions for **Set Widget Value**, or browse the Logistics app's actions.
2. Leave **Name** set to `DuoFoldCount`; it is filled in automatically.
3. Set **Value** to the **Calculation Result** variable from the existing
   **Calculate: Stored Content + 1** action. Select the variable; do not type its name.
4. Expand the action if necessary and leave **Title** set to `Folds`.

The action copies your calculated total into the widget's storage. It does not
add one itself or read Shortcuts' global storage automatically. Keep this action
after the counter's existing save so a failed counter save cannot publish a newer
widget total. Running the counting shortcut manually still adds one.

To publish the current total without counting another fold, add **Set Widget
Value** between **Get Stored Content** and **Show Content** in **Show Fold Count**.
Pass **Stored Content** to Set Widget Value, and explicitly keep **Show Content**
connected to **Stored Content** too: Set Widget Value does not return the number.
Run Show Fold Count once to initialize the widget with your current total.

Keep the counting shortcut's trigger set to the phone being **Closed**, with
**Allow Running When Locked** enabled. The hinge trigger depends on the Duo's
installed iOS version; the widget itself does not need a folding phone.

## Add the widget

1. Hold an empty part of the Home Screen, then choose **Edit → Add Widget**.
2. Find Logistics (the installed app may be named **Logisticks**).
3. Select **Shortcut Value**, choose small or medium, and tap **Add Widget**.
4. Leave the widget's **Name** at its automatic default, `DuoFoldCount`.

Widgets and actions made with the earlier `folds` default keep working without
editing their names. That earlier name now refers to `DuoFoldCount`, with the old
saved display value used until the shortcut publishes a new one.

Use the widget supplied by Logistics, rather than Apple's Shortcuts widget,
which is a button for running a shortcut. Your existing Show Fold Count button
can remain available as an immediate check of the saved counter.

An em dash means that name has no saved value yet. An unavailable message means
the shared storage could not be read; unlock the phone and publish the value again.
Names are case-sensitive and must match the action exactly.

Selecting `DuoFoldCount` in the widget does not read Apple's Shortcuts storage.
The **Set Widget Value** action is the connection between those two stores and
must run with the current number as its Value. The initial em dash and setup
message mean no display record was found for that name; changing the widget's
name alone cannot create one.

## Battery, refresh timing and privacy

The action and widget run in separate native extensions. Updating a value does
not launch Logistics' Python runtime, browser, readers, transfers or application
interface. They make no network requests and run no polling timer. Each changed
value replaces one small local record and requests a widget reload. Sending the
same title and value again skips both the write and reload request.

iOS schedules actual widget refreshes, so the displayed number can lag behind
Shortcuts. There is no periodic refresh fallback. Battery impact has not been
measured on a physical phone; the implementation avoids continuous background work.

Only explicitly supplied values are shared with the extensions. They stay in
the app's local shared container, outside its document library. The widget may
be visible to anyone who can see your screen; use it for non-sensitive values.
The action permits locked execution after the phone's first unlock following a
restart. Before that first unlock, protected storage may be unavailable.
Tapping the widget opens the app through its normal launch/resume path. It does
not unlock LocalCrypt or restore session-only credentials. Existing session
password and configured trusted-Wi-Fi resume rules still apply. Updating the
widget in the background does not run that application resume path at all.
Removing a widget does not delete its saved value. To clear its displayed content,
publish an empty value under that name. Uninstalling the app can remove widget data.

Titles are limited to 64 characters, names to 64, and values to 512. Long text is
scaled or truncated to fit; the widget is intended for compact information.
