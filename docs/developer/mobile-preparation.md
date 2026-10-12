# Mobile preparation and next steps

Logistics remains a desktop application. This phase prepares and tests reusable
document operations; it does not introduce mobile navigation, a Qt mobile port,
application packaging or a new dependency policy for existing desktop consumers.

## Current boundary

| Component | Portable foundation | Remaining host work |
| --- | --- | --- |
| EPUB | `features.books.epub` reads bounded resources, spine and navigation; `metadata` stages conflict-checked saves while preserving resources | Document-provider access, mobile rendering, navigation and lifecycle |
| Comics | `ComicDocument` reads/updates ComicInfo; `ComicPages` sorts names and returns compressed page bytes without importing Pillow or legacy archive tools | Image decoding/cover rendering needs Pillow or a future mobile adapter; encrypted archives need cryptography dependencies; conversion remains separate |
| Text and Markdown | Existing commonUtils text snapshots, encoding preservation, conflict detection and atomic writes; Markdown properties | Editor presentation, unsaved buffers, suspension/recovery, mobile document selection and permission persistence |
| Desktop integrations | Existing Qt widgets, feature discovery, launchers and tools remain intact | Select only relevant features for a future mobile host; do not import the desktop application as its entry point |

The comic archive helper now loads legacy tooling only when archive rebuilding is
requested. Its existing `zipUtils` alias is still lazily available to callers.
Comic page access loads Pillow only for TIFF conversion or cover rendering; the
existing `Image`/`ImageOps` exports remain available lazily. Missing Pillow raises
an explanatory error at decoding. Existing desktop behavior and signatures stay
unchanged. The EPUB data layer already had the appropriate separation and was
validated without an unnecessary rewrite. The Qt editor remains a widget; its
file I/O was already independently reusable.

## Run the headless document check

From the repository root, using a Python interpreter without desktop packages:

```sh
PYTHONPATH=Python python Python/tests/portable_documents.py
```

The suite actively rejects imports of PySide6, Pillow, patoolib and pyzipper,
even when installed. It creates its own EPUB/CBZ/text fixtures, checks resource
preservation, metadata saves, natural page order and stale-save rejection. It
also checks that a cover request reports the missing image decoder clearly.
The static CI job runs it before installing desktop dependencies; a fresh-process
regression also enforces the boundary in the normal suite.

This is a **host** test, without OS mocks. It is ready to be packaged into a future
mobile testbed but has not run inside iOS/Android. It does not test image decoding,
Qt rendering, Android content URIs, iOS security-scoped URLs or physical devices.

## Your first mobile CI run

The next gate belongs in commonUtils, before selecting a mobile UI framework.
Follow its [mobile test guide](../../Python/commonUtils/docs/developer/mobile-testing.md)
for the manual Actions controls, artifacts, success criteria and troubleshooting.
Start with Android, then iOS. The workflow setup has been pushed but **has not
been dispatched**. Existing desktop push-triggered CI remains enabled.

For each run, keep the commit SHA, runtime result JSON and build/testbed logs. A
red build step is a toolchain/setup problem; a red test or missing result is not a
successful mobile run. The guide distinguishes these cases. Do not enable a
capability merely because a simulator boots or an app builds.

## After those runs pass

1. Extend the mobile payload with the small Logistics document modules and this
   headless fixture suite. Keep platform-specific dependencies out of that package.
2. Build one document prototype: import a file into app-private storage, display
   text, edit/save safely and reopen it. Choose its mobile UI/framework then;
   existing desktop Qt widgets do not determine that choice.
3. Add Android document-provider and iOS document-picker/security-scoped access,
   then permission persistence and unsaved-change recovery across suspension.
4. Validate on physical Android and iOS devices before expanding reader features
   or adding signing/store distribution. Hosted emulator/simulator passes do not
   certify device behavior.

No production mobile UI is implemented yet. This sequencing preserves the earlier
infrastructure-only boundary and avoids choosing a UI stack before verifying the
shared runtime and dependencies. The first hosted runs and framework/device
choices are explicit future gates, not unreported passes.

## Local validation record

The preparation changes passed 923 Logistics tests in 91 isolated modules on
macOS. The three headless document scenarios also passed directly, with optional
desktop/image/archive packages blocked. Ruff passed across Python and CI scripts,
and actionlint accepted the updated desktop and new commonUtils mobile workflows.
The commonUtils revision linked by this update passed 735 shared tests and its
seven-case staged host harness. No mobile workflow has been dispatched and no
physical-device result is claimed.
