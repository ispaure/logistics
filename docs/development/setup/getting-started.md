# Your first Logistics contribution

Use a disposable file and the locked desktop environment for your first change.

## 1. Prepare your environment

From a local terminal:

```sh
git clone --recurse-submodules https://github.com/ispaure/logistics.git
cd logistics
python3 dev.py setup desktop --dry-run
python3 dev.py setup desktop
python3 dev.py doctor
```

On Windows use `py`. Setup creates root `.venv`. Expect Python, uv, commonUtils
and the desktop environment to report OK. A desktop-only machine may lack
mobile tools. Use the pinned `Python/commonUtils` submodule.
[Setup details](../testing/testing.md#set-up-a-checkout)

On macOS, if a restricted runner denies boot identity verification, run setup
in a normal local Terminal with access to `/usr/sbin/sysctl -n kern.bootsessionuuid`.

## 2. Try the behavior before editing it

Run your checkout launcher. On macOS open `LaunchLogistics_MAC.command`, on
Windows open `LaunchLogistics_WIN.bat`, and on Linux run
`bash LaunchLogistics_LINUX_UV.sh`. Choose **File Browser** on the launch screen
and open a folder containing a disposable `.txt` file. Double-click the file.
Switch back to **File Browser**, then choose the file under **Open documents**
on the rail. Expect the same tab and text. If the file opens externally, enable
Text Editor in **Settings → Features**. [Desktop guide](../../user/user.md)

## 3. Find one owner and its tests

Start from the [visible screen](../architecture/ui-architecture.md#find-a-screen-by-its-visible-name)
or [feature catalog](../../features/features.md). Feature `__init__.py` files
declare launchers. Follow the factory to its desktop UI or mobile adapter.
Logistics owns app policy, commonUtils owns reusable mechanisms and Build
Manager executes the project's plans.
[Code map](../architecture/code-map.md) · [Plan review](../build-release/build-manager-journeys.md#trace-a-validation-plan)

## 4. Make a small change and check it

For a complete example, follow [notebook brushes](../../features/notebooks/development/brush-calibration.md#try-a-brush-change).
From the checkout root, a focused registry check is:

```sh
python3 dev.py test desktop test_feature_registry.py
```

Expect exit zero and a passing isolated test file. Add `--dry-run` to see its
selection and interpreter. [Test selection](../testing/testing.md#find-the-tests-for-your-change)

## 5. Update the guide a reader needs

Update user workflows or developer contracts at their [owning wiki path](../documentation/documentation-hierarchy.md).
Run `python3 dev.py test desktop test_documentation_layout.py`. Review the
diff for unrelated and private files.
