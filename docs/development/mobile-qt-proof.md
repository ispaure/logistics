# PySide6 iOS reuse proof — October 14, 2026

The user requested an isolated PySide6 iOS experiment while retaining Toga. The
four requested areas run together in a separate app, `LogisticsQtProof`, with
bundle identity `io.github.ispaure.logisticsqtproof`. This is feasibility evidence,
not a production runtime migration or completion of the remaining navigation phases.

## Implemented and checked

| Requested area | Actual implementation reused | Simulator result |
| --- | --- | --- |
| File browser with tabs | commonUtils FileBrowser and ScopedTabBar in two Qt tabs | Both models list synthetic files; navigation survives tab switching; Back/Forward button signals restore the correct locations |
| Highlighted editor | commonUtils CodeEdit and SyntaxHighlighter with Pygments 2.19.2 | Python tokens have real QTextBlock formatting; Save writes the edited private fixture and clears modification state |
| Markdown reader | commonUtils MarkdownViewer | Existing selectable QTextBrowser renders headings, bold text and lists |
| Rclone | Logistics CloudClient/Downloads and the compiled Go rclone bridge | Synthetic memory connection imports; native probe writes its own fixture; list/download return the expected 22 bytes; credentials are cleared |

All four programmatic checks pass on an iPhone Duo simulator with iOS 27.1 and
an iPad Pro 11-inch (M5) simulator with iOS 27.0. These execute actual Qt widgets
and statically linked rclone, not a desktop mock or fake service response.
Phone evidence (local artifact `test-results/mobile-evidence/2026-10-14-qt-proof-phone/evidence.json`) and
tablet evidence (local artifact `test-results/mobile-evidence/2026-10-14-qt-proof-ipad/evidence.json`) include
screenshots alongside their reports. The app remains available in the simulators
under its separate name; the Toga app is preserved.

Source checkpoint: Logistics `e9e3d54`, commonUtils `615a70d`; PySide6/Qt 6.12.0,
Python-Apple-support 3.15.0rc2, rclone v1.74.1. The generated application has
`MinimumOSVersion=18`. Its unoptimized debug bundle is approximately 725 MiB;
this includes deployment-tool resources and is not an optimized release estimate.

The shared Qt regression check passed 71 tests: file browser, CodeEdit, folding,
multi-cursor editing, column guides, browser polish, explicit mobile Qt host
admission, platform detection and portability. Earlier sandboxed filesystem
checks failed; the complete rerun with real filesystem/watcher access passed.

## Adaptations and findings

commonUtils now admits Qt widgets only after an explicit live Qt 6.12+ QApplication
registration. It requires registration on the GUI thread, holds a weak reference,
and leaves desktop dialogs, shell commands, external applications and default
storage unavailable on mobile. The host supplies private paths and personal
settings. Shared API documentation and commits live in commonUtils.

Browser breadcrumbs and editor paint handlers now close QPainter objects
explicitly. Their previous dependence on local-variable destruction produced
active-painter warnings and broken rendering in the iOS Python runtime.

Changing a populated browser root exposed a native segmentation fault in
QColumnView's column creation path. Keeping Python references and setting an
explicit parent did not resolve it; those attempted fixes were discarded. The
proof supplies the new explicit `column_navigation=False` host option, which
omits QColumnView entirely. Existing desktop hosts retain the default behavior.
List and thumbnail modes are available in the proof; column navigation has **not**
been fixed or certified. Only list navigation is covered by the native assertions.
The native logs still report collation limitations and dynamic-method wrapper
warnings, despite the passing checks. These remain investigation items.

The reusable browser toolbar and columns overflow the phone width in the initial
screenshot. This is a direct reuse experiment, not the agreed mobile layout.
The reader/editor views render successfully, but mobile chrome, compact browser
controls, touch selection, keyboard behavior and accessibility need dedicated work.

## Scope and architectural consequence

This confirms meaningful Python/Qt component reuse on iOS, including Pygments
and the existing native rclone interface. It supports continuing the PySide
experiment before deciding whether to migrate. It does not establish that every
Qt desktop workflow is suitable for mobile, that Qt tabs are UIKit destination
navigation, or that a Qt Quick presentation would automatically reuse QWidget UI.

Keep Toga available while validating physical-device typing/selection, provider
permissions and imports, background/lifecycle recovery, realistic network and
cancellation behavior, accessibility, older OS requirements, packaging size,
signing and release gates. No physical-device, iOS 15, EPUB, live remote,
independent-window or Android Qt proof is claimed here. The read-aloud and other
reader extras are visible existing controls, but were not exercised by this proof.

[Build and collection instructions](qt-proof-launchers.md) describe the
curated staging, public checksummed Qt simulator wheels, Python framework, static
Go linking, required zlib linking and simulator ad hoc signing. No production
entry point, Toga bundle identity or release workflow was replaced.
