# Mobile Markdown editing and layout

The Text Editor and Notes Library share mobile Markdown authoring. This guide
covers rendering, storage permissions, keyboard layout and native validation.

## Starting points and ownership

### Markdown typography

Markdown document sizes use CSS pixels across formatted editing, previews,
Notes Library and the documentation article pane. Native source editors convert
that preference to Toga's integer CSS-point units at the font-binding boundary;
rounding can differ by at most two-thirds of a native logical unit. Initial
provider opening, mode changes, settings refresh and pinch updates use the same
conversion. Plain text and EPUB retain their independent size policies.

Reading and formatted editing use matching heading, code and table sizes.
Both disable WebKit's automatic text enlargement so viewport changes do not
silently change the selected size. Navigation labels and sidebar rows retain
their interface typography.

The browser regression in `test_mobile_markdown_editing_dom.py` compares computed
element sizes in the editor, preview and Chat transcript at 12, 16, 23 and 32.
The isolated native `markdown_typography_probe.py` measures local files, Notes
Library/provider documents, documentation and Chat, including UIKit source and
message-field font sizes, at 16 and 24.
Run it through `mobile_build.validation.document_storage_tools` with
`ios --probe markdown-typography --family iPhone` (or `iPad`) and an ignored
`--output` directory. The runner owns simulator creation, evidence and cleanup.

On November 1, 2026, focused iPhone and iPad simulator runs passed all seven
surface measurements at both sizes: file formatted/source/preview, note
formatted/source/reader, and the documentation article. UIKit source fonts and
WebView body text measured exactly 16 and 24 respectively. Screenshots were
reviewed and the owned QA apps/simulators were removed. Host font, Markdown,
provider, notes and documentation regressions passed, as did all 20 browser
editing tests (including computed-style parity at four sizes).

A second pass included Chat's rendered replies and native composer: on both
iPhone and iPad all nine surfaces matched at 16 and 24 while Chat's legacy
general preference was set to 12. The iPad install timed out before the probe
on its first attempt; a clean simulator retry passed. Both simulator runs
removed their QA apps and devices.

These were current Python/CSS checks in a cached native shell, with its missing
incoming-file service disabled only in the isolated harness. A fresh native
build was blocked by unrelated concurrent video compilation errors. This is
typography acceptance, not release-build, incoming-file, physical-device or
Android-device acceptance.

### Owner map

Read the [developer index](../../../development/development.md),
[mobile runtime](../../../development/mobile-runtime.md),
[workspace navigation](../../../development/mobile-workspace-navigation.md),
[mobile handbook](../../../development/mobile-handbook.md), and
[commonUtils boundary](../../../development/commonutils-integration.md).

| Owner | Current responsibility and planned review |
| --- | --- |
| `Python/services/documents/authoring/markdown_editor.py` | Formatted WebView, block serialization, formatting commands, HTML/CSS and change bridge. Diagnose iOS rendering, input and synchronization before choosing the editing engine. |
| `Python/features/text_editor/mobile/ui.py` | Managed-document editor. Bring its modes, controls and lifecycle into the same interaction model as provider documents. |
| `Python/services/documents/authoring/provider_markdown.py` | Provider Markdown modes, rendering, source synchronization and controls. Retain one authoritative draft and guarded asynchronous rendering. |
| `Python/features/text_editor/mobile/notes_library.py` and `notes.py` | Library navigation, note reading, provider bounds and editor handoff. Rework presentation and preserve bounded folder loading and containment. |
| `Python/mobile/provider_*.py`, `editor_picker.py`, composition and session owners | Opening, access policy, saving and lifecycle. Enforce storage permissions beneath the controls. |
| `Python/mobile/keyboard.py`, native host adapters and shared adaptive components | Keyboard geometry, safe areas, native bars and allocated pane sizes. Fix the responsible layout owner rather than adding competing offsets. |

Keep Logistics storage policy, document lifecycle and feature presentation in
Logistics. If reusable editor or adaptive mechanisms need changes in commonUtils,
read its own `AGENTS.md`, test that repository and document its APIs there. Keep
the parent dependency update explicit. Avoid broad unrelated navigation changes;
preserve `DestinationRail.tools_menu` and the existing Misc glyph.

## Storage and write permissions

Use one explicit access decision shared by editor and library entry points.
Derive it from the selected storage location and provider capabilities, not the
display label, the existence of a download/cache, or whether the provider is private.
An encrypted cloud remote is still a remote; LocalCrypt is an editable local copy.

| Location | Required behavior |
| --- | --- |
| Local | Read, formatted edit, source edit and save back to the selected local file. Allow creating a note in a writable library folder. |
| LocalCrypt | The same editing workflow while unlocked, saving through the encrypted local provider. Locking or changing credentials invalidates pending work and retires private surfaces according to the existing privacy contract. |
| Cloud remote, including encrypted remotes | Read rendered Markdown, navigate notes and search the open note. Optional source inspection is read-only. No edit, create, replace, rename, delete or save-back operation from these Markdown surfaces. |

Enforce remote restrictions in command handlers and persistence paths as well as
menus and widgets. A direct callback, restored session or stale WebView message
must not bypass them. Reuse existing authorized local-copy/export workflows if
offered; a copy must be explicitly created as a separate local document before
editing. Preserve existing privacy restrictions for LocalCrypt exports.

## Reading and writing design

Create representative native previews before spreading the layout through both
hosts. Establish typography, spacing, semantic colors, selected states and icon
treatment that fit the existing mobile app. Review light and dark themes at phone
and tablet sizes. Avoid stacked toolbars, unexplained icons and dense desktop controls.

- Use clear Read, Formatted and Source modes with an unmistakable active state.
  Opening a note reads it; entering Formatted must show styled, directly editable
  content. Source must expose the exact Markdown syntax.
- Keep the note title, navigation, mode access, save state and actions coherent
  across standalone documents and library notes. Show a clear read-only state for
  remotes. Save feedback must distinguish unsaved, saving, saved and failed.
- Put common formatting within easy reach: headings, bold, italic, lists, links,
  quotes, code, undo and redo. Place secondary tools in an accessible sheet or menu
  that fits the remaining viewport. Preserve the selection when using controls.
- Support blank-note tapping, caret placement, selection handles, long-press
  editing, paste, autocorrect, dictation and composition input. Mode changes must
  not lose the latest input, unexpectedly move the caret, or reset reading position.
- Render unsupported or source-only syntax honestly, with an obvious route to
  Source for editable locations. Never silently flatten or discard it. Keep source
  inspection read-only on remotes.
- Keep tables and code readable with contained horizontal scrolling. Preserve
  relative images, links, wiki links and frontmatter within their current supported
  contracts, with useful loading/error states.

## Keyboard and adaptive layout

Make usable space come from the actual window or pane and keyboard occlusion.
Assign one owner to each inset and one primary scroller to the writing surface.
Account for safe areas and visual viewport changes without applying keyboard
clearance twice. Essential controls must remain reachable while typing; controls
may move into a reachable menu rather than simply disappear.

- Android: reproduce the reported failure with a real software keyboard, including
  landscape, a tall suggestion row, enlarged text and both gesture and button
  navigation where available. Verify formatting, settings/actions, mode access,
  Save and keyboard dismissal remain usable.
- iPhone: validate actual WKWebView rendering and touch input, notch/home-indicator
  clearance, keyboard transitions, selection and formatting with the keyboard open.
- iPad: support full screen, narrow multitasking windows, rotation, floating/docked
  keyboards and hardware keyboards. Choose library sidebar versus drawer from the
  available pane width.
- iPhone Duo: use the dedicated runtime and existing pose tooling. Test outer and
  inner displays, supported folded/partially open/flat states, and transitions
  during an unsaved edit. Respect the seam and retain document, selection and mode.
- All targets: keep the caret visible during sustained typing and Enter, permit
  intentional scrolling away from it, and avoid jumping on each keystroke. Test
  keyboard open/close, mode switching, menus and rotation in combination.

## Notes Library redesign

Use the same reading surface, typography, actions and access rules as standalone
Markdown. Give the local-only library a clear location title and Local or LocalCrypt
context, a legible folder/note list, selected-note state and useful empty, loading,
locked and error states. Mobile uses floating Files and Links drawers over a
retained full-width document, including on tablets and Duo.

Preserve navigation history, list position, note position and active filename
when opening an editor and returning. Refresh the rendered note and relevant list
entry after a successful save. Test unsaved navigation through Save, Discard and
Cancel. Provide note creation for writable local libraries; show no mutation
library entry for cloud folders. Keep filename filtering distinct from searching
the open note. Backlinks and outgoing connections scan bounded local libraries
on demand without writing an index. Standalone cloud Markdown remains read-only.

## Testing and acceptance

Extend the existing suites: `mobile_build/tests/editing/test_markdown_editor.py`,
`test_provider_markdown.py`, `test_source_editor.py`, Markdown image/search/font
tests, `mobile_build/tests/documents/test_notes_library.py`, `test_editor_picker.py`
and relevant session/privacy tests. Use existing native editor, keyboard and
rotation probes as starting points; add reusable drivers under their test owner.
Run shared component tests only where the changed mechanism requires them, and
retain desktop editor/library regressions when touching shared behavior.

| Target | Required native coverage |
| --- | --- |
| iPhone | Portrait/landscape, software keyboard, touch formatting and selection, real formatted rendering, light/dark, enlarged text. Include a physical iPhone run when available. |
| iPad | Portrait/landscape, narrow and wide windows, sidebar/drawer transitions, docked/floating and hardware keyboards. |
| iPhone Duo | Dedicated Duo runtime, outer/inner displays and supported poses, folding/rotation during editing, seam-aware layout. Ordinary iPhone emulation does not satisfy this row. |
| Android phone | Compact and tall screens, portrait/landscape, actual software keyboard and suggestion row, navigation insets, large text. Include physical-phone verification of the reported overflow when available. |

Exercise each target with standalone Local, standalone LocalCrypt, local library,
LocalCrypt library and remote library/file routes. Cover blank, short, long and
mixed-syntax notes, rapid mode changes, save failure, external modification,
background/resume and closing while work is pending. Use focused combinations
after broad route coverage so each layout and storage risk has explicit evidence.

Acceptance requires all of the following:

- Formatted mode visibly renders and edits headings, emphasis, lists, links, quotes,
  code and supported tables on iOS and Android; there is no source-like fallback
  mislabeled as Formatted. Native typing, paste and composition actually update
  the saved Markdown.
- Read → Formatted → Source → Read → Save → reopen preserves intended content,
  untouched syntax and Unicode. A no-op mode round trip does not rewrite the file.
  Undo/redo remains coherent; unsupported blocks and document-size limits are explicit.
- Every Local/LocalCrypt route can edit and save, and every remote route rejects
  mutations even when handlers are invoked directly. Tests assert zero remote
  writes and no plaintext LocalCrypt artifacts escaping its existing privacy boundary.
- The keyboard never pushes essential actions irretrievably out of view. Visual
  inspection and geometry assertions confirm reachable controls, visible caret,
  unobscured dialogs and no accidental outer-page scrolling in constrained layouts.
- Library navigation and editor handoff retain context; saved changes appear on
  return, failed saves retain the draft, and Cancel prevents destructive navigation.
- VoiceOver/TalkBack labels, focus order, text scaling, contrast and platform-sized
  touch targets remain usable. Opening formatting controls does not lose selection.
- Loading, typing, scrolling and mode changes stay responsive on representative
  long notes. Record timings and inspect repeated open/close for leaked WebViews,
  tasks or memory growth; investigate regressions against the initial baseline.

Store screenshots, recordings, geometry reports and timings under ignored
`test-results/` or `mobile_build/logs/`. Keep public documentation limited to a
concise validation scope, without links to local-only evidence. Report separately
what passed host tests, simulator/emulator interaction and physical-device review.
If BOOX testing is included, save evidence and uninstall temporary Logistics test,
probe and QA packages afterward. Verify only `io.github.ispaure.logisticsmobile`
remains among Logistics packages; preserve that main app and all its data.

## Remaining acceptance gates

Manual checks include the Duo inner display and fold transitions during editing,
actual narrow iPad multitasking, hardware-keyboard focus and navigation,
physical selection/autocorrect/dictation, and spoken VoiceOver and TalkBack
traversal. Include additional gesture-navigation and keyboard configurations
and sustained memory and background/resume stress runs when validating those
changes.

## In-place library documents

`mobile/library_document.py` owns an embedded Markdown draft over DocumentResource,
using the regular FormattedMarkdownInput and CodeInput. It does not create a
second workspace session. `services/documents/mobile_notebooks.py:notes_editor`
embeds the regular NotebookPanel over NotebookDocument. Library-specific canvas
state suppresses commands that would leave this storage context. Native-bound
ink must drain through `window.notebookIdle` before a document transition.

Library transitions flush the active editor, resolve Save/Discard/Cancel and
bind asynchronous loads to the library epoch. A stale load disposes its resource
rather than replacing the newly selected document. Source save conflicts retain
the draft. Session close and application-exit checks include embedded editors.

The library accepts Markdown and `.rmdoc` entries; Markdown connection scans skip
archive documents. Creation uses the library containment boundary for both formats.
Home selects the format before the existing name/location flow, preserving the
broader host destination policy. Formatted single-line wiki paragraphs/headings use
the live-source DOM so editing does not escape or lose wiki delimiters.

Formatted controls are below the writing viewport during editing, with the same
shortcuts for hardware keyboards. Active horizontal fold geometry bounds the
writing pane; the system owns keyboard sizing. This follows the accessory and
keyboard-layout guidance in [Apple’s virtual keyboard guidance](https://developer.apple.com/design/human-interface-guidelines/virtual-keyboards).

Run the `notes-library` native probe through the owned document-storage validation
helper on iOS and Android. It checks in-place identity, live wiki input, drawers,
keyboard toolbar bounds, search cancellation, canvas saving, guarded transitions
and the confined creation picker. Screenshots/reports stay in ignored test-results.
