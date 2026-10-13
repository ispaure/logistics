# Logistics mobile prototype

This independent Toga application targets Android and iOS. It opens imported text
and Markdown as app-private copies, edits them, saves their original encoding and
line endings, and checkpoints drafts for recovery. Its hub also opens a private EPUB/CBZ library
with chapter/page navigation, bookmarks and saved progress, plus text LM chat
with private history and explicit server connections. It does not launch the desktop
Qt application or install its dependency list.

See the [user guide](../Python/logisticsmobile/user_docs/README.md) and
[architecture and validation guide](../docs/developer/mobile-preparation.md).

## Prepare a native build

Use a separate Python 3.12 environment with `briefcase==0.4.5`. Toga backends are
pinned to 0.5.7 in `pyproject.toml`. From the repository root, after committing
source changes:

```sh
python Mobile/tools.py stage Mobile/payload
cd Mobile
briefcase create android --no-input
briefcase build android --no-input
# On a Mac with the iOS platform installed:
briefcase create iOS --no-input
briefcase build iOS --no-input
```

Staging creates a new directory and refuses to replace an existing payload. Move
or remove your previous generated `Mobile/payload` before staging again. For local
development, `--allow-dirty` permits uncommitted mobile sources; such payloads
cannot pass the mobile runtime evidence verifier.

Briefcase needs the Android SDK/JDK or Xcode/iOS platform resources. A listed iOS
SDK alone may be insufficient: the local Xcode installation reported
`iOS 26.5 Platform Not Installed` while compiling the launch storyboard. No local
simulator devices were installed. Use the hosted build or install the platform
through Xcode Settings → Components before trying a simulator run.

Only public, selected Python sources and licenses enter the payload. Private
INIs, Git metadata, ignored resources and the external emulation link are excluded.
Native builds contain the host, commonUtils and selected portable EPUB/comic
modules. Runtime testbeds also contain generated fixture tests. Briefcase test-mode
builds add the separate `native_tests/tests` entry point; normal app artifacts are
captured before test-mode rebuilds and contain no test entry point.

## Host validation

```sh
PYTHONPATH=Python:Python/tests python -m logisticsmobile.smoke --target host
PYTHONPATH=Python python -m unittest discover -s Python/tests -p 'test_mobile_*.py' -v
```

For the widget contract check, install `toga-dummy==0.5.7` in the separate
environment, then run:

```sh
PYTHONPATH=Python TOGA_BACKEND=toga_dummy python -m unittest discover -s Mobile/tests -v
```

These commands verify host behavior; they do not certify device interfaces.

## Hosted builds and runtime checks

[Native builds](../.github/workflows/mobile-build.yml) produce an Android debug APK
and an iOS Simulator app archive. [Runtime checks](../.github/workflows/mobile-runtime.yml)
build the pinned CPython 3.14.7 testbeds and execute 25 Logistics document/core
cases inside actual Android and iOS interpreters. Result verification requires
the expected runtime, clean source commits, every case and zero failures or skips.

Both workflows run for changes to their mobile source paths on `alpha`; they also
define manual Android/iOS/both controls. GitHub exposes manual controls after the
workflow is present on the default branch. Native builds have a 45-minute upper
bound; cold interpreter/testbed jobs have a 90-minute upper bound. Diagnostic
artifacts remain available for 14 days. New mobile pushes supersede older mobile
push runs. These workflows do not publish store releases or use signing secrets.

The Source release workflow calls both mobile workflows for Android and iOS.
Their native builds and runtime checks are mandatory alongside macOS, Windows
and Linux validation before a release can be packaged or published. A manual
Source release run validates and packages without publishing a release.

Native build jobs additionally run the actual Toga app in Briefcase test mode on
an Android emulator and iPhone Simulator. Eight required UI cases cover the hub,
preferences, documents, rendered Markdown, rendered EPUB chapters, bookmarks and
native comic image decoding and a loopback-only streamed LM conversation. Source/backend checks reject missing or stale reports.
Each app run has a 15-minute bound within its build job. These automated cases do
not interact with real system document pickers.

Build success establishes packaging. Runtime core success establishes the tested
document/storage operations. Native picker interactions, touch/keyboard behavior,
real suspension and physical devices still need separate validation. Simulator
app archives are not installable iPhone releases.

Framework references: [Toga platforms](https://toga.beeware.org/en/stable/reference/platforms/),
[Briefcase configuration](https://briefcase.beeware.org/en/stable/reference/configuration/),
[Android build tutorial](https://tutorial.beeware.org/tutorial/tutorial-5/android/),
[iOS build tutorial](https://tutorial.beeware.org/tutorial/tutorial-5/iOS/).
